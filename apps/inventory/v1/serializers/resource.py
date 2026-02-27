from rest_framework import serializers

from apps.inventory.models import Resource, ResourceRelationship, ResourceSighting
from apps.inventory.v1.serializers.tags import TagSerializer


class ResourceSerializer(serializers.ModelSerializer):
    resource_type_slug = serializers.SlugRelatedField(
        source="resource_type", slug_field="slug", read_only=True,
    )
    resource_type_name = serializers.StringRelatedField(
        source="resource_type", read_only=True,
    )
    provider_name = serializers.StringRelatedField(
        source="provider", read_only=True,
    )
    tags = TagSerializer(many=True, read_only=True)

    # Automation correlation annotations (no migration needed)
    is_automated = serializers.BooleanField(
        read_only=True, default=False,
        help_text="Whether this resource has any automation records.",
    )
    automation_count = serializers.IntegerField(
        read_only=True, default=0,
        help_text="Number of automation records for this resource.",
    )
    last_automated_at = serializers.DateTimeField(
        read_only=True, default=None,
        help_text="Most recent automation timestamp.",
    )

    class Meta:
        model = Resource
        fields = [
            "id", "resource_type", "resource_type_slug", "resource_type_name",
            "provider", "provider_name", "name", "description",
            "ems_ref", "canonical_id", "vendor_identifiers", "vendor_type",
            "state", "power_state", "region", "availability_zone",
            "cloud_tenant", "flavor", "ems_created_on",
            "cpu_count", "memory_mb", "disk_gb",
            "ip_addresses", "fqdn", "mac_addresses",
            "os_type", "os_name", "boot_time",
            "properties", "provider_tags",
            "ansible_host", "ansible_connection", "inventory_group",
            "first_discovered_at", "last_seen_at", "seen_count",
            "deleted_at", "is_deleted", "organization", "tags",
            "is_automated", "automation_count", "last_automated_at",
        ]
        read_only_fields = fields


class ResourceRelationshipSerializer(serializers.ModelSerializer):
    source_name = serializers.StringRelatedField(source="source", read_only=True)
    target_name = serializers.StringRelatedField(source="target", read_only=True)

    class Meta:
        model = ResourceRelationship
        fields = [
            "id", "source", "source_name", "target", "target_name",
            "relationship_type", "properties",
        ]
        read_only_fields = fields


class ResourceSightingSerializer(serializers.ModelSerializer):
    resource_name = serializers.StringRelatedField(
        source="resource", read_only=True
    )

    class Meta:
        model = ResourceSighting
        fields = [
            "id", "resource", "resource_name", "collection_run",
            "seen_at", "state", "power_state",
            "cpu_count", "memory_mb", "disk_gb", "metrics",
        ]
        read_only_fields = fields
