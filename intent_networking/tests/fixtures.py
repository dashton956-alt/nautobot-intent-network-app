"""Create fixtures for tests."""

from django.contrib.contenttypes.models import ContentType
from nautobot.extras.models import Status
from nautobot.tenancy.models import Tenant

from intent_networking.models import Intent, IntentTypeChoices

INTENT_STATUSES = ["Draft", "Validated", "Deploying", "Deployed", "Failed", "Rolled Back", "Deprecated", "Retired"]


def ensure_intent_statuses():
    """Ensure all Intent lifecycle statuses exist in the test database."""
    intent_ct = ContentType.objects.get_for_model(Intent)
    for name in INTENT_STATUSES:
        status, _ = Status.objects.get_or_create(name=name)
        status.content_types.add(intent_ct)


def create_intents():
    """Create a small set of Intent records for use in test cases."""
    ensure_intent_statuses()
    tenant, _ = Tenant.objects.get_or_create(name="Test Tenant")
    status = Status.objects.filter(name="Draft").first()
    if status is None:
        status = Status.objects.first()

    intent_configs = [
        (
            IntentTypeChoices.CONNECTIVITY,
            {"type": "connectivity", "name": "test-intent-001", "source": "GigabitEthernet0/1"},
        ),
        (
            IntentTypeChoices.SECURITY,
            {"type": "security", "name": "test-intent-002"},
        ),
        (
            IntentTypeChoices.REACHABILITY,
            {"type": "reachability", "name": "test-intent-003", "reachability_type": "static"},
        ),
    ]
    for idx, (itype, idata) in enumerate(intent_configs, start=1):
        Intent.objects.get_or_create(
            intent_id=f"test-intent-{idx:03d}",
            defaults={
                "version": 1,
                "intent_type": itype,
                "tenant": tenant,
                "status": status,
                "intent_data": idata,
            },
        )
