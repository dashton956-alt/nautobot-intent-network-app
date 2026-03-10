"""All database models for the intent engine plugin.

Models:
  Intent                  — one row per intent file in Git
  IntentApproval          — explicit approval record (who, when, comment)
  IntentAuditEntry        — immutable audit trail for every lifecycle action
  DeploymentStage         — staged/canary deployment tracking
  ResolutionPlan          — the resolved plan for a specific intent version
  VerificationResult      — result of each verification/reconciliation check
  VxlanVniPool            — pool of VNI values available for allocation
  VniAllocation           — individual VNI allocation
  TunnelIdPool            — pool of tunnel interface IDs for allocation
  TunnelIdAllocation      — individual tunnel ID allocation
  ManagedLoopbackPool     — pool of /32 loopback IPs for allocation
  ManagedLoopback         — individual loopback IP allocation
  WirelessVlanPool        — pool of VLAN IDs for wireless SSID mapping
  WirelessVlanAllocation  — individual wireless VLAN allocation

RD and RT allocation now uses Nautobot's native VRF (with rd field),
Namespace and RouteTarget models from nautobot.ipam.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import models
from nautobot.apps.models import PrimaryModel, extras_features
from nautobot.core.models import BaseModel
from nautobot.extras.models import GitRepository, StatusField
from nautobot.tenancy.models import Tenant

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# Choices
# ────────────────────────────────────────────────────────────────────────────


class IntentTypeChoices(models.TextChoices):
    """Allowed values for the intent_type field.

    Covers all 14 domains: Layer 2, Layer 3, MPLS/SP, DC/EVPN/VXLAN,
    Security, WAN/SD-WAN, Wireless, Cloud/Hybrid, QoS, Multicast,
    Management, Reachability, Service, and legacy connectivity/security.
    """

    # ── Legacy / Original ─────────────────────────────────────────────────
    CONNECTIVITY = "connectivity", "Connectivity"
    SECURITY = "security", "Security"
    REACHABILITY = "reachability", "Reachability"
    SERVICE = "service", "Service"

    # ── 1. Layer 2 / Switching ────────────────────────────────────────────
    VLAN_PROVISION = "vlan_provision", "VLAN Provisioning"
    L2_ACCESS_PORT = "l2_access_port", "Access Port"
    L2_TRUNK_PORT = "l2_trunk_port", "Trunk Port"
    LAG = "lag", "Port Channel / LAG"
    MLAG = "mlag", "MLAG / MC-LAG"
    STP_POLICY = "stp_policy", "Spanning Tree Policy"
    QINQ = "qinq", "QinQ / Double Tagging"
    PVLAN = "pvlan", "Private VLAN"
    STORM_CONTROL = "storm_control", "Storm Control"
    PORT_SECURITY = "port_security", "Port Security / MAC Limit"
    DHCP_SNOOPING = "dhcp_snooping", "DHCP Snooping"
    DAI = "dai", "Dynamic ARP Inspection"
    IP_SOURCE_GUARD = "ip_source_guard", "IP Source Guard"
    MACSEC = "macsec", "MACsec"

    # ── 2. Layer 3 / Routing ──────────────────────────────────────────────
    STATIC_ROUTE = "static_route", "Static Route"
    OSPF = "ospf", "OSPF Adjacency / Area"
    BGP_EBGP = "bgp_ebgp", "BGP Peering (eBGP)"
    BGP_IBGP = "bgp_ibgp", "BGP Peering (iBGP)"
    ISIS = "isis", "IS-IS"
    EIGRP = "eigrp", "EIGRP"
    ROUTE_REDISTRIBUTION = "route_redistribution", "Route Redistribution"
    ROUTE_POLICY = "route_policy", "Route Policy / Route Map"
    PREFIX_LIST = "prefix_list", "Prefix List"
    VRF_BASIC = "vrf_basic", "VRF (non-MPLS)"
    BFD = "bfd", "BFD"
    PBR = "pbr", "Policy-Based Routing"
    IPV6_DUAL_STACK = "ipv6_dual_stack", "IPv6 Dual-Stack Interface"
    OSPFV3 = "ospfv3", "OSPFv3 (IPv6)"
    BGP_IPV6_AF = "bgp_ipv6_af", "BGP IPv6 Address Family"
    FHRP = "fhrp", "HSRP / VRRP / GLBP"

    # ── 3. MPLS & Service Provider ────────────────────────────────────────
    MPLS_L3VPN = "mpls_l3vpn", "MPLS L3VPN"
    MPLS_L2VPN = "mpls_l2vpn", "MPLS L2VPN / VPLS"
    PSEUDOWIRE = "pseudowire", "Pseudowire / EoMPLS"
    EVPN_MPLS = "evpn_mpls", "EVPN over MPLS"
    LDP = "ldp", "LDP"
    RSVP_TE = "rsvp_te", "RSVP-TE Tunnel"
    SR_MPLS = "sr_mpls", "Segment Routing MPLS"
    SRV6 = "srv6", "SRv6"
    SIXPE_SIXVPE = "6pe_6vpe", "6PE / 6VPE"
    MVPN = "mvpn", "Multicast VRF / mVPN"

    # ── 4. Data Centre / Overlay (EVPN / VXLAN) ──────────────────────────
    EVPN_VXLAN_FABRIC = "evpn_vxlan_fabric", "VXLAN EVPN Fabric"
    L2VNI = "l2vni", "L2VNI Provisioning"
    L3VNI = "l3vni", "L3VNI / IP VRF over VXLAN"
    BGP_EVPN_AF = "bgp_evpn_af", "BGP EVPN Address Family"
    ANYCAST_GATEWAY = "anycast_gateway", "Anycast Gateway"
    VTEP = "vtep", "VTEP Configuration"
    EVPN_MULTISITE = "evpn_multisite", "Multi-Site EVPN"
    DC_UNDERLAY = "dc_underlay", "DC Underlay (OSPF/BGP)"
    DC_MLAG = "dc_mlag", "MLAG in DC Fabric"

    # ── 5. Security & Firewalling ─────────────────────────────────────────
    ACL = "acl", "ACL"
    ZBF = "zbf", "Zone-Based Firewall"
    IPSEC_S2S = "ipsec_s2s", "IPSec Site-to-Site Tunnel"
    IPSEC_IKEV2 = "ipsec_ikev2", "IPSec with IKEv2"
    GRE_TUNNEL = "gre_tunnel", "GRE Tunnel"
    GRE_OVER_IPSEC = "gre_over_ipsec", "GRE over IPSec"
    DMVPN = "dmvpn", "DMVPN"
    MACSEC_POLICY = "macsec_policy", "MACsec Policy"
    COPP = "copp", "CoPP (Control Plane Policing)"
    URPF = "urpf", "uRPF"
    DOT1X_NAC = "dot1x_nac", "802.1X / NAC"
    AAA = "aaa", "RADIUS / TACACS AAA"
    RA_GUARD = "ra_guard", "RA Guard (IPv6)"
    SSL_INSPECTION = "ssl_inspection", "SSL/TLS Inspection"

    # ── 6. WAN & SD-WAN ──────────────────────────────────────────────────
    WAN_UPLINK = "wan_uplink", "WAN Uplink / Dual ISP"
    BGP_ISP = "bgp_isp", "BGP to ISP"
    SDWAN_OVERLAY = "sdwan_overlay", "SD-WAN Overlay"
    SDWAN_APP_POLICY = "sdwan_app_policy", "SD-WAN Application Policy"
    SDWAN_QOS = "sdwan_qos", "SD-WAN QoS Policy"
    SDWAN_DIA = "sdwan_dia", "SD-WAN DIA"
    NAT_PAT = "nat_pat", "NAT / PAT"
    NAT64 = "nat64", "NAT64"
    WAN_FAILOVER = "wan_failover", "WAN Redundancy / Failover"

    # ── 7. Wireless ───────────────────────────────────────────────────────
    WIRELESS_SSID = "wireless_ssid", "SSID Provisioning"
    WIRELESS_VLAN_MAP = "wireless_vlan_map", "VLAN to SSID Mapping"
    WIRELESS_DOT1X = "wireless_dot1x", "802.1X Wireless"
    WIRELESS_GUEST = "wireless_guest", "Guest Wireless / Captive Portal"
    WIRELESS_RF = "wireless_rf", "RF Policy"
    WIRELESS_QOS = "wireless_qos", "QoS for Wireless"
    WIRELESS_BAND_STEER = "wireless_band_steer", "Band Steering"
    WIRELESS_ROAM = "wireless_roam", "Fast Roaming / 802.11r"
    WIRELESS_SEGMENT = "wireless_segment", "Wireless Segmentation"
    WIRELESS_MESH = "wireless_mesh", "Mesh Wireless"
    WIRELESS_FLEXCONNECT = "wireless_flexconnect", "FlexConnect / Local Switching"

    # ── 8. Cloud & Hybrid Cloud ───────────────────────────────────────────
    CLOUD_VPC_PEER = "cloud_vpc_peer", "VPC / VNet Peering"
    CLOUD_TRANSIT_GW = "cloud_transit_gw", "Transit Gateway / Hub-Spoke"
    CLOUD_DIRECT_CONNECT = "cloud_direct_connect", "Cloud Direct Connect"
    CLOUD_VPN_GW = "cloud_vpn_gw", "Cloud VPN Gateway"
    CLOUD_BGP = "cloud_bgp", "BGP to Cloud Provider"
    CLOUD_SECURITY_GROUP = "cloud_security_group", "Cloud Firewall / Security Group"
    CLOUD_NAT = "cloud_nat", "Cloud NAT"
    CLOUD_ROUTE_TABLE = "cloud_route_table", "Cloud Route Table"
    HYBRID_DNS = "hybrid_dns", "Hybrid DNS"
    CLOUD_SDWAN = "cloud_sdwan", "Cloud SD-WAN Integration"

    # ── 9. QoS ────────────────────────────────────────────────────────────
    QOS_CLASSIFY = "qos_classify", "Traffic Classification"
    QOS_DSCP_MARK = "qos_dscp_mark", "DSCP Marking"
    QOS_COS_REMARK = "qos_cos_remark", "CoS Remarking"
    QOS_QUEUE = "qos_queue", "Queuing Policy"
    QOS_POLICE = "qos_police", "Policing"
    QOS_SHAPE = "qos_shape", "Traffic Shaping"
    QOS_TRUST = "qos_trust", "QoS Trust Boundary"

    # ── 10. Multicast ─────────────────────────────────────────────────────
    MULTICAST_PIM_SM = "multicast_pim_sm", "PIM Sparse Mode"
    MULTICAST_PIM_SSM = "multicast_pim_ssm", "PIM SSM"
    IGMP_SNOOPING = "igmp_snooping", "IGMP Snooping"
    MULTICAST_VRF = "multicast_vrf", "Multicast VRF"
    MSDP = "msdp", "MSDP"

    # ── 11. Management & Operations ───────────────────────────────────────
    MGMT_NTP = "mgmt_ntp", "NTP"
    MGMT_DNS_DHCP = "mgmt_dns_dhcp", "DNS / DHCP"
    MGMT_SNMP = "mgmt_snmp", "SNMP"
    MGMT_SYSLOG = "mgmt_syslog", "Syslog"
    MGMT_NETFLOW = "mgmt_netflow", "NetFlow / IPFIX"
    MGMT_TELEMETRY = "mgmt_telemetry", "gRPC / Streaming Telemetry"
    MGMT_SSH = "mgmt_ssh", "SSH Access Control"
    MGMT_AAA_DEVICE = "mgmt_aaa_device", "TACACS / RADIUS for Device Mgmt"
    MGMT_INTERFACE = "mgmt_interface", "Loopback / Management Interface"
    MGMT_LLDP_CDP = "mgmt_lldp_cdp", "LLDP / CDP Policy"
    MGMT_STP_ROOT = "mgmt_stp_root", "Spanning Tree Root"

    # ── 12. Reachability (expanded) ───────────────────────────────────────
    REACHABILITY_STATIC = "reachability_static", "Static Reachability"
    REACHABILITY_BGP_NETWORK = "reachability_bgp_network", "BGP Network Statement"
    REACHABILITY_FLOATING = "reachability_floating", "Floating Static / Backup Route"
    REACHABILITY_IP_SLA = "reachability_ip_sla", "IP SLA Probe"

    # ── 13. Service (expanded) ────────────────────────────────────────────
    SERVICE_LB_VIP = "service_lb_vip", "Load Balancer VIP"
    SERVICE_DNS = "service_dns", "DNS Record"
    SERVICE_DHCP = "service_dhcp", "DHCP Pool / Scope"
    SERVICE_NAT = "service_nat", "NAT Entry (Service)"
    SERVICE_PROXY = "service_proxy", "Proxy / Service Insertion"


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

    # ── Scheduled deployment (#9) ─────────────────────────────────────────
    scheduled_deploy_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="If set, deployment will not proceed before this timestamp. Leave blank for immediate deployment.",
    )

    # ── Staged rollout (#10) ──────────────────────────────────────────────
    deployment_strategy = models.CharField(
        max_length=20,
        choices=[
            ("all_at_once", "All at once"),
            ("canary", "Canary (single site first)"),
            ("rolling", "Rolling (one site at a time)"),
        ],
        default="all_at_once",
        help_text="How to deploy across multiple sites.",
    )

    # ── Rendered config cache (preview) ───────────────────────────────────
    rendered_configs = models.JSONField(
        default=dict,
        blank=True,
        help_text="Cached rendered device configs from the last dry-run / preview. Maps device_name → config_string.",
    )

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

    # ── Status workflow enforcement (#9) ──────────────────────────────────

    # Maps current status (lower-case) → set of allowed next statuses.
    VALID_STATUS_TRANSITIONS = {
        "draft": {"validated", "deprecated"},
        "validated": {"deploying", "deprecated"},
        "deploying": {"deployed", "failed"},
        "deployed": {"validated", "failed", "rolled back", "deprecated"},
        "failed": {"validated", "rolled back", "deprecated"},
        "rolled back": {"validated", "deploying", "deprecated"},
        "deprecated": set(),  # terminal state
    }

    def clean(self):
        """Enforce that status transitions follow the defined workflow.

        Raises ``ValidationError`` when an invalid transition is attempted.
        Jobs that manage status internally can bypass this by calling
        ``save(update_fields=[...])`` without going through ``full_clean()``.
        """
        super().clean()

        if not self.pk:
            # New record — any initial status is fine (typically "Draft")
            return

        try:
            old = Intent.objects.only("status").get(pk=self.pk)
        except Intent.DoesNotExist:
            return

        old_name = old.status.name.lower() if old.status else None
        new_name = self.status.name.lower() if self.status else None

        if old_name == new_name:
            return  # no change

        allowed = self.VALID_STATUS_TRANSITIONS.get(old_name)
        if allowed is not None and new_name not in allowed:
            raise ValidationError(
                {
                    "status": (
                        f"Invalid status transition: '{old.status}' → '{self.status}'. "
                        f"Allowed next statuses: {', '.join(sorted(allowed)) or 'none (terminal)'}."
                    )
                }
            )

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

    @property
    def is_approved(self):
        """Return True if at least one approval exists and none are rejected."""
        approvals = self.approvals.all()
        if not approvals.exists():
            return False
        return not approvals.filter(decision="rejected").exists()

    @property
    def has_resource_conflicts(self):
        """Return True if any overlapping prefix or device conflicts exist with other intents."""
        return bool(detect_conflicts(self))


# ────────────────────────────────────────────────────────────────────────────
# Approval Workflow (#2)
# ────────────────────────────────────────────────────────────────────────────


class IntentApproval(BaseModel):
    """Explicit approval record for an intent.

    Enterprise environments (PCI-DSS, HIPAA, SOC2) require at least one
    senior engineer to approve before production deployment. This model
    records each decision with full attribution.
    """

    intent = models.ForeignKey(
        Intent,
        on_delete=models.CASCADE,
        related_name="approvals",
    )
    approver = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="intent_approvals",
        help_text="Nautobot user who made this decision.",
    )
    decision = models.CharField(
        max_length=20,
        choices=[
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("revoked", "Revoked"),
        ],
    )
    comment = models.TextField(
        blank=True,
        help_text="Optional comment explaining the decision.",
    )
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for IntentApproval."""

        ordering = ["-decided_at"]
        verbose_name = "Intent Approval"
        verbose_name_plural = "Intent Approvals"

    def __str__(self):
        """Return approver, decision and intent."""
        return f"{self.approver} {self.decision} {self.intent.intent_id}"


