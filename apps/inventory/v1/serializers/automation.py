"""Serializer for Automation Records."""
from rest_framework import serializers
from apps.inventory.models.automation import AutomationRecord


class AutomationRecordSerializer(serializers.ModelSerializer):
    """Read-only serializer for automation records."""

    resource_name = serializers.StringRelatedField(source="resource", read_only=True)
    resource_canonical_id = serializers.CharField(source="resource.canonical_id", read_only=True)

    class Meta:
        model = AutomationRecord
        fields = [
            "id", "resource", "resource_name", "resource_canonical_id",
            "source_name",
            "correlation_type", "correlation_key", "correlation_confidence",
            "aap_host_id", "aap_host_name",
            "aap_job_id", "aap_job_name", "aap_job_status",
            "aap_job_started_at", "aap_job_finished_at",
            "aap_inventory_name", "automation_details",
            "synced_at", "organization",
        ]
        read_only_fields = fields
