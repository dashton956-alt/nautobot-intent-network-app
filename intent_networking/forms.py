"""Form definitions for the intent_networking app."""

from django import forms
from nautobot.apps.forms import NautobotBulkEditForm, NautobotFilterForm, NautobotModelForm
from nautobot.extras.forms.mixins import StatusModelBulkEditFormMixin
from nautobot.tenancy.models import Tenant

from intent_networking.models import Intent, IntentTypeChoices, RouteDistinguisherPool, RouteTargetPool


class IntentForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """Model form for creating and editing Intent records."""

    class Meta:
        """Meta options for IntentForm."""

        model = Intent
        fields = "__all__"
        widgets = {
            "intent_data": forms.Textarea(attrs={"rows": 20, "class": "font-monospace"}),
        }
        help_texts = {
            "intent_data": "Paste the full YAML intent content here as JSON.",
        }


class IntentBulkEditForm(StatusModelBulkEditFormMixin, NautobotBulkEditForm):  # pylint: disable=too-many-ancestors
    """Bulk edit form for Intent records."""

    pk = forms.ModelMultipleChoiceField(queryset=Intent.objects.all(), widget=forms.MultipleHiddenInput())
    tenant = forms.ModelChoiceField(queryset=Tenant.objects.all(), required=False)
    version = forms.IntegerField(required=False)

    class Meta:
        """Meta options for IntentBulkEditForm."""

        nullable_fields = []


class IntentFilterForm(NautobotFilterForm):
    """Filter form for the Intent list view."""

    model = Intent
    q = forms.CharField(required=False, label="Search")
    tenant = forms.ModelMultipleChoiceField(queryset=Tenant.objects.all(), required=False)
    intent_type = forms.MultipleChoiceField(choices=IntentTypeChoices.choices, required=False)


class RouteDistinguisherPoolForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """Model form for creating and editing RD Pool records."""

    class Meta:
        """Meta options for RouteDistinguisherPoolForm."""

        model = RouteDistinguisherPool
        fields = "__all__"


class RouteTargetPoolForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """Model form for creating and editing RT Pool records."""

    class Meta:
        """Meta options for RouteTargetPoolForm."""

        model = RouteTargetPool
        fields = "__all__"
