"""Unit tests for intent_networking REST API."""

from nautobot.apps.testing import APIViewTestCases
from nautobot.extras.models import Status
from nautobot.tenancy.models import Tenant

from intent_networking import models
from intent_networking.tests import fixtures


class IntentAPIViewTest(APIViewTestCases.APIViewTestCase):
    """Test the API viewsets for Intent."""

    model = models.Intent
    choices_fields = ("intent_type",)

    @classmethod
    def setUpTestData(cls):
        """Create test data for Intent API viewset tests."""
        super().setUpTestData()
        fixtures.create_intents()

        tenant = Tenant.objects.get(name="Test Tenant")
        status = Status.objects.filter(name="Draft").first() or Status.objects.first()

        cls.create_data = [
            {
                "intent_id": "api-test-001",
                "version": 1,
                "intent_type": models.IntentTypeChoices.CONNECTIVITY,
                "tenant": tenant.pk,
                "status": status.pk,
                "intent_data": {"type": "connectivity", "name": "api-test-001"},
            },
            {
                "intent_id": "api-test-002",
                "version": 1,
                "intent_type": models.IntentTypeChoices.SECURITY,
                "tenant": tenant.pk,
                "status": status.pk,
                "intent_data": {"type": "security", "name": "api-test-002"},
            },
            {
                "intent_id": "api-test-003",
                "version": 1,
                "intent_type": models.IntentTypeChoices.REACHABILITY,
                "tenant": tenant.pk,
                "status": status.pk,
                "intent_data": {"type": "reachability", "name": "api-test-003"},
            },
        ]
        cls.update_data = {
            "intent_data": {"type": "connectivity", "name": "api-test-001", "updated": True},
        }
        cls.bulk_update_data = {
            "version": 2,
        }
