"""Add cross-provider asset identity, sighting tracking, and ResourceSighting model.

- Resource.canonical_id: Stable cross-provider fingerprint (SMBIOS UUID, etc.)
- Resource.vendor_identifiers: All vendor-specific IDs as JSONB
- Resource.seen_count: Number of collection runs observing this resource
- ResourceSighting: Point-in-time observation record for historical graphing
"""

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0003_collectionrun_dispatcher_fields"),
    ]

    operations = [
        # === Resource identity fields ===
        migrations.AddField(
            model_name="resource",
            name="canonical_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "Stable cross-provider asset fingerprint. For compute resources "
                    "this is typically the SMBIOS UUID, which persists across provider "
                    "boundaries (e.g. the same physical machine seen via VMware and via "
                    "bare-metal IPMI). For cloud resources, use the most stable vendor "
                    "identifier (e.g. EC2 instance-id). Collectors are responsible for "
                    "determining the best canonical_id for each resource type."
                ),
                max_length=1024,
            ),
        ),
        migrations.AddField(
            model_name="resource",
            name="vendor_identifiers",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "All vendor-specific identifiers as key-value pairs. "
                    "Examples: {'moid': 'vm-1001', 'instance_uuid': '502e71fa-...', "
                    "'bios_uuid': '4202e71f-...'} for VMware; {'instance_id': 'i-0abc', "
                    "'smbios_uuid': 'ec2abcde-...'} for AWS EC2."
                ),
            ),
        ),
        migrations.AddField(
            model_name="resource",
            name="seen_count",
            field=models.PositiveIntegerField(
                default=1,
                help_text=(
                    "Number of collection runs that have observed this resource. "
                    "Incremented by the collector on each run where the resource is found."
                ),
            ),
        ),
        # === Indexes for new fields ===
        migrations.AddIndex(
            model_name="resource",
            index=models.Index(fields=["canonical_id"], name="inventory_r_canonic_idx"),
        ),
        migrations.AddIndex(
            model_name="resource",
            index=models.Index(fields=["seen_count"], name="inventory_r_seen_co_idx"),
        ),
        # === ResourceSighting model ===
        migrations.CreateModel(
            name="ResourceSighting",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("seen_at", models.DateTimeField(auto_now_add=True, db_index=True, help_text="Timestamp of the observation.")),
                ("state", models.CharField(
                    choices=[
                        ("active", "Active"), ("inactive", "Inactive"),
                        ("stopped", "Stopped"), ("running", "Running"),
                        ("suspended", "Suspended"), ("terminated", "Terminated"),
                        ("error", "Error"), ("unknown", "Unknown"),
                        ("provisioning", "Provisioning"), ("decommissioned", "Decommissioned"),
                    ],
                    help_text="Resource state at time of observation.",
                    max_length=32,
                )),
                ("power_state", models.CharField(blank=True, default="", help_text="Power state at time of observation.", max_length=32)),
                ("cpu_count", models.IntegerField(blank=True, help_text="vCPU count at time of observation.", null=True)),
                ("memory_mb", models.IntegerField(blank=True, help_text="Memory in MB at time of observation.", null=True)),
                ("disk_gb", models.IntegerField(blank=True, help_text="Disk in GB at time of observation.", null=True)),
                ("metrics", models.JSONField(
                    blank=True, default=dict,
                    help_text="Type-specific metrics snapshot at time of observation. Examples: cpu_usage_pct, memory_usage_pct, disk_usage_pct, network_throughput_mbps, iops, power_consumption_watts.",
                )),
                ("collection_run", models.ForeignKey(
                    help_text="The collection run during which this resource was observed.",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sightings",
                    to="inventory.collectionrun",
                )),
                ("resource", models.ForeignKey(
                    help_text="The resource that was observed.",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sightings",
                    to="inventory.resource",
                )),
            ],
            options={
                "ordering": ["-seen_at"],
                "unique_together": {("resource", "collection_run")},
            },
        ),
        migrations.AddIndex(
            model_name="resourcesighting",
            index=models.Index(fields=["resource", "-seen_at"], name="inventory_r_resourc_seen_idx"),
        ),
        migrations.AddIndex(
            model_name="resourcesighting",
            index=models.Index(fields=["collection_run"], name="inventory_r_collect_run_idx"),
        ),
        migrations.AddIndex(
            model_name="resourcesighting",
            index=models.Index(fields=["state"], name="inventory_r_sighting_state_idx"),
        ),
    ]
