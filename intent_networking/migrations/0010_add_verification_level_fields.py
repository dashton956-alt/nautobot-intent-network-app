# Generated manually for pyATS extended verification fields.

from django.db import migrations, models


def populate_verification_defaults(apps, schema_editor):
    """Set default values for new verification fields on existing rows."""
    Intent = apps.get_model("intent_networking", "Intent")
    Intent.objects.filter(verification_level__isnull=True).update(verification_level="basic")
    Intent.objects.filter(verification_trigger__isnull=True).update(verification_trigger="on_deploy")
    Intent.objects.filter(verification_fail_action__isnull=True).update(verification_fail_action="alert")

    VerificationResult = apps.get_model("intent_networking", "VerificationResult")
    VerificationResult.objects.filter(verification_engine__isnull=True).update(verification_engine="basic")


class Migration(migrations.Migration):
    """Add verification_level, verification_trigger, verification_schedule,
    verification_fail_action fields to Intent model and verification_engine,
    escalation_reason, pyats_diff_output fields to VerificationResult model.

    All new fields have defaults or are nullable — non-destructive, additive only.
    Uses a three-step pattern (add nullable → backfill → alter) for fields with
    defaults to avoid holding a table lock on large tables.
    """

    dependencies = [
        ("intent_networking", "0009_add_fw_rule_intent_type"),
    ]

    # Each step (add nullable → backfill → alter non-null) must run in its own
    # transaction so PostgreSQL doesn't reject the ALTER with
    # "pending trigger events".
    atomic = False

    operations = [
        # ── Step 1: Add all fields as nullable (no default in schema) ────
        migrations.AddField(
            model_name="intent",
            name="verification_level",
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="intent",
            name="verification_trigger",
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="intent",
            name="verification_schedule",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Cron expression — required if trigger includes 'scheduled'",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="intent",
            name="verification_fail_action",
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="verificationresult",
            name="verification_engine",
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="verificationresult",
            name="escalation_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="verificationresult",
            name="pyats_diff_output",
            field=models.TextField(blank=True, default=""),
        ),
        # ── Step 2: Backfill defaults on existing rows ───────────────────
        migrations.RunPython(
            populate_verification_defaults,
            migrations.RunPython.noop,
        ),
        # ── Step 3: Alter to final schema (non-nullable with defaults) ───
        migrations.AlterField(
            model_name="intent",
            name="verification_level",
            field=models.CharField(
                choices=[("basic", "Basic"), ("extended", "Extended")],
                default="basic",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="intent",
            name="verification_trigger",
            field=models.CharField(
                choices=[
                    ("on_deploy", "On Deploy Only"),
                    ("scheduled", "Scheduled Only"),
                    ("both", "On Deploy + Scheduled"),
                ],
                default="on_deploy",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="intent",
            name="verification_fail_action",
            field=models.CharField(
                choices=[
                    ("alert", "Alert Only"),
                    ("rollback", "Auto Rollback"),
                    ("remediate", "Auto Remediate"),
                ],
                default="alert",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="verificationresult",
            name="verification_engine",
            field=models.CharField(
                choices=[("basic", "Basic"), ("extended", "Extended"), ("escalated", "Escalated")],
                default="basic",
                max_length=20,
            ),
        ),
    ]
