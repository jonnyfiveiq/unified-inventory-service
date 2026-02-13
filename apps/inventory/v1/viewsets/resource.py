"""
Resource viewset — read-only.  Resources are created by collection tasks,
not directly via the API.
"""

from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from apps.inventory.models import Resource, ResourceRelationship
from apps.inventory.v1.serializers import ResourceRelationshipSerializer, ResourceSerializer


class ResourceViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = Resource.objects.select_related("resource_type", "provider").all()
    serializer_class = ResourceSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = [
        "provider",
        "resource_type",
        "state",
        "region",
        "os_type",
        "organization",
    ]
    search_fields = ["name", "ems_ref", "fqdn", "vendor_type"]
    ordering_fields = ["name", "state", "first_discovered_at", "last_seen_at"]


class ResourceRelationshipViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = ResourceRelationship.objects.select_related("source", "target").all()
    serializer_class = ResourceRelationshipSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["relationship_type", "source", "target"]
    ordering_fields = ["relationship_type"]
