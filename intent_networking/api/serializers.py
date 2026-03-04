"""API serializers for intent_networking."""

from nautobot.apps.api import NautobotModelSerializer
from rest_framework import serializers

from intent_networking.models import Intent, ResolutionPlan, VerificationResult


class IntentSerializer(NautobotModelSerializer):
    """Serializer for the Intent model."""

    latest_plan_id = serializers.SerializerMethodField()
    latest_verification_passed = serializers.SerializerMethodField()

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
