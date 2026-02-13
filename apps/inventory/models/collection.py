"""
Collection tracking models.

These track when inventory was collected, what changed, and provide the
audit trail needed for billing reconciliation and compliance.

ManageIQ alignment:
  Equivalent to ManageIQ's EmsRefresh tracking — recording when refreshes
  happen, what targets were refreshed, and the outcome.
"""

import uuid

from django.db import models


class CollectionRun(models.Model):
    """
    A record of a single inventory collection run against a provider.

    Tracks what was collected, when, how many resources were found,
    created, updated, or removed. This is critical for:
    - Billing reconciliation (indirect node counting)
    - Audit trail
    - Debugging collection issues
    - Metrics service event correlation

    The task_uuid field links this record to a dispatcherd background task,
    enabling status tracking, cancellation, and result retrieval through
    the REST API.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Partial (some targets failed)"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    class CollectionType(models.TextChoices):
        FULL = "full", "Full Refresh"
        TARGETED = "targeted", "Targeted Refresh"
        EVENT_DRIVEN = "event_driven", "Event-Driven Update"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    provider = models.ForeignKey(
        "inventory.Provider",
        on_delete=models.CASCADE,
        related_name="collection_runs",
    )

    collection_type = models.CharField(
        max_length=16,
        choices=CollectionType.choices,
        default=CollectionType.FULL,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this run was canceled.",
    )

    # === Dispatcherd Task Tracking ===
    task_uuid = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="UUID of the dispatcherd background task running this collection.",
    )

    # Collection statistics
    resources_found = models.IntegerField(default=0)
    resources_created = models.IntegerField(default=0)
    resources_updated = models.IntegerField(default=0)
    resources_removed = models.IntegerField(default=0)
    resources_unchanged = models.IntegerField(default=0)

    # Error tracking
    error_message = models.TextField(blank=True, default="")
    error_details = models.JSONField(default=dict, blank=True)
    result_traceback = models.TextField(
        blank=True,
        default="",
        help_text="Python traceback if the task failed with an exception.",
    )

    # Which resource types were targeted (empty = all)
    target_resource_types = models.JSONField(
        default=list,
        blank=True,
        help_text="List of resource_type slugs targeted. Empty means full refresh.",
    )

    # Collector metadata
    collector_version = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Version of the collection plugin/module that ran.",
    )
    ansible_collection = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Ansible collection used for this run.",
    )
    job_id = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="AAP Job ID that triggered this collection.",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["provider", "-started_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["task_uuid"]),
        ]

    def __str__(self):
        return f"{self.provider.name} @ {self.started_at} [{self.status}]"

    @property
    def is_terminal(self) -> bool:
        """Whether this run has reached a final state."""
        return self.status in (
            self.Status.COMPLETED,
            self.Status.FAILED,
            self.Status.CANCELED,
            self.Status.PARTIAL,
        )
