"""Nautobot UI views for the intent_networking app.

NautobotUIViewSet generates list, detail, create,
edit, and delete views automatically using the table and form classes.
"""

from nautobot.apps.views import NautobotUIViewSet
from nautobot.core.views.generic import ObjectListView
from nautobot.core.views.generic import ObjectView as ObjectDetailView

from intent_networking.api.serializers import IntentSerializer
from intent_networking.filters import IntentFilterSet
from intent_networking.forms import IntentBulkEditForm, IntentFilterForm, IntentForm
from intent_networking.models import Intent, ResolutionPlan, VerificationResult
from intent_networking.tables import IntentTable, ResolutionPlanTable, VerificationResultTable


class IntentUIViewSet(NautobotUIViewSet):
    """Full CRUD UI views for the Intent model."""

    queryset = Intent.objects.all()
    serializer_class = IntentSerializer
    form_class = IntentForm
    bulk_update_form_class = IntentBulkEditForm
    filterset_class = IntentFilterSet
    filterset_form_class = IntentFilterForm
    table_class = IntentTable

    def get_extra_context(self, request, instance=None):
        """Add resolution plans and verification history to the detail view context."""
        context = super().get_extra_context(request, instance)
        if instance:
            context["resolution_plans"] = instance.resolution_plans.order_by("-resolved_at")[:5]
            context["verifications"] = instance.verifications.order_by("-verified_at")[:10]
        return context


class ResolutionPlanListView(ObjectListView):
    """Read-only list view for resolution plans."""

    queryset = ResolutionPlan.objects.all().select_related("intent")
    table = ResolutionPlanTable
    action_buttons = ("export",)


class ResolutionPlanDetailView(ObjectDetailView):
    """Read-only detail view for a resolution plan."""

    queryset = ResolutionPlan.objects.all().select_related("intent")
    template_name = "generic/object_detail.html"


class VerificationResultListView(ObjectListView):
    """Read-only list view for verification results."""

    queryset = VerificationResult.objects.all().select_related("intent")
    table = VerificationResultTable
    action_buttons = ("export",)


class VerificationResultDetailView(ObjectDetailView):
    """Read-only detail view for a verification result."""

    queryset = VerificationResult.objects.all().select_related("intent")
    template_name = "generic/object_detail.html"
