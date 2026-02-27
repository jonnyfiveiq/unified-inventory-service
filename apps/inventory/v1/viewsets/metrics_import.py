"""ViewSets for Metrics Import, PendingMatch, and HostMapping."""
import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, DestroyModelMixin
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from apps.inventory.models.metrics_import import (
    HostMapping, MetricsImport, PendingMatch,
)
from apps.inventory.v1.serializers.metrics_import import (
    HostMappingSerializer, MetricsImportSerializer,
    MetricsImportUploadSerializer, PendingMatchResolveSerializer,
    PendingMatchSerializer,
)

logger = logging.getLogger('apps.inventory.views')

MAX_UPLOAD_SIZE = 200 * 1024 * 1024


class MetricsImportViewSet(ListModelMixin, RetrieveModelMixin, DestroyModelMixin, GenericViewSet):
    """
    Metrics Import management.

    GET    /api/inventory/v1/metrics-imports/          -- list all imports
    GET    /api/inventory/v1/metrics-imports/{id}/      -- import detail
    POST   /api/inventory/v1/metrics-imports/upload/    -- upload a tarball
    DELETE /api/inventory/v1/metrics-imports/{id}/      -- delete an import
    """

    serializer_class = MetricsImportSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'organization']
    ordering_fields = ['uploaded_at', 'processed_at', 'status']
    search_fields = ['filename', 'source_label']

    def get_queryset(self):
        return (
            MetricsImport.objects
            .prefetch_related('pending_matches')
            .order_by('-uploaded_at')
        )

    @action(
        detail=False, methods=['post'], url_path='upload',
        url_name='upload', parser_classes=[MultiPartParser],
    )
    def upload(self, request):
        """Upload a metrics-utility tarball for processing."""
        serializer = MetricsImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        archive_file = serializer.validated_data['file']
        source_label = serializer.validated_data.get('source_label', '')

        if archive_file.size > MAX_UPLOAD_SIZE:
            return Response(
                {'detail': f'Upload too large ({archive_file.size} bytes). Max is {MAX_UPLOAD_SIZE}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fname = archive_file.name or 'unknown.tar.gz'
        allowed_ext = ('.tar.gz', '.tgz', '.tar', '.zip')
        if not any(fname.endswith(ext) for ext in allowed_ext):
            return Response(
                {'detail': 'File must be a tarball (.tar.gz, .tgz, .tar) or a zip file (.zip).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        imports_dir = Path(getattr(settings, 'METRICS_IMPORTS_DIR', Path(settings.BASE_DIR) / 'metrics_imports'))
        imports_dir.mkdir(parents=True, exist_ok=True)

        dest_path = imports_dir / f'{timezone.now():%Y%m%d_%H%M%S}_{fname}'
        with open(dest_path, 'wb') as f:
            for chunk in archive_file.chunks():
                f.write(chunk)

        from apps.core.models import Organization
        org = Organization.objects.first()
        if not org:
            dest_path.unlink(missing_ok=True)
            return Response({'detail': 'No organization configured.'}, status=status.HTTP_400_BAD_REQUEST)

        imp = MetricsImport.objects.create(
            filename=fname, source_label=source_label,
            file_path=str(dest_path), status=MetricsImport.Status.PENDING,
            organization=org,
        )

        try:
            from apps.inventory.metrics_import_tasks import process_metrics_import
            process_metrics_import(str(imp.pk))
        except Exception as exc:
            logger.warning('Dispatcherd not available, running synchronously: %s', exc)
            from apps.inventory.metrics_import_tasks import process_metrics_import as sync_process
            sync_process(str(imp.pk))

        imp.refresh_from_db()
        return Response(MetricsImportSerializer(imp).data, status=status.HTTP_201_CREATED)


class PendingMatchViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """
    Pending match review queue.

    GET   /api/inventory/v1/pending-matches/
    GET   /api/inventory/v1/pending-matches/{id}/
    POST  /api/inventory/v1/pending-matches/{id}/resolve/
    POST  /api/inventory/v1/pending-matches/bulk-resolve/
    """

    serializer_class = PendingMatchSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['metrics_import', 'status', 'match_score']
    ordering_fields = ['match_score', 'aap_host_name', 'created_at']
    search_fields = ['aap_host_name']

    def get_queryset(self):
        return (
            PendingMatch.objects
            .select_related('candidate_resource', 'candidate_resource__resource_type', 'resolved_resource')
            .order_by('-match_score', 'aap_host_name')
        )

    @action(detail=True, methods=['post'], url_path='resolve', url_name='resolve')
    def resolve(self, request, pk=None):
        """Approve, reject, or ignore a pending match."""
        pending = self.get_object()

        if pending.status != PendingMatch.Status.PENDING:
            return Response(
                {'detail': f"Match already resolved as '{pending.status}'."}, status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PendingMatchResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action_type = serializer.validated_data['action']
        resource_id = serializer.validated_data.get('resource_id')

        if action_type == 'approve':
            return self._approve(pending, resource_id)
        elif action_type == 'reject':
            pending.status = PendingMatch.Status.REJECTED
            pending.resolved_at = timezone.now()
            pending.save(update_fields=['status', 'resolved_at'])
            return Response(PendingMatchSerializer(pending).data)
        else:
            pending.status = PendingMatch.Status.IGNORED
            pending.resolved_at = timezone.now()
            pending.save(update_fields=['status', 'resolved_at'])
            return Response(PendingMatchSerializer(pending).data)

    @action(detail=False, methods=['post'], url_path='bulk-resolve', url_name='bulk-resolve')
    def bulk_resolve(self, request):
        """Bulk resolve multiple pending matches."""
        ids = request.data.get('ids', [])
        action_type = request.data.get('action', '')

        if not ids or action_type not in ('approve', 'reject', 'ignore'):
            return Response(
                {'detail': "Provide 'ids' (list) and 'action' (approve/reject/ignore)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pendings = PendingMatch.objects.filter(
            pk__in=ids, status=PendingMatch.Status.PENDING
        ).select_related('candidate_resource', 'candidate_resource__resource_type')

        results = {'resolved': 0, 'errors': []}
        for pending in pendings:
            try:
                if action_type == 'approve':
                    self._approve(pending, resource_id=None)
                elif action_type == 'reject':
                    pending.status = PendingMatch.Status.REJECTED
                    pending.resolved_at = timezone.now()
                    pending.save(update_fields=['status', 'resolved_at'])
                else:
                    pending.status = PendingMatch.Status.IGNORED
                    pending.resolved_at = timezone.now()
                    pending.save(update_fields=['status', 'resolved_at'])
                results['resolved'] += 1
            except Exception as exc:
                results['errors'].append({'id': str(pending.pk), 'error': str(exc)})

        return Response(results)

    def _approve(self, pending, resource_id=None):
        from apps.inventory.models import AutomationRecord, Resource

        if resource_id:
            try:
                resource = Resource.objects.get(pk=resource_id)
            except Resource.DoesNotExist:
                return Response({'detail': f'Resource {resource_id} not found.'}, status=status.HTTP_400_BAD_REQUEST)
        elif pending.candidate_resource:
            resource = pending.candidate_resource
        else:
            return Response({'detail': 'No candidate resource and no resource_id provided.'}, status=status.HTTP_400_BAD_REQUEST)

        AutomationRecord.objects.get_or_create(
            resource=resource,
            source_name=pending.metrics_import.source_label or pending.metrics_import.filename,
            aap_host_name=pending.aap_host_name,
            defaults={
                'correlation_type': 'direct',
                'correlation_key': f'metrics-import:{pending.aap_host_name}',
                'correlation_confidence': 'probable',
                'aap_job_id': 0,
                'aap_job_name': f'Metrics import: {pending.metrics_import.filename}',
                'aap_job_status': 'aggregated',
                'automation_details': {'import_id': str(pending.metrics_import.pk), 'approved_by_admin': True, **pending.raw_data},
                'organization': pending.metrics_import.organization,
            },
        )

        HostMapping.objects.update_or_create(
            aap_host_name=pending.aap_host_name,
            source_label=pending.metrics_import.source_label,
            organization=pending.metrics_import.organization,
            defaults={'resource': resource},
        )

        pending.status = PendingMatch.Status.APPROVED
        pending.resolved_resource = resource
        pending.resolved_at = timezone.now()
        pending.save(update_fields=['status', 'resolved_resource', 'resolved_at'])

        return Response(PendingMatchSerializer(pending).data)


class HostMappingViewSet(ModelViewSet):
    """Learned host mappings -- CRUD."""

    serializer_class = HostMappingSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['organization', 'source_label']
    search_fields = ['aap_host_name']
    ordering_fields = ['aap_host_name', 'created_at']

    def get_queryset(self):
        return HostMapping.objects.select_related('resource').order_by('aap_host_name')
