"""Nautobot UI views for the intent_networking app.

NautobotUIViewSet generates list, detail, create,
edit, and delete views automatically using the table and form classes.
"""

import logging

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView
from nautobot.apps.views import NautobotUIViewSet
from nautobot.core.views.generic import ObjectListView
from nautobot.core.views.generic import ObjectView as ObjectDetailView
from nautobot.ipam.models import VRF, Namespace
from nautobot.ipam.models import RouteTarget as NautobotRouteTarget

from intent_networking.api.serializers import IntentSerializer, VxlanVniPoolSerializer
from intent_networking.filters import (
    IntentAuditEntryFilterSet,
    IntentFilterSet,
)
from intent_networking.forms import (
    IntentBulkEditForm,
    IntentFilterForm,
    IntentForm,
    VxlanVniPoolForm,
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
    VxlanVniPoolTable,
)

logger = logging.getLogger(__name__)

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
        context["retired_count"] = status_map.get("retired", 0)

        # ── Recent intents ────────────────────────────────────────────────
        context["recent_intents"] = Intent.objects.select_related("tenant", "status").order_by("-last_updated")[:10]

        # ── NUTS verification results for last 15 intents ────────────────
        recent_nuts = (
            VerificationResult.objects.filter(verification_engine__in=("nuts", "escalated"))
            .select_related("intent", "intent__status")
            .order_by("-verified_at")[:15]
        )
        context["recent_nuts_results"] = recent_nuts

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
            Intent.objects.filter(approved_by="").exclude(status__name__in=["Deprecated", "Draft", "Retired"]).count()
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
    template_name = "intent_networking/verificationresult_detail.html"

    # ── NUTS test-class → human label mapping ─────────────────────────
    _NUTS_CLASS_LABELS = {
        "TestNapalmInterfaces": "Interface State",
        "TestNapalmBgpNeighbors": "BGP Neighbors",
        "TestNapalmLldpNeighbors": "LLDP Neighbors",
        "TestNetmikoOspfNeighbors": "OSPF Neighbors",
        "TestNetmikoCdpNeighbors": "CDP Neighbors",
        "TestNetmikoLldpNeighbors": "LLDP Neighbors",
        "TestNapalmNtp": "NTP Servers",
        "TestNapalmUsers": "User Accounts",
        "TestNapalmPing": "Ping Reachability",
        "TestNapalmTraceroute": "Traceroute",
    }

    def get_extra_context(self, request, instance):
        """Pre-process checks for the template."""
        ctx = super().get_extra_context(request, instance)

        checks = instance.checks or []
        total = len(checks)
        passed = sum(1 for c in checks if c.get("passed"))
        failed = total - passed
        pass_rate = int(passed / total * 100) if total else 0

        # --- enrich each check with parsed fields -----------------------
        enriched = []
        for c in checks:
            raw_id = c.get("check", "")
            e = {**c, "raw_id": raw_id}

            # Parse NUTS node-ids like
            #   "test_bundle.yaml::TestNapalmInterfaces::test[host=sw01 …]"
            parts = raw_id.split("::")
            if len(parts) >= 2:
                class_name = parts[1] if len(parts) >= 2 else ""
                e["test_class"] = self._NUTS_CLASS_LABELS.get(class_name, class_name)
                # extract param string from test[host=sw01 name=Mgmt0 …]
                param_match = None
                test_part = parts[-1] if len(parts) >= 3 else ""
                if "[" in test_part:
                    param_match = test_part[test_part.index("[") + 1 : test_part.rindex("]")]
                e["params"] = param_match or ""
            else:
                e["test_class"] = raw_id
                e["params"] = ""

            # Parse "device" from either the explicit field or from params
            device = c.get("device", "")
            if not device and "host=" in e["params"]:
                try:
                    device = e["params"].split("host=")[1].split()[0].rstrip(",")
                except IndexError:
                    pass
            e["device"] = device or "—"

            # Parse detail into structured parts
            detail = c.get("detail", "")
            e["outcome"] = ""
            e["duration"] = ""
            e["error_message"] = ""
            if detail:
                for part in detail.split("; "):
                    if part.startswith("outcome="):
                        e["outcome"] = part.split("=", 1)[1]
                    elif part.startswith("duration="):
                        e["duration"] = part.split("=", 1)[1]
                    else:
                        e["error_message"] = (e["error_message"] + " " + part).strip()

            enriched.append(e)

        # --- group by device --------------------------------------------
        device_groups = {}
        for e in enriched:
            dev = e["device"]
            if dev not in device_groups:
                device_groups[dev] = {
                    "device": dev,
                    "checks": [],
                    "passed": 0,
                    "failed": 0,
                    "total": 0,
                }
            device_groups[dev]["checks"].append(e)
            device_groups[dev]["total"] += 1
            if e.get("passed"):
                device_groups[dev]["passed"] += 1
            else:
                device_groups[dev]["failed"] += 1

        # sort: devices with failures first
        sorted_groups = sorted(device_groups.values(), key=lambda g: (-g["failed"], g["device"]))

        # --- previous runs for this intent (last 10, excluding self) ----
        prev = (
            VerificationResult.objects.filter(intent=instance.intent)
            .exclude(pk=instance.pk)
            .order_by("-verified_at")[:10]
        )

        ctx.update(
            {
                "enriched_checks": enriched,
                "device_groups": sorted_groups,
                "failed_checks": [e for e in enriched if not e.get("passed")],
                "total_checks": total,
                "passed_checks_count": passed,
                "failed_checks_count": failed,
                "pass_rate": pass_rate,
                "previous_results": prev,
            }
        )
        return ctx


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


