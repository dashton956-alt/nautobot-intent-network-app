"""Test intent_networking forms."""

from django.test import TestCase

from intent_networking import forms


class IntentFormTest(TestCase):
    """Test IntentForm validation."""

    def test_form_fields_present(self):
        """IntentForm exposes expected fields."""
        form = forms.IntentForm()
        for field in ("intent_id", "version", "intent_type", "tenant", "status", "intent_data"):
            self.assertIn(field, form.fields)

    def test_empty_form_is_invalid(self):
        """An empty form should not be valid."""
        form = forms.IntentForm(data={})
        self.assertFalse(form.is_valid())


class IntentFilterFormTest(TestCase):
    """Test IntentFilterForm."""

    def test_filter_form_fields_present(self):
        """IntentFilterForm exposes expected filter fields."""
        form = forms.IntentFilterForm()
        for field in ("q", "tenant", "intent_type"):
            self.assertIn(field, form.fields)
