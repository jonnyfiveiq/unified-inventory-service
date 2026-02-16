"""Add new Resource fields and PropertyDefinition model.

New Resource fields (from ManageIQ gap analysis):
  - description: TextField for resource notes
  - boot_time: DateTimeField for uptime calculations
  - cloud_tenant: CharField for Azure/OpenStack/GCP tenant/project/subscription
  - flavor: CharField for cloud instance type (m5.xlarge, Standard_D4s_v3, etc.)
  - ems_created_on: DateTimeField for provider-side creation timestamp

New model:
  - PropertyDefinition: defines the expected JSONB keys in Resource.properties
    per ResourceType, solving the consistency problem for collector authors.
"""
import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0004_resource_identity_tracking"),
    ]

    operations = [
        # === New Resource fields ===
        migrations.AddField(
            model_name="resource",
            name="description",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Description or notes for this resource.",
            ),
        ),
        migrations.AddField(
            model_name="resource",
            name="boot_time",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "Last boot/start time for compute resources. "
                    "Used for uptime calculations."
                ),
            ),
        ),
        migrations.AddField(
            model_name="resource",
            name="cloud_tenant",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=256,
                help_text=(
                    "Cloud tenant/project/subscription ID. "
                    "Azure subscription, OpenStack project, GCP project ID."
                ),
            ),
        ),
        migrations.AddField(
            model_name="resource",
            name="flavor",
            field=models.CharField(
                blank=True,
                default="",
                max_length=256,
                help_text=(
                    "Cloud instance type or flavor (e.g. 'm5.xlarge', "
                    "'Standard_D4s_v3', 'm1.large'). First-class field because "
                    "flavor drives cost analysis, capacity planning and right-sizing."
                ),
            ),
        ),
        migrations.AddField(
            model_name="resource",
            name="ems_created_on",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    "When the provider created this resource (not when we "
                    "first discovered it). Important for age-based lifecycle policies."
                ),
            ),
        ),
        # === PropertyDefinition model ===
        migrations.CreateModel(
            name="PropertyDefinition",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.CharField(help_text="The JSONB key name that collectors should use in Resource.properties.", max_length=128)),
                ("name", models.CharField(help_text="Human-readable name.", max_length=256)),
                ("description", models.TextField(blank=True, default="", help_text="What this property represents.")),
                ("value_type", models.CharField(choices=[("string", "String"), ("integer", "Integer"), ("float", "Float"), ("boolean", "Boolean"), ("datetime", "DateTime (ISO 8601)"), ("json", "JSON object/array")], default="string", max_length=16)),
                ("required", models.BooleanField(default=False, help_text="Whether collectors MUST populate this property.")),
                ("example_value", models.CharField(blank=True, default="", max_length=512)),
                ("vendor_scope", models.CharField(blank=True, default="", help_text="Vendor-specific scope (empty = all vendors).", max_length=64)),
                ("resource_type", models.ForeignKey(help_text="The resource type this property applies to.", on_delete=django.db.models.deletion.CASCADE, related_name="property_definitions", to="inventory.resourcetype")),
            ],
            options={
                "ordering": ["resource_type", "key"],
                "unique_together": {("resource_type", "key")},
                "verbose_name_plural": "property definitions",
            },
        ),
    ]
