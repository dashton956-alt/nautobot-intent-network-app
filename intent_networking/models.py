"""All database models for the intent engine plugin.

Models:
  Intent                  — one row per intent file in Git
  ResolutionPlan          — the resolved plan for a specific intent version
  VerificationResult      — result of each verification/reconciliation check
  RouteDistinguisherPool  — pool of RD values available for allocation
  RouteDistinguisher      — individual RD allocation (device + VRF)
  RouteTargetPool         — pool of RT values available for allocation
  RouteTarget             — individual RT allocation (intent-level)
"""

from django.db import models
from nautobot.apps.models import PrimaryModel, extras_features
from nautobot.core.models import BaseModel
from nautobot.extras.models import GitRepository, StatusField
from nautobot.tenancy.models import Tenant

# ────────────────────────────────────────────────────────────────────────────
# Choices
# ────────────────────────────────────────────────────────────────────────────


class IntentTypeChoices(models.TextChoices):
    """Allowed values for the intent_type field."""

    CONNECTIVITY = "connectivity", "Connectivity"
    SECURITY = "security", "Security"
    REACHABILITY = "reachability", "Reachability"
    SERVICE = "service", "Service"


# ────────────────────────────────────────────────────────────────────────────
# Core Intent Model
# ────────────────────────────────────────────────────────────────────────────


@extras_features("custom_links", "custom_validators", "export_templates", "graphql", "webhooks")
class Intent(PrimaryModel):  # pylint: disable=too-many-ancestors
    """The central record for a network intent.

    One row per intent file in the network-as-code Git repo.
    Created/updated automatically when Nautobot syncs a GitRepository
    that provides "intent definitions" content, or via the legacy
    ``sync-from-git`` REST endpoint for CI-driven workflows.

    The intent_data field holds the complete parsed YAML as JSON so nothing
    is lost — all fields from the original file are preserved even if they
    don't have dedicated columns here.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    intent_id = models.CharField(
        max_length=200,
        unique=True,
        db_index=True,
        help_text="Matches the 'id' field in the YAML file. e.g. fin-pci-connectivity-001",
    )
    version = models.PositiveIntegerField(
        default=1, help_text="Intent version number. Incremented when the YAML changes."
    )
    intent_type = models.CharField(
        max_length=50,
        choices=IntentTypeChoices.choices,
        db_index=True,
    )

    # ── Ownership ─────────────────────────────────────────────────────────
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,  # PROTECT not CASCADE — never silently delete intents
        related_name="intents",
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────
    # Statuses managed in Nautobot admin:
    # draft → validated → deploying → deployed → failed → rolled_back → deprecated
    status = StatusField()

    # ── Raw intent data ───────────────────────────────────────────────────
    intent_data = models.JSONField(
        help_text="Full parsed YAML stored as JSON. Single source of truth "
        "for all intent fields not promoted to top-level columns."
    )

    # ── Change governance ─────────────────────────────────────────────────
    change_ticket = models.CharField(max_length=50, blank=True, help_text="Change ticket reference e.g. CHG0012345")
    approved_by = models.CharField(max_length=200, blank=True, help_text="GitHub username of PR approver")
    git_commit_sha = models.CharField(
        max_length=40, blank=True, help_text="Git commit SHA that triggered the most recent deployment"
    )
    git_branch = models.CharField(max_length=200, blank=True)
    git_pr_number = models.PositiveIntegerField(null=True, blank=True)
    git_repository = models.ForeignKey(
        GitRepository,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intents",
        help_text="Nautobot GitRepository that manages this intent (set automatically on sync)",
    )

    # ── Timestamps ────────────────────────────────────────────────────────
    # created / last_updated come free from Nautobot's PrimaryModel
    deployed_at = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Meta options for the Intent model."""

        ordering = ["-created"]
        verbose_name = "Intent"
        verbose_name_plural = "Intents"
        permissions = [
            ("approve_intent", "Can approve intents for deployment"),
            ("deploy_intent", "Can trigger intent deployment"),
            ("rollback_intent", "Can trigger intent rollback"),
        ]

    def __str__(self):
        """Return intent ID, version and status as a string."""
        return f"{self.intent_id} v{self.version} [{self.status}]"

    @property
    def is_deployed(self):
        """Return True if intent status name is 'deployed'."""
        return self.status and self.status.name.lower() == "deployed"

    @property
    def latest_plan(self):
        """Return the most recent ResolutionPlan for the current version."""
        return self.resolution_plans.filter(intent_version=self.version).order_by("-resolved_at").first()

    @property
    def latest_verification(self):
        """Return the most recent VerificationResult for this intent."""
        return self.verifications.order_by("-verified_at").first()


