"""API serializers for intent_networking."""

from nautobot.apps.api import NautobotModelSerializer
from rest_framework import serializers

from intent_networking.models import (
    DeploymentStage,
    Intent,
    IntentApproval,
    IntentAuditEntry,
    ResolutionPlan,
    VerificationResult,
)


class IntentSerializer(NautobotModelSerializer):
    """Serializer for the Intent model."""

    latest_plan_id = serializers.SerializerMethodField()
    latest_verification_passed = serializers.SerializerMethodField()
    is_approved = serializers.BooleanField(read_only=True)
    has_resource_conflicts = serializers.BooleanField(read_only=True)

    def get_latest_plan_id(self, obj):
        """Return the primary key of the latest resolution plan, or None."""
        plan = obj.latest_plan
        return str(plan.pk) if plan else None

    def get_latest_verification_passed(self, obj):
        """Return passed status of the latest verification, or None."""
        v = obj.latest_verification
        return v.passed if v else None

    class Meta:
        """Meta options for IntentSerializer."""

        model = Intent
        fields = "__all__"


class IntentApprovalSerializer(NautobotModelSerializer):
    """Serializer for the IntentApproval model."""

    approver_username = serializers.CharField(source="approver.username", read_only=True)

    class Meta:
        """Meta options for IntentApprovalSerializer."""

        model = IntentApproval
        fields = [
            "id",
            "url",
            "intent",
            "approver",
            "approver_username",
            "decision",
            "comment",
            "decided_at",
        ]


class IntentAuditEntrySerializer(NautobotModelSerializer):
    """Serializer for the IntentAuditEntry model (read-only)."""

    class Meta:
        """Meta options for IntentAuditEntrySerializer."""

        model = IntentAuditEntry
        fields = [
            "id",
            "url",
            "intent",
            "action",
            "actor",
            "timestamp",
            "detail",
            "git_commit_sha",
            "job_result_id",
        ]


class DeploymentStageSerializer(NautobotModelSerializer):
    """Serializer for the DeploymentStage model (read-only)."""

    location_name = serializers.CharField(source="location.name", read_only=True, default=None)
    device_names = serializers.SerializerMethodField()

    def get_device_names(self, obj):
        """Return list of device names in this stage."""
        return list(obj.devices.values_list("name", flat=True))

    class Meta:
        """Meta options for DeploymentStageSerializer."""

        model = DeploymentStage
        fields = [
            "id",
            "url",
            "intent",
            "stage_order",
            "location",
            "location_name",
            "devices",
            "device_names",
            "status",
            "started_at",
            "completed_at",
            "rendered_configs",
        ]


class ResolutionPlanSerializer(NautobotModelSerializer):
    """Serializer for the ResolutionPlan model."""

    affected_devices = serializers.SerializerMethodField()
    primitive_count = serializers.IntegerField(read_only=True)

    def get_affected_devices(self, obj):
        """Return list of device names in this plan."""
        return list(obj.affected_devices.values_list("name", flat=True))

    class Meta:
        """Meta options for ResolutionPlanSerializer."""

        model = ResolutionPlan
        fields = "__all__"


class VerificationResultSerializer(NautobotModelSerializer):
    """Serializer for the VerificationResult model."""

    bgp_health_pct = serializers.IntegerField(read_only=True)

    class Meta:
        """Meta options for VerificationResultSerializer."""

        model = VerificationResult
        fields = "__all__"


class SyncFromGitSerializer(serializers.Serializer):
    """Input for the sync-from-git endpoint."""

    intent_data = serializers.JSONField(required=True)
    git_commit_sha = serializers.CharField(required=False, default="")
    git_branch = serializers.CharField(required=False, default="")
    git_pr_number = serializers.IntegerField(required=False, allow_null=True)


class DeploySerializer(serializers.Serializer):
    """Input for the deploy endpoint."""

    commit_sha = serializers.CharField(required=True)
    dry_run = serializers.BooleanField(default=False)
