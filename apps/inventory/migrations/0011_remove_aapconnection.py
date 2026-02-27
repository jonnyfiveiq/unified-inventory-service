"""Remove AAPConnection model and simplify AutomationRecord.

Replaces the aap_connection FK with a source_name CharField.
Drops the inventory_aapconnection table entirely.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0010_automation_correlation"),
    ]

    operations = [
        # 1. Add source_name column to AutomationRecord
        migrations.AddField(
            model_name="automationrecord",
            name="source_name",
            field=models.CharField(
                blank=True, default="", max_length=512,
                help_text="Name of the AAP source that reported this automation.",
            ),
        ),
        # 2. Populate source_name from aap_connection.name before dropping FK
        migrations.RunSQL(
            sql="""
                UPDATE inventory_automationrecord ar
                SET source_name = ac.name
                FROM inventory_aapconnection ac
                WHERE ar.aap_connection_id = ac.id
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # 3. Make aap_host_id nullable (was required when syncing, now optional for webhooks)
        migrations.AlterField(
            model_name="automationrecord",
            name="aap_host_id",
            field=models.IntegerField(null=True, blank=True, help_text="Host ID in the AAP controller."),
        ),
        # 4. Drop the old unique_together that references aap_connection
        migrations.AlterUniqueTogether(
            name="automationrecord",
            unique_together=set(),
        ),
        # 5. Remove the aap_connection FK from AutomationRecord
        migrations.RemoveField(
            model_name="automationrecord",
            name="aap_connection",
        ),
        # 6. Set new unique_together using source_name
        migrations.AlterUniqueTogether(
            name="automationrecord",
            unique_together={("resource", "source_name", "aap_job_id")},
        ),
        # 7. Remove old indexes that referenced aap_connection
        migrations.AlterIndexTogether(
            name="automationrecord",
            index_together=set(),
        ),
        # 8. Drop the AAPConnection table
        migrations.DeleteModel(
            name="AAPConnection",
        ),
    ]
