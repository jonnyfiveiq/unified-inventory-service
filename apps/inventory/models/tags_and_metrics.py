"""
Tag and Metrics models.

Tags provide a flexible, user-defined labeling system on top of the
provider-native tags (which are stored directly on Resource.provider_tags).

ResourceMetric stores point-in-time metric snapshots associated with
resources — the foundation for the event-based pricing model described
in the taxonomy document's "Event Generation" section.

ManageIQ alignment:
  Tag       ↔ ManageIQ's Tag + Classification system
  Metric    ↔ ManageIQ's Metric / MetricRollup tables
"""

import uuid

from django.db import models


class Tag(models.Model):
    """
    An Ansible-managed tag that can be applied to resources.

    Separate from provider_tags (which are the vendor's native labels).
    These are organization-scoped tags for internal classification:
    environment (prod/dev/staging), cost center, application mapping,
    compliance labels, etc.

    Maps to the "Metadata" section of the taxonomy:
    - Application Mapping
    - Outage Impact
    - Cost Center / Department
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="tags",
    )
    namespace = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Tag namespace (e.g. 'environment', 'cost_center', 'application').",
    )
    key = models.CharField(
        max_length=256,
        help_text="Tag key.",
    )
    value = models.CharField(
        max_length=1024,
        blank=True,
        default="",
        help_text="Tag value.",
    )

    resources = models.ManyToManyField(
        "inventory.Resource",
        related_name="tags",
        blank=True,
    )

    class Meta:
        unique_together = [("organization", "namespace", "key", "value")]
        ordering = ["namespace", "key", "value"]

    def __str__(self):
        if self.value:
            return f"{self.namespace}/{self.key}={self.value}"
        return f"{self.namespace}/{self.key}"


class ResourceMetric(models.Model):
    """
    Point-in-time metric snapshot for a resource.

    This is the foundation for event-based pricing from the taxonomy doc:
    - VMs/Containers: CPU/memory usage, network I/O, hours run
    - Serverless: invocations, duration, memory used
    - Messaging: messages sent/received, topic subscriptions
    - Storage: data stored in GB, read/write operations
    - ML Model Hosting: API calls/inferences
    - CI/CD Pipelines: pipeline runs, build minutes

    ManageIQ stores these in dedicated Metric/MetricRollup tables with
    typed columns. We use a flexible JSONB approach initially.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.ForeignKey(
        "inventory.Resource",
        on_delete=models.CASCADE,
        related_name="metrics",
    )
    timestamp = models.DateTimeField(
        db_index=True,
        help_text="When this metric was captured.",
    )

    # Metric classification
    metric_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Type of metric (cpu_usage, memory_usage, invocation_count, etc.).",
    )

    # Value — numeric for aggregation
    value_float = models.FloatField(
        null=True,
        blank=True,
        help_text="Numeric metric value.",
    )
    value_int = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Integer metric value (counts, bytes, etc.).",
    )
    unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Unit of measurement (percent, mb, gb, count, ms, etc.).",
    )

    # Extra metric context
    dimensions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metric dimensions/labels.",
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["resource", "metric_type", "-timestamp"]),
            models.Index(fields=["metric_type", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.resource.name}:{self.metric_type}={self.value_float or self.value_int}"
