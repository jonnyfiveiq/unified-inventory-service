"""
CollectionRun viewset — read-only list/detail plus ``cancel`` action.

Collection runs are created exclusively through the provider ``collect``
action, never directly via POST to this endpoint.

GET  /api/v1/collection-runs/              → list all runs (filterable)
GET  /api/v1/collection-runs/{id}/         → detail
POST /api/v1/collection-runs/{id}/cancel/  → cancel a running task
"""

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.inventory.models import CollectionRun
from apps.inventory.v1.serializers import CollectionRunSerializer

logger = logging.getLogger("apps.inventory.views")


class CollectionRunViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """
    Read-only viewset for collection runs with a ``cancel`` action.

    Filtering examples:
        ?status=running
        ?provider=<uuid>
        ?collection_type=full
    """

    queryset = CollectionRun.objects.select_related("provider").all()
    serializer_class = CollectionRunSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "provider", "collection_type"]
    search_fields = ["provider__name", "task_uuid"]
    ordering_fields = ["started_at", "completed_at", "status"]

    @action(detail=True, methods=["post"], url_path="cancel", url_name="cancel")
    def cancel(self, request, pk=None):
        """
        Cancel a running or pending collection run.

        If the run has a dispatcherd task_uuid, a cancel control message
        is sent to the dispatcher service to kill the worker subprocess.
        The CollectionRun is marked as ``canceled`` regardless.

        Response: 200 with the updated CollectionRun.
        """
        run = self.get_object()

        if run.is_terminal:
            return Response(
                {"detail": f"Cannot cancel — run is already in terminal state '{run.status}'."},
                status=status.HTTP_409_CONFLICT,
            )

        # Try to cancel the dispatcherd task
        if run.task_uuid:
            _cancel_dispatcher_task(run.task_uuid)

        run.status = CollectionRun.Status.CANCELED
        run.canceled_at = timezone.now()
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "canceled_at", "completed_at"])

        logger.info("CollectionRun %s canceled (task_uuid=%s)", run.pk, run.task_uuid)
        serializer = CollectionRunSerializer(run)
        return Response(serializer.data, status=status.HTTP_200_OK)


def _cancel_dispatcher_task(task_uuid: str) -> None:
    """
    Send a cancel command to the dispatcherd service for the given task.

    Uses the dispatcherd control interface to send a ``cancel`` command
    over the broker.  If the dispatcher is unreachable, we log a warning
    but still mark the DB record as canceled — the task will detect this
    on its next checkpoint.
    """
    try:
        from dispatcherd.config import settings as dsettings
        from dispatcherd.control import Control

        broker_name = dsettings.publish.get("default_broker", "pg_notify")
        broker_config = dsettings.brokers.get(broker_name, {})
        channels = broker_config.get("channels", [])
        queue = channels[0] if channels else None

        ctrl = Control(broker_name=broker_name, broker_config=broker_config, queue=queue)
        ctrl.control(command="cancel", data={"uuid": task_uuid})
        logger.info("Sent cancel command for task %s", task_uuid)
    except ImportError:
        logger.warning("dispatcherd not installed — cannot send cancel command for task %s", task_uuid)
    except Exception:
        logger.exception("Failed to send cancel command for task %s", task_uuid)
