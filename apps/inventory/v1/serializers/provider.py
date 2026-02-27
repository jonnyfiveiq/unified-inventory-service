from rest_framework import serializers

from apps.inventory.models import CollectionRun, Provider


class ProviderSerializer(serializers.ModelSerializer):
    last_collection_status = serializers.SerializerMethodField(
        help_text="Status of the most recent collection run.",
    )
    schedule_count = serializers.SerializerMethodField(
        help_text="Number of active schedules on this provider.",
    )
    resource_count = serializers.IntegerField(
        read_only=True,
        default=0,
        help_text="Number of resources discovered by this provider.",
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
            "schedule_count",
            "resource_count",
        ]
        read_only_fields = ["id", "created", "modified", "last_refresh_at", "last_collection_status", "schedule_count", "resource_count"]

    def get_last_collection_status(self, obj) -> str | None:
        latest = obj.collection_runs.order_by("-started_at").values("status").first()
        return latest["status"] if latest else None

    def get_schedule_count(self, obj) -> int:
        return obj.schedules.filter(enabled=True).count()


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