# ────────────────────────────────────────────────────────────────────────────
# Resolution Plan
# ────────────────────────────────────────────────────────────────────────────


class ResolutionPlan(BaseModel):
    """The normalized output of the intent resolver for a specific intent version.

    Stored so N8N can retrieve it without re-resolving, giving idempotency —
    if N8N calls /deploy twice for the same commit, both calls get the same
    plan with the same RD/RT allocations.

    unique_together on (intent, intent_version) enforces one plan per version.
    """

    intent = models.ForeignKey(
        Intent,
        on_delete=models.CASCADE,
        related_name="resolution_plans",
    )
    intent_version = models.PositiveIntegerField()

    # ── Plan content ──────────────────────────────────────────────────────
    primitives = models.JSONField(
        default=list,
        help_text="List of vendor-neutral primitive dicts (VrfPrimitive, BgpNeighborPrimitive, AclPrimitive, ...)",
    )
    affected_devices = models.ManyToManyField(
        "dcim.Device",
        related_name="intent_resolutions",
        blank=True,
        help_text="Nautobot Device objects this plan modifies. "
        "Used for conflict detection and device detail page display.",
    )

    # ── VRF metadata ──────────────────────────────────────────────────────
    vrf_name = models.CharField(max_length=100, blank=True)
    requires_new_vrf = models.BooleanField(default=False)
    requires_mpls = models.BooleanField(default=False)

    # ── Resource allocations made during resolution ───────────────────────
    # Stored here so they can be retrieved without re-querying allocation tables
    allocated_rds = models.JSONField(default=dict, help_text="Maps device_name → route_distinguisher string")
    allocated_rts = models.JSONField(default=dict, help_text="{'export': '65000:100', 'import': '65000:100'}")

    # ── Audit ─────────────────────────────────────────────────────────────
    resolved_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.CharField(
        max_length=200, blank=True, help_text="Job name or username that triggered resolution"
    )

    class Meta:
        """Meta options for the ResolutionPlan model."""

        unique_together = [("intent", "intent_version")]
        ordering = ["-resolved_at"]
        verbose_name = "Resolution Plan"
        verbose_name_plural = "Resolution Plans"

    def __str__(self):
        """Return plan description string."""
        return f"Plan for {self.intent.intent_id} v{self.intent_version}"

    @property
    def affected_device_names(self):
        """Return sorted list of device names in this plan."""
        return list(self.affected_devices.values_list("name", flat=True))

    @property
    def primitive_count(self):
        """Return number of primitives in this plan."""
        return len(self.primitives)


# ────────────────────────────────────────────────────────────────────────────
# Verification Result
# ────────────────────────────────────────────────────────────────────────────


class VerificationResult(BaseModel):
    """Records the result of a single verification run against a deployed intent.

    Created by IntentVerificationJob (post-deployment) and
    IntentReconciliationJob (hourly). Multiple rows per intent — one per run.
    """

    intent = models.ForeignKey(
        Intent,
        on_delete=models.CASCADE,
        related_name="verifications",
    )

    # ── Result ────────────────────────────────────────────────────────────
    verified_at = models.DateTimeField(auto_now_add=True)
    passed = models.BooleanField()
    triggered_by = models.CharField(
        max_length=50, default="deployment", help_text="deployment | reconciliation | manual"
    )

    # ── Individual checks ─────────────────────────────────────────────────
    checks = models.JSONField(default=list, help_text="List of {device, check_name, passed, detail} dicts")

    # ── SLA measurements ──────────────────────────────────────────────────
    measured_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    bgp_sessions_expected = models.PositiveIntegerField(default=0)
    bgp_sessions_established = models.PositiveIntegerField(default=0)
    prefixes_expected = models.PositiveIntegerField(default=0)
    prefixes_received = models.PositiveIntegerField(default=0)

    # ── Drift detail ──────────────────────────────────────────────────────
    drift_details = models.JSONField(
        default=dict, blank=True, help_text="Populated when drift is detected. Maps device_name → diff"
    )
    remediation_triggered = models.BooleanField(default=False)
    github_issue_url = models.URLField(
        blank=True, help_text="GitHub issue raised for manual review (if non-auto-remediable drift)"
    )

    class Meta:
        """Meta options for the VerificationResult model."""

        ordering = ["-verified_at"]
        verbose_name = "Verification Result"
        verbose_name_plural = "Verification Results"

    def __str__(self):
        """Return intent ID, pass/fail result and verification timestamp."""
        result = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{self.intent.intent_id} — {result} @ {self.verified_at:%Y-%m-%d %H:%M}"

    @property
    def bgp_health_pct(self):
        """Return BGP session health as an integer percentage."""
        if self.bgp_sessions_expected == 0:
            return 100
        return int(self.bgp_sessions_established / self.bgp_sessions_expected * 100)