# ────────────────────────────────────────────────────────────────────────────
# Audit Trail (#4)
# ────────────────────────────────────────────────────────────────────────────


class IntentAuditEntry(BaseModel):
    """Immutable audit record for every lifecycle action on an intent.

    Required for SOC2/PCI-DSS compliance. Tracks who did what, when,
    and what exact config was pushed.
    """

    ACTION_CHOICES = [
        ("created", "Created"),
        ("updated", "Updated"),
        ("resolved", "Resolved"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("deployed", "Deployed"),
        ("dry_run", "Dry-Run"),
        ("verified", "Verified"),
        ("rolled_back", "Rolled Back"),
        ("deprecated", "Deprecated"),
        ("conflict_detected", "Conflict Detected"),
        ("scheduled", "Scheduled"),
        ("config_preview", "Config Preview"),
    ]

    intent = models.ForeignKey(
        Intent,
        on_delete=models.CASCADE,
        related_name="audit_trail",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    actor = models.CharField(
        max_length=200,
        help_text="Username or system process that triggered this action.",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    detail = models.JSONField(
        default=dict,
        blank=True,
        help_text="Action-specific payload: rendered config, approval comment, "
        "verification checks, conflict details, etc.",
    )
    git_commit_sha = models.CharField(max_length=40, blank=True)
    job_result_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Link to the Nautobot JobResult that performed this action.",
    )

    class Meta:
        """Meta options for IntentAuditEntry."""

        ordering = ["-timestamp"]
        verbose_name = "Audit Entry"
        verbose_name_plural = "Audit Entries"
        # Prevent deletion — audit entries are immutable
        default_permissions = ("add", "view")

    def __str__(self):
        """Return action description string."""
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.intent.intent_id}: {self.action} by {self.actor}"


# ────────────────────────────────────────────────────────────────────────────
# Staged / Canary Deployment (#10)
# ────────────────────────────────────────────────────────────────────────────


class DeploymentStage(BaseModel):
    """Tracks per-site deployment progress for staged rollouts.

    When ``Intent.deployment_strategy`` is 'canary' or 'rolling', one
    ``DeploymentStage`` row is created per site/device group. The
    deployment job advances stages sequentially, verifying each before
    proceeding to the next.
    """

    intent = models.ForeignKey(
        Intent,
        on_delete=models.CASCADE,
        related_name="deployment_stages",
    )
    stage_order = models.PositiveIntegerField(
        help_text="Execution order. Stage 0 = canary site.",
    )
    location = models.ForeignKey(
        "dcim.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Site / location for this stage.",
    )
    devices = models.ManyToManyField(
        "dcim.Device",
        related_name="deployment_stages",
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("deploying", "Deploying"),
            ("deployed", "Deployed"),
            ("verifying", "Verifying"),
            ("verified", "Verified"),
            ("failed", "Failed"),
            ("rolled_back", "Rolled Back"),
        ],
        default="pending",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    rendered_configs = models.JSONField(
        default=dict,
        blank=True,
        help_text="Device configs pushed in this stage.",
    )

    class Meta:
        """Meta options for DeploymentStage."""

        ordering = ["intent", "stage_order"]
        unique_together = [("intent", "stage_order")]
        verbose_name = "Deployment Stage"
        verbose_name_plural = "Deployment Stages"

    def __str__(self):
        """Return stage description string."""
        loc = self.location.name if self.location else "unassigned"
        return f"{self.intent.intent_id} stage {self.stage_order} ({loc}): {self.status}"


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
# Resource Allocation — VXLAN VNI
# ────────────────────────────────────────────────────────────────────────────


class VxlanVniPool(BaseModel):
    """Pool of VXLAN VNI values for allocation in DC overlay fabrics.

    Create one pool per data-centre fabric or tenant in Nautobot admin.
    e.g. name="dc1-vni-pool", range_start=10000, range_end=19999
    """

    name = models.CharField(max_length=100, unique=True)
    range_start = models.PositiveIntegerField(help_text="First VNI value in pool e.g. 10000")
    range_end = models.PositiveIntegerField(help_text="Last VNI value in pool e.g. 19999")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Tenant-specific pool. Leave blank for shared pool.",
    )

    class Meta:
        """Meta options for the VxlanVniPool model."""

        verbose_name = "VXLAN VNI Pool"
        verbose_name_plural = "VXLAN VNI Pools"

    def __str__(self):
        """Return pool name with range."""
        return f"{self.name} ({self.range_start}-{self.range_end})"

    @property
    def utilisation_pct(self):
        """Return percentage of pool values currently allocated."""
        allocated = VniAllocation.objects.filter(pool=self).count()
        total = self.range_end - self.range_start + 1
        return int(allocated / total * 100) if total else 0


