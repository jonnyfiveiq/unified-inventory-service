from rest_framework import serializers

from apps.inventory.models import Watchlist


class WatchlistSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    resource_count = serializers.IntegerField(read_only=True, source='resource_count_annotation', default=None)

    class Meta:
        model = Watchlist
        fields = [
            "id", "name", "description",
            "watchlist_type", "filter_query",
            "organization", "created_by",
            "created_at", "updated_at",
            "resource_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "resource_count"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # If the annotation wasn't present (e.g. detail view), fall back to property
        if data.get('resource_count') is None:
            data['resource_count'] = instance.resource_count
        return data


class WatchlistResourcesSerializer(serializers.Serializer):
    """Accepts a list of resource IDs for add/remove operations."""
    resource_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of resource UUIDs to add or remove.",
    )
