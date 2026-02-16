"""Resource viewset — read-only.  Resources are created by collection tasks,
not directly via the API."""
from django.db.models import Avg, Count, Max, Min
from django_filters import rest_framework as filters
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.inventory.models import Resource, ResourceRelationship, ResourceSighting
from apps.inventory.v1.serializers import (
    ResourceRelationshipSerializer,
    ResourceSerializer,
    ResourceSightingSerializer,
)


class ResourceFilter(filters.FilterSet):
    canonical_id = filters.CharFilter(lookup_expr="exact")
    canonical_id_contains = filters.CharFilter(
        field_name="canonical_id", lookup_expr="icontains"
    )
    seen_count_min = filters.NumberFilter(field_name="seen_count", lookup_expr="gte")
    seen_count_max = filters.NumberFilter(field_name="seen_count", lookup_expr="lte")
    first_discovered_after = filters.DateTimeFilter(
        field_name="first_discovered_at", lookup_expr="gte"
    )
    first_discovered_before = filters.DateTimeFilter(
        field_name="first_discovered_at", lookup_expr="lte"
    )
    last_seen_after = filters.DateTimeFilter(
        field_name="last_seen_at", lookup_expr="gte"
    )
    last_seen_before = filters.DateTimeFilter(
        field_name="last_seen_at", lookup_expr="lte"
    )
    boot_time_after = filters.DateTimeFilter(
        field_name="boot_time", lookup_expr="gte"
    )
    boot_time_before = filters.DateTimeFilter(
        field_name="boot_time", lookup_expr="lte"
    )

    class Meta:
        model = Resource
        fields = [
            "provider",
            "resource_type",
            "state",
            "region",
            "os_type",
            "organization",
            "canonical_id",
            "cloud_tenant",
            "flavor",
        ]


class ResourceViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = Resource.objects.select_related("resource_type", "provider").all()
    serializer_class = ResourceSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ResourceFilter
    search_fields = ["name", "ems_ref", "canonical_id", "fqdn", "vendor_type", "cloud_tenant", "flavor"]
    ordering_fields = [
        "name", "state", "first_discovered_at", "last_seen_at", "seen_count", "boot_time", "ems_created_on"
    ]

    @action(detail=True, methods=["get"], url_path="sightings")
    def sightings(self, request, pk=None):
        """
        Return the sighting history for this resource.

        GET /resources/{id}/sightings/
        GET /resources/{id}/sightings/?seen_after=2025-01-01T00:00:00Z
        GET /resources/{id}/sightings/?state=running

        Each sighting is a point-in-time snapshot captured during a collection
        run. Use this to build historical graphs of state, compute metrics, and
        drift detection for a single asset over time.
        """
        resource = self.get_object()
        qs = ResourceSighting.objects.filter(resource=resource).select_related(
            "collection_run"
        ).order_by("-seen_at")

        # Apply optional date range filters
        seen_after = request.query_params.get("seen_after")
        seen_before = request.query_params.get("seen_before")
        state = request.query_params.get("state")
        if seen_after:
            qs = qs.filter(seen_at__gte=seen_after)
        if seen_before:
            qs = qs.filter(seen_at__lte=seen_before)
        if state:
            qs = qs.filter(state=state)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = ResourceSightingSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ResourceSightingSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        """
        Return an aggregated history summary for this resource, designed for
        graphing and dashboard widgets.

        GET /resources/{id}/history/

        Returns:
            - identity: canonical_id, vendor_identifiers, ems_ref
            - tracking: first_discovered_at, last_seen_at, seen_count
            - timeline: list of sighting snapshots (state, metrics, timestamp)
            - summary: aggregated stats (avg CPU, memory range, state changes)
        """
        resource = self.get_object()
        sightings = ResourceSighting.objects.filter(
            resource=resource
        ).order_by("seen_at")

        # Build timeline
        timeline = []
        for s in sightings:
            timeline.append({
                "seen_at": s.seen_at,
                "state": s.state,
                "power_state": s.power_state,
                "cpu_count": s.cpu_count,
                "memory_mb": s.memory_mb,
                "disk_gb": s.disk_gb,
                "metrics": s.metrics,
                "collection_run": str(s.collection_run_id),
            })

        # Aggregated summary
        agg = sightings.aggregate(
            avg_cpu=Avg("cpu_count"),
            min_cpu=Min("cpu_count"),
            max_cpu=Max("cpu_count"),
            avg_memory_mb=Avg("memory_mb"),
            min_memory_mb=Min("memory_mb"),
            max_memory_mb=Max("memory_mb"),
            avg_disk_gb=Avg("disk_gb"),
            min_disk_gb=Min("disk_gb"),
            max_disk_gb=Max("disk_gb"),
            total_sightings=Count("id"),
        )

        # Count distinct states observed
        states_observed = list(
            sightings.values_list("state", flat=True).distinct()
        )

        return Response({
            "identity": {
                "id": str(resource.id),
                "name": resource.name,
                "canonical_id": resource.canonical_id,
                "ems_ref": resource.ems_ref,
                "vendor_identifiers": resource.vendor_identifiers,
            },
            "tracking": {
                "first_discovered_at": resource.first_discovered_at,
                "last_seen_at": resource.last_seen_at,
                "seen_count": resource.seen_count,
            },
            "summary": {
                "total_sightings": agg["total_sightings"],
                "states_observed": states_observed,
                "cpu": {
                    "avg": agg["avg_cpu"],
                    "min": agg["min_cpu"],
                    "max": agg["max_cpu"],
                },
                "memory_mb": {
                    "avg": agg["avg_memory_mb"],
                    "min": agg["min_memory_mb"],
                    "max": agg["max_memory_mb"],
                },
                "disk_gb": {
                    "avg": agg["avg_disk_gb"],
                    "min": agg["min_disk_gb"],
                    "max": agg["max_disk_gb"],
                },
            },
            "timeline": timeline,
        })


class ResourceRelationshipViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = ResourceRelationship.objects.select_related("source", "target").all()
    serializer_class = ResourceRelationshipSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["relationship_type", "source", "target"]
    ordering_fields = ["relationship_type"]
