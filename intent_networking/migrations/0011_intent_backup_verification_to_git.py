# Generated for backup_verification_to_git BooleanField on Intent.

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add backup_verification_to_git boolean field to Intent model."""

    dependencies = [
        ("intent_networking", "0010_add_verification_level_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="intent",
            name="backup_verification_to_git",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, verification results are committed to the configured Git repository.",
            ),
        ),
    ]
