"""Dispatcherd task definitions for inventory collection."""
import logging
import traceback

import django
from django.utils import timezone

logger = logging.getLogger('apps.inventory.tasks')

try:
    from apps.inventory.dispatcher import setup_dispatcher
    setup_dispatcher()
    from dispatcherd.publish import task
except ImportError:
    logger.debug('dispatcherd not available')

    def task(*args, **kwargs):
        def wrapper(fn):
            return fn
        return wrapper


def _ensure_django():
    try:
        django.setup()
    except RuntimeError:
        pass


@task(queue='inventory')
def run_collection(collection_run_id: str) -> dict:
    """Execute an inventory collection run as a background task."""
    _ensure_django()
    from apps.inventory.models import CollectionRun

    try:
        run = CollectionRun.objects.select_related('provider').get(pk=collection_run_id)
    except CollectionRun.DoesNotExist:
        logger.error('CollectionRun %s not found', collection_run_id)
        return {'error': f'CollectionRun {collection_run_id} not found'}

    if run.is_terminal:
        logger.warning('CollectionRun %s already %s -- skipping', run.pk, run.status)
        return {'skipped': True, 'status': run.status}

    run.status = CollectionRun.Status.RUNNING
    run.save(update_fields=['status'])
    logger.info('Starting collection for provider %s (run=%s)', run.provider.name, run.pk)

    try:
        result = _do_collection(run)
        run.status = CollectionRun.Status.COMPLETED
        run.completed_at = timezone.now()
        run.resources_found     = result.get('found', 0)
        run.resources_created   = result.get('created', 0)
        run.resources_updated   = result.get('updated', 0)
        run.resources_removed   = result.get('removed', 0)
        run.resources_unchanged = result.get('unchanged', 0)
        run.save(update_fields=[
            'status', 'completed_at',
            'resources_found', 'resources_created', 'resources_updated',
            'resources_removed', 'resources_unchanged',
        ])
        logger.info('CollectionRun %s completed: %s', run.pk, result)
        return result
    except Exception as exc:
        run.status = CollectionRun.Status.FAILED
        run.completed_at = timezone.now()
        run.error_message = str(exc)[:2000]
        run.result_traceback = traceback.format_exc()[:8000]
        run.save(update_fields=['status', 'completed_at', 'error_message', 'result_traceback'])
        logger.exception('CollectionRun %s failed', run.pk)
        return {'error': str(exc)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _snapshot(resource, fields: list) -> dict:
    """Return {field: current_value} for the given field list."""
    return {f: getattr(resource, f, None) for f in fields}


def _diff(before: dict, after: dict) -> dict:
    """Return {field: {from: old, to: new}} for fields that changed."""
    return {
        f: {'from': before[f], 'to': after[f]}
        for f in before
        if before[f] != after[f]
    }


def _previous_run(provider_model, current_run):
    """Return the last completed CollectionRun before this one, or None."""
    from apps.inventory.models import CollectionRun
    return (
        CollectionRun.objects
        .filter(provider=provider_model, status=CollectionRun.Status.COMPLETED)
        .exclude(pk=current_run.pk)
        .order_by('-completed_at')
        .first()
    )


def _do_collection(run) -> dict:
    from inventory_providers import registry
    from inventory_providers.base import CollectionResult, ProviderCredential
    from apps.inventory.models import (
        DRIFT_TRACKED_FIELDS,
        Resource,
        ResourceDrift,
        ResourceRelationship,
        ResourceSighting,
        ResourceType,
    )

    provider_model = run.provider
    config = provider_model.connection_config or {}

    credential = ProviderCredential(
        hostname=provider_model.endpoint,
        username=config.get('username', ''),
        password=config.get('password', ''),
        port=config.get('port', 443),
        extra={k: v for k, v in config.items() if k not in ('username', 'password', 'port')},
    )

    provider_instance = registry.instantiate(provider_model, credential)
    run.collector_version = getattr(provider_instance, '__version__', '0.1.0')
    run.save(update_fields=['collector_version'])

    result = CollectionResult()
    deferred_rels: list = []
    rt_cache: dict = {}
    drift_events: list = []

    def _get_rt(slug):
        if slug not in rt_cache:
            rt, _ = ResourceType.objects.get_or_create(
                slug=slug, defaults={'name': slug.replace('_', ' ').title()}
            )
            rt_cache[slug] = rt
        return rt_cache[slug]

    import sys
    from pathlib import Path
    deps_dir = str(Path('/app/plugins/.deps'))
    if deps_dir not in sys.path and Path(deps_dir).is_dir():
        sys.path.insert(0, deps_dir)

    prev_run = _previous_run(provider_model, run)

    provider_instance.connect()
    logger.info('Connected to provider %s', provider_model.name)

    try:
        seen_ems_refs: set = set()

        for rd in provider_instance.collect():
            result.found += 1
            seen_ems_refs.add(rd.ems_ref)
            rt = _get_rt(rd.resource_type_slug)

            new_values = dict(
                name=rd.name or rd.ems_ref,
                resource_type=rt,
                description=rd.description,
                canonical_id=rd.canonical_id,
                vendor_identifiers=rd.vendor_identifiers,
                vendor_type=rd.vendor_type,
                state=rd.state or 'unknown',
                power_state=rd.power_state,
                boot_time=rd.boot_time,
                region=rd.region,
                availability_zone=rd.availability_zone,
                cloud_tenant=rd.cloud_tenant,
                flavor=rd.flavor,
                cpu_count=rd.cpu_count,
                memory_mb=rd.memory_mb,
                disk_gb=rd.disk_gb,
                ip_addresses=rd.ip_addresses,
                fqdn=rd.fqdn,
                mac_addresses=rd.mac_addresses,
                os_type=rd.os_type,
                os_name=rd.os_name,
                properties=rd.properties,
                provider_tags=rd.provider_tags,
                ansible_host=rd.ansible_host,
                ansible_connection=rd.ansible_connection,
                inventory_group=rd.inventory_group,
                ems_created_on=rd.ems_created_on,
                organization=provider_model.organization,
                deleted_at=None,  # clear soft-delete if resource is back
            )

            # Snapshot BEFORE the update so we can diff
            try:
                existing = Resource.objects.get(provider=provider_model, ems_ref=rd.ems_ref)
                before_snap = _snapshot(existing, DRIFT_TRACKED_FIELDS)
                was_deleted = existing.deleted_at is not None
            except Resource.DoesNotExist:
                existing = None
                before_snap = None
                was_deleted = False

            resource, created = Resource.objects.update_or_create(
                provider=provider_model,
                ems_ref=rd.ems_ref,
                defaults=new_values,
            )

            if created:
                result.created += 1
            else:
                result.updated += 1

                if was_deleted:
                    # Resource has been restored after a soft-delete
                    drift_events.append(ResourceDrift(
                        resource=resource,
                        collection_run=run,
                        previous_collection_run=prev_run,
                        drift_type=ResourceDrift.DriftType.RESTORED,
                        changes=_snapshot(resource, DRIFT_TRACKED_FIELDS),
                    ))
                    logger.info('RESTORED: %s (ems_ref=%s)', resource.name, rd.ems_ref)
                elif before_snap:
                    after_snap = _snapshot(resource, DRIFT_TRACKED_FIELDS)
                    diff = _diff(before_snap, after_snap)
                    if diff:
                        drift_events.append(ResourceDrift(
                            resource=resource,
                            collection_run=run,
                            previous_collection_run=prev_run,
                            drift_type=ResourceDrift.DriftType.MODIFIED,
                            changes=diff,
                        ))
                        logger.info('MODIFIED: %s fields=%s', resource.name, list(diff.keys()))
                else:
                    result.unchanged += 1

            ResourceSighting.objects.create(
                resource=resource,
                collection_run=run,
                state=rd.state or 'unknown',
                power_state=rd.power_state,
                cpu_count=rd.cpu_count,
                memory_mb=rd.memory_mb,
                metrics=rd.metrics,
            )

            for rel in rd.relationships:
                deferred_rels.append((rd.ems_ref, rel['target_ems_ref'], rel['relationship_type']))

        # --- Soft-delete: resources absent from this run ----------------------
        absent_qs = (
            Resource.objects
            .filter(provider=provider_model, deleted_at__isnull=True)
            .exclude(ems_ref__in=seen_ems_refs)
        )

        deleted_count = 0
        for absent in absent_qs.iterator():
            drift_events.append(ResourceDrift(
                resource=absent,
                collection_run=run,
                previous_collection_run=prev_run,
                drift_type=ResourceDrift.DriftType.DELETED,
                changes=_snapshot(absent, DRIFT_TRACKED_FIELDS),
            ))
            deleted_count += 1

        if deleted_count:
            absent_qs.update(deleted_at=timezone.now(), state='decommissioned')
            logger.info('Soft-deleted %d absent resources', deleted_count)

        # --- Bulk-create all drift events -------------------------------------
        if drift_events:
            ResourceDrift.objects.bulk_create(drift_events)
            logger.info('Created %d drift events', len(drift_events))

        # --- Resolve deferred relationships -----------------------------------
        if deferred_rels:
            ems_map = dict(
                Resource.objects
                .filter(provider=provider_model, ems_ref__in=seen_ems_refs)
                .values_list('ems_ref', 'id')
            )
            for s, t, rtype in deferred_rels:
                sid, tid = ems_map.get(s), ems_map.get(t)
                if sid and tid:
                    ResourceRelationship.objects.update_or_create(
                        source_id=sid, target_id=tid,
                        defaults={'relationship_type': rtype},
                    )

    finally:
        provider_instance.disconnect()
        logger.info('Disconnected from provider %s', provider_model.name)

    r = result.as_dict()
    r['removed'] = deleted_count
    return r
