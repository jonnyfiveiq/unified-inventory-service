"""Serializers for the provider plugin registry API.

These serializers expose the plugin discovery layer — which provider
classes are available and their metadata — as a read-only REST API.

The data comes from the external inventory_providers package, not
from Django models.
"""
from rest_framework import serializers


class ProviderPluginSerializer(serializers.Serializer):
    """
    Summary of a discovered provider plugin.

    Maps to the dict returned by BaseProvider.metadata().
    """

    key = serializers.CharField(help_text="Unique key: vendor:provider_type")
    vendor = serializers.CharField()
    provider_type = serializers.CharField()
    display_name = serializers.CharField()
    class_path = serializers.CharField(
        source="class", help_text="Fully qualified Python class name"
    )
    supported_resource_types = serializers.ListField(child=serializers.CharField())
    configured_instances = serializers.IntegerField(
        default=0,
        help_text="Number of Provider model instances using this plugin",
    )


class ProviderPluginTestResultSerializer(serializers.Serializer):
    """Result of a provider connectivity test."""

    provider_id = serializers.UUIDField()
    provider_name = serializers.CharField()
    plugin_key = serializers.CharField()
    success = serializers.BooleanField()
    message = serializers.CharField()


class ProviderPluginUploadSerializer(serializers.Serializer):
    """Validates the upload request for a provider plugin archive."""

    plugin = serializers.FileField(
        help_text=(
            "Plugin archive file (.tar.gz, .tgz, or .zip). "
            "Must contain manifest.yml and provider.py at minimum."
        ),
    )
