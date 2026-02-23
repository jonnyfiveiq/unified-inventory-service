"""CollectionSchedule model — per-provider cron-based collection scheduling."""
import uuid
from django.db import models
from django.utils import timezone


class CollectionSchedule(models.Model):
    """
    A recurring schedule for automated inventory collection against a provider.

    Schedules are defined using standard cron expressions (5-field),
    e.g. "0 */6 * * *" for every 6 hours, "30 2 * * *" for 2:30am daily.

    The scheduler process evaluates next_run_at on each wake cycle (~30s)
    and dispatches a run_collection task when the time is due.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    provider = models.ForeignKey(
        "inventory.Provider",
        on_delete=models.CASCADE,
        related_name="schedules",
    )

    name = models.CharField(
        max_length=255,
        help_text="Human-readable label, e.g. 'Nightly full refresh'.",
    )

    cron_expression = models.CharField(
        max_length=100,
        help_text=(
            "Standard 5-field cron expression (minute hour day month weekday). "
            "Example: '0 */6 * * *' = every 6 hours."
        ),
    )

    enabled = models.BooleanField(
        default=True,
        help_text="Disabled schedules are skipped by the scheduler.",
    )

    last_run_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the last collection was triggered by this schedule.",
    )

    next_run_at = models.DateTimeField(
        null=True, blank=True,
        db_index=True,
        help_text="Pre-computed next fire time, updated after each run.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider", "name"]
        indexes = [
            models.Index(fields=["enabled", "next_run_at"]),
        ]

    def __str__(self):
        return f"{self.provider.name} — {self.name} [{self.cron_expression}]"

    def compute_next_run(self, after=None):
        """Return the next datetime this schedule should fire after `after`."""
        from croniter import croniter
        base = after or timezone.now()
        # croniter works with naive datetimes; we'll make it aware
        it = croniter(self.cron_expression, base)
        nxt = it.get_next(float)
        import datetime
        return datetime.datetime.fromtimestamp(nxt, tz=timezone.utc)

    def update_next_run(self, after=None):
        """Compute and persist next_run_at."""
        self.next_run_at = self.compute_next_run(after)
        self.save(update_fields=["next_run_at"])
