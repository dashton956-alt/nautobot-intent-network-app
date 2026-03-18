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

    def test_intent_verification_level_defaults_to_basic(self):
        intent = models.Intent.objects.first()
        self.assertEqual(intent.verification_level, "basic")

    def test_intent_verification_trigger_defaults_to_on_deploy(self):
        intent = models.Intent.objects.first()
        self.assertEqual(intent.verification_trigger, "on_deploy")

    def test_intent_verification_fail_action_defaults_to_alert(self):
        intent = models.Intent.objects.first()
        self.assertEqual(intent.verification_fail_action, "alert")

    def test_intent_verification_schedule_defaults_blank(self):
        intent = models.Intent.objects.first()
        self.assertEqual(intent.verification_schedule, "")

    def test_verification_result_engine_defaults_to_basic(self):
        intent = models.Intent.objects.first()
        vr = models.VerificationResult.objects.create(
            intent=intent,
            passed=True,
            checks=[],
        )
        self.assertEqual(vr.verification_engine, "basic")


class TestIntentDependencyGraph(ModelTestCases.BaseModelTestCase):
    """Test intent dependency graph features."""

    model = models.Intent

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        fixtures.create_intents()

    def _get_status(self, name):
        from nautobot.extras.models import Status

        return Status.objects.get(name__iexact=name)

    def test_dependency_status_ready_no_dependencies(self):
        """Intent with no dependencies returns 'ready'."""
        intent = models.Intent.objects.first()
        self.assertEqual(intent.dependency_status, "ready")

    def test_dependency_status_blocked_when_dep_not_deployed(self):
        """Intent returns 'blocked' when a dependency is not Deployed."""
        intents = list(models.Intent.objects.all()[:2])
        parent = intents[0]
        child = intents[1]
        # Parent is in Draft status
        parent.status = self._get_status("Draft")
        parent.save()
        child.dependencies.add(parent)
        self.assertEqual(child.dependency_status, "blocked")

    def test_dependency_status_ready_when_all_deps_deployed(self):
        """Intent returns 'ready' when all dependencies are Deployed."""
        intents = list(models.Intent.objects.all()[:2])
        parent = intents[0]
        child = intents[1]
        parent.status = self._get_status("Deployed")
        parent.save()
        child.dependencies.add(parent)
        self.assertEqual(child.dependency_status, "ready")

    def test_blocking_dependencies_returns_correct_ids(self):
        """blocking_dependencies returns intent_ids of non-Deployed deps."""
        intents = list(models.Intent.objects.all()[:3])
        dep1, dep2, child = intents[0], intents[1], intents[2]
        dep1.status = self._get_status("Draft")
        dep1.save()
        dep2.status = self._get_status("Deployed")
        dep2.save()
        child.dependencies.set([dep1, dep2])
        blocked = child.blocking_dependencies
        self.assertIn(dep1.intent_id, blocked)
        self.assertNotIn(dep2.intent_id, blocked)
