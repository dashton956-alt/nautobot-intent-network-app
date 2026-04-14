"""Ensure all Intent lifecycle statuses exist and are associated with the Intent content type.

Previously these statuses were only created by the development seed script, meaning
fresh installs on non-development Nautobot instances would fail with
'Status.DoesNotExist' when the first job ran.

Idempotent — uses get_or_create so re-running migrations on instances that already
have these statuses from seed_data.py is safe.
"""

from django.db import migrations

INTENT_STATUSES = [
    "Draft",
    "Validated",
    "Deploying",
    "Deployed",
    "Failed",
    "Rolled Back",
    "Deprecated",
    "Retired",
]


def add_intent_statuses(apps, schema_editor):
    """Create Intent lifecycle statuses and associate them with the Intent content type."""
    Status = apps.get_model("extras", "Status")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Intent = apps.get_model("intent_networking", "Intent")

    intent_ct = ContentType.objects.get_for_model(Intent)
    for name in INTENT_STATUSES:
        status, _ = Status.objects.get_or_create(name=name)
        status.content_types.add(intent_ct)


def remove_intent_statuses(apps, schema_editor):
    """Remove the Intent content type association from lifecycle statuses (reverse migration).

    Statuses themselves are not deleted — they may be used elsewhere in Nautobot.
    """
    Status = apps.get_model("extras", "Status")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Intent = apps.get_model("intent_networking", "Intent")

    intent_ct = ContentType.objects.get_for_model(Intent)
    for name in INTENT_STATUSES:
        try:
            status = Status.objects.get(name=name)
            status.content_types.remove(intent_ct)
        except Status.DoesNotExist:
            pass


class Migration(migrations.Migration):
    """Data migration to ensure all Intent lifecycle statuses exist on any Nautobot instance."""

    dependencies = [
        ("intent_networking", "0014_replace_pyats_with_nuts"),
    ]

    operations = [
        migrations.RunPython(add_intent_statuses, remove_intent_statuses),
    ]
