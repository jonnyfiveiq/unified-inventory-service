from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("apps.inventory.v1.urls")),
]
