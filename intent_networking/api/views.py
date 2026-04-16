"""API views for intent_networking.

Provides REST endpoints for the full intent lifecycle including:
  - CRUD operations on intents
  - Sync from Git (legacy CI mode)
  - Resolve, Deploy, Verify, Rollback actions
  - Approval workflow (#2)
  - Config preview / dry-run (#1)
  - Conflict detection (#6)
  - Audit trail (#4)
  - Change window / scheduling (#9)
  - Bulk operations
"""

import json
import logging

from django.utils import timezone
from nautobot.apps.api import NautobotModelViewSet
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from intent_networking import filters
from intent_networking.api.serializers import (
    DeploySerializer,
    IntentSerializer,
    ResolutionPlanSerializer,
    SyncFromGitSerializer,
    VerificationResultSerializer,
)
from intent_networking.events import (
    EVENT_INTENT_APPROVED,
    EVENT_INTENT_REJECTED,
    EVENT_INTENT_SCHEDULED,
    dispatch_event,
)
from intent_networking.jobs import _enqueue_job
from intent_networking.models import (
    Intent,
    IntentApproval,
    IntentAuditEntry,
    ResolutionPlan,
    VerificationResult,
    detect_conflicts,
    validate_tenant_isolation,
)

logger = logging.getLogger(__name__)


class IntentViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """ViewSet for Intent CRUD and lifecycle actions."""

    queryset = Intent.objects.all().select_related("tenant", "status")
    serializer_class = IntentSerializer
    filterset_class = filters.IntentFilterSet

    # ── Sync from Git ──────────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="sync-from-git")
    def sync_from_git(self, request):
        """Create or update an intent from a parsed YAML payload (legacy push mode).

        POST /api/plugins/intent-networking/intents/sync-from-git/
        """
        ser = SyncFromGitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        intent_data = ser.validated_data["intent_data"]
        intent_id = intent_data.get("id")

        if not intent_id:
            return Response({"error": "intent_data must contain an 'id' field"}, status=status.HTTP_400_BAD_REQUEST)

        job_kwargs = {
            "intent_id": intent_id,
            "intent_data": json.dumps(intent_data),
            "git_commit_sha": ser.validated_data.get("git_commit_sha", ""),
            "git_branch": ser.validated_data.get("git_branch", ""),
            "git_pr_number": str(ser.validated_data.get("git_pr_number", "")),
        }
        _enqueue_job("IntentSyncFromGitJob", **job_kwargs)

        return Response({"intent_id": intent_id, "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    # ── Resolve ────────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/resolve/."""
        if not request.user.has_perm("intent_networking.change_intent"):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        intent = self.get_object()
        force = request.data.get("force_re_resolve", False)

        _enqueue_job("IntentResolutionJob", intent_id=intent.intent_id, force_re_resolve=force)

        return Response(
            {"intent_id": intent.intent_id, "status": "queued"},
            status=status.HTTP_202_ACCEPTED,
        )

    # ── Config Preview (#1) ───────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="preview")
    def preview(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/preview/.

        Triggers a config render job. Results are cached on the intent.
        """
        intent = self.get_object()

        if not intent.latest_plan:
            return Response(
                {"error": "No resolution plan found — resolve first."},
                status=status.HTTP_409_CONFLICT,
            )

        _enqueue_job("IntentConfigPreviewJob", intent_id=intent.intent_id)

        return Response(
            {
                "intent_id": intent.intent_id,
                "status": "preview_queued",
                "cached_configs": intent.rendered_configs or {},
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="rendered-configs")
    def rendered_configs(self, request, pk=None):  # pylint: disable=unused-argument
        """GET /api/plugins/intent-networking/intents/{id}/rendered-configs/.

        Returns the cached rendered device configs from the last preview.
        """
        intent = self.get_object()
        return Response(
            {
                "intent_id": intent.intent_id,
                "rendered_configs": intent.rendered_configs or {},
            }
        )

    # ── Approve (#2) ──────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/approve/.

        Creates an IntentApproval record. Requires ``approve_intent`` perm.
        Body: ``{"comment": "optional reason"}``
        """
        if not request.user.has_perm("intent_networking.approve_intent"):
            return Response({"error": "approve_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        intent = self.get_object()
        comment = request.data.get("comment", "")

        from intent_networking.opa_client import check_approval_gate  # pylint: disable=import-outside-toplevel

        gate = check_approval_gate(intent)
        if not gate["allowed"]:
            return Response(
                {
                    "error": "OPA compliance check failed — approval blocked.",
                    "violations": gate["violations"],
                    "hint": "Resolve the policy violations or set require_opa_for_approval=False in plugin config.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        approval = IntentApproval.objects.create(
            intent=intent,
            approver=request.user,
            decision="approved",
            comment=comment,
        )

        # Legacy field for backward compat
        intent.approved_by = request.user.username
        intent.save(update_fields=["approved_by"])

        IntentAuditEntry.objects.create(
            intent=intent,
            action="approved",
            actor=request.user.username,
            detail={"comment": comment, "approval_id": str(approval.pk)},
        )
        dispatch_event(EVENT_INTENT_APPROVED, intent, {"approver": request.user.username})

        return Response(
            {
                "intent_id": intent.intent_id,
                "approved_by": request.user.username,
                "decision": "approved",
                "approval_id": str(approval.pk),
            }
        )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/reject/.

        Records a rejection. Blocks deployment.
        Body: ``{"comment": "reason for rejection"}``
        """
        if not request.user.has_perm("intent_networking.approve_intent"):
            return Response({"error": "approve_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        intent = self.get_object()
        comment = request.data.get("comment", "")

        IntentApproval.objects.create(
            intent=intent,
            approver=request.user,
            decision="rejected",
            comment=comment,
        )

        # Clear legacy field
        intent.approved_by = ""
        intent.save(update_fields=["approved_by"])

        IntentAuditEntry.objects.create(
            intent=intent,
            action="rejected",
            actor=request.user.username,
            detail={"comment": comment},
        )
        dispatch_event(EVENT_INTENT_REJECTED, intent, {"rejector": request.user.username, "comment": comment})

        return Response({"intent_id": intent.intent_id, "decision": "rejected"})

    # ── Deploy ─────────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="deploy")
    def deploy(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/deploy/.

        Enforced approval gate (#2) — will not proceed without approval.
        Respects scheduled_deploy_at (#9).
        """
        if not request.user.has_perm("intent_networking.deploy_intent"):
            return Response({"error": "deploy_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        intent = self.get_object()

        # Approval gate (#2)
        if not intent.is_approved:
            return Response(
                {
                    "error": (
                        "Intent must be approved before deployment. "
                        "Use the /approve/ endpoint first. "
                        "Requires a user with 'approve_intent' permission."
                    ),
                    "approvals": list(
                        intent.approvals.values("approver__username", "decision", "decided_at", "comment")
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        ser = DeploySerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        dry_run = ser.validated_data["dry_run"]

        if not intent.status or intent.status.name.lower() not in ("validated", "rolled back"):
            return Response(
                {"error": f"Intent is in status '{intent.status}'. Must be 'validated' or 'rolled_back' to deploy."},
                status=status.HTTP_409_CONFLICT,
            )

        _enqueue_job(
            "IntentDeploymentJob",
            intent_id=intent.intent_id,
            commit_sha=ser.validated_data["commit_sha"],
            commit=not dry_run,
        )

        return Response(
            {"intent_id": intent.intent_id, "dry_run": dry_run, "status": "deploying"},
            status=status.HTTP_202_ACCEPTED,
        )

    # ── Schedule deployment (#9) ──────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="schedule")
    def schedule(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/schedule/.

        Body: ``{"deploy_at": "2026-03-15T02:00:00Z", "commit_sha": "abc123"}``
        Sets scheduled_deploy_at. The deployment job honours this timestamp.
        """
        if not request.user.has_perm("intent_networking.deploy_intent"):
            return Response({"error": "deploy_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        intent = self.get_object()
        deploy_at_str = request.data.get("deploy_at")
        commit_sha = request.data.get("commit_sha", "scheduled-deploy")

        if not deploy_at_str:
            return Response({"error": "'deploy_at' is required (ISO 8601 format)"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            deploy_at = drf_serializers.DateTimeField().to_internal_value(deploy_at_str)
        except Exception:
            return Response({"error": "Invalid datetime format. Use ISO 8601."}, status=status.HTTP_400_BAD_REQUEST)

        if deploy_at <= timezone.now():
            return Response({"error": "deploy_at must be in the future"}, status=status.HTTP_400_BAD_REQUEST)

        intent.scheduled_deploy_at = deploy_at
        intent.save(update_fields=["scheduled_deploy_at"])

        IntentAuditEntry.objects.create(
            intent=intent,
            action="scheduled",
            actor=request.user.username,
            detail={"deploy_at": str(deploy_at), "commit_sha": commit_sha},
        )
        dispatch_event(EVENT_INTENT_SCHEDULED, intent, {"deploy_at": str(deploy_at)})

        return Response(
            {
                "intent_id": intent.intent_id,
                "scheduled_deploy_at": str(deploy_at),
            }
        )

    # ── Conflicts (#6) ────────────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="conflicts")
    def conflicts(self, request, pk=None):  # pylint: disable=unused-argument
        """GET /api/plugins/intent-networking/intents/{id}/conflicts/.

        Returns any resource conflicts with other active intents.
        """
        intent = self.get_object()
        conflict_list = detect_conflicts(intent)
        tenant_warnings = validate_tenant_isolation(intent)

        return Response(
            {
                "intent_id": intent.intent_id,
                "conflicts": conflict_list,
                "tenant_warnings": tenant_warnings,
                "has_conflicts": bool(conflict_list),
            }
        )

    # ── Audit trail (#4) ─────────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="audit-trail")
    def audit_trail(self, request, pk=None):  # pylint: disable=unused-argument
        """GET /api/plugins/intent-networking/intents/{id}/audit-trail/.

        Returns the complete immutable audit trail for this intent.
        """
        intent = self.get_object()
        entries = intent.audit_trail.order_by("-timestamp")[:200]

        data = [
            {
                "id": str(e.pk),
                "action": e.action,
                "actor": e.actor,
                "timestamp": e.timestamp.isoformat(),
                "detail": e.detail,
                "git_commit_sha": e.git_commit_sha,
                "job_result_id": str(e.job_result_id) if e.job_result_id else None,
            }
            for e in entries
        ]

        return Response({"intent_id": intent.intent_id, "audit_trail": data})

    # ── Status ─────────────────────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="status")
    def deployment_status(self, request, pk=None):  # pylint: disable=unused-argument
        """GET /api/plugins/intent-networking/intents/{id}/status/."""
        intent = self.get_object()
        plan = intent.latest_plan
        verif = intent.latest_verification

        return Response(
            {
                "intent_id": intent.intent_id,
                "version": intent.version,
                "status": str(intent.status),
                "is_approved": intent.is_approved,
                "deployed_at": intent.deployed_at,
                "last_verified_at": intent.last_verified_at,
                "scheduled_deploy_at": intent.scheduled_deploy_at,
                "deployment_strategy": intent.deployment_strategy,
                "has_conflicts": intent.has_resource_conflicts,
                "plan": ResolutionPlanSerializer(plan).data if plan else None,
                "latest_verification": VerificationResultSerializer(verif).data if verif else None,
            }
        )

    # ── Rollback ───────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="rollback")
    def rollback(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/rollback/."""
        if not request.user.has_perm("intent_networking.rollback_intent"):
            return Response({"error": "rollback_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        intent = self.get_object()
        _enqueue_job("IntentRollbackJob", intent_id=intent.intent_id)

        return Response(
            {"intent_id": intent.intent_id, "status": "rolling_back"},
            status=status.HTTP_202_ACCEPTED,
        )

    # ── Retire ─────────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="retire")
    def retire(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/retire/.

        Retires an intent by removing its configuration from devices,
        releasing allocated resources, and marking it as Retired.

        Body: ``{"dry_run": false}``
        """
        if not request.user.has_perm("intent_networking.deploy_intent"):
            return Response({"error": "deploy_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        intent = self.get_object()
        dry_run = request.data.get("dry_run", False)

        allowed_statuses = {"deployed", "failed", "rolled back", "validated", "draft"}
        current_status = intent.status.name.lower() if intent.status else ""
        if current_status not in allowed_statuses:
            return Response(
                {
                    "error": f"Intent is in status '{intent.status}'. "
                    f"Can only retire from: {', '.join(sorted(allowed_statuses))}."
                },
                status=status.HTTP_409_CONFLICT,
            )

        _enqueue_job("IntentRetireJob", intent_id=intent.intent_id, commit=not dry_run)

        return Response(
            {"intent_id": intent.intent_id, "dry_run": dry_run, "status": "retiring"},
            status=status.HTTP_202_ACCEPTED,
        )

    # ── Verification history / trending (#11) ─────────────────────────────

    @action(detail=True, methods=["get"], url_path="verifications")
    def verifications(self, request, pk=None):  # pylint: disable=unused-argument
        """GET /api/plugins/intent-networking/intents/{id}/verifications/."""
        intent = self.get_object()
        results = intent.verifications.order_by("-verified_at")[:50]
        return Response(VerificationResultSerializer(results, many=True).data)

    @action(detail=True, methods=["get"], url_path="verification-trend")
    def verification_trend(self, request, pk=None):  # pylint: disable=unused-argument
        """GET /api/plugins/intent-networking/intents/{id}/verification-trend/.

        Returns latency and pass/fail data points for trending charts (#11).
        """
        intent = self.get_object()
        results = intent.verifications.order_by("verified_at")[:200]

        data = [
            {
                "verified_at": r.verified_at.isoformat(),
                "passed": r.passed,
                "latency_ms": r.measured_latency_ms,
                "bgp_health_pct": r.bgp_health_pct,
            }
            for r in results
        ]

        return Response({"intent_id": intent.intent_id, "trend": data})

    # ── Deployment stages (#10) ───────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="stages")
    def stages(self, request, pk=None):  # pylint: disable=unused-argument
        """GET /api/plugins/intent-networking/intents/{id}/stages/.

        Returns staged deployment progress for canary/rolling rollouts.
        """
        intent = self.get_object()
        stages_qs = intent.deployment_stages.order_by("stage_order")

        data = [
            {
                "stage_order": s.stage_order,
                "location": s.location.name if s.location else None,
                "status": s.status,
                "devices": list(s.devices.values_list("name", flat=True)),
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in stages_qs
        ]

        return Response({"intent_id": intent.intent_id, "stages": data})

    # ── Bulk operations ───────────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="bulk-resolve")
    def bulk_resolve(self, request):
        """POST /api/plugins/intent-networking/intents/bulk-resolve/."""
        intent_ids = request.data.get("intent_ids", [])
        if not intent_ids:
            return Response({"error": "intent_ids list is required"}, status=status.HTTP_400_BAD_REQUEST)

        queued = []
        for iid in intent_ids:
            _enqueue_job("IntentResolutionJob", intent_id=iid)
            queued.append(iid)

        return Response({"queued": queued}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="bulk-deploy")
    def bulk_deploy(self, request):
        """POST /api/plugins/intent-networking/intents/bulk-deploy/."""
        if not request.user.has_perm("intent_networking.deploy_intent"):
            return Response({"error": "deploy_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        intent_ids = request.data.get("intent_ids", [])
        commit_sha = request.data.get("commit_sha", "bulk-deploy")

        if not intent_ids:
            return Response({"error": "intent_ids list is required"}, status=status.HTTP_400_BAD_REQUEST)

        queued = []
        skipped = []
        for iid in intent_ids:
            try:
                intent = Intent.objects.get(intent_id=iid)
                if not intent.is_approved:
                    skipped.append({"intent_id": iid, "reason": "not approved"})
                    continue
            except Intent.DoesNotExist:
                skipped.append({"intent_id": iid, "reason": "not found"})
                continue

            _enqueue_job("IntentDeploymentJob", intent_id=iid, commit_sha=commit_sha)
            queued.append(iid)

        return Response({"queued": queued, "skipped": skipped}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="bulk-verify")
    def bulk_verify(self, request):
        """POST /api/plugins/intent-networking/intents/bulk-verify/."""
        intent_ids = request.data.get("intent_ids", [])
        if not intent_ids:
            return Response({"error": "intent_ids list is required"}, status=status.HTTP_400_BAD_REQUEST)

        queued = []
        for iid in intent_ids:
            _enqueue_job("IntentVerificationJob", intent_id=iid, triggered_by="manual")
            queued.append(iid)

        return Response({"queued": queued}, status=status.HTTP_202_ACCEPTED)


class ResolutionPlanViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """Read-only viewset for ResolutionPlan — plans are created by jobs."""

    queryset = ResolutionPlan.objects.all().select_related("intent")
    serializer_class = ResolutionPlanSerializer
    http_method_names = ["get", "head", "options"]


class VerificationResultViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """Read-only viewset for VerificationResult — results are created by jobs."""

    queryset = VerificationResult.objects.all().select_related("intent")
    serializer_class = VerificationResultSerializer
    http_method_names = ["get", "head", "options"]
