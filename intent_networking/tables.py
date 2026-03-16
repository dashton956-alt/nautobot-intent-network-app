"""Django-tables2 table definitions for list views."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, ButtonsColumn, ColoredLabelColumn, ToggleColumn

from intent_networking.models import (
    Intent,
    IntentApproval,
    IntentAuditEntry,
    ResolutionPlan,
    VerificationResult,
)


class IntentTable(BaseTable):
    """Table for the Intent list view."""

    pk = ToggleColumn()
    intent_id = tables.Column(linkify=True)
    tenant = tables.Column(linkify=True)
    intent_type = tables.Column(verbose_name="Type")
    status = ColoredLabelColumn()
    version = tables.Column()
    is_approved = tables.BooleanColumn(verbose_name="Approved", orderable=False)
    deployment_strategy = tables.Column(verbose_name="Strategy")
    deployed_at = tables.DateTimeColumn(verbose_name="Deployed")
    last_verified_at = tables.DateTimeColumn(verbose_name="Last Verified")
    scheduled_deploy_at = tables.DateTimeColumn(verbose_name="Scheduled")
    actions = ButtonsColumn(Intent, buttons=("edit", "delete"))

    class Meta(BaseTable.Meta):
        """Meta options for IntentTable."""

        model = Intent
        fields = [
            "pk",
            "intent_id",
            "tenant",
            "intent_type",
            "status",
            "version",
            "is_approved",
            "deployment_strategy",
            "deployed_at",
            "last_verified_at",
            "scheduled_deploy_at",
            "actions",
        ]
        default_columns = [
            "intent_id",
            "tenant",
            "intent_type",
            "status",
            "is_approved",
            "deployed_at",
        ]


class ResolutionPlanTable(BaseTable):
    """Table for the Resolution Plan list view."""

    intent_version = tables.Column(verbose_name="Version")
    vrf_name = tables.Column(verbose_name="VRF")
    device_count = tables.Column(verbose_name="Devices", empty_values=())
    affected_devices = tables.Column(verbose_name="Affected Devices", empty_values=(), orderable=False)
    primitive_count = tables.Column(verbose_name="Primitives")
    resolved_at = tables.DateTimeColumn(verbose_name="Resolved")

    def render_device_count(self, record):
        """Render the number of affected devices."""
        return record.affected_devices.count()

    def render_affected_devices(self, record):
        """Render a comma-separated list of affected device names."""
        return ", ".join(record.affected_device_names) or "—"

    class Meta(BaseTable.Meta):
        """Meta options for ResolutionPlanTable."""

        model = ResolutionPlan
        fields = [
            "intent",
            "intent_version",
            "vrf_name",
            "device_count",
            "affected_devices",
            "primitive_count",
            "resolved_at",
            "resolved_by",
        ]


class VerificationResultTable(BaseTable):
    """Table for the Verification Result list view."""

    passed = tables.BooleanColumn(verbose_name="Passed")
    triggered_by = tables.Column(verbose_name="Trigger")
    measured_latency_ms = tables.Column(verbose_name="Latency (ms)")
    verified_at = tables.DateTimeColumn(verbose_name="Verified")

    class Meta(BaseTable.Meta):
        """Meta options for VerificationResultTable."""

        model = VerificationResult
        fields = ["intent", "passed", "triggered_by", "measured_latency_ms", "verified_at"]


# ─────────────────────────────────────────────────────────────────────────────
# Audit Trail (#4)
# ─────────────────────────────────────────────────────────────────────────────


class IntentAuditEntryTable(BaseTable):
    """Table for the Audit Trail list view."""

    intent = tables.Column(
        linkify=lambda record: record.intent.get_absolute_url(),
        accessor="intent.intent_id",
        verbose_name="Intent",
    )
    action = tables.Column()
    actor = tables.Column()
    timestamp = tables.DateTimeColumn()
    git_commit_sha = tables.Column(verbose_name="Commit SHA")

    class Meta(BaseTable.Meta):
        """Meta options for IntentAuditEntryTable."""

        model = IntentAuditEntry
        fields = ["intent", "action", "actor", "timestamp", "git_commit_sha"]
        default_columns = ["intent", "action", "actor", "timestamp"]


# ─────────────────────────────────────────────────────────────────────────────
# Approvals (#2)
# ─────────────────────────────────────────────────────────────────────────────


class IntentApprovalTable(BaseTable):
    """Table for the Approval list view."""

    intent = tables.Column(linkify=True, accessor="intent.intent_id", verbose_name="Intent")
    approver = tables.Column(accessor="approver.username", verbose_name="Approver")
    decision = tables.Column()
    comment = tables.Column()
    decided_at = tables.DateTimeColumn(verbose_name="Decided At")

    class Meta(BaseTable.Meta):
        """Meta options for IntentApprovalTable."""

        model = IntentApproval
        fields = ["intent", "approver", "decision", "comment", "decided_at"]
        default_columns = ["intent", "approver", "decision", "decided_at"]