# ─────────────────────────────────────────────────────────────────────────────
# Approve / Reject (UI buttons — POST only)
# ─────────────────────────────────────────────────────────────────────────────


class IntentApproveView(View):
    """Handle approve POST from the intent detail page."""

    http_method_names = ["post"]

    def post(self, request, pk):
        """Create an approval record and redirect back to the intent detail."""
        from intent_networking.events import EVENT_INTENT_APPROVED, dispatch_event

        intent = get_object_or_404(Intent, pk=pk)

        if not request.user.has_perm("intent_networking.approve_intent"):
            messages.error(request, "You do not have the 'approve_intent' permission.")
            return redirect(intent.get_absolute_url())

        comment = request.POST.get("comment", "")

        approval = IntentApproval.objects.create(
            intent=intent,
            approver=request.user,
            decision="approved",
            comment=comment,
        )
        intent.approved_by = request.user.username
        intent.save(update_fields=["approved_by"])

        IntentAuditEntry.objects.create(
            intent=intent,
            action="approved",
            actor=request.user.username,
            detail={"comment": comment, "approval_id": str(approval.pk), "source": "ui"},
        )
        dispatch_event(EVENT_INTENT_APPROVED, intent, {"approver": request.user.username})

        messages.success(request, f"Intent '{intent.intent_id}' approved.")
        logger.info("Intent %s approved by %s via UI.", intent.intent_id, request.user.username)
        return redirect(intent.get_absolute_url())


class IntentRejectView(View):
    """Handle reject POST from the intent detail page."""

    http_method_names = ["post"]

    def post(self, request, pk):
        """Create a rejection record and redirect back to the intent detail."""
        from intent_networking.events import EVENT_INTENT_REJECTED, dispatch_event

        intent = get_object_or_404(Intent, pk=pk)

        if not request.user.has_perm("intent_networking.approve_intent"):
            messages.error(request, "You do not have the 'approve_intent' permission.")
            return redirect(intent.get_absolute_url())

        comment = request.POST.get("comment", "")

        IntentApproval.objects.create(
            intent=intent,
            approver=request.user,
            decision="rejected",
            comment=comment,
        )
        intent.approved_by = ""
        intent.save(update_fields=["approved_by"])

        IntentAuditEntry.objects.create(
            intent=intent,
            action="rejected",
            actor=request.user.username,
            detail={"comment": comment, "source": "ui"},
        )
        dispatch_event(EVENT_INTENT_REJECTED, intent, {"rejector": request.user.username, "comment": comment})

        messages.warning(request, f"Intent '{intent.intent_id}' rejected.")
        logger.info("Intent %s rejected by %s via UI.", intent.intent_id, request.user.username)
        return redirect(intent.get_absolute_url())


