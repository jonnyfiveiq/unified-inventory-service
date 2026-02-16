"""
Taxonomy viewsets — read-only reference data.

These expose the normalized resource classification hierarchy:
  ResourceCategory (Level 1) → ResourceType (Level 2) → VendorTypeMapping
"""

from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from apps.inventory.models import ResourceCategory, ResourceType, VendorTypeMapping, PropertyDefinition
from apps.inventory.v1.serializers import (
    ResourceCategorySerializer,
    ResourceTypeSerializer,
    VendorTypeMappingSerializer,
    PropertyDefinitionSerializer,
)


class ResourceCategoryViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = ResourceCategory.objects.all()
    serializer_class = ResourceCategorySerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["name", "slug"]
    ordering_fields = ["sort_order", "name"]


class ResourceTypeViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = ResourceType.objects.select_related("category").all()
    serializer_class = ResourceTypeSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["category", "is_countable"]
    search_fields = ["name", "slug"]
    ordering_fields = ["sort_order", "name", "category"]


class VendorTypeMappingViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = VendorTypeMapping.objects.select_related("resource_type").all()
    serializer_class = VendorTypeMappingSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["vendor", "resource_type"]
    search_fields = ["vendor", "vendor_resource_type"]
    ordering_fields = ["vendor", "vendor_resource_type"]


class PropertyDefinitionViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """
    Property definitions define the expected JSONB keys for each resource type.

    Collector authors should query this endpoint to discover the contract for
    Resource.properties for any given resource type. This ensures consistent
    key naming across collectors (solving the 'publicly_available' vs 'public'
    vs 'is_public' problem).

    Filters: resource_type, vendor_scope, required, value_type
    Search: key, name
    """
    queryset = PropertyDefinition.objects.select_related("resource_type").all()
    serializer_class = PropertyDefinitionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["resource_type", "vendor_scope", "required", "value_type"]
    search_fields = ["key", "name"]
    ordering_fields = ["key", "name", "resource_type"]
