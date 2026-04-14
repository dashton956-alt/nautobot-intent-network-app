"""Ensure all Intent lifecycle statuses exist and are associated with the Intent content type.

This migration backfills the Intent lifecycle statuses that were otherwise only
created by the development seed script, while also ensuring the full set of
statuses is associated with the Intent content type. Note that 'Retired' was
previously handled by migration 0008_add_retired_status — it is included here
to guarantee the content type association is present regardless of install path.

Idempotent — uses get_or_create so re-running migrations on instances that already
have some or all of these statuses from seed_data.py or earlier migrations is safe.
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
