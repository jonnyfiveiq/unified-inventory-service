"""URL configuration for inventory v1 API."""
from .router import router, providers_router

urlpatterns = router.urls + providers_router.urls
