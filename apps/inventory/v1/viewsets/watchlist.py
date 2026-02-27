"""Watchlist viewset — full CRUD plus resource membership management."""
from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.inventory.models import Resource, Watchlist
from apps.inventory.v1.serializers import (
    ResourceSerializer,
    WatchlistResourcesSerializer,
    WatchlistSerializer,
)


class WatchlistViewSet(ModelViewSet):
    serializer_class = WatchlistSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at", "updated_at"]
    filterset_fields = ["watchlist_type", "organization"]

    def get_queryset(self):
        return (
            Watchlist.objects
            .annotate(resource_count_annotation=Count("resources"))
            .order_by("-updated_at")
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user.username)

    # ── Resource membership actions ────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="resources")
    def list_resources(self, request, pk=None):
        """GET /watchlists/{id}/resources/ — list resources in this watchlist."""
        watchlist = self.get_object()
        qs = (
            watchlist.resources
            .select_related("resource_type", "provider")
            .prefetch_related("tags")
        )

        # Spotlight search — filter across multiple fields
        search = request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(vendor_type__icontains=search)
                | Q(state__icontains=search)
                | Q(region__icontains=search)
                | Q(os_name__icontains=search)
                | Q(os_type__icontains=search)
                | Q(fqdn__icontains=search)
                | Q(flavor__icontains=search)
                | Q(cloud_tenant__icontains=search)
                | Q(provider__name__icontains=search)
                | Q(resource_type__name__icontains=search)
            )

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = ResourceSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ResourceSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="resources/add")
    def add_resources(self, request, pk=None):
        """POST /watchlists/{id}/resources/add/ {resource_ids: [...]}"""
        watchlist = self.get_object()
        ser = WatchlistResourcesSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        resources = Resource.objects.filter(id__in=ser.validated_data["resource_ids"])
        watchlist.resources.add(*resources)
        return Response({"detail": f"Added {resources.count()} resource(s)."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="resources/remove")
    def remove_resources(self, request, pk=None):
        """POST /watchlists/{id}/resources/remove/ {resource_ids: [...]}"""
        watchlist = self.get_object()
        ser = WatchlistResourcesSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        resources = Resource.objects.filter(id__in=ser.validated_data["resource_ids"])
        watchlist.resources.remove(*resources)
        return Response({"detail": f"Removed {resources.count()} resource(s)."}, status=status.HTTP_200_OK)
