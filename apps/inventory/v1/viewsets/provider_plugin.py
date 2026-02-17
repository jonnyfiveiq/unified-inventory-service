"""Provider Plugin viewset — read-only API over the external plugin registry.

The provider plugin registry lives in the ``inventory_providers`` package,
which is external to this Django app. Plugins are installed as separate
Python packages and discovered via entry points. This viewset exposes
that registry through the REST API.

Endpoints:

    GET  /api/inventory/v1/provider-plugins/
        List all discovered provider plugins.

    GET  /api/inventory/v1/provider-plugins/{key}/
        Detail view for a single plugin.
        The key is vendor:provider_type (e.g. vmware:vcenter).

    POST /api/inventory/v1/provider-plugins/{key}/test/
        Test connectivity for all configured Provider instances
        using this plugin.

    POST /api/inventory/v1/provider-plugins/refresh/
        Force re-discovery of provider plugins.
"""

import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from inventory_providers import ProviderCredential, registry

from apps.inventory.v1.serializers.provider_plugin import (
    ProviderPluginSerializer,
    ProviderPluginTestResultSerializer,
)

logger = logging.getLogger("apps.inventory.views")


class ProviderPluginViewSet(ViewSet):
    """
    Read-only API for the external provider plugin registry.

    This is a plain ViewSet (not ModelViewSet) because the data comes
    from the in-memory registry in the ``inventory_providers`` package,
    not from Django models. Plugins are discovered at startup from
    Python entry points declared by externally installed packages.
    """

    permission_classes = [IsAuthenticated]
    lookup_field = "key"
    lookup_value_regex = r"[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+"

    def list(self, request):
        """List all discovered provider plugins."""
        plugins = registry.list_providers()
        plugins = self._annotate_instance_counts(plugins)
        serializer = ProviderPluginSerializer(plugins, many=True)
        return Response(serializer.data)

    def retrieve(self, request, key=None):
        """Detail view for a single provider plugin."""
        vendor, provider_type = self._parse_key(key)
        if vendor is None:
            return Response(
                {"detail": f"Invalid plugin key '{key}'. Expected format: vendor:provider_type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider_cls = registry.get(vendor, provider_type)
        if provider_cls is None:
            return Response(
                {"detail": f"No registered provider plugin for '{key}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = provider_cls.metadata()
        data = self._annotate_instance_counts([data])[0]
        serializer = ProviderPluginSerializer(data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="test", url_name="test")
    def test_connectivity(self, request, key=None):
        """
        Test connectivity for all enabled Provider instances using this plugin.

        Instantiates the plugin for each matching Provider model instance
        and calls ``validate_connection()``. Returns a per-instance result.
        """
        vendor, provider_type = self._parse_key(key)
        if vendor is None:
            return Response(
                {"detail": f"Invalid plugin key '{key}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider_cls = registry.get(vendor, provider_type)
        if provider_cls is None:
            return Response(
                {"detail": f"No registered provider plugin for '{key}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from apps.inventory.models import Provider

        instances = Provider.objects.filter(
            vendor=vendor,
            provider_type=provider_type,
            enabled=True,
        )

        if not instances.exists():
            return Response(
                {"detail": "No enabled Provider instances configured for this plugin.",
                 "results": []},
                status=status.HTTP_200_OK,
            )

        results = []
        for provider_model in instances:
            try:
                credential = self._resolve_credential(provider_model)
                instance = registry.instantiate(provider_model, credential)
                success, message = instance.validate_connection()
            except Exception as exc:
                success = False
                message = str(exc)

            results.append({
                "provider_id": provider_model.pk,
                "provider_name": provider_model.name,
                "plugin_key": key,
                "success": success,
                "message": message,
            })

        serializer = ProviderPluginTestResultSerializer(results, many=True)
        return Response({"results": serializer.data})

    @action(detail=False, methods=["post"], url_path="refresh", url_name="refresh")
    def refresh(self, request):
        """
        Force re-discovery of provider plugins.

        Resets the registry and re-scans entry points. Useful after
        pip installing a new external provider package without
        restarting the service.
        """
        registry.reset()
        registry.discover()
        plugins = registry.list_providers()
        return Response({
            "detail": f"Registry refreshed. {len(plugins)} provider(s) discovered.",
            "providers": ProviderPluginSerializer(plugins, many=True).data,
        })

    # -- Helpers --------------------------------------------------------

    @staticmethod
    def _parse_key(key: str):
        """Split 'vendor:provider_type' into a tuple, or (None, None)."""
        if not key or ":" not in key:
            return None, None
        parts = key.split(":", 1)
        return parts[0], parts[1]

    @staticmethod
    def _annotate_instance_counts(plugins: list[dict]) -> list[dict]:
        """Add configured_instances count from the Provider model."""
        from apps.inventory.models import Provider
        from django.db.models import Count

        counts = (
            Provider.objects
            .values("vendor", "provider_type")
            .annotate(count=Count("id"))
        )
        count_map = {
            f"{row['vendor']}:{row['provider_type']}": row["count"]
            for row in counts
        }

        for plugin in plugins:
            plugin["configured_instances"] = count_map.get(plugin["key"], 0)

        return plugins

    @staticmethod
    def _resolve_credential(provider_model) -> ProviderCredential:
        """Build a ProviderCredential from a Provider model instance."""
        creds = provider_model.credentials or {}
        return ProviderCredential(
            hostname=provider_model.endpoint or "",
            port=provider_model.port or 443,
            username=creds.get("username", ""),
            password=creds.get("password", ""),
            extra=creds.get("extra", {}),
        )
