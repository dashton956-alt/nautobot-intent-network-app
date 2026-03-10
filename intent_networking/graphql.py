"""GraphQL type definitions for the intent_networking plugin.

Provides GraphQL query support for Intent, ResolutionPlan, and
VerificationResult models so they can be queried via Nautobot's
/api/graphql endpoint.
"""

from graphene_django import DjangoObjectType
from nautobot.ipam.models import VRF, Namespace
from nautobot.ipam.models import RouteTarget as NautobotRouteTarget

from intent_networking.filters import IntentFilterSet
from intent_networking.models import (
    Intent,
    ResolutionPlan,
    VerificationResult,
)


class IntentType(DjangoObjectType):
    """GraphQL type for Intent objects."""

    class Meta:
        """Meta options for IntentType."""

        model = Intent
        filterset_class = IntentFilterSet
        fields = [
            "id",
            "intent_id",
            "version",
            "intent_type",
            "tenant",
            "status",
            "intent_data",
            "change_ticket",
            "approved_by",
            "git_commit_sha",
            "git_branch",
            "git_pr_number",
            "git_repository",
            "deployed_at",
            "last_verified_at",
            "created",
            "last_updated",
        ]


class ResolutionPlanType(DjangoObjectType):
    """GraphQL type for ResolutionPlan objects."""

    class Meta:
        """Meta options for ResolutionPlanType."""

        model = ResolutionPlan
        fields = [
            "id",
            "intent",
            "intent_version",
            "primitives",
            "affected_devices",
            "vrf_name",
            "requires_new_vrf",
            "requires_mpls",
            "allocated_rds",
            "allocated_rts",
            "resolved_at",
            "resolved_by",
        ]


class VerificationResultType(DjangoObjectType):
    """GraphQL type for VerificationResult objects."""

    class Meta:
        """Meta options for VerificationResultType."""

        model = VerificationResult
        fields = [
            "id",
            "intent",
            "verified_at",
            "passed",
            "triggered_by",
            "checks",
            "measured_latency_ms",
            "bgp_sessions_expected",
            "bgp_sessions_established",
            "prefixes_expected",
            "prefixes_received",
            "drift_details",
            "remediation_triggered",
            "github_issue_url",
        ]


class NautobotVRFType(DjangoObjectType):
    """GraphQL type for Nautobot VRF objects."""

    class Meta:
        """Meta options for NautobotVRFType."""

        model = VRF
        fields = ["id", "name", "rd", "namespace", "tenant", "description", "created", "last_updated"]


class NautobotRouteTargetType(DjangoObjectType):
    """GraphQL type for Nautobot RouteTarget objects."""

    class Meta:
        """Meta options for NautobotRouteTargetType."""

        model = NautobotRouteTarget
        fields = ["id", "name", "description", "tenant", "created", "last_updated"]


class NautobotNamespaceType(DjangoObjectType):
    """GraphQL type for Nautobot Namespace objects."""

    class Meta:
        """Meta options for NautobotNamespaceType."""

        model = Namespace
        fields = ["id", "name", "description", "location", "tenant", "created", "last_updated"]


graphql_types = [
    IntentType,
    ResolutionPlanType,
    VerificationResultType,
    NautobotVRFType,
    NautobotRouteTargetType,
    NautobotNamespaceType,
]
