"""Add 'Retired' status for Intent model.

Retired intents remain in Git but are non-actionable.
Only allowed transition out of Retired is back to Draft.
Reconciliation skips retired intents.
"""

from django.db import migrations


def add_retired_status(apps, schema_editor):
    """Create the Retired status and associate it with the Intent content type."""
    Status = apps.get_model("extras", "Status")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Intent = apps.get_model("intent_networking", "Intent")

    intent_ct = ContentType.objects.get_for_model(Intent)
    status, _ = Status.objects.get_or_create(name="Retired")
    status.content_types.add(intent_ct)


def remove_retired_status(apps, schema_editor):
    """Remove the Retired status association from Intent (reverse migration)."""
    Status = apps.get_model("extras", "Status")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Intent = apps.get_model("intent_networking", "Intent")

    intent_ct = ContentType.objects.get_for_model(Intent)
    try:
        status = Status.objects.get(name="Retired")
        status.content_types.remove(intent_ct)
    except Status.DoesNotExist:
        pass


class Migration(migrations.Migration):
    """Data migration to add the Retired status."""

    dependencies = [
        ("intent_networking", "0007_update_intent_type_choices_mgmt_global_config"),
    ]

    operations = [
        migrations.RunPython(add_retired_status, remove_retired_status),
    ]
