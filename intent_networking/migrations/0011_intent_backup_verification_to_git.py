# Generated for backup_verification_to_git BooleanField on Intent.

from django.db import migrations, models


def backfill_backup_flag(apps, schema_editor):
    """Set backup_verification_to_git=False on all existing rows."""
    Intent = apps.get_model("intent_networking", "Intent")
    Intent.objects.filter(backup_verification_to_git__isnull=True).update(backup_verification_to_git=False)


class Migration(migrations.Migration):
    """Add backup_verification_to_git boolean field to Intent model.

    Uses add-nullable / backfill / alter pattern to avoid holding a table lock.
    """

    dependencies = [
        ("intent_networking", "0010_add_verification_level_fields"),
    ]

    operations = [
        # Step 1: add as nullable (no default in schema)
        migrations.AddField(
            model_name="intent",
            name="backup_verification_to_git",
            field=models.NullBooleanField(),
        ),
        # Step 2: backfill existing rows
        migrations.RunPython(backfill_backup_flag, migrations.RunPython.noop),
        # Step 3: alter to final non-nullable schema with default
        migrations.AlterField(
            model_name="intent",
            name="backup_verification_to_git",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, verification results are committed to the configured Git repository.",
            ),
        ),
    ]
