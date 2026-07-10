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


class VxlanVniPoolFormTest(TestCase):
    """Test VxlanVniPoolForm."""

    def test_form_instantiates_for_new_instance(self):
        """The add view instantiates the form with an unsaved instance.

        Regression: as a NautobotModelForm this crashed on newer Nautobot with
        AttributeError('VxlanVniPool' object has no attribute 'get_relationships')
        because VxlanVniPool is a plain BaseModel.
        """
        from intent_networking.models import VxlanVniPool

        form = forms.VxlanVniPoolForm(instance=VxlanVniPool())
        for field in ("name", "range_start", "range_end", "tenant"):
            self.assertIn(field, form.fields)

    def test_form_not_relationship_dependent(self):
        """The form must not inherit mixins that require RelationshipModel."""
        from nautobot.extras.forms.mixins import RelationshipModelFormMixin

        self.assertNotIsInstance(forms.VxlanVniPoolForm(), RelationshipModelFormMixin)

    def test_form_validates_pool(self):
        """A well-formed pool payload validates."""
        form = forms.VxlanVniPoolForm(data={"name": "dc1-vni", "range_start": 10000, "range_end": 19999})
        self.assertTrue(form.is_valid(), form.errors)
