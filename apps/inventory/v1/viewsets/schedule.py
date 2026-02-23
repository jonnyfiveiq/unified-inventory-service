"""ViewSet for CollectionSchedule - full CRUD nested under a provider."""
import logging
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.inventory.models import Provider, CollectionRun
from apps.inventory.models.schedule import CollectionSchedule
from apps.inventory.v1.serializers.schedule import CollectionScheduleSerializer
from apps.inventory.v1.serializers import CollectionRunSerializer

logger = logging.getLogger("apps.inventory.views")


class CollectionScheduleViewSet(ModelViewSet):
    """
    CRUD for collection schedules, scoped to a provider:
        GET/POST   /api/v1/providers/{provider_id}/schedules/
        GET/PUT/PATCH/DELETE  /api/v1/providers/{provider_id}/schedules/{id}/
        POST  /api/v1/providers/{provider_id}/schedules/{id}/trigger/
    """
    serializer_class = CollectionScheduleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CollectionSchedule.objects.filter(
            provider_id=self.kwargs["provider_pk"]
        ).order_by("name")

    def perform_create(self, serializer):
        provider = Provider.objects.get(pk=self.kwargs["provider_pk"])
        serializer.save(provider=provider)

    @action(detail=True, methods=["post"], url_path="trigger")
    def trigger(self, request, provider_pk=None, pk=None):
        """Immediately fire a collection run for this schedule's provider."""
        schedule = self.get_object()
        provider = schedule.provider

        if not provider.enabled:
            return Response({"detail": "Provider is disabled."}, status=status.HTTP_409_CONFLICT)

        if provider.collection_runs.filter(
            status__in=[CollectionRun.Status.PENDING, CollectionRun.Status.RUNNING]
        ).exists():
            return Response(
                {"detail": "A collection is already in progress for this provider."},
                status=status.HTTP_409_CONFLICT,
            )

        run = CollectionRun.objects.create(
            provider=provider,
            collection_type=CollectionRun.CollectionType.FULL,
            status=CollectionRun.Status.PENDING,
        )
        try:
            from apps.inventory.tasks import run_collection
            from dispatcherd.publish import submit_task
            submit_task(run_collection, kwargs={"collection_run_id": str(run.id)})
        except Exception as exc:
            logger.exception("Failed to dispatch trigger for schedule %s", schedule.pk)
            run.status = CollectionRun.Status.FAILED
            run.error_message = str(exc)
            run.save(update_fields=["status", "error_message"])
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(CollectionRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)
