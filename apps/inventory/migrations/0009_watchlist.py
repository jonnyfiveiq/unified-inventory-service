import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("inventory", "0008_add_collection_schedule"),
    ]

    operations = [
        migrations.CreateModel(
            name="Watchlist",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("watchlist_type", models.CharField(
                    choices=[("static", "Static"), ("dynamic", "Dynamic")],
                    db_index=True, default="static", max_length=16,
                    help_text="Static: explicit resource membership. Dynamic: filter_query evaluated on read.",
                )),
                ("filter_query", models.JSONField(
                    blank=True, default=dict,
                    help_text=(
                        "For dynamic watchlists: a JSON object describing the filter criteria "
                        "applied at query time. Ignored for static watchlists. "
                        "Schema TBD — will support field filters, tag matches, and search terms."
                    ),
                )),
                ("created_by", models.CharField(blank=True, default="", max_length=255, help_text="Username of the creator (informational).")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="watchlists",
                    to="core.organization",
                )),
                ("resources", models.ManyToManyField(
                    blank=True,
                    related_name="watchlists",
                    to="inventory.resource",
                )),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
    ]
