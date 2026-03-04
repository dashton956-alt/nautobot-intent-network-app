"""Django-tables2 table definitions for list views."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, ButtonsColumn, ColoredLabelColumn, ToggleColumn

from intent_networking.models import Intent, ResolutionPlan, VerificationResult


class IntentTable(BaseTable):
    """Table for the Intent list view."""

    pk = ToggleColumn()
    intent_id = tables.Column(linkify=True)
    tenant = tables.Column(linkify=True)
    intent_type = tables.Column(verbose_name="Type")
    status = ColoredLabelColumn()
    version = tables.Column()
    deployed_at = tables.DateTimeColumn(verbose_name="Deployed")
    last_verified_at = tables.DateTimeColumn(verbose_name="Last Verified")
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
            "deployed_at",
            "last_verified_at",
            "actions",
        ]
        default_columns = ["intent_id", "tenant", "intent_type", "status", "deployed_at"]


class ResolutionPlanTable(BaseTable):
    """Table for the Resolution Plan list view."""

    intent_version = tables.Column(verbose_name="Version")
    vrf_name = tables.Column(verbose_name="VRF")
    primitive_count = tables.Column(verbose_name="Primitives")
    resolved_at = tables.DateTimeColumn(verbose_name="Resolved")

    class Meta(BaseTable.Meta):
        """Meta options for ResolutionPlanTable."""

        model = ResolutionPlan
        fields = ["intent", "intent_version", "vrf_name", "primitive_count", "resolved_at", "resolved_by"]


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
