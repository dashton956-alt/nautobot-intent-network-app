# Generated manually — replace pyATS with NUTS verification engine.

from django.db import migrations, models


def migrate_extended_to_nuts(apps, schema_editor):
    """Rename 'extended' verification values to 'nuts'."""
    Intent = apps.get_model("intent_networking", "Intent")
    Intent.objects.filter(verification_level="extended").update(verification_level="nuts")

    VerificationResult = apps.get_model("intent_networking", "VerificationResult")
    VerificationResult.objects.filter(verification_engine="extended").update(verification_engine="nuts")


def migrate_nuts_to_extended(apps, schema_editor):
    """Reverse: rename 'nuts' back to 'extended'."""
    Intent = apps.get_model("intent_networking", "Intent")
    Intent.objects.filter(verification_level="nuts").update(verification_level="extended")

    VerificationResult = apps.get_model("intent_networking", "VerificationResult")
    VerificationResult.objects.filter(verification_engine="nuts").update(verification_engine="extended")


class Migration(migrations.Migration):
    """Replace pyATS with NUTS as the extended verification engine.

    - Rename pyats_diff_output field to nuts_output on VerificationResult
    - Update verification_level choices: 'extended' → 'nuts'
    - Update verification_engine choices: 'extended' → 'nuts'
    - Migrate existing data from 'extended' to 'nuts'
    """

    dependencies = [
        ("intent_networking", "0013_intent_controller_fields"),
    ]

    operations = [
        # Rename the field
        migrations.RenameField(
            model_name="verificationresult",
            old_name="pyats_diff_output",
            new_name="nuts_output",
        ),
        # Migrate data before altering choices
        migrations.RunPython(
            migrate_extended_to_nuts,
            migrate_nuts_to_extended,
        ),
        # Update verification_level choices on Intent
        migrations.AlterField(
            model_name="intent",
            name="verification_level",
            field=models.CharField(
                choices=[("basic", "Basic"), ("nuts", "NUTS")],
                default="basic",
                max_length=20,
            ),
        ),
        # Update verification_engine choices on VerificationResult
        migrations.AlterField(
            model_name="verificationresult",
            name="verification_engine",
            field=models.CharField(
                choices=[("basic", "Basic"), ("nuts", "NUTS"), ("escalated", "Escalated")],
                default="basic",
                max_length=20,
            ),
        ),
    ]
