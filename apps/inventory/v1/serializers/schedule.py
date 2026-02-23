"""Serializer for CollectionSchedule."""
from rest_framework import serializers
from apps.inventory.models.schedule import CollectionSchedule


class CollectionScheduleSerializer(serializers.ModelSerializer):
    next_run_at = serializers.DateTimeField(read_only=True)
    last_run_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = CollectionSchedule
        fields = [
            "id", "provider", "name", "cron_expression",
            "enabled", "last_run_at", "next_run_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "provider", "last_run_at", "next_run_at", "created_at", "updated_at"]

    def validate_cron_expression(self, value):
        try:
            from croniter import croniter
            if not croniter.is_valid(value):
                raise serializers.ValidationError(f"'{value}' is not a valid cron expression.")
        except ImportError:
            pass
        return value

    def create(self, validated_data):
        schedule = super().create(validated_data)
        schedule.update_next_run()
        return schedule

    def update(self, instance, validated_data):
        schedule = super().update(instance, validated_data)
        if "cron_expression" in validated_data or "enabled" in validated_data:
            schedule.update_next_run()
        return schedule