class VniAllocation(BaseModel):
    """A single VNI allocation. One row per VNI value.

    Allocated atomically by the resolver using select_for_update().
    """

    pool = models.ForeignKey(VxlanVniPool, on_delete=models.PROTECT, related_name="allocations")
    value = models.PositiveIntegerField(unique=True, help_text="VNI value e.g. 10042")
    intent = models.ForeignKey(Intent, on_delete=models.PROTECT, related_name="allocated_vnis")
    vni_type = models.CharField(
        max_length=10,
        choices=[("l2", "Layer 2 VNI"), ("l3", "Layer 3 VNI")],
        help_text="Whether this VNI is for L2VNI or L3VNI.",
    )
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for the VniAllocation model."""

        verbose_name = "VNI Allocation"
        verbose_name_plural = "VNI Allocations"

    def __str__(self):
        """Return VNI value with type and intent."""
        return f"VNI {self.value} ({self.vni_type}) → {self.intent.intent_id}"


# ────────────────────────────────────────────────────────────────────────────
# Resource Allocation — Tunnel IDs
# ────────────────────────────────────────────────────────────────────────────


class TunnelIdPool(BaseModel):
    """Pool of tunnel interface IDs for IPSec, GRE and DMVPN tunnels.

    e.g. name="ipsec-tunnel-pool", range_start=100, range_end=999
    """

    name = models.CharField(max_length=100, unique=True)
    range_start = models.PositiveIntegerField(help_text="First tunnel ID e.g. 100")
    range_end = models.PositiveIntegerField(help_text="Last tunnel ID e.g. 999")

    class Meta:
        """Meta options for the TunnelIdPool model."""

        verbose_name = "Tunnel ID Pool"
        verbose_name_plural = "Tunnel ID Pools"

    def __str__(self):
        """Return pool name with range."""
        return f"{self.name} ({self.range_start}-{self.range_end})"

    @property
    def utilisation_pct(self):
        """Return percentage of pool values currently allocated."""
        allocated = TunnelIdAllocation.objects.filter(pool=self).count()
        total = self.range_end - self.range_start + 1
        return int(allocated / total * 100) if total else 0


class TunnelIdAllocation(BaseModel):
    """A single tunnel ID allocation. One row per device+tunnel.

    Allocated atomically by the resolver using select_for_update().
    """

    pool = models.ForeignKey(TunnelIdPool, on_delete=models.PROTECT, related_name="allocations")
    value = models.PositiveIntegerField(help_text="Tunnel interface number e.g. 100")
    device = models.ForeignKey("dcim.Device", on_delete=models.PROTECT, related_name="tunnel_id_allocations")
    intent = models.ForeignKey(Intent, on_delete=models.PROTECT, related_name="allocated_tunnel_ids")
    tunnel_type = models.CharField(
        max_length=20,
        choices=[("ipsec", "IPSec"), ("gre", "GRE"), ("dmvpn", "DMVPN")],
    )
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for the TunnelIdAllocation model."""

        unique_together = [("device", "value")]
        verbose_name = "Tunnel ID Allocation"
        verbose_name_plural = "Tunnel ID Allocations"

    def __str__(self):
        """Return tunnel ID with device and type."""
        return f"Tunnel{self.value} ({self.tunnel_type}) → {self.device.name}"


