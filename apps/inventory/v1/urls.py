"""URL configuration for inventory v1 API."""
from .router import router, providers_router, resources_router

urlpatterns = router.urls + providers_router.urls + resources_router.urls
