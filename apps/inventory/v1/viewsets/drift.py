"""ViewSet for ResourceDrift -- read-only drift history."""
from django_filters import rest_framework as filters
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from apps.inventory.models import ResourceDrift
from apps.inventory.v1.serializers.drift import ResourceDriftSerializer


class ResourceDriftFilter(filters.FilterSet):
    detected_after = filters.DateTimeFilter(field_name='detected_at', lookup_expr='gte')
    detected_before = filters.DateTimeFilter(field_name='detected_at', lookup_expr='lte')

    class Meta:
        model = ResourceDrift
        fields = [
            'resource',
            'collection_run',
            'drift_type',
            'resource__provider',
        ]


class ResourceDriftViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """Read-only drift event history.

    Supports filtering by:
      resource          - UUID of the resource
      collection_run    - UUID of the collection run
      drift_type        - modified | deleted | restored
      resource__provider - UUID of the provider (all drift across a provider)
      detected_after    - ISO datetime lower bound
      detected_before   - ISO datetime upper bound

    Examples:
      GET /api/inventory/v1/resource-drift/?resource=<uuid>
      GET /api/inventory/v1/resource-drift/?resource__provider=<uuid>&drift_type=deleted
      GET /api/inventory/v1/resource-drift/?drift_type=modified&detected_after=2025-01-01
    """

    queryset = (
        ResourceDrift.objects
        .select_related(
            'resource',
            'resource__resource_type',
            'resource__provider',
            'collection_run',
            'previous_collection_run',
        )
        .all()
    )
    serializer_class = ResourceDriftSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ResourceDriftFilter
    ordering_fields = ['detected_at', 'drift_type']
    ordering = ['-detected_at']
