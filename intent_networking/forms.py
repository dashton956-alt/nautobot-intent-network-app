"""Form definitions for the intent_networking app."""

from django import forms
from nautobot.apps.forms import NautobotBulkEditForm, NautobotFilterForm, NautobotModelForm
from nautobot.extras.forms.mixins import StatusModelBulkEditFormMixin
from nautobot.tenancy.models import Tenant

from intent_networking.models import (
    Intent,
    IntentTypeChoices,
    VerificationFailAction,
    VerificationLevel,
    VerificationTrigger,
)


class IntentForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """Model form for creating and editing Intent records."""

    class Meta:
        """Meta options for IntentForm."""

        model = Intent
        fields = "__all__"
        widgets = {
            "intent_data": forms.Textarea(attrs={"rows": 20, "class": "font-monospace"}),
            "scheduled_deploy_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
            ),
            "verification_level": forms.Select(),
            "verification_trigger": forms.Select(),
            "verification_fail_action": forms.Select(),
            "verification_schedule": forms.TextInput(
                attrs={"placeholder": "e.g. 0 * * * * (hourly)"},
            ),
            "backup_verification_to_git": forms.CheckboxInput(),
        }
        help_texts = {
            "intent_data": "Paste the full YAML intent content here as JSON.",
            "scheduled_deploy_at": "Leave blank for immediate deployment. "
            "Set a future date/time to schedule deployment.",
        }

    class Media:
        """Include JS to toggle verification_schedule visibility."""

        js = ("intent_networking/js/verification_form.js",)


class IntentBulkEditForm(StatusModelBulkEditFormMixin, NautobotBulkEditForm):  # pylint: disable=too-many-ancestors
    """Bulk edit form for Intent records."""

    pk = forms.ModelMultipleChoiceField(queryset=Intent.objects.all(), widget=forms.MultipleHiddenInput())
    tenant = forms.ModelChoiceField(queryset=Tenant.objects.all(), required=False)
    version = forms.IntegerField(required=False)
    deployment_strategy = forms.ChoiceField(
        choices=[("", "---------")]
        + [
            ("all_at_once", "All at once"),
            ("canary", "Canary"),
            ("rolling", "Rolling"),
        ],
        required=False,
    )
    verification_level = forms.ChoiceField(
        choices=[("", "---------")] + list(VerificationLevel.choices),
        required=False,
    )
    verification_fail_action = forms.ChoiceField(
        choices=[("", "---------")] + list(VerificationFailAction.choices),
        required=False,
    )

    class Meta:
        """Meta options for IntentBulkEditForm."""

        nullable_fields = ["scheduled_deploy_at"]


class IntentFilterForm(NautobotFilterForm):
    """Filter form for the Intent list view."""

    model = Intent
    q = forms.CharField(required=False, label="Search")
    tenant = forms.ModelMultipleChoiceField(queryset=Tenant.objects.all(), required=False)
    intent_type = forms.MultipleChoiceField(choices=IntentTypeChoices.choices, required=False)
    deployment_strategy = forms.MultipleChoiceField(
        choices=[
            ("all_at_once", "All at once"),
            ("canary", "Canary"),
            ("rolling", "Rolling"),
        ],
        required=False,
    )
    verification_level = forms.MultipleChoiceField(
        choices=VerificationLevel.choices,
        required=False,
    )
    verification_trigger = forms.MultipleChoiceField(
        choices=VerificationTrigger.choices,
        required=False,
    )
    verification_fail_action = forms.MultipleChoiceField(
        choices=VerificationFailAction.choices,
        required=False,
    )
