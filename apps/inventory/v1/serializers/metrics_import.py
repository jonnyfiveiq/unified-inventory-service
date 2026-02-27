"""Serializers for Metrics Import, PendingMatch, and HostMapping."""
from rest_framework import serializers

from apps.inventory.models.metrics_import import (
    HostMapping,
    MetricsImport,
    PendingMatch,
)


class MetricsImportSerializer(serializers.ModelSerializer):
    """Read serializer for MetricsImport."""

    pending_count = serializers.SerializerMethodField()
    matched_count = serializers.SerializerMethodField()

    class Meta:
        model = MetricsImport
        fields = [
            'id', 'filename', 'source_label', 'status',
            'stats', 'error_log',
            'uploaded_at', 'processed_at', 'organization',
            'pending_count', 'matched_count',
        ]
        read_only_fields = fields

    def get_pending_count(self, obj):
        return obj.pending_matches.filter(status=PendingMatch.Status.PENDING).count()

    def get_matched_count(self, obj):
        return obj.pending_matches.filter(status=PendingMatch.Status.APPROVED).count()


class MetricsImportUploadSerializer(serializers.Serializer):
    """Validates the upload payload."""

    file = serializers.FileField(
        help_text='The metrics-utility tarball (.tar.gz or .tgz).',
    )
    source_label = serializers.CharField(
        max_length=512,
        required=False,
        default='',
        help_text='Label for the AAP instance this data came from.',
    )


class PendingMatchSerializer(serializers.ModelSerializer):
    """Read serializer for PendingMatch."""

    candidate_resource_name = serializers.CharField(
        source='candidate_resource.name', read_only=True, default=''
    )
    candidate_resource_type = serializers.CharField(
        source='candidate_resource.resource_type.name', read_only=True, default=''
    )
    resolved_resource_name = serializers.CharField(
        source='resolved_resource.name', read_only=True, default=''
    )

    class Meta:
        model = PendingMatch
        fields = [
            'id', 'metrics_import', 'aap_host_name',
            'candidate_resource', 'candidate_resource_name', 'candidate_resource_type',
            'match_reason', 'match_score', 'status',
            'resolved_resource', 'resolved_resource_name',
            'raw_data', 'created_at', 'resolved_at',
        ]
        read_only_fields = [
            'id', 'metrics_import', 'aap_host_name',
            'candidate_resource', 'candidate_resource_name', 'candidate_resource_type',
            'match_reason', 'match_score',
            'raw_data', 'created_at',
        ]


class PendingMatchResolveSerializer(serializers.Serializer):
    """Payload for approving/rejecting a PendingMatch."""

    action = serializers.ChoiceField(
        choices=['approve', 'reject', 'ignore'],
    )
    resource_id = serializers.UUIDField(
        required=False,
        help_text='Override: pick a different Resource (for approve only).',
    )


class HostMappingSerializer(serializers.ModelSerializer):
    """Read serializer for HostMapping (learned mappings)."""

    resource_name = serializers.CharField(source='resource.name', read_only=True)

    class Meta:
        model = HostMapping
        fields = [
            'id', 'aap_host_name', 'source_label',
            'resource', 'resource_name',
            'created_at', 'organization',
        ]
        read_only_fields = ['id', 'created_at']
