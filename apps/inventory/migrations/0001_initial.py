"""
Initial schema migration for the inventory service.

Creates all inventory tables implementing the ManageIQ-inspired normalized
resource taxonomy for Ansible Automation Platform.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _create_gin_indexes(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('CREATE INDEX IF NOT EXISTS "idx_resource_properties_gin" ON "inventory_resource" USING gin ("properties" jsonb_path_ops);')
        schema_editor.execute('CREATE INDEX IF NOT EXISTS "idx_resource_provider_tags_gin" ON "inventory_resource" USING gin ("provider_tags" jsonb_path_ops);')

def _drop_gin_indexes(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('DROP INDEX IF EXISTS "idx_resource_properties_gin";')
        schema_editor.execute('DROP INDEX IF EXISTS "idx_resource_provider_tags_gin";')


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ─── Taxonomy Reference Tables ──────────────────────────────────

        migrations.CreateModel(
            name="ResourceCategory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("slug", models.SlugField(help_text="Machine-readable key (e.g. 'compute', 'networking').", max_length=64, unique=True)),
                ("name", models.CharField(help_text="Human-readable name (e.g. 'Compute', 'Networking').", max_length=128)),
                ("description", models.TextField(blank=True, default="")),
                ("sort_order", models.IntegerField(default=0)),
            ],
            options={
                "ordering": ["sort_order", "name"],
                "verbose_name_plural": "resource categories",
            },
        ),

        migrations.CreateModel(
            name="ResourceType",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("slug", models.SlugField(help_text="Machine-readable key (e.g. 'virtual_machine', 'switch').", max_length=96, unique=True)),
                ("name", models.CharField(help_text="Human-readable name (e.g. 'Virtual Machine', 'Switch').", max_length=256)),
                ("description", models.TextField(blank=True, default="")),
                ("is_countable", models.BooleanField(default=True, help_text="Whether resources of this type should be counted for billing/licensing.")),
                ("long_term_strategic_value", models.IntegerField(blank=True, help_text="LTSV score (1-5) from the normalized taxonomy.", null=True)),
                ("short_term_opportunity", models.IntegerField(blank=True, help_text="STO / metrics-utility fit score (1-5).", null=True)),
                ("sort_order", models.IntegerField(default=0)),
                ("category", models.ForeignKey(help_text="The device category this type belongs to.", on_delete=django.db.models.deletion.CASCADE, related_name="resource_types", to="inventory.resourcecategory")),
            ],
            options={
                "ordering": ["category", "sort_order", "name"],
            },
        ),

        migrations.CreateModel(
            name="VendorTypeMapping",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("vendor", models.CharField(db_index=True, help_text="Vendor slug matching Provider.vendor.", max_length=64)),
                ("vendor_resource_type", models.CharField(help_text="The vendor's native name for this resource type.", max_length=256)),
                ("ansible_collection", models.CharField(blank=True, default="", help_text="Ansible collection (e.g. 'amazon.aws', 'cisco.nxos').", max_length=256)),
                ("ansible_module", models.CharField(blank=True, default="", help_text="Primary Ansible module for this resource type.", max_length=256)),
                ("query_file_ref", models.CharField(blank=True, default="", help_text="Reference to the query file used in indirect node counting.", max_length=512)),
                ("resource_type", models.ForeignKey(help_text="The normalized resource type this maps to.", on_delete=django.db.models.deletion.CASCADE, related_name="vendor_mappings", to="inventory.resourcetype")),
            ],
            options={
                "ordering": ["vendor", "vendor_resource_type"],
                "unique_together": {("vendor", "vendor_resource_type")},
            },
        ),

        # ─── Provider ──────────────────────────────────────────────────

        migrations.CreateModel(
            name="Provider",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="Display name for this provider.", max_length=512)),
                ("infrastructure", models.CharField(choices=[("public_cloud", "Public Cloud"), ("private_cloud", "Private Cloud"), ("networking", "Networking"), ("storage", "Storage")], help_text="Top-level infrastructure classification.", max_length=32)),
                ("vendor", models.CharField(db_index=True, help_text="Vendor slug matching the Ansible collection namespace.", max_length=64)),
                ("provider_type", models.CharField(blank=True, default="", help_text="Specific manager type within the vendor.", max_length=64)),
                ("endpoint", models.CharField(blank=True, default="", help_text="Connection URL or hostname for this provider.", max_length=1024)),
                ("credential_ref", models.CharField(blank=True, default="", help_text="External credential reference.", max_length=512)),
                ("enabled", models.BooleanField(default=True, help_text="Whether inventory collection is active.")),
                ("connection_config", models.JSONField(blank=True, default=dict, help_text="Vendor-specific connection parameters.")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                ("last_refresh_at", models.DateTimeField(blank=True, help_text="Timestamp of the last successful inventory collection.", null=True)),
                ("organization", models.ForeignKey(help_text="Organization that owns this provider.", on_delete=django.db.models.deletion.CASCADE, related_name="providers", to="core.organization")),
                ("created_by", models.ForeignKey(default=None, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(default=None, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("organization", "name")},
            },
        ),
        migrations.AddIndex(
            model_name="provider",
            index=models.Index(fields=["vendor"], name="inventory_p_vendor_idx"),
        ),
        migrations.AddIndex(
            model_name="provider",
            index=models.Index(fields=["infrastructure", "vendor"], name="inventory_p_infra_vendor_idx"),
        ),

        # ─── Collection Run ────────────────────────────────────────────

        migrations.CreateModel(
            name="CollectionRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("collection_type", models.CharField(choices=[("full", "Full Refresh"), ("targeted", "Targeted Refresh"), ("event_driven", "Event-Driven Update")], default="full", max_length=16)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("completed", "Completed"), ("partial", "Partial (some targets failed)"), ("failed", "Failed")], default="pending", max_length=16)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("resources_found", models.IntegerField(default=0)),
                ("resources_created", models.IntegerField(default=0)),
                ("resources_updated", models.IntegerField(default=0)),
                ("resources_removed", models.IntegerField(default=0)),
                ("resources_unchanged", models.IntegerField(default=0)),
                ("error_message", models.TextField(blank=True, default="")),
                ("error_details", models.JSONField(blank=True, default=dict)),
                ("target_resource_types", models.JSONField(blank=True, default=list, help_text="List of resource_type slugs targeted.")),
                ("collector_version", models.CharField(blank=True, default="", max_length=64)),
                ("ansible_collection", models.CharField(blank=True, default="", max_length=256)),
                ("job_id", models.CharField(blank=True, default="", max_length=256)),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="collection_runs", to="inventory.provider")),
            ],
            options={
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="collectionrun",
            index=models.Index(fields=["provider", "-started_at"], name="inventory_cr_provider_time_idx"),
        ),
        migrations.AddIndex(
            model_name="collectionrun",
            index=models.Index(fields=["status"], name="inventory_cr_status_idx"),
        ),

        # ─── Resource (the main normalized inventory table) ────────────

        migrations.CreateModel(
            name="Resource",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="Display name of the resource.", max_length=1024)),
                ("ems_ref", models.CharField(db_index=True, help_text="Provider-native unique reference.", max_length=1024)),
                ("vendor_type", models.CharField(blank=True, default="", help_text="The vendor's native type name (pre-normalization).", max_length=256)),
                ("state", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive"), ("stopped", "Stopped"), ("running", "Running"), ("suspended", "Suspended"), ("terminated", "Terminated"), ("error", "Error"), ("unknown", "Unknown"), ("provisioning", "Provisioning"), ("decommissioned", "Decommissioned")], db_index=True, default="unknown", max_length=32)),
                ("power_state", models.CharField(blank=True, default="", max_length=32)),
                ("region", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("availability_zone", models.CharField(blank=True, default="", max_length=128)),
                # Compute attributes
                ("cpu_count", models.IntegerField(blank=True, help_text="Number of vCPUs / cores.", null=True)),
                ("memory_mb", models.IntegerField(blank=True, help_text="Memory in MB.", null=True)),
                ("disk_gb", models.IntegerField(blank=True, help_text="Total disk/storage in GB.", null=True)),
                # Network attributes
                ("ip_addresses", models.JSONField(blank=True, default=list)),
                ("fqdn", models.CharField(blank=True, default="", max_length=1024)),
                ("mac_addresses", models.JSONField(blank=True, default=list)),
                # OS / Platform
                ("os_type", models.CharField(blank=True, default="", max_length=64)),
                ("os_name", models.CharField(blank=True, default="", max_length=256)),
                # Flexible properties (Level 3)
                ("properties", models.JSONField(blank=True, default=dict, help_text="Type-specific and vendor-specific attributes (JSONB).")),
                ("provider_tags", models.JSONField(blank=True, default=dict, help_text="Tags/labels from the provider.")),
                # Ansible metadata
                ("ansible_host", models.CharField(blank=True, default="", max_length=1024)),
                ("ansible_connection", models.CharField(blank=True, default="", max_length=64)),
                ("inventory_group", models.CharField(blank=True, default="", max_length=512)),
                ("last_job_id", models.CharField(blank=True, default="", max_length=256)),
                # Timestamps
                ("first_discovered_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                # Foreign keys
                ("resource_type", models.ForeignKey(help_text="Normalized resource type.", on_delete=django.db.models.deletion.PROTECT, related_name="resources", to="inventory.resourcetype")),
                ("provider", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resources", to="inventory.provider")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resources", to="core.organization")),
                ("collection_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resources", to="inventory.collectionrun")),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("provider", "ems_ref")},
            },
        ),
        migrations.AddIndex(
            model_name="resource",
            index=models.Index(fields=["resource_type", "state"], name="inventory_r_type_state_idx"),
        ),
        migrations.AddIndex(
            model_name="resource",
            index=models.Index(fields=["provider", "resource_type"], name="inventory_r_provider_type_idx"),
        ),
        migrations.AddIndex(
            model_name="resource",
            index=models.Index(fields=["organization", "resource_type"], name="inventory_r_org_type_idx"),
        ),
        migrations.AddIndex(
            model_name="resource",
            index=models.Index(fields=["region"], name="inventory_r_region_idx"),
        ),
        migrations.AddIndex(
            model_name="resource",
            index=models.Index(fields=["vendor_type"], name="inventory_r_vendor_type_idx"),
        ),
        migrations.AddIndex(
            model_name="resource",
            index=models.Index(fields=["last_seen_at"], name="inventory_r_last_seen_idx"),
        ),
        # GIN indexes for JSONB — PostgreSQL only, skipped on SQLite
        migrations.RunPython(
            code=_create_gin_indexes,
            reverse_code=_drop_gin_indexes,
        ),

        # ─── Resource Relationship ─────────────────────────────────────

        migrations.CreateModel(
            name="ResourceRelationship",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("relationship_type", models.CharField(choices=[("runs_on", "Runs On"), ("part_of", "Part Of"), ("member_of", "Member Of"), ("attached_to", "Attached To"), ("connected_to", "Connected To"), ("managed_by", "Managed By"), ("contains", "Contains"), ("depends_on", "Depends On"), ("load_balances", "Load Balances"), ("routes_to", "Routes To"), ("backs_up", "Backs Up"), ("replicates_to", "Replicates To")], db_index=True, max_length=32)),
                ("properties", models.JSONField(blank=True, default=dict)),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="outgoing_relationships", to="inventory.resource")),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incoming_relationships", to="inventory.resource")),
            ],
            options={
                "unique_together": {("source", "target", "relationship_type")},
            },
        ),
        migrations.AddIndex(
            model_name="resourcerelationship",
            index=models.Index(fields=["source", "relationship_type"], name="inventory_rr_source_type_idx"),
        ),
        migrations.AddIndex(
            model_name="resourcerelationship",
            index=models.Index(fields=["target", "relationship_type"], name="inventory_rr_target_type_idx"),
        ),

        # ─── Tag ───────────────────────────────────────────────────────

        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("namespace", models.CharField(db_index=True, max_length=128)),
                ("key", models.CharField(max_length=256)),
                ("value", models.CharField(blank=True, default="", max_length=1024)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tags", to="core.organization")),
                ("resources", models.ManyToManyField(blank=True, related_name="tags", to="inventory.resource")),
            ],
            options={
                "ordering": ["namespace", "key", "value"],
                "unique_together": {("organization", "namespace", "key", "value")},
            },
        ),

        # ─── Resource Metric ──────────────────────────────────────────

        migrations.CreateModel(
            name="ResourceMetric",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("timestamp", models.DateTimeField(db_index=True)),
                ("metric_type", models.CharField(db_index=True, max_length=64)),
                ("value_float", models.FloatField(blank=True, null=True)),
                ("value_int", models.BigIntegerField(blank=True, null=True)),
                ("unit", models.CharField(blank=True, default="", max_length=32)),
                ("dimensions", models.JSONField(blank=True, default=dict)),
                ("resource", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="metrics", to="inventory.resource")),
            ],
            options={
                "ordering": ["-timestamp"],
            },
        ),
        migrations.AddIndex(
            model_name="resourcemetric",
            index=models.Index(fields=["resource", "metric_type", "-timestamp"], name="inventory_rm_res_type_time_idx"),
        ),
        migrations.AddIndex(
            model_name="resourcemetric",
            index=models.Index(fields=["metric_type", "-timestamp"], name="inventory_rm_type_time_idx"),
        ),
    ]
