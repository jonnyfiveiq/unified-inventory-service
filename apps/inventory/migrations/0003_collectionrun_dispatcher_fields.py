"""Add dispatcher task tracking fields to CollectionRun."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0002_seed_taxonomy"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectionrun",
            name="task_uuid",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="UUID of the dispatcherd background task running this collection.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="collectionrun",
            name="canceled_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Timestamp when this run was canceled.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="collectionrun",
            name="result_traceback",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Python traceback if the task failed with an exception.",
            ),
        ),
        migrations.AlterField(
            model_name="collectionrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("completed", "Completed"),
                    ("partial", "Partial (some targets failed)"),
                    ("failed", "Failed"),
                    ("canceled", "Canceled"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddIndex(
            model_name="collectionrun",
            index=models.Index(fields=["task_uuid"], name="inventory_c_task_uu_idx"),
        ),
    ]
