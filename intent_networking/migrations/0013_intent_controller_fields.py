"""Add controller_type, controller_site, controller_org fields to Intent."""

from django.db import migrations, models


def backfill_controller_defaults(apps, schema_editor):
    """Set default values for new controller fields on existing rows."""
    Intent = apps.get_model("intent_networking", "Intent")
    Intent.objects.filter(controller_type__isnull=True).update(controller_type="nornir")
    Intent.objects.filter(controller_site__isnull=True).update(controller_site="")
    Intent.objects.filter(controller_org__isnull=True).update(controller_org="")


class Migration(migrations.Migration):
    """Add controller routing fields to Intent model."""

    dependencies = [
        ("intent_networking", "0012_intent_dependencies"),
    ]

    # Each step (add nullable → backfill → alter non-null) must run in its own
    # transaction so PostgreSQL doesn't reject the ALTER with
    # "pending trigger events".
    atomic = False

    operations = [
        # Step 1: Add fields as nullable (no table lock for default backfill)
        migrations.AddField(
            model_name="intent",
            name="controller_type",
            field=models.CharField(
                choices=[
                    ("nornir", "Nornir (SSH/NETCONF)"),
                    ("catalyst_center", "Catalyst Center"),
                    ("meraki", "Meraki"),
                    ("mist", "Mist AI"),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="intent",
            name="controller_site",
            field=models.CharField(
                max_length=200,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="intent",
            name="controller_org",
            field=models.CharField(
                max_length=200,
                null=True,
            ),
        ),
        # Step 2: Backfill defaults on existing rows
        migrations.RunPython(backfill_controller_defaults, migrations.RunPython.noop),
        # Step 3: Alter to non-nullable with defaults
        migrations.AlterField(
            model_name="intent",
            name="controller_type",
            field=models.CharField(
                choices=[
                    ("nornir", "Nornir (SSH/NETCONF)"),
                    ("catalyst_center", "Catalyst Center"),
                    ("meraki", "Meraki"),
                    ("mist", "Mist AI"),
                ],
                default="nornir",
                help_text="Which controller or method to use for deployment.",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="intent",
            name="controller_site",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Controller site name (e.g. Catalyst Center fabric site).",
                max_length=200,
            ),
        ),
        migrations.AlterField(
            model_name="intent",
            name="controller_org",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Controller organisation name (e.g. Meraki org name).",
                max_length=200,
            ),
        ),
    ]
