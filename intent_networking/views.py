"""Nautobot UI views for the intent_networking app.

NautobotUIViewSet generates list, detail, create,
edit, and delete views automatically using the table and form classes.
"""

from django.db.models import Count
from django.views.generic import TemplateView
from nautobot.apps.views import NautobotUIViewSet
from nautobot.core.views.generic import ObjectListView
from nautobot.core.views.generic import ObjectView as ObjectDetailView
from nautobot.ipam.models import VRF, Namespace
from nautobot.ipam.models import RouteTarget as NautobotRouteTarget

from intent_networking.api.serializers import IntentSerializer
from intent_networking.filters import (
    IntentAuditEntryFilterSet,
    IntentFilterSet,
)
from intent_networking.forms import (
    IntentBulkEditForm,
    IntentFilterForm,
    IntentForm,
)
from intent_networking.models import (
    Intent,
    IntentApproval,
    IntentAuditEntry,
    ManagedLoopbackPool,
    ResolutionPlan,
    TunnelIdPool,
    VerificationResult,
    VxlanVniPool,
    WirelessVlanPool,
)
from intent_networking.tables import (
    IntentAuditEntryTable,
    IntentTable,
    ResolutionPlanTable,
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

        # ── Status counts ─────────────────────────────────────────────────
        context["status_counts"] = (
            Intent.objects.values("status__name").annotate(count=Count("id")).order_by("status__name")
        )
        context["total_intents"] = Intent.objects.count()

        # Quick-access status counters for stat cards
        status_qs = Intent.objects.values("status__name").annotate(count=Count("id"))
        status_map = {row["status__name"].lower(): row["count"] for row in status_qs if row["status__name"]}
        context["deployed_count"] = status_map.get("deployed", 0)
        context["failed_count"] = status_map.get("failed", 0)
        context["deploying_count"] = status_map.get("deploying", 0)
        context["draft_count"] = status_map.get("draft", 0)
        context["validated_count"] = status_map.get("validated", 0)

        # ── Recent intents ────────────────────────────────────────────────
        context["recent_intents"] = Intent.objects.select_related("tenant", "status").order_by("-last_updated")[:10]

        # ── Nautobot native VRF / RT / Namespace counts ────────────────
        context["vrf_count"] = VRF.objects.count()
        context["rt_count"] = NautobotRouteTarget.objects.count()
        context["namespace_count"] = Namespace.objects.count()
        context["namespaces"] = Namespace.objects.all()
        context["vni_pools"] = VxlanVniPool.objects.all()
        context["tunnel_pools"] = TunnelIdPool.objects.all()
        context["loopback_pools"] = ManagedLoopbackPool.objects.all()
        context["wireless_pools"] = WirelessVlanPool.objects.all()

        # ── Verification stats ────────────────────────────────────────────
        context["recent_verifications"] = VerificationResult.objects.select_related("intent").order_by("-verified_at")[
            :10
        ]
        total_verifications = VerificationResult.objects.count()
        passed_verifications = VerificationResult.objects.filter(passed=True).count()
        context["total_verifications"] = total_verifications
        context["passed_verifications"] = passed_verifications
        context["failed_verifications"] = total_verifications - passed_verifications
        context["verification_pass_pct"] = (
            int(passed_verifications / total_verifications * 100) if total_verifications else 0
        )

        # ── Approval stats ────────────────────────────────────────────────
        context["pending_approvals"] = (
            Intent.objects.filter(approved_by="").exclude(status__name__in=["Deprecated", "Draft"]).count()
        )

        # ── Intent type breakdown (top 10 by count) ──────────────────────
        context["intent_type_breakdown"] = (
            Intent.objects.values("intent_type").annotate(count=Count("id")).order_by("-count")[:10]
        )

        # ── Recent audit trail ────────────────────────────────────────────
        context["recent_audit"] = IntentAuditEntry.objects.select_related("intent").order_by("-timestamp")[:8]

        # ── Resolution plan stats ─────────────────────────────────────────
        context["total_resolution_plans"] = ResolutionPlan.objects.count()
        context["recent_resolutions"] = ResolutionPlan.objects.select_related("intent").order_by("-resolved_at")[:5]

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
        """Add resolution plans, verifications, approvals and audit trail to detail view."""
        context = super().get_extra_context(request, instance)
        if instance:
            context["resolution_plans"] = instance.resolution_plans.prefetch_related("affected_devices").order_by(
                "-resolved_at"
            )[:5]
            context["verifications"] = instance.verifications.order_by("-verified_at")[:10]
            context["approvals"] = instance.approvals.order_by("-decided_at")[:10]
            context["audit_entries"] = instance.audit_trail.order_by("-timestamp")[:20]
            context["rendered_configs"] = instance.rendered_configs or {}
        return context


# ─────────────────────────────────────────────────────────────────────────────
# Resolution Plans (read-only)
# ─────────────────────────────────────────────────────────────────────────────


class ResolutionPlanListView(ObjectListView):
    """Read-only list view for resolution plans."""

    queryset = ResolutionPlan.objects.all().select_related("intent").prefetch_related("affected_devices")
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


class VerificationResultDetailView(ObjectDetailView):
    """Read-only detail view for a verification result."""

    queryset = VerificationResult.objects.all().select_related("intent")
    template_name = "generic/object_detail.html"


# ─────────────────────────────────────────────────────────────────────────────
# Audit Trail (#4)
# ─────────────────────────────────────────────────────────────────────────────


class AuditTrailListView(ObjectListView):
    """Read-only list view for all audit entries across all intents."""

    queryset = IntentAuditEntry.objects.all().select_related("intent")
    table = IntentAuditEntryTable
    filterset = IntentAuditEntryFilterSet
    action_buttons = ("export",)


class AuditTrailDetailView(ObjectDetailView):
    """Read-only detail view for a single audit entry."""

    queryset = IntentAuditEntry.objects.all().select_related("intent")
    template_name = "intent_networking/audit_entry_detail.html"


# ─────────────────────────────────────────────────────────────────────────────
# Config Preview (#1)
# ─────────────────────────────────────────────────────────────────────────────


class ConfigPreviewView(TemplateView):
    """Displays the rendered configs for a given intent (dry-run preview)."""

    template_name = "intent_networking/config_preview.html"

    def get_context_data(self, **kwargs):
        """Build context with intent and its rendered configs."""
        context = super().get_context_data(**kwargs)
        intent_id = self.kwargs.get("intent_id")
        try:
            intent = Intent.objects.get(intent_id=intent_id)
        except Intent.DoesNotExist:
            intent = None
        context["intent"] = intent
        context["rendered_configs"] = intent.rendered_configs if intent else {}
        return context


# ─────────────────────────────────────────────────────────────────────────────
# Approval History
# ─────────────────────────────────────────────────────────────────────────────


class ApprovalListView(ObjectListView):
    """Read-only list of all approvals across all intents."""

    queryset = IntentApproval.objects.all().select_related("intent", "approver")
    table_class = None  # Uses generic rendering
    action_buttons = ("export",)
