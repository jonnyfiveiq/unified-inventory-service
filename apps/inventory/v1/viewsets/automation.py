"""ViewSet for Automation Records (read-only)."""
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from apps.inventory.models.automation import AutomationRecord
from apps.inventory.v1.serializers.automation import AutomationRecordSerializer


class AutomationRecordViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """
    Read-only access to automation records.
    GET   /api/inventory/v1/automation-records/
    GET   /api/inventory/v1/automation-records/{id}/
    """

    serializer_class = AutomationRecordSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["aap_host_name", "aap_job_name", "correlation_key"]
    ordering_fields = ["aap_job_started_at", "synced_at", "aap_job_name"]
    filterset_fields = [
        "resource", "correlation_type",
        "correlation_confidence", "aap_job_status", "organization",
    ]

    def get_queryset(self):
        return (
            AutomationRecord.objects
            .select_related("resource")
            .order_by("-aap_job_started_at")
        )
