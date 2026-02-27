from rest_framework_nested import routers as nested_routers

"""Router configuration for inventory v1 API."""
from rest_framework.routers import DefaultRouter

from apps.inventory.v1.viewsets import (
    AutomationRecordViewSet,
    HostMappingViewSet,
    MetricsImportViewSet,
    PendingMatchViewSet,
    ProviderPluginViewSet,
    CollectionRunViewSet,
    ProviderViewSet,
    ResourceCategoryViewSet,
    ResourceDriftViewSet,
    ResourceRelationshipViewSet,
    ResourceTagViewSet,
    ResourceTypeViewSet,
    ResourceViewSet,
    ResourceSightingViewSet,
    TagViewSet,
    VendorTypeMappingViewSet,
    PropertyDefinitionViewSet,
    CollectionScheduleViewSet,
    WatchlistViewSet,
)

router = DefaultRouter()

# Core inventory endpoints
router.register(r'providers', ProviderViewSet, basename='provider')
router.register(r'collection-runs', CollectionRunViewSet, basename='collectionrun')
router.register(r'resources', ResourceViewSet, basename='resource')
router.register(r'resource-relationships', ResourceRelationshipViewSet, basename='resourcerelationship')

# Tags
router.register(r'tags', TagViewSet, basename='tag')

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

# Watchlists
router.register(r'watchlists', WatchlistViewSet, basename='watchlist')

# Automation records (read-only)
router.register(r'automation-records', AutomationRecordViewSet, basename='automationrecord')

# Metrics imports
router.register(r'metrics-imports', MetricsImportViewSet, basename='metricsimport')
router.register(r'pending-matches', PendingMatchViewSet, basename='pendingmatch')
router.register(r'host-mappings', HostMappingViewSet, basename='hostmapping')

# Nested schedules under providers
providers_router = nested_routers.NestedDefaultRouter(router, r'providers', lookup='provider')
providers_router.register(r'schedules', CollectionScheduleViewSet, basename='provider-schedule')

# Nested tags under resources
resources_router = nested_routers.NestedDefaultRouter(router, r'resources', lookup='resource')
resources_router.register(r'tags', ResourceTagViewSet, basename='resource-tag')