# ────────────────────────────────────────────────────────────────────────────
# Resource Allocation — Managed Loopback IPs (DC Underlay)
# ────────────────────────────────────────────────────────────────────────────


class ManagedLoopbackPool(BaseModel):
    """Pool of /32 loopback IPs for DC underlay or router-ID allocation.

    e.g. name="dc1-loopbacks", prefix="192.0.2.0/24"
    Allocates individual /32 addresses from the prefix.
    """

    name = models.CharField(max_length=100, unique=True)
    prefix = models.CharField(
        max_length=50,
        help_text="CIDR prefix to allocate /32s from e.g. 192.0.2.0/24",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Tenant-specific pool. Leave blank for shared pool.",
    )

    class Meta:
        """Meta options for the ManagedLoopbackPool model."""

        verbose_name = "Managed Loopback Pool"
        verbose_name_plural = "Managed Loopback Pools"

    def __str__(self):
        """Return pool name with prefix."""
        return f"{self.name} ({self.prefix})"

    @property
    def utilisation_pct(self):
        """Return percentage of pool addresses currently allocated."""
        import ipaddress  # noqa: PLC0415

        net = ipaddress.ip_network(self.prefix, strict=False)
        total = net.num_addresses - 2  # exclude network and broadcast
        allocated = ManagedLoopback.objects.filter(pool=self).count()
        return int(allocated / total * 100) if total > 0 else 0


