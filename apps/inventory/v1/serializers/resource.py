from rest_framework import serializers

from apps.inventory.models import Resource, ResourceRelationship, ResourceSighting


class ResourceSerializer(serializers.ModelSerializer):
    resource_type_slug = serializers.SlugRelatedField(
        source="resource_type",
        slug_field="slug",
        read_only=True,
    )
    resource_type_name = serializers.StringRelatedField(
        source="resource_type",
        read_only=True,
    )
    provider_name = serializers.StringRelatedField(
        source="provider",
        read_only=True,
    )

    class Meta:
        model = Resource
        fields = [
            "id",
            "resource_type",
            "resource_type_slug",
            "resource_type_name",
            "provider",
            "provider_name",
            "name",
            "description",
            "ems_ref",
            "canonical_id",
            "vendor_identifiers",
            "vendor_type",
            "state",
            "power_state",
            "boot_time",
            "region",
            "availability_zone",
            "cloud_tenant",
            "flavor",
            "ems_created_on",
            "cpu_count",
            "memory_mb",
            "disk_gb",
            "ip_addresses",
            "fqdn",
            "mac_addresses",
            "os_type",
            "os_name",
            "properties",
            "provider_tags",
            "ansible_host",
            "ansible_connection",
            "inventory_group",
            "first_discovered_at",
            "last_seen_at",
            "seen_count",
            "organization",
        ]
        read_only_fields = fields


class ResourceRelationshipSerializer(serializers.ModelSerializer):
    source_name = serializers.StringRelatedField(source="source", read_only=True)
    target_name = serializers.StringRelatedField(source="target", read_only=True)

    class Meta:
        model = ResourceRelationship
        fields = [
            "id",
            "source",
            "source_name",
            "target",
            "target_name",
            "relationship_type",
            "properties",
        ]
        read_only_fields = fields


class ResourceSightingSerializer(serializers.ModelSerializer):
    resource_name = serializers.StringRelatedField(
        source="resource", read_only=True
    )

    class Meta:
        model = ResourceSighting
        fields = [
            "id",
            "resource",
            "resource_name",
            "collection_run",
            "seen_at",
            "state",
            "power_state",
            "boot_time",
            "cpu_count",
            "memory_mb",
            "disk_gb",
            "metrics",
        ]
        read_only_fields = fields
