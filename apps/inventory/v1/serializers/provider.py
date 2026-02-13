from rest_framework import serializers

from apps.inventory.models import CollectionRun, Provider


class ProviderSerializer(serializers.ModelSerializer):
    last_collection_status = serializers.SerializerMethodField(
        help_text="Status of the most recent collection run.",
    )

    class Meta:
        model = Provider
        fields = [
            "id",
            "name",
            "infrastructure",
            "vendor",
            "provider_type",
            "endpoint",
            "credential_ref",
            "enabled",
            "connection_config",
            "organization",
            "created",
            "modified",
            "last_refresh_at",
            "last_collection_status",
        ]
        read_only_fields = ["id", "created", "modified", "last_refresh_at", "last_collection_status"]

    def get_last_collection_status(self, obj) -> str | None:
        latest = obj.collection_runs.order_by("-started_at").values("status").first()
        return latest["status"] if latest else None


class ProviderCollectSerializer(serializers.Serializer):
    """Input serializer for the collect action."""

    collection_type = serializers.ChoiceField(
        choices=CollectionRun.CollectionType.choices,
        default=CollectionRun.CollectionType.FULL,
        help_text="Type of collection to perform.",
    )
    target_resource_types = serializers.ListField(
        child=serializers.CharField(max_length=96),
        required=False,
        default=list,
        help_text="List of resource_type slugs to collect. Empty for full refresh.",
    )
