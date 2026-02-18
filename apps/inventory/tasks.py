"""Dispatcherd task definitions for inventory collection.

Tasks are registered via the ``@task()`` decorator so that they can be
submitted from any process that has called ``dispatcherd.config.setup()``,
and executed by the dispatcherd worker service.

Collection is delegated to pluggable provider classes discovered via
the provider registry. The task scaffolding here handles the full lifecycle:

    pending -> running -> completed | failed | canceled
"""
import logging
import traceback

import django
from django.utils import timezone

logger = logging.getLogger("apps.inventory.tasks")


# ---------------------------------------------------------------------------
# Dispatcherd registration — guarded so the module is still importable
# when dispatcherd is not installed (e.g. during migrations).
# ---------------------------------------------------------------------------

try:
    from apps.inventory.dispatcher import setup_dispatcher
    setup_dispatcher()
    from dispatcherd.publish import task
except ImportError:
    logger.debug("dispatcherd not available — tasks will not be registerable")

    def task(*args, **kwargs):
        """No-op decorator when dispatcherd is not installed."""
        def wrapper(fn):
            return fn
        return wrapper


def _ensure_django():
    """Ensure Django is set up (idempotent)."""
    try:
        django.setup()
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@task(queue="inventory")
def run_collection(collection_run_id: str) -> dict:
    """
    Execute an inventory collection run.

    This is dispatched as a background task via dispatcherd. The function:

    1. Marks the CollectionRun as ``running``
    2. Resolves the provider via the plugin registry
    3. Delegates collection to the provider plugin
    4. Updates statistics and marks as ``completed`` or ``failed``

    Args:
        collection_run_id: UUID primary key of the CollectionRun record.

    Returns:
        dict with summary statistics.
    """
    _ensure_django()

    from apps.inventory.models import CollectionRun

    try:
        run = CollectionRun.objects.select_related("provider").get(pk=collection_run_id)
    except CollectionRun.DoesNotExist:
        logger.error("CollectionRun %s not found — task dropped", collection_run_id)
        return {"error": f"CollectionRun {collection_run_id} not found"}

    # Guard: don't re-run a terminal job
    if run.is_terminal:
        logger.warning("CollectionRun %s is already %s — skipping", run.pk, run.status)
        return {"skipped": True, "status": run.status}

    # Mark running
    run.status = CollectionRun.Status.RUNNING
    run.save(update_fields=["status"])
    logger.info(
        "Starting %s collection for provider %s (run=%s)",
        run.collection_type,
        run.provider.name,
        run.pk,
    )

    try:
        result = _do_collection(run)
        run.status = CollectionRun.Status.COMPLETED
        run.completed_at = timezone.now()
        run.resources_found = result.get("found", 0)
        run.resources_created = result.get("created", 0)
        run.resources_updated = result.get("updated", 0)
        run.resources_removed = result.get("removed", 0)
        run.resources_unchanged = result.get("unchanged", 0)
        run.save(
            update_fields=[
                "status",
                "completed_at",
                "resources_found",
                "resources_created",
                "resources_updated",
                "resources_removed",
                "resources_unchanged",
            ]
        )
        logger.info("CollectionRun %s completed: %s", run.pk, result)
        return result

    except Exception as exc:
        run.status = CollectionRun.Status.FAILED
        run.completed_at = timezone.now()
        run.error_message = str(exc)[:2000]
        run.result_traceback = traceback.format_exc()[:8000]
        run.save(update_fields=["status", "completed_at", "error_message", "result_traceback"])
        logger.exception("CollectionRun %s failed", run.pk)
        return {"error": str(exc)}


def _do_collection(run) -> dict:
    from inventory_providers import registry
    from inventory_providers.base import CollectionResult, ProviderCredential
    from apps.inventory.models import Resource, ResourceRelationship, ResourceSighting, ResourceType

    provider_model = run.provider
    config = provider_model.connection_config or {}
    logger.info("Collecting from provider=%s endpoint=%s", provider_model.name, provider_model.endpoint)

    credential = ProviderCredential(
        hostname=provider_model.endpoint,
        username=config.get("username", ""),
        password=config.get("password", ""),
        port=config.get("port", 443),
        extra={k: v for k, v in config.items() if k not in ("username", "password", "port")},
    )

    provider_instance = registry.instantiate(provider_model, credential)
    run.collector_version = getattr(provider_instance, "__version__", "0.1.0")
    run.save(update_fields=["collector_version"])

    result = CollectionResult()
    deferred_rels = []
    rt_cache = {}

    def _get_rt(slug):
        if slug not in rt_cache:
            rt, _ = ResourceType.objects.get_or_create(slug=slug, defaults={"name": slug.replace("_", " ").title()})
            rt_cache[slug] = rt
        return rt_cache[slug]

    # Ensure plugin deps are on sys.path (may not have been at startup)
    import sys
    from pathlib import Path
    deps_dir = str(Path("/app/plugins/.deps"))
    if deps_dir not in sys.path and Path(deps_dir).is_dir():
        sys.path.insert(0, deps_dir)
        logger.info("Added plugin deps to sys.path: %s", deps_dir)

    provider_instance.connect()
    logger.info("Connected to provider %s", provider_model.name)
    try:
        seen = set()
        for rd in provider_instance.collect():
            result.found += 1
            seen.add(rd.ems_ref)
            rt = _get_rt(rd.resource_type_slug)
            defaults = dict(name=rd.name or rd.ems_ref, resource_type=rt, description=rd.description,
                canonical_id=rd.canonical_id, vendor_identifiers=rd.vendor_identifiers,
                vendor_type=rd.vendor_type, state=rd.state or "unknown", power_state=rd.power_state,
                boot_time=rd.boot_time, region=rd.region, availability_zone=rd.availability_zone,
                cloud_tenant=rd.cloud_tenant, flavor=rd.flavor, cpu_count=rd.cpu_count,
                memory_mb=rd.memory_mb, disk_gb=rd.disk_gb, ip_addresses=rd.ip_addresses,
                fqdn=rd.fqdn, mac_addresses=rd.mac_addresses, os_type=rd.os_type, os_name=rd.os_name,
                properties=rd.properties, provider_tags=rd.provider_tags,
                ansible_host=rd.ansible_host, ansible_connection=rd.ansible_connection,
                inventory_group=rd.inventory_group, ems_created_on=rd.ems_created_on)
            defaults["organization"] = provider_model.organization
            resource, created = Resource.objects.update_or_create(provider=provider_model, ems_ref=rd.ems_ref, defaults=defaults)
            if created:
                result.created += 1
            else:
                result.updated += 1
            ResourceSighting.objects.create(resource=resource, collection_run=run,
                state=rd.state or "unknown", power_state=rd.power_state,
                cpu_count=rd.cpu_count, memory_mb=rd.memory_mb, metrics=rd.metrics)
            for rel in rd.relationships:
                deferred_rels.append((rd.ems_ref, rel["target_ems_ref"], rel["relationship_type"]))
        if deferred_rels:
            ems_map = dict(Resource.objects.filter(provider=provider_model, ems_ref__in=seen).values_list("ems_ref", "id"))
            for s, t, rtype in deferred_rels:
                sid, tid = ems_map.get(s), ems_map.get(t)
                if sid and tid:
                    ResourceRelationship.objects.update_or_create(source_id=sid, target_id=tid, defaults={"relationship_type": rtype})
        logger.info("Collection complete: found=%d created=%d updated=%d", result.found, result.created, result.updated)
    finally:
        provider_instance.disconnect()
        logger.info("Disconnected from provider %s", provider_model.name)
    return result.as_dict()
