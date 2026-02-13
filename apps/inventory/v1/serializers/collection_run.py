from rest_framework import serializers

from apps.inventory.models import CollectionRun


class CollectionRunSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.SerializerMethodField(
        help_text="Elapsed seconds from start to completion (null if still running).",
    )

    class Meta:
        model = CollectionRun
        fields = [
            "id",
            "provider",
            "collection_type",
            "status",
            "started_at",
            "completed_at",
            "canceled_at",
            "task_uuid",
            "resources_found",
            "resources_created",
            "resources_updated",
            "resources_removed",
            "resources_unchanged",
            "error_message",
            "result_traceback",
            "target_resource_types",
            "collector_version",
            "ansible_collection",
            "job_id",
            "duration_seconds",
        ]
        read_only_fields = fields  # collection runs are created via the collect action, not directly

    def get_duration_seconds(self, obj) -> float | None:
        if obj.completed_at and obj.started_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None


class CollectionRunCancelSerializer(serializers.Serializer):
    """Empty serializer for the cancel action (POST body is optional)."""

    pass
