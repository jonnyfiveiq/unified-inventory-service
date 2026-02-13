"""
Provider viewset with ``collect`` action for triggering inventory collection.

POST /api/v1/providers/{id}/collect/
  → creates a CollectionRun, dispatches a dispatcherd task, returns the run.
"""

import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.inventory.models import CollectionRun, Provider
from apps.inventory.v1.serializers import (
    CollectionRunSerializer,
    ProviderCollectSerializer,
    ProviderSerializer,
)

logger = logging.getLogger("apps.inventory.views")


class ProviderViewSet(ModelViewSet):
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["vendor", "infrastructure", "enabled", "organization"]
    search_fields = ["name", "vendor", "provider_type"]
    ordering_fields = ["name", "vendor", "created", "modified"]

    @action(detail=True, methods=["post"], url_path="collect", url_name="collect")
    def collect(self, request, pk=None):
        """
        Trigger an async inventory collection for this provider.

        Creates a CollectionRun record in ``pending`` state, submits a
        dispatcherd task via pg_notify, and returns the run immediately
        so the caller can poll for status.

        Request body (all optional):
            {
                "collection_type": "full",          // full | targeted | event_driven
                "target_resource_types": ["virtual_machine", "vpc"]  // empty = all
            }

        Response: 202 Accepted with the CollectionRun representation.
        """
        provider = self.get_object()

        if not provider.enabled:
            return Response(
                {"detail": "Provider is disabled. Enable it before collecting."},
                status=status.HTTP_409_CONFLICT,
            )

        # Check for an already-running collection on this provider
        active = provider.collection_runs.filter(
            status__in=[CollectionRun.Status.PENDING, CollectionRun.Status.RUNNING]
        ).first()
        if active:
            return Response(
                {
                    "detail": "A collection is already in progress for this provider.",
                    "collection_run": CollectionRunSerializer(active).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        input_serializer = ProviderCollectSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        # Create the collection run record
        run = CollectionRun.objects.create(
            provider=provider,
            collection_type=input_serializer.validated_data["collection_type"],
            target_resource_types=input_serializer.validated_data.get("target_resource_types", []),
        )

        # Dispatch via dispatcherd
        task_uuid = _submit_collection_task(run)
        if task_uuid:
            run.task_uuid = task_uuid
            run.save(update_fields=["task_uuid"])

        serializer = CollectionRunSerializer(run)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


def _submit_collection_task(run: CollectionRun) -> str:
    """Submit the collection task to dispatcherd.  Returns the task UUID or empty string."""
    try:
        from dispatcherd.publish import submit_task

        from apps.inventory.tasks import run_collection

        body, _queue = submit_task(
            run_collection,
            kwargs={"collection_run_id": str(run.id)},
        )
        task_uuid = body.get("uuid", "")
        logger.info("Dispatched collection task %s for run %s", task_uuid, run.id)
        return task_uuid
    except Exception:
        logger.exception("Failed to submit dispatcherd task for run %s — marking as failed", run.id)
        from django.utils import timezone

        run.status = CollectionRun.Status.FAILED
        run.completed_at = timezone.now()
        run.error_message = "Failed to submit task to dispatcherd. Is the dispatcher worker running?"
        run.save(update_fields=["status", "completed_at", "error_message"])
        return ""
