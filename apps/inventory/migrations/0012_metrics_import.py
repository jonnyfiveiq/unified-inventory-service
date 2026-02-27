import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("inventory", "0011_remove_aapconnection"),
    ]

    operations = [
        # -- MetricsImport --
        migrations.CreateModel(
            name="MetricsImport",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("filename", models.CharField(help_text="Original filename of the uploaded tarball.", max_length=512)),
                ("source_label", models.CharField(blank=True, default="", help_text="User-provided label for the AAP instance.", max_length=512)),
                ("file_path", models.CharField(blank=True, default="", help_text="Server-side path where the tarball is stored for processing.", max_length=1024)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed")], db_index=True, default="pending", max_length=16)),
                ("stats", models.JSONField(blank=True, default=dict, help_text="Processing stats.")),
                ("error_log", models.TextField(blank=True, default="", help_text="Processing errors and warnings.")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="metrics_imports", to="core.organization")),
            ],
            options={
                "ordering": ["-uploaded_at"],
            },
        ),
        migrations.AddIndex(
            model_name="metricsimport",
            index=models.Index(fields=["status", "-uploaded_at"], name="inventory_me_status_idx"),
        ),
        # -- PendingMatch --
        migrations.CreateModel(
            name="PendingMatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("aap_host_name", models.CharField(help_text="The hostname from the metrics data.", max_length=1024)),
                ("match_reason", models.CharField(blank=True, default="", help_text="Why we think this might match.", max_length=256)),
                ("match_score", models.IntegerField(default=0, help_text="Confidence score 0-100.")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("ignored", "Ignored")], db_index=True, default="pending", max_length=16)),
                ("raw_data", models.JSONField(blank=True, default=dict, help_text="Aggregated job data from the CSV for this host.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("metrics_import", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pending_matches", to="inventory.metricsimport")),
                ("candidate_resource", models.ForeignKey(blank=True, help_text="Best-guess Resource match (if any).", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pending_match_candidates", to="inventory.resource")),
                ("resolved_resource", models.ForeignKey(blank=True, help_text="The Resource the admin selected (on approval).", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pending_match_resolved", to="inventory.resource")),
            ],
            options={
                "ordering": ["-match_score", "aap_host_name"],
            },
        ),
        migrations.AddIndex(
            model_name="pendingmatch",
            index=models.Index(fields=["metrics_import", "status"], name="inventory_pm_import_status_idx"),
        ),
        migrations.AddIndex(
            model_name="pendingmatch",
            index=models.Index(fields=["aap_host_name"], name="inventory_pm_hostname_idx"),
        ),
        # -- HostMapping --
        migrations.CreateModel(
            name="HostMapping",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("aap_host_name", models.CharField(db_index=True, help_text="The AAP hostname (as it appears in metrics-utility exports).", max_length=1024)),
                ("source_label", models.CharField(blank=True, default="", help_text="Scoped to a specific AAP source label (empty = global).", max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resource", models.ForeignKey(help_text="The inventory resource this host maps to.", on_delete=django.db.models.deletion.CASCADE, related_name="host_mappings", to="inventory.resource")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="host_mappings", to="core.organization")),
            ],
        ),
        migrations.AddConstraint(
            model_name="hostmapping",
            constraint=models.UniqueConstraint(fields=["aap_host_name", "source_label", "organization"], name="unique_host_mapping_per_org"),
        ),
        migrations.AddIndex(
            model_name="hostmapping",
            index=models.Index(fields=["aap_host_name", "source_label"], name="inventory_hm_host_source_idx"),
        ),
    ]