# ─────────────────────────────────────────────────────────────────────────────
# Bulk Intent Actions (Dry-Run, Preview, Deploy, Validate)
# ─────────────────────────────────────────────────────────────────────────────


class _BulkIntentJobView(View):
    """Base view for bulk intent job actions from the list page.

    Subclasses set ``job_class_name``, ``action_label``, and optionally
    override ``get_extra_kwargs()`` and ``validate_intent()``.
    """

    http_method_names = ["post"]
    job_class_name = None
    action_label = "action"

    def get_extra_kwargs(self, intent):
        """Return extra keyword arguments to pass to _enqueue_job."""
        return {}

    def validate_intent(self, intent):
        """Return an error string if the intent cannot be actioned, or None."""
        return None

    def post(self, request):
        """Enqueue jobs for all selected intents and redirect back to the list."""
        from intent_networking.jobs import _enqueue_job  # noqa: PLC0415

        return_url = request.POST.get("return_url", "/plugins/intent-networking/intents/")

        pk_list = request.POST.getlist("pk")
        if not pk_list:
            messages.warning(request, "No intents were selected.")
            return redirect(return_url)

        intents = Intent.objects.filter(pk__in=pk_list)
        queued = 0
        skipped = 0
        for intent in intents:
            error = self.validate_intent(intent)  # pylint: disable=assignment-from-none
            if error:
                messages.warning(request, f"Skipped '{intent.intent_id}': {error}")
                skipped += 1
                continue
            extra = self.get_extra_kwargs(intent)
            _enqueue_job(self.job_class_name, intent_id=intent.intent_id, **extra)
            queued += 1

        if queued:
            messages.success(request, f"{self.action_label} queued for {queued} intent(s).")
        if skipped:
            messages.warning(request, f"Skipped {skipped} intent(s) — see warnings above.")
        return redirect(return_url)


class IntentBulkDryRunView(_BulkIntentJobView):
    """Bulk dry-run deploy for selected intents (commit=False)."""

    job_class_name = "IntentDeploymentJob"
    action_label = "Dry-run"

    def get_extra_kwargs(self, intent):
        """Pass commit=False for dry-run."""
        return {
            "commit_sha": intent.git_commit_sha or "dry-run",
            "commit": False,
        }


class IntentBulkPreviewView(_BulkIntentJobView):
    """Bulk config preview for selected intents."""

    job_class_name = "IntentConfigPreviewJob"
    action_label = "Config preview"


class IntentBulkDeployView(_BulkIntentJobView):
    """Bulk deploy for selected intents."""

    job_class_name = "IntentDeploymentJob"
    action_label = "Deploy"

    def validate_intent(self, intent):
        """Only allow deploy from Validated or Rolled Back status."""
        if not intent.status or intent.status.name.lower() not in ("validated", "rolled back"):
            return f"status is '{intent.status}' — must be 'Validated' or 'Rolled Back'"
        return None

    def get_extra_kwargs(self, intent):
        """Pass commit_sha for real deploy."""
        return {
            "commit_sha": intent.git_commit_sha or "manual-deploy",
        }


# ─────────────────────────────────────────────────────────────────────────────
# VXLAN VNI Pools
# ─────────────────────────────────────────────────────────────────────────────


class VxlanVniPoolUIViewSet(NautobotUIViewSet):
    """CRUD UI views for VxlanVniPool."""

    queryset = VxlanVniPool.objects.prefetch_related("tenant")
    serializer_class = VxlanVniPoolSerializer
    form_class = VxlanVniPoolForm
    table_class = VxlanVniPoolTable


class IntentBulkValidateView(_BulkIntentJobView):
    """Bulk verify for selected intents."""

    job_class_name = "IntentVerificationJob"
    action_label = "Validation"

    def get_extra_kwargs(self, intent):
        """Pass triggered_by for manual verification."""
        return {"triggered_by": "manual"}