class ManagedLoopback(BaseModel):
    """A single loopback IP allocation. One row per device.

    Allocated atomically by the resolver using select_for_update().
    """

    pool = models.ForeignKey(ManagedLoopbackPool, on_delete=models.PROTECT, related_name="allocations")
    ip_address = models.GenericIPAddressField(unique=True, help_text="Allocated /32 IP e.g. 192.0.2.1")
    device = models.ForeignKey("dcim.Device", on_delete=models.PROTECT, related_name="managed_loopbacks")
    intent = models.ForeignKey(Intent, on_delete=models.PROTECT, related_name="allocated_loopbacks")
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for the ManagedLoopback model."""

        unique_together = [("device", "pool")]
        verbose_name = "Managed Loopback"
        verbose_name_plural = "Managed Loopbacks"

    def __str__(self):
        """Return loopback IP with device name."""
        return f"{self.ip_address} → {self.device.name}"


# ────────────────────────────────────────────────────────────────────────────
# Resource Allocation — Wireless VLANs
# ────────────────────────────────────────────────────────────────────────────


class WirelessVlanPool(BaseModel):
    """Pool of VLAN IDs for wireless SSID-to-VLAN mapping.

    Per-site pool so different sites can use different VLAN ranges.
    e.g. name="hq-wireless-vlans", range_start=200, range_end=299
    """

    name = models.CharField(max_length=100, unique=True)
    range_start = models.PositiveIntegerField(help_text="First VLAN ID e.g. 200")
    range_end = models.PositiveIntegerField(help_text="Last VLAN ID e.g. 299")
    site = models.ForeignKey(
        "dcim.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="wireless_vlan_pools",
        help_text="Site this pool belongs to. Leave blank for global pool.",
    )

    class Meta:
        """Meta options for the WirelessVlanPool model."""

        verbose_name = "Wireless VLAN Pool"
        verbose_name_plural = "Wireless VLAN Pools"

    def __str__(self):
        """Return pool name with VLAN range."""
        return f"{self.name} (VLAN {self.range_start}-{self.range_end})"

    @property
    def utilisation_pct(self):
        """Return percentage of pool values currently allocated."""
        allocated = WirelessVlanAllocation.objects.filter(pool=self).count()
        total = self.range_end - self.range_start + 1
        return int(allocated / total * 100) if total else 0


class WirelessVlanAllocation(BaseModel):
    """A single wireless VLAN allocation. One row per SSID-to-VLAN mapping.

    Allocated atomically by the resolver using select_for_update().
    """

    pool = models.ForeignKey(WirelessVlanPool, on_delete=models.PROTECT, related_name="allocations")
    vlan_id = models.PositiveIntegerField(help_text="Allocated VLAN ID e.g. 201")
    ssid_name = models.CharField(max_length=100, help_text="SSID this VLAN is mapped to")
    intent = models.ForeignKey(Intent, on_delete=models.PROTECT, related_name="allocated_wireless_vlans")
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for the WirelessVlanAllocation model."""

        unique_together = [("pool", "vlan_id")]
        verbose_name = "Wireless VLAN Allocation"
        verbose_name_plural = "Wireless VLAN Allocations"

    def __str__(self):
        """Return VLAN ID with SSID name."""
        return f"VLAN {self.vlan_id} → SSID '{self.ssid_name}'"


