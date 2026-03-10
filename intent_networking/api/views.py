"""API views for intent_networking."""

import json
import logging

from nautobot.apps.api import NautobotModelViewSet
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
from intent_networking.jobs import (
    _enqueue_job,
)
from intent_networking.models import Intent, ResolutionPlan, VerificationResult

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

        Note: The preferred approach is to use Nautobot's native GitRepository
        integration (Extensibility → Git Repositories) with the "intent definitions"
        content type.  This endpoint is kept for backward-compatible CI pipelines.
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
            {
                "intent_id": intent.intent_id,
                "status": "queued",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    # ── Deploy ─────────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="deploy")
    def deploy(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/deploy/."""
        if not request.user.has_perm("intent_networking.deploy_intent"):
            return Response({"error": "deploy_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        # ── Approval gate (#10) ──────────────────────────────────────────
        intent = self.get_object()
        if not intent.approved_by:
            return Response(
                {"error": ("Intent must be approved before deployment. Set 'approved_by' via the UI or API first.")},
                status=status.HTTP_409_CONFLICT,
            )

        ser = DeploySerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        dry_run = ser.validated_data["dry_run"]

        if not intent.status or intent.status.name.lower() not in ("validated", "rolled back"):
            return Response(
                {"error": (f"Intent is in status '{intent.status}'. Must be 'validated' or 'rolled_back' to deploy.")},
                status=status.HTTP_409_CONFLICT,
            )

        _enqueue_job(
            "IntentDeploymentJob",
            intent_id=intent.intent_id,
            commit_sha=ser.validated_data["commit_sha"],
            commit=not dry_run,
        )

        return Response(
            {
                "intent_id": intent.intent_id,
                "dry_run": dry_run,
                "status": "deploying",
            },
            status=status.HTTP_202_ACCEPTED,
        )

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
                "deployed_at": intent.deployed_at,
                "last_verified_at": intent.last_verified_at,
                "plan": ResolutionPlanSerializer(plan).data if plan else None,
                "latest_verification": (VerificationResultSerializer(verif).data if verif else None),
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
            {
                "intent_id": intent.intent_id,
                "status": "rolling_back",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    # ── Verification history ───────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="verifications")
    def verifications(self, request, pk=None):  # pylint: disable=unused-argument
        """GET /api/plugins/intent-networking/intents/{id}/verifications/."""
        intent = self.get_object()
        results = intent.verifications.order_by("-verified_at")[:50]
        return Response(VerificationResultSerializer(results, many=True).data)

    # ── Approve (#10) ─────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):  # pylint: disable=unused-argument
        """POST /api/plugins/intent-networking/intents/{id}/approve/.

        Records the approving user and returns the updated intent.
        Requires the ``approve_intent`` permission.
        """
        if not request.user.has_perm("intent_networking.approve_intent"):
            return Response({"error": "approve_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        intent = self.get_object()
        intent.approved_by = request.user.username
        intent.save(update_fields=["approved_by"])

        return Response({"intent_id": intent.intent_id, "approved_by": intent.approved_by})

    # ── Bulk operations (#13) ─────────────────────────────────────────────

    @action(detail=False, methods=["post"], url_path="bulk-resolve")
    def bulk_resolve(self, request):
        """POST /api/plugins/intent-networking/intents/bulk-resolve/.

        Body: ``{"intent_ids": ["id-1", "id-2", ...]}``
        Queues a resolution job for each intent.
        """
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
        """POST /api/plugins/intent-networking/intents/bulk-deploy/.

        Body: ``{"intent_ids": ["id-1", ...], "commit_sha": "abc123"}``
        Queues a deployment job for each intent.
        """
        if not request.user.has_perm("intent_networking.deploy_intent"):
            return Response({"error": "deploy_intent permission required"}, status=status.HTTP_403_FORBIDDEN)

        intent_ids = request.data.get("intent_ids", [])
        commit_sha = request.data.get("commit_sha", "bulk-deploy")

        if not intent_ids:
            return Response({"error": "intent_ids list is required"}, status=status.HTTP_400_BAD_REQUEST)

        queued = []
        for iid in intent_ids:
            _enqueue_job("IntentDeploymentJob", intent_id=iid, commit_sha=commit_sha)
            queued.append(iid)

        return Response({"queued": queued}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="bulk-verify")
    def bulk_verify(self, request):
        """POST /api/plugins/intent-networking/intents/bulk-verify/.

        Body: ``{"intent_ids": ["id-1", ...]}``
        Queues a verification job for each intent.
        """
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
