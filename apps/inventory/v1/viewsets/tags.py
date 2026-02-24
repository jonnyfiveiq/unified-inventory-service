"""Tag viewset — list/create/destroy tags and manage resource tag assignments."""
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from django_filters import rest_framework as filters

from apps.inventory.models import Resource, Tag
from apps.inventory.v1.serializers.tags import TagSerializer


class TagFilter(filters.FilterSet):
    namespace = filters.CharFilter(lookup_expr="iexact")
    key = filters.CharFilter(lookup_expr="icontains")
    value = filters.CharFilter(lookup_expr="icontains")
    resource = filters.UUIDFilter(field_name="resources__id")

    class Meta:
        model = Tag
        fields = ["namespace", "key", "value"]


class TagViewSet(ListModelMixin, RetrieveModelMixin, CreateModelMixin, DestroyModelMixin, GenericViewSet):
    """
    CRUD for Tags + resource assignment actions.

    GET    /tags/                       — list all tags
    POST   /tags/                       — create a tag
    GET    /tags/{id}/                  — retrieve a tag
    DELETE /tags/{id}/                  — delete a tag (and all assignments)

    POST   /resources/{id}/tags/        — set tags on a resource (replaces all)
    POST   /resources/{id}/tags/add/    — add tags to a resource
    POST   /resources/{id}/tags/remove/ — remove tags from a resource
    GET    /resources/{id}/tags/        — list tags on a resource
    """
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = TagFilter

    def perform_create(self, serializer):
        # Default organization to 1 if not provided
        org_id = self.request.data.get("organization", 1)
        serializer.save(organization_id=org_id)


class ResourceTagViewSet(GenericViewSet):
    """Actions for managing tags on a specific resource."""
    permission_classes = [IsAuthenticated]
    serializer_class = TagSerializer

    def _get_resource(self, pk):
        try:
            return Resource.objects.get(pk=pk)
        except Resource.DoesNotExist:
            return None

    def list(self, request, resource_pk=None):
        """GET /resources/{id}/tags/ — list current tags."""
        resource = self._get_resource(resource_pk)
        if resource is None:
            return Response({"detail": "Resource not found."}, status=status.HTTP_404_NOT_FOUND)
        tags = resource.tags.all()
        return Response(TagSerializer(tags, many=True).data)

    @action(detail=False, methods=["post"], url_path="set")
    def set_tags(self, request, resource_pk=None):
        """POST /resources/{id}/tags/set/ — replace all tags on a resource.

        Body: [{"namespace": "type", "key": "category", "value": "Compute"}, ...]
        """
        resource = self._get_resource(resource_pk)
        if resource is None:
            return Response({"detail": "Resource not found."}, status=status.HTTP_404_NOT_FOUND)
        org_id = resource.organization_id
        tag_ids = []
        for tag_data in request.data:
            tag, _ = Tag.objects.get_or_create(
                organization_id=org_id,
                namespace=tag_data.get("namespace", "user"),
                key=tag_data.get("key", ""),
                value=tag_data.get("value", ""),
            )
            tag_ids.append(tag.pk)
        resource.tags.set(tag_ids)
        return Response(TagSerializer(resource.tags.all(), many=True).data)

    @action(detail=False, methods=["post"], url_path="add")
    def add_tags(self, request, resource_pk=None):
        """POST /resources/{id}/tags/add/ — add tags (no removal)."""
        resource = self._get_resource(resource_pk)
        if resource is None:
            return Response({"detail": "Resource not found."}, status=status.HTTP_404_NOT_FOUND)
        org_id = resource.organization_id
        for tag_data in request.data:
            tag, _ = Tag.objects.get_or_create(
                organization_id=org_id,
                namespace=tag_data.get("namespace", "user"),
                key=tag_data.get("key", ""),
                value=tag_data.get("value", ""),
            )
            resource.tags.add(tag)
        return Response(TagSerializer(resource.tags.all(), many=True).data)

    @action(detail=False, methods=["post"], url_path="remove")
    def remove_tags(self, request, resource_pk=None):
        """POST /resources/{id}/tags/remove/ — remove specific tags by id."""
        resource = self._get_resource(resource_pk)
        if resource is None:
            return Response({"detail": "Resource not found."}, status=status.HTTP_404_NOT_FOUND)
        tag_ids = request.data  # list of tag UUIDs
        resource.tags.remove(*Tag.objects.filter(pk__in=tag_ids))
        return Response(TagSerializer(resource.tags.all(), many=True).data)
