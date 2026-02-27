"""Watchlist model — curated (static) or query-driven (dynamic) resource lists.

Static watchlists hold an explicit M2M set of resources, managed by the user.
Dynamic watchlists store a filter query and resolve their membership on read.

This module implements static watchlists fully. Dynamic watchlists are
designed-in via the ``watchlist_type`` and ``filter_query`` fields but
their query evaluation is deferred to a follow-up feature.
"""

import uuid

from django.db import models


class WatchlistType(models.TextChoices):
    STATIC = "static", "Static"
    DYNAMIC = "dynamic", "Dynamic"


class Watchlist(models.Model):
    """A named list of inventory resources, similar to a playlist.

    Static watchlists have an explicit M2M membership managed by the user.
    Dynamic watchlists (future) store a filter_query that is evaluated at
    query time to produce the resource set on demand.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    watchlist_type = models.CharField(
        max_length=16,
        choices=WatchlistType.choices,
        default=WatchlistType.STATIC,
        db_index=True,
        help_text="Static: explicit resource membership. Dynamic: filter_query evaluated on read.",
    )
    filter_query = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "For dynamic watchlists: a JSON object describing the filter criteria "
            "applied at query time. Ignored for static watchlists. "
            "Schema TBD — will support field filters, tag matches, and search terms."
        ),
    )

    # Explicit membership for static watchlists
    resources = models.ManyToManyField(
        "inventory.Resource",
        related_name="watchlists",
        blank=True,
    )

    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="watchlists",
    )
    created_by = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Username of the creator (informational).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    @property
    def resource_count(self):
        """Return the number of resources in this watchlist.

        For static watchlists this is the M2M count.
        For dynamic watchlists this will eventually evaluate the filter_query.
        """
        if self.watchlist_type == WatchlistType.DYNAMIC:
            # TODO: evaluate filter_query against Resource queryset
            return 0
        return self.resources.count()
