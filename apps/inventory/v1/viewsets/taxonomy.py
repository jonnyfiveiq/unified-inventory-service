"""
Taxonomy viewsets — read-only reference data.

These expose the normalized resource classification hierarchy:
  ResourceCategory (Level 1) → ResourceType (Level 2) → VendorTypeMapping
"""

from rest_framework.mixins import ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from apps.inventory.models import ResourceCategory, ResourceType, VendorTypeMapping
from apps.inventory.v1.serializers import (
    ResourceCategorySerializer,
    ResourceTypeSerializer,
    VendorTypeMappingSerializer,
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
