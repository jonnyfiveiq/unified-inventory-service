from rest_framework import serializers
from apps.inventory.models import Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "namespace", "key", "value", "organization"]
        read_only_fields = ["id"]
