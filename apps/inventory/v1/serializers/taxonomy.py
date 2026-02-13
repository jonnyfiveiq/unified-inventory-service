from rest_framework import serializers

from apps.inventory.models import ResourceCategory, ResourceType, VendorTypeMapping


class ResourceCategorySerializer(serializers.ModelSerializer):
    resource_type_count = serializers.SerializerMethodField()

    class Meta:
        model = ResourceCategory
        fields = ["id", "slug", "name", "description", "sort_order", "resource_type_count"]
        read_only_fields = fields

    def get_resource_type_count(self, obj) -> int:
        return obj.resource_types.count()


class ResourceTypeSerializer(serializers.ModelSerializer):
    category_slug = serializers.SlugRelatedField(
        source="category",
        slug_field="slug",
        read_only=True,
    )
    category_name = serializers.StringRelatedField(
        source="category",
        read_only=True,
    )

    class Meta:
        model = ResourceType
        fields = [
            "id",
            "category",
            "category_slug",
            "category_name",
            "slug",
            "name",
            "description",
            "is_countable",
            "long_term_strategic_value",
            "short_term_opportunity",
            "sort_order",
        ]
        read_only_fields = fields


class VendorTypeMappingSerializer(serializers.ModelSerializer):
    resource_type_slug = serializers.SlugRelatedField(
        source="resource_type",
        slug_field="slug",
        read_only=True,
    )

    class Meta:
        model = VendorTypeMapping
        fields = [
            "id",
            "vendor",
            "vendor_resource_type",
            "resource_type",
            "resource_type_slug",
            "ansible_collection",
            "ansible_module",
            "query_file_ref",
        ]
        read_only_fields = fields
