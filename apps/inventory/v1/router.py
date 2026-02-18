"""Router configuration for inventory v1 API."""
from rest_framework.routers import DefaultRouter

from apps.inventory.v1.viewsets import (
    ProviderPluginViewSet,
    CollectionRunViewSet,
    ProviderViewSet,
    ResourceCategoryViewSet,
    ResourceDriftViewSet,
    ResourceRelationshipViewSet,
    ResourceTypeViewSet,
    ResourceViewSet,
    ResourceSightingViewSet,
    VendorTypeMappingViewSet,
    PropertyDefinitionViewSet,
)

router = DefaultRouter()

# Core inventory endpoints
router.register(r'providers', ProviderViewSet, basename='provider')
router.register(r'collection-runs', CollectionRunViewSet, basename='collectionrun')
router.register(r'resources', ResourceViewSet, basename='resource')
router.register(r'resource-relationships', ResourceRelationshipViewSet, basename='resourcerelationship')

# Drift tracking
router.register(r'resource-drift', ResourceDriftViewSet, basename='resourcedrift')

# Taxonomy reference data
router.register(r'resource-categories', ResourceCategoryViewSet, basename='resourcecategory')
router.register(r'resource-types', ResourceTypeViewSet, basename='resourcetype')
router.register(r'vendor-type-mappings', VendorTypeMappingViewSet, basename='vendortypemapping')
router.register(r'property-definitions', PropertyDefinitionViewSet, basename='propertydefinition')
router.register(r'resource-sightings', ResourceSightingViewSet, basename='resourcesighting')

# Provider plugin registry
router.register(r'provider-plugins', ProviderPluginViewSet, basename='providerplugin')
