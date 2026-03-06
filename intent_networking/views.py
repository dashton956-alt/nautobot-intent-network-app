"""Nautobot UI views for the intent_networking app.

NautobotUIViewSet generates list, detail, create,
edit, and delete views automatically using the table and form classes.
"""

from django.db.models import Count
from django.views.generic import TemplateView
from nautobot.apps.views import NautobotUIViewSet
from nautobot.core.views.generic import ObjectListView
from nautobot.core.views.generic import ObjectView as ObjectDetailView

from intent_networking.api.serializers import IntentSerializer
from intent_networking.filters import IntentFilterSet, RouteDistinguisherPoolFilterSet, RouteTargetPoolFilterSet
from intent_networking.forms import (
    IntentBulkEditForm,
    IntentFilterForm,
    IntentForm,
    RouteDistinguisherPoolForm,
    RouteTargetPoolForm,
)
from intent_networking.models import (
    Intent,
    ResolutionPlan,
    RouteDistinguisherPool,
    RouteTargetPool,
    VerificationResult,
)
from intent_networking.tables import (
    IntentTable,
    ResolutionPlanTable,
    RouteDistinguisherPoolTable,
    RouteTargetPoolTable,
    VerificationResultTable,
)

# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────


class DashboardView(TemplateView):
    """Plugin home page showing intent status counts and pool utilisation."""

    template_name = "intent_networking/dashboard.html"

    def get_context_data(self, **kwargs):
        """Build context with counts, recent intents, pools and verifications."""
        context = super().get_context_data(**kwargs)

        context["status_counts"] = (
            Intent.objects.values("status__name").annotate(count=Count("id")).order_by("status__name")
        )
        context["total_intents"] = Intent.objects.count()
        context["recent_intents"] = Intent.objects.select_related("tenant", "status").order_by("-last_updated")[:10]
        context["rd_pools"] = RouteDistinguisherPool.objects.all()
        context["rt_pools"] = RouteTargetPool.objects.all()
        context["recent_verifications"] = (
            VerificationResult.objects.select_related("intent").order_by("-verified_at")[:10]
        )

        return context


# ─────────────────────────────────────────────────────────────────────────────
# Intents
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Resolution Plans (read-only)
# ─────────────────────────────────────────────────────────────────────────────


class ResolutionPlanListView(ObjectListView):
    """Read-only list view for resolution plans."""

    queryset = ResolutionPlan.objects.all().select_related("intent")
    table = ResolutionPlanTable
    action_buttons = ("export",)


class ResolutionPlanDetailView(ObjectDetailView):
    """Read-only detail view for a resolution plan."""

    queryset = ResolutionPlan.objects.all().select_related("intent")
    template_name = "generic/object_detail.html"


# ─────────────────────────────────────────────────────────────────────────────
# Verification Results (read-only)
# ─────────────────────────────────────────────────────────────────────────────


class VerificationResultListView(ObjectListView):
    """Read-only list view for verification results."""

    queryset = VerificationResult.objects.all().select_related("intent")
    table = VerificationResultTable
    action_buttons = ("export",)


# ─────────────────────────────────────────────────────────────────────────────
# RD / RT Pool Management
# ─────────────────────────────────────────────────────────────────────────────


class RouteDistinguisherPoolUIViewSet(NautobotUIViewSet):
    """Full CRUD UI views for managing Route Distinguisher pools."""

    queryset = RouteDistinguisherPool.objects.all()
    form_class = RouteDistinguisherPoolForm
    filterset_class = RouteDistinguisherPoolFilterSet
    table_class = RouteDistinguisherPoolTable
    lookup_field = "pk"


class RouteTargetPoolUIViewSet(NautobotUIViewSet):
    """Full CRUD UI views for managing Route Target pools."""

    queryset = RouteTargetPool.objects.all()
    form_class = RouteTargetPoolForm
    filterset_class = RouteTargetPoolFilterSet
    table_class = RouteTargetPoolTable
    lookup_field = "pk"


class VerificationResultDetailView(ObjectDetailView):
    """Read-only detail view for a verification result."""

    queryset = VerificationResult.objects.all().select_related("intent")
    template_name = "generic/object_detail.html"
