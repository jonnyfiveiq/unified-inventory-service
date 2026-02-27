"""Automation correlation models.

AutomationRecord — a correlated automation event linking an AAP job to an
inventory resource.
"""
import uuid

from django.db import models


class CorrelationType(models.TextChoices):
    DIRECT = "direct", "Direct"
    INDIRECT = "indirect", "Indirect"


class CorrelationConfidence(models.TextChoices):
    EXACT = "exact", "Exact"
    PROBABLE = "probable", "Probable"


class AutomationRecord(models.Model):
    """
    A correlated automation event linking an AAP job execution to an
    inventory resource.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    resource = models.ForeignKey(
        "inventory.Resource",
        on_delete=models.CASCADE,
        related_name="automation_records",
        help_text="The matched inventory resource.",
    )

    # Source identification (which AAP instance sent this)
    source_name = models.CharField(
        max_length=512, blank=True, default="",
        help_text="Name of the AAP source that reported this automation.",
    )

    correlation_type = models.CharField(
        max_length=16,
        choices=CorrelationType.choices,
        default=CorrelationType.DIRECT,
        db_index=True,
        help_text="direct (host-level SSH/WinRM) or indirect (API/fabric).",
    )
    correlation_key = models.CharField(
        max_length=1024,
        help_text="The value used to match (e.g. SMBIOS UUID).",
    )
    correlation_confidence = models.CharField(
        max_length=16,
        choices=CorrelationConfidence.choices,
        default=CorrelationConfidence.EXACT,
        help_text="Match confidence: exact (UUID) or probable (heuristic).",
    )

    aap_host_id = models.IntegerField(null=True, blank=True, help_text="Host ID in the AAP controller.")
    aap_host_name = models.CharField(max_length=1024, blank=True, default="", help_text="Hostname as known to AAP.")
    aap_job_id = models.IntegerField(help_text="The job execution ID in AAP.")
    aap_job_name = models.CharField(max_length=1024, blank=True, default="", help_text="Job template name.")
    aap_job_status = models.CharField(max_length=32, blank=True, default="", help_text="Job status: successful, failed, canceled, etc.")
    aap_job_started_at = models.DateTimeField(null=True, blank=True, help_text="When the job started.")
    aap_job_finished_at = models.DateTimeField(null=True, blank=True, help_text="When the job completed.")
    aap_inventory_name = models.CharField(max_length=512, blank=True, default="", help_text="AAP inventory the host belongs to.")
    automation_details = models.JSONField(
        default=dict, blank=True,
        help_text="Full metadata snapshot (playbook, extra_vars, etc.).",
    )

    synced_at = models.DateTimeField(auto_now=True, help_text="When this record was created/updated.")
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="automation_records",
        help_text="Owning organization.",
    )

    class Meta:
        ordering = ["-aap_job_started_at"]
        unique_together = [("resource", "source_name", "aap_job_id")]
        indexes = [
            models.Index(fields=["resource", "-aap_job_started_at"]),
            models.Index(fields=["correlation_type"]),
            models.Index(fields=["correlation_key"]),
            models.Index(fields=["aap_job_started_at"]),
        ]

    def __str__(self):
        return f"{self.resource.name} \u2190 {self.aap_job_name or self.aap_job_id}"
