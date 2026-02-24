"""Custom filter backends for UUID-primary-key models.

The upstream ``ansible_base.rest_filters`` ``FieldLookupBackend`` assumes
integer PKs (its ``to_python_related`` calls ``int(value)``).  We override
that single method so UUID strings are handled correctly.
"""
import uuid as _uuid

from django.utils.encoding import force_str

from ansible_base.rest_filters.rest_framework.field_lookup_backend import (
    FieldLookupBackend,
)


class UUIDFieldLookupBackend(FieldLookupBackend):
    """FieldLookupBackend that accepts UUID values for related-field filters."""

    def to_python_related(self, value):
        value = force_str(value)
        if value.lower() in ('none', 'null'):
            return None
        try:
            return _uuid.UUID(value)
        except (ValueError, AttributeError):
            return super().to_python_related(value)
