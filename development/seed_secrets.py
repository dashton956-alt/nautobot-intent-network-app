"""Create Secrets Group and assign to all lab Arista devices."""

from nautobot.dcim.models import Device
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import Secret, SecretsGroup, SecretsGroupAssociation

# Create Secrets for username and password using environment variables
username_secret, created = Secret.objects.get_or_create(
    name="Device Username (env)",
    defaults={
        "provider": "environment-variable",
        "parameters": {"variable": "DEVICE_USERNAME"},
    },
)
tag = "Created" if created else "Exists"
print(f"  {tag} secret: {username_secret.name}")

password_secret, created = Secret.objects.get_or_create(
    name="Device Password (env)",
    defaults={
        "provider": "environment-variable",
        "parameters": {"variable": "DEVICE_PASSWORD"},
    },
)
tag = "Created" if created else "Exists"
print(f"  {tag} secret: {password_secret.name}")

# Create Secrets Group
sg, created = SecretsGroup.objects.get_or_create(name="Lab Device Credentials")
tag = "Created" if created else "Exists"
print(f"  {tag} secrets group: {sg.name}")

# Associate username + password via Generic access type
SecretsGroupAssociation.objects.get_or_create(
    secrets_group=sg,
    access_type=SecretsGroupAccessTypeChoices.TYPE_GENERIC,
    secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    defaults={"secret": username_secret},
)
SecretsGroupAssociation.objects.get_or_create(
    secrets_group=sg,
    access_type=SecretsGroupAccessTypeChoices.TYPE_GENERIC,
    secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    defaults={"secret": password_secret},
)
print("  Associated username + password with Generic access type")

# Assign to all lab devices
for dev_name in ["lab-arista-sw01", "lab-arista-sw02", "lab-spine-01", "lab-spine-02"]:
    try:
        dev = Device.objects.get(name=dev_name)
        dev.secrets_group = sg
        dev.validated_save()
        print(f"  Assigned secrets group to {dev.name}")
    except Device.DoesNotExist:
        print(f"  Skipped {dev_name} — not found")
print("  Done!")
