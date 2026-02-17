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
    from dispatcherd.config import setup as _dispatcherd_setup
    from dispatcherd.publish import task

    _dispatcherd_setup(
        settings_module="inventory_service.settings",
        service_name="inventory",
    )
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
    """
    Delegate collection to the appropriate provider plugin.

    Looks up the registered provider for this run's provider model,
    instantiates it with resolved credentials, and delegates the
    full collection lifecycle to it.
    """
    from inventory_providers import registry

    provider_model = run.provider

    logger.info(
        "Collecting from provider=%s vendor=%s type=%s endpoint=%s",
        provider_model.name,
        provider_model.vendor,
        provider_model.provider_type,
        provider_model.endpoint,
    )

    # Instantiate the provider plugin (resolves credentials automatically)
    provider_instance = registry.instantiate(provider_model)

    # Update collection run metadata
    run.collector_version = getattr(provider_instance, "__version__", "0.1.0")
    run.save(update_fields=["collector_version"])

    # Run the collection
    result = provider_instance.run_collection(run)

    return result.as_dict()
