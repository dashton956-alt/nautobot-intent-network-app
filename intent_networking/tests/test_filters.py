"""Test IntentFilterSet."""

from nautobot.apps.testing import FilterTestCases

from intent_networking import filters, models
from intent_networking.tests import fixtures


class IntentFilterSetTestCase(FilterTestCases.FilterTestCase):
    """FilterSet test case for Intent."""

    queryset = models.Intent.objects.all()
    filterset = filters.IntentFilterSet
    generic_filter_tests = (
        ("id",),
        ("created",),
        ("last_updated",),
        ("intent_type",),
    )

    @classmethod
    def setUpTestData(cls):
        """Set up test data for Intent filter tests."""
        fixtures.create_intents()

    def test_q_search_intent_id(self):
        """Test using Q search with intent_id substring."""
        params = {"q": "test-intent-001"}
        self.assertEqual(self.filterset(params, self.queryset).qs.count(), 1)

    def test_q_invalid(self):
        """Test using invalid Q search returns no results."""
        params = {"q": "nonexistent-intent-xyz"}
        self.assertEqual(self.filterset(params, self.queryset).qs.count(), 0)
