# Generated manually for pyATS extended verification fields.

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add verification_level, verification_trigger, verification_schedule,
    verification_fail_action fields to Intent model and verification_engine,
    escalation_reason, pyats_diff_output fields to VerificationResult model.

    All new fields have defaults or are nullable — non-destructive, additive only.
    """

    dependencies = [
        ("intent_networking", "0009_add_fw_rule_intent_type"),
    ]

    operations = [
        # ── Intent model: verification settings ──────────────────────────
        migrations.AddField(
            model_name="intent",
            name="verification_level",
            field=models.CharField(
                choices=[("basic", "Basic"), ("extended", "Extended")],
                default="basic",
                max_length=20,
            ),
        ),
        migrations.AddField(
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
        migrations.AddField(
            model_name="intent",
            name="verification_schedule",
            field=models.CharField(
                blank=True,
                help_text="Cron expression — required if trigger includes 'scheduled'",
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
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
        # ── VerificationResult model: engine metadata ────────────────────
        migrations.AddField(
            model_name="verificationresult",
            name="verification_engine",
            field=models.CharField(
                choices=[("basic", "Basic"), ("extended", "Extended"), ("escalated", "Escalated")],
                default="basic",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="verificationresult",
            name="escalation_reason",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="verificationresult",
            name="pyats_diff_output",
            field=models.TextField(blank=True, null=True),
        ),
    ]
