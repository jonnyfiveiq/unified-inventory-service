"""Metrics Import models.

MetricsImport — tracks an uploaded metrics-utility tarball.
PendingMatch  — uncertain host→resource matches needing admin review.
HostMapping   — learned mappings so confirmed matches auto-resolve on future imports.
"""
import uuid

from django.db import models


class MetricsImport(models.Model):
    """Tracks an uploaded metrics-utility tarball and its processing state."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    filename = models.CharField(
        max_length=512,
        help_text="Original filename of the uploaded tarball.",
    )
    source_label = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="User-provided label for the AAP instance.",
    )
    file_path = models.CharField(
        max_length=1024,
        blank=True,
        default="",
        help_text="Server-side path where the tarball is stored for processing.",
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    stats = models.JSONField(
        default=dict,
        blank=True,
        help_text="Processing stats.",
    )
    error_log = models.TextField(
        blank=True,
        default="",
        help_text="Processing errors and warnings.",
    )

    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="metrics_imports",
    )

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["status", "-uploaded_at"]),
        ]

    def __str__(self):
        return f"{self.filename} ({self.status})"


class PendingMatch(models.Model):
    """An uncertain host→resource match that needs administrator review."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        IGNORED = "ignored", "Ignored"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    metrics_import = models.ForeignKey(
        MetricsImport,
        on_delete=models.CASCADE,
        related_name="pending_matches",
    )

    aap_host_name = models.CharField(
        max_length=1024,
        help_text="The hostname from the metrics data.",
    )

    candidate_resource = models.ForeignKey(
        "inventory.Resource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pending_match_candidates",
        help_text="Best-guess Resource match (if any).",
    )
    match_reason = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Why we think this might match.",
    )
    match_score = models.IntegerField(
        default=0,
        help_text="Confidence score 0-100.",
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    resolved_resource = models.ForeignKey(
        "inventory.Resource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pending_match_resolved",
        help_text="The Resource the admin selected (on approval).",
    )

    raw_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Aggregated job data from the CSV for this host.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-match_score", "aap_host_name"]
        indexes = [
            models.Index(fields=["metrics_import", "status"]),
            models.Index(fields=["aap_host_name"]),
        ]

    def __str__(self):
        candidate = self.candidate_resource or "?"
        return f"{self.aap_host_name} -> {candidate} ({self.status})"


class HostMapping(models.Model):
    """Learned mapping: once an admin confirms host X = Resource Y,
    future imports auto-match without asking again."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    aap_host_name = models.CharField(
        max_length=1024,
        db_index=True,
        help_text="The AAP hostname (as it appears in metrics-utility exports).",
    )
    source_label = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Scoped to a specific AAP source label (empty = global).",
    )
    resource = models.ForeignKey(
        "inventory.Resource",
        on_delete=models.CASCADE,
        related_name="host_mappings",
        help_text="The inventory resource this host maps to.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="host_mappings",
    )

    class Meta:
        unique_together = [("aap_host_name", "source_label", "organization")]
        indexes = [
            models.Index(fields=["aap_host_name", "source_label"]),
        ]

    def __str__(self):
        return f"{self.aap_host_name} -> {self.resource.name}"