# ────────────────────────────────────────────────────────────────────────────
# Conflict Detection (#6)
# ────────────────────────────────────────────────────────────────────────────


def detect_conflicts(intent):
    """Detect resource conflicts between *intent* and other active intents.

    Checks:
      1. Overlapping destination prefixes
      2. Shared affected devices (from resolution plans)
      3. Overlapping RD/RT allocations

    Returns:
        list[dict]: Each dict has keys ``type``, ``other_intent``, ``detail``.
        Empty list means no conflicts.
    """
    conflicts = []
    active_statuses = {"draft", "validated", "deploying", "deployed"}

    # Only check intents that aren't deprecated / terminal
    other_intents = (
        Intent.objects.filter(status__name__in=[s.title() for s in active_statuses])
        .exclude(pk=intent.pk)
        .select_related("tenant")
    )

    my_prefixes = set()
    for prefix_list_key in ("source", "destination"):
        block = intent.intent_data.get(prefix_list_key, {})
        if isinstance(block, dict):
            for prefix in block.get("prefixes", []):
                my_prefixes.add(prefix)

    if not my_prefixes:
        return conflicts

    # 1. Prefix overlap
    for other in other_intents:
        other_prefixes = set()
        for prefix_list_key in ("source", "destination"):
            block = other.intent_data.get(prefix_list_key, {})
            if isinstance(block, dict):
                for prefix in block.get("prefixes", []):
                    other_prefixes.add(prefix)
        overlap = my_prefixes & other_prefixes
        if overlap:
            conflicts.append(
                {
                    "type": "prefix_overlap",
                    "other_intent": other.intent_id,
                    "detail": f"Overlapping prefixes: {', '.join(sorted(overlap))}",
                }
            )

    # 2. Device overlap (from resolution plans)
    my_plan = intent.latest_plan
    if my_plan:
        my_device_ids = set(my_plan.affected_devices.values_list("pk", flat=True))
        for other in other_intents:
            other_plan = other.latest_plan
            if other_plan:
                other_device_ids = set(other_plan.affected_devices.values_list("pk", flat=True))
                shared = my_device_ids & other_device_ids
                if shared:
                    from nautobot.dcim.models import Device  # noqa: PLC0415

                    shared_names = list(Device.objects.filter(pk__in=shared).values_list("name", flat=True))
                    conflicts.append(
                        {
                            "type": "device_overlap",
                            "other_intent": other.intent_id,
                            "detail": f"Shared devices: {', '.join(sorted(shared_names))}",
                        }
                    )

    return conflicts


# ────────────────────────────────────────────────────────────────────────────
# Multi-Tenancy Guardrails (#12)
# ────────────────────────────────────────────────────────────────────────────


def validate_tenant_isolation(intent):
    """Verify that an intent's plan doesn't touch devices owned by another tenant.

    Returns:
        list[str]: Warning messages. Empty list = clean.
    """
    warnings = []
    plan = intent.latest_plan
    if not plan:
        return warnings

    for device in plan.affected_devices.select_related("tenant").all():
        if device.tenant and intent.tenant and device.tenant_id != intent.tenant_id:
            warnings.append(
                f"Device '{device.name}' belongs to tenant '{device.tenant.name}' "
                f"but intent belongs to tenant '{intent.tenant.name}'."
            )

    return warnings
