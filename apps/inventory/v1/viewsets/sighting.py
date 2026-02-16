from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets

from apps.inventory.models import ResourceSighting
from apps.inventory.v1.serializers.resource import ResourceSightingSerializer


class ResourceSightingFilter(filters.FilterSet):
    resource = filters.UUIDFilter(field_name="resource__id")
    collection_run = filters.UUIDFilter(field_name="collection_run__id")
    state = filters.CharFilter()
    seen_after = filters.DateTimeFilter(field_name="seen_at", lookup_expr="gte")
    seen_before = filters.DateTimeFilter(field_name="seen_at", lookup_expr="lte")

    class Meta:
        model = ResourceSighting
        fields = ["resource", "collection_run", "state"]


class ResourceSightingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only endpoint for resource sighting history.

    Sightings are created automatically by collectors during collection
    runs. Each sighting is a point-in-time snapshot of a resource state,
    enabling historical graphing, drift detection, and compliance auditing.

    Filters: resource, collection_run, state, seen_after, seen_before
    Search: resource__name
    Ordering: seen_at, state, cpu_count, memory_mb
    """

    queryset = ResourceSighting.objects.select_related(
        "resource", "collection_run"
    ).all()
    serializer_class = ResourceSightingSerializer
    filterset_class = ResourceSightingFilter
    search_fields = ["resource__name"]
    ordering_fields = ["seen_at", "state", "cpu_count", "memory_mb"]
    ordering = ["-seen_at"]
