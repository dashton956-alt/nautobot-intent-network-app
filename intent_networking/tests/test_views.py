"""Unit tests for intent_networking UI views."""

from nautobot.apps.testing import ViewTestCases
from nautobot.extras.models import Status
from nautobot.tenancy.models import Tenant

from intent_networking import models
from intent_networking.tests import fixtures


class IntentViewTest(ViewTestCases.PrimaryObjectViewTestCase):
    """Test the Intent UI views."""

    model = models.Intent

    @classmethod
    def setUpTestData(cls):
        """Create test data for Intent view tests."""
        fixtures.create_intents()

        tenant = Tenant.objects.get(name="Test Tenant")
        status = Status.objects.filter(name="Draft").first() or Status.objects.first()

        cls.form_data = {
            "intent_id": "view-test-new-001",
            "version": 1,
            "intent_type": models.IntentTypeChoices.CONNECTIVITY,
            "tenant": tenant.pk,
            "status": status.pk,
            "intent_data": '{"name": "view-test-new-001", "type": "connectivity", "source": "GigabitEthernet0/1"}',
            "deployment_strategy": "all_at_once",
            "rendered_configs": "{}",
        }
        cls.update_data = {
            "intent_id": "view-test-new-001",
            "version": 2,
            "intent_type": models.IntentTypeChoices.CONNECTIVITY,
            "tenant": tenant.pk,
            "status": status.pk,
            "intent_data": '{"name": "view-test-new-001", "type": "connectivity", "source": "GigabitEthernet0/1", "updated": true}',
            "deployment_strategy": "all_at_once",
            "rendered_configs": "{}",
        }
        cls.bulk_edit_data = {
            "version": 2,
        }
