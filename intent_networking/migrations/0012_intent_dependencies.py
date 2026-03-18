from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("intent_networking", "0011_intent_backup_verification_to_git"),
    ]

    operations = [
        migrations.AddField(
            model_name="intent",
            name="dependencies",
            field=models.ManyToManyField(
                blank=True,
                help_text="Other intents that must be Deployed before this intent can be deployed.",
                related_name="dependents",
                to="intent_networking.intent",
            ),
        ),
    ]
