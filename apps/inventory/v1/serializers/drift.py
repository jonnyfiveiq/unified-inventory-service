"""Serializer for ResourceDrift."""
from rest_framework import serializers
from apps.inventory.models import ResourceDrift


class ResourceDriftSerializer(serializers.ModelSerializer):
    resource_name = serializers.CharField(source='resource.name', read_only=True)
    resource_type_slug = serializers.CharField(source='resource.resource_type.slug', read_only=True)
    provider_name = serializers.CharField(source='resource.provider.name', read_only=True)
    collection_run_started_at = serializers.DateTimeField(
        source='collection_run.started_at', read_only=True
    )
    previous_collection_run_started_at = serializers.DateTimeField(
        source='previous_collection_run.started_at', read_only=True
    )

    class Meta:
        model = ResourceDrift
        fields = [
            'id',
            'resource',
            'resource_name',
            'resource_type_slug',
            'provider_name',
            'collection_run',
            'collection_run_started_at',
            'previous_collection_run',
            'previous_collection_run_started_at',
            'drift_type',
            'detected_at',
            'changes',
        ]
        read_only_fields = fields
