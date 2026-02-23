"""Database-driven scheduler producer for dispatcherd.

Wakes up every POLL_INTERVAL seconds, finds CollectionSchedule rows
whose next_run_at is in the past, dispatches a run_collection task for
each, and updates last_run_at / next_run_at.

Runs inside the existing dispatcherd service process - no extra process needed.
"""
import asyncio
import logging

from django.utils import timezone

from dispatcherd.producers.base import BaseProducer

logger = logging.getLogger("apps.inventory.scheduler")

POLL_INTERVAL = 30


class SchedulerProducer(BaseProducer):
    def __init__(self, shared=None):
        super().__init__()
        self._task = None
        self._shutdown = False

    def all_tasks(self):
        return [self._task] if self._task else []

    async def shutdown(self):
        self._shutdown = True
        if self._task:
            self._task.cancel()

    async def start_producing(self, dispatcher):
        self._task = asyncio.create_task(
            self._produce_loop(), name="scheduler_producer"
        )

    async def _produce_loop(self):
        logger.info("SchedulerProducer started (poll interval: %ds)", POLL_INTERVAL)
        while not self._shutdown:
            try:
                await self._check_and_dispatch()
            except Exception:
                logger.exception("SchedulerProducer error during check cycle")
            await asyncio.sleep(POLL_INTERVAL)

    async def _check_and_dispatch(self):
        loop = asyncio.get_event_loop()
        from apps.inventory.models import CollectionRun
        from apps.inventory.models.schedule import CollectionSchedule

        now = timezone.now()
        due = await loop.run_in_executor(
            None,
            lambda: list(
                CollectionSchedule.objects
                .filter(enabled=True, next_run_at__lte=now)
                .select_related("provider")
            )
        )

        if not due:
            return

        logger.info("SchedulerProducer: %d schedule(s) due", len(due))
        for schedule in due:
            provider = schedule.provider
            if not provider.enabled:
                await loop.run_in_executor(None, schedule.update_next_run)
                continue

            running = await loop.run_in_executor(
                None,
                lambda p=provider: p.collection_runs.filter(
                    status__in=["pending", "running"]
                ).exists()
            )
            if running:
                logger.info("Skipping %s - collection in progress", schedule.name)
                await loop.run_in_executor(None, schedule.update_next_run)
                continue

            try:
                run = await loop.run_in_executor(
                    None,
                    lambda p=provider: CollectionRun.objects.create(
                        provider=p,
                        collection_type=CollectionRun.CollectionType.FULL,
                        status=CollectionRun.Status.PENDING,
                    )
                )

                from apps.inventory.tasks import run_collection
                from dispatcherd.publish import submit_task

                await loop.run_in_executor(
                    None,
                    lambda r=run: submit_task(
                        run_collection, kwargs={"collection_run_id": str(r.id)}
                    )
                )

                next_run = schedule.compute_next_run()
                await loop.run_in_executor(
                    None,
                    lambda s=schedule, nr=next_run, n=now: (
                        CollectionSchedule.objects.filter(pk=s.pk).update(
                            last_run_at=n, next_run_at=nr
                        )
                    )
                )

                logger.info(
                    "Dispatched scheduled collection: provider=%s schedule=%s run=%s next=%s",
                    provider.name, schedule.name, run.pk, next_run,
                )
            except Exception:
                logger.exception("Failed to dispatch schedule %s", schedule.name)
                await loop.run_in_executor(None, schedule.update_next_run)
