"""
Dispatcherd task definitions for inventory collection.

Tasks are registered via the ``@task()`` decorator so that they can be
submitted from any process that has called ``dispatcherd.config.setup()``,
and executed by the dispatcherd worker service.

The actual collection logic (calling Ansible modules, parsing provider
responses, upserting Resource records) will be implemented in collector
plugins later.  The task scaffolding here handles the full lifecycle:

    pending → running → completed | failed | canceled
"""

import logging
import time
import traceback

import django
from django.utils import timezone

logger = logging.getLogger("apps.inventory.tasks")

# ---------------------------------------------------------------------------
# Dispatcherd registration — guarded so the module is still importable
# when dispatcherd is not installed (e.g. during migrations).
# ---------------------------------------------------------------------------
try:
    from dispatcherd.publish import task

    _HAS_DISPATCHER = True
except ImportError:
    _HAS_DISPATCHER = False

    # Provide a no-op decorator so the function definitions below don't fail
    def task(**kwargs):  # type: ignore[no-redef]
        def wrapper(fn):
            return fn
        return wrapper


def _ensure_django():
    """Ensure Django is set up in the worker subprocess."""
    try:
        from django.conf import settings
        _ = settings.DATABASES  # noqa: F841 — force lazy setup
    except Exception:
        django.setup()


# ---------------------------------------------------------------------------
# Collection task
# ---------------------------------------------------------------------------

@task(queue="inventory_tasks", decorate=False)
def run_collection(collection_run_id: str) -> dict:
    """
    Execute an inventory collection for the given CollectionRun.

    This is dispatched as a background task via dispatcherd.  The function:

    1. Marks the CollectionRun as ``running``
    2. Resolves the provider and determines which resource types to collect
    3. Executes the collection (placeholder — real collectors come later)
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
    Placeholder for real collection logic.

    In a real implementation this would:
    - Look up the provider's vendor and determine the Ansible collection to use
    - Resolve credentials from credential_ref
    - Call the appropriate collector plugin (AWS, Azure, VMware, etc.)
    - Upsert Resource records, handle deletes for missing resources
    - Return statistics

    For now, simulates a short collection run.
    """
    provider = run.provider
    logger.info(
        "Collecting from provider=%s vendor=%s type=%s endpoint=%s",
        provider.name,
        provider.vendor,
        provider.provider_type,
        provider.endpoint,
    )

    # Simulate work — replace with real collector dispatch
    time.sleep(2)

    return {
        "found": 0,
        "created": 0,
        "updated": 0,
        "removed": 0,
        "unchanged": 0,
        "message": f"Placeholder collection for {provider.vendor}/{provider.provider_type} — no collector plugin installed yet.",
    }