# ────────────────────────────────────────────────────────────────────────────
# Resource Allocation — Route Distinguishers
# ────────────────────────────────────────────────────────────────────────────


class RouteDistinguisherPool(BaseModel):
    """A pre-defined pool of RD values to allocate from.

    Create one per ASN range in Nautobot admin before using the plugin.
    e.g. name="provider-rd-pool", asn=65000, range_start=1, range_end=65535
    """

    name = models.CharField(max_length=100, unique=True)
    asn = models.PositiveIntegerField(help_text="BGP ASN for the RD prefix e.g. 65000")
    range_start = models.PositiveIntegerField(help_text="First value in pool e.g. 1")
    range_end = models.PositiveIntegerField(help_text="Last value in pool e.g. 65535")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Tenant-specific pool. Leave blank for shared pool.",
    )

    class Meta:
        """Meta options for the RouteDistinguisherPool model."""

        verbose_name = "Route Distinguisher Pool"
        verbose_name_plural = "Route Distinguisher Pools"

    def __str__(self):
        """Return pool name with ASN range."""
        return f"{self.name} ({self.asn}:{self.range_start}-{self.range_end})"

    @property
    def utilisation_pct(self):
        """Return percentage of pool values currently allocated."""
        allocated = RouteDistinguisher.objects.filter(pool=self).count()
        total = self.range_end - self.range_start + 1
        return int(allocated / total * 100)


class RouteDistinguisher(BaseModel):
    """A single RD allocation. One row per device per VRF.

    Allocated atomically by the resolver using select_for_update().
    """

    pool = models.ForeignKey(RouteDistinguisherPool, on_delete=models.PROTECT, related_name="allocations")
    value = models.CharField(max_length=50, unique=True, help_text="e.g. 65000:7823")
    device = models.ForeignKey("dcim.Device", on_delete=models.PROTECT, related_name="route_distinguishers")
    vrf_name = models.CharField(max_length=100)
    intent = models.ForeignKey(Intent, on_delete=models.PROTECT, related_name="allocated_rds")
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for the RouteDistinguisher model."""

        unique_together = [("device", "vrf_name")]
        verbose_name = "Route Distinguisher"
        verbose_name_plural = "Route Distinguishers"

    def __str__(self):
        """Return RD value with device and VRF name."""
        return f"{self.value} → {self.device.name}/{self.vrf_name}"


# ────────────────────────────────────────────────────────────────────────────
# Resource Allocation — Route Targets
# ────────────────────────────────────────────────────────────────────────────


class RouteTargetPool(BaseModel):
    """Pool of RT values for allocation. Same concept as RD pool."""

    name = models.CharField(max_length=100, unique=True)
    asn = models.PositiveIntegerField()
    range_start = models.PositiveIntegerField()
    range_end = models.PositiveIntegerField()

    class Meta:
        """Meta options for the RouteTargetPool model."""

        verbose_name = "Route Target Pool"
        verbose_name_plural = "Route Target Pools"

    def __str__(self):
        """Return pool name with ASN range."""
        return f"{self.name} ({self.asn}:{self.range_start}-{self.range_end})"


class RouteTarget(BaseModel):
    """A single RT allocation shared across all devices implementing an intent.

    One row per intent — unlike RDs which are per-device.
    """

    pool = models.ForeignKey(RouteTargetPool, on_delete=models.PROTECT, related_name="allocations")
    value = models.CharField(max_length=50, unique=True)
    intent = models.OneToOneField(Intent, on_delete=models.PROTECT, related_name="allocated_rt")
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for the RouteTarget model."""

        verbose_name = "Route Target"
        verbose_name_plural = "Route Targets"

    def __str__(self):
        """Return RT value with intent ID."""
        return f"{self.value} → {self.intent.intent_id}"
