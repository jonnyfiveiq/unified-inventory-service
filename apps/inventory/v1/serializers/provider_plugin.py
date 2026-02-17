"""Serializers for the provider plugin registry API.

These serializers expose the plugin discovery layer — which provider
classes are available, their manifests, connection parameters, and
dependency requirements — as a read-only REST API.
"""

from rest_framework import serializers


class ConnectionParameterSerializer(serializers.Serializer):
    """A single connection parameter defined in a provider's manifest."""
    name = serializers.CharField()
    type = serializers.CharField(default="string")
    required = serializers.BooleanField(default=False)
    secret = serializers.BooleanField(default=False)
    default = serializers.CharField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class ProviderManifestSerializer(serializers.Serializer):
    """Manifest metadata for a provider plugin (mirrors manifest.yml)."""
    namespace = serializers.CharField()
    name = serializers.CharField()
    version = serializers.CharField()
    display_name = serializers.CharField()
    description = serializers.CharField(allow_blank=True, default="")
    infrastructure = serializers.CharField(required=False, default="")
    ansible_collection = serializers.CharField(required=False, default="")
    connection_parameters = ConnectionParameterSerializer(many=True, required=False, default=[])
    has_python_requirements = serializers.BooleanField(default=False)
    has_collection_requirements = serializers.BooleanField(default=False)
    has_system_requirements = serializers.BooleanField(default=False)


class ProviderPluginSerializer(serializers.Serializer):
    """
    Summary of a discovered provider plugin.

    This is a read-only representation of a registered provider class
    and its manifest. It is NOT a model serializer — the data comes
    from the in-memory provider registry, not the database.
    """
    key = serializers.CharField(help_text="Unique key: vendor:provider_type")
    vendor = serializers.CharField()
    provider_type = serializers.CharField()
    display_name = serializers.CharField()
    class_path = serializers.CharField(
        source="class", help_text="Fully qualified Python class name"
    )
    supported_resource_types = serializers.ListField(child=serializers.CharField())
    manifest = ProviderManifestSerializer(required=False, allow_null=True)
    configured_instances = serializers.IntegerField(
        default=0,
        help_text="Number of Provider model instances using this plugin",
    )


class ProviderPluginDetailSerializer(ProviderPluginSerializer):
    """Extended detail view with dependency content."""
    python_requirements = serializers.CharField(
        required=False, allow_null=True, allow_blank=True,
        help_text="Contents of requirements.txt",
    )
    collection_requirements = serializers.DictField(
        required=False, allow_null=True,
        help_text="Parsed requirements.yml",
    )
    system_requirements = serializers.CharField(
        required=False, allow_null=True, allow_blank=True,
        help_text="Contents of bindep.txt",
    )


class ProviderPluginTestSerializer(serializers.Serializer):
    """Result of a provider connectivity test."""
    provider_id = serializers.UUIDField()
    provider_name = serializers.CharField()
    plugin_key = serializers.CharField()
    success = serializers.BooleanField()
    message = serializers.CharField()


class AggregatedDependenciesSerializer(serializers.Serializer):
    """Aggregated dependency requirements across all active provider plugins."""
    python_requirements = serializers.CharField(allow_blank=True, default="")
    collection_requirements = serializers.DictField(default=dict)
    system_requirements = serializers.CharField(allow_blank=True, default="")
