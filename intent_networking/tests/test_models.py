"""Test Intent model."""

from nautobot.apps.testing import ModelTestCases

from intent_networking import models
from intent_networking.tests import fixtures


class TestIntentModel(ModelTestCases.BaseModelTestCase):
    """Test the Intent model."""

    model = models.Intent

    @classmethod
    def setUpTestData(cls):
        """Create test data for Intent model tests."""
        super().setUpTestData()
        fixtures.create_intents()

    def test_str_representation(self):
        """Intent __str__ includes intent_id, version and status."""
        intent = models.Intent.objects.first()
        self.assertIn(intent.intent_id, str(intent))

    def test_latest_plan_none_when_no_plans(self):
        """latest_plan returns None when no ResolutionPlan exists."""
        intent = models.Intent.objects.first()
        self.assertIsNone(intent.latest_plan)

    def test_latest_verification_none_when_no_verifications(self):
        """latest_verification returns None when no VerificationResult exists."""
        intent = models.Intent.objects.first()
        self.assertIsNone(intent.latest_verification)
