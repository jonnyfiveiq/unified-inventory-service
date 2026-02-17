"""Provider Plugin viewset — read-only API over the plugin registry.

Endpoints:

    GET  /api/inventory/v1/provider-plugins/
        List all discovered provider plugins with manifest summaries.

    GET  /api/inventory/v1/provider-plugins/{key}/
        Detail view for a single plugin including dependency info.
        The key is vendor:provider_type (e.g. vmware:vcenter).

    GET  /api/inventory/v1/provider-plugins/dependencies/
        Aggregated dependency files across all active plugins.

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

from apps.inventory.providers import registry
from apps.inventory.v1.serializers.provider_plugin import (
    AggregatedDependenciesSerializer,
    ProviderPluginDetailSerializer,
    ProviderPluginSerializer,
    ProviderPluginTestSerializer,
)

logger = logging.getLogger("apps.inventory.views")


class ProviderPluginViewSet(ViewSet):
    """
    Read-only API for the provider plugin registry.

    This is a plain ViewSet (not ModelViewSet) because the data comes
    from the in-memory registry, not from Django models. The registry
    discovers plugins at startup from built-in packages, entry points,
    and runtime registrations.
    """

    permission_classes = [IsAuthenticated]
    # Used by the router — the 'key' is vendor:provider_type
    lookup_field = "key"
    lookup_value_regex = r"[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+"

    def list(self, request):
        """
        List all discovered provider plugins.

        Returns summary info for each registered plugin including
        manifest metadata and how many Provider model instances
        are configured to use it.
        """
        plugins = registry.list_providers()
        plugins = self._annotate_instance_counts(plugins)
        serializer = ProviderPluginSerializer(plugins, many=True)
        return Response(serializer.data)

    def retrieve(self, request, key=None):
        """
        Detail view for a single provider plugin.

        Includes full manifest info plus the contents of dependency
        files (requirements.txt, requirements.yml, bindep.txt).
        """
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

        manifest = registry.get_manifest(vendor, provider_type)

        data = {
            "key": key,
            "vendor": vendor,
            "provider_type": provider_type,
            "display_name": getattr(provider_cls, "display_name", key),
            "class": f"{provider_cls.__module__}.{provider_cls.__qualname__}",
            "supported_resource_types": list(
                getattr(provider_cls, "supported_resource_types", [])
            ),
            "manifest": manifest.as_dict() if manifest else None,
            "python_requirements": manifest.python_requirements() if manifest else None,
            "collection_requirements": manifest.collection_requirements() if manifest else None,
            "system_requirements": manifest.system_requirements() if manifest else None,
        }
        data = self._annotate_instance_counts([data])[0]
        serializer = ProviderPluginDetailSerializer(data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="test", url_name="test")
    def test_connectivity(self, request, key=None):
        """
        Test connectivity for all enabled Provider instances using this plugin.

        For each matching Provider model instance, the registry instantiates
        the plugin and calls ``validate_connection()``. Returns a list of
        results (one per instance).
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
                instance = registry.instantiate(provider_model)
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

        serializer = ProviderPluginTestSerializer(results, many=True)
        return Response({"results": serializer.data})

    @action(detail=False, methods=["get"], url_path="dependencies", url_name="dependencies")
    def dependencies(self, request):
        """
        Aggregated dependency requirements across all active provider plugins.

        Returns the merged contents of requirements.txt, requirements.yml,
        and bindep.txt from all discovered providers. Useful for building
        execution environments or validating that a deployment has all
        required packages.
        """
        data = {
            "python_requirements": registry.aggregated_python_requirements(),
            "collection_requirements": registry.aggregated_collection_requirements(),
            "system_requirements": registry.aggregated_system_requirements(),
        }
        serializer = AggregatedDependenciesSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="refresh", url_name="refresh")
    def refresh(self, request):
        """
        Force re-discovery of provider plugins.

        Resets the registry and re-scans built-in packages and entry
        points. Useful after installing a new external provider package
        without restarting the service.
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
        """
        Add ``configured_instances`` count to each plugin dict by querying
        the Provider model.
        """
        from apps.inventory.models import Provider
        from django.db.models import Count, Q

        # Build a single query to count instances per vendor+provider_type
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
