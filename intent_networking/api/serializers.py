"""API serializers for intent_networking.

Includes per-intent-type field validators that enforce required YAML keys
before an intent can be saved or synced.
"""

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

# ---------------------------------------------------------------------------
# Per-intent-type YAML field validators
# ---------------------------------------------------------------------------

# Maps each intent type to the required top-level keys in intent_data.
# The resolver will hard-fail anyway, but catching early in the API gives
# immediate feedback to the caller.

INTENT_REQUIRED_FIELDS: dict[str, list[str]] = {
    # Legacy / generic
    "connectivity": ["source"],
    "security": [],
    "reachability": ["reachability_type"],
    "service": ["service_type"],
    # L2 / Switching
    "vlan_provision": ["vlans"],
    "l2_access_port": ["interface", "vlan_id"],
    "l2_trunk_port": ["interface"],
    "lag": ["member_interfaces", "channel_id"],
    "mlag": ["peer_link_interfaces", "domain_id"],
    "stp_policy": [],
    "qinq": ["interface", "outer_vlan"],
    "pvlan": ["primary_vlan"],
    "storm_control": [],
    "port_security": ["interface"],
    "dhcp_snooping": [],
    "dai": [],
    "ip_source_guard": ["interfaces"],
    "macsec": ["interfaces"],
    # L3 / Routing
    "static_route": ["routes"],
    "ospf": ["interfaces"],
    "bgp_ebgp": ["local_asn", "neighbor_ip", "neighbor_asn"],
    "bgp_ibgp": ["local_asn", "neighbor_ip"],
    "isis": ["net"],
    "eigrp": ["as_number", "networks"],
    "route_redistribution": ["source_protocol", "dest_protocol"],
    "route_policy": ["policy_name", "entries"],
    "prefix_list": ["list_name", "entries"],
    "vrf_basic": ["vrf_name"],
    "bfd": [],
    "pbr": ["policy_name"],
    "ipv6_dual_stack": ["interfaces"],
    "ospfv3": [],
    "bgp_ipv6_af": ["local_asn"],
    "fhrp": ["group_id", "virtual_ip", "interface"],
    # MPLS / SP
    "mpls_l3vpn": ["source"],
    "mpls_l2vpn": ["vpls_instance"],
    "pseudowire": ["pw_id", "remote_pe"],
    "evpn_mpls": ["evi"],
    "ldp": [],
    "rsvp_te": ["tunnel_destination"],
    "sr_mpls": [],
    "srv6": ["locator_block"],
    "6pe_6vpe": [],
    "mvpn": ["vrf", "mdt_default_group"],
    # DC / EVPN / VXLAN
    "evpn_vxlan_fabric": [],
    "l2vni": ["vlan_id"],
    "l3vni": ["vrf_name"],
    "bgp_evpn_af": ["local_asn"],
    "anycast_gateway": ["virtual_ip", "vlan_id"],
    "vtep": [],
    "evpn_multisite": [],
    "dc_underlay": [],
    "dc_mlag": ["peer_link_interfaces", "domain_id"],
    # Security
    "acl": ["acl_name"],
    "zbf": ["zone_pairs"],
    "ipsec_s2s": ["remote_peer"],
    "ipsec_ikev2": [],
    "gre_tunnel": ["tunnel_destination", "tunnel_source"],
    "gre_over_ipsec": ["tunnel_destination"],
    "dmvpn": ["nhs_address"],
    "macsec_policy": ["interfaces"],
    "copp": [],
    "urpf": ["interfaces"],
    "dot1x_nac": [],
    "aaa": [],
    "ra_guard": [],
    "ssl_inspection": [],
    # WAN / SD-WAN
    "wan_uplink": ["uplinks"],
    "bgp_isp": ["local_asn", "neighbor_ip", "neighbor_asn"],
    "sdwan_overlay": [],
    "sdwan_app_policy": [],
    "sdwan_qos": [],
    "sdwan_dia": [],
    "nat_pat": [],
    "nat64": [],
    "wan_failover": [],
    # Wireless
    "wireless_ssid": ["ssid_name"],
    "wireless_vlan_map": ["ssid_name"],
    "wireless_dot1x": [],
    "wireless_guest": [],
    "wireless_rf": [],
    "wireless_qos": [],
    "wireless_band_steer": [],
    "wireless_roam": [],
    "wireless_segment": [],
    "wireless_mesh": [],
    "wireless_flexconnect": [],
    # Cloud
    "cloud_vpc_peer": ["requester_vpc", "accepter_vpc"],
    "cloud_transit_gw": ["transit_gateway_id"],
    "cloud_direct_connect": ["connection_id"],
    "cloud_vpn_gw": [],
    "cloud_bgp": [],
    "cloud_security_group": ["security_group_name"],
    "cloud_nat": [],
    "cloud_route_table": [],
    "hybrid_dns": [],
    "cloud_sdwan": [],
    # QoS
    "qos_classify": [],
    "qos_dscp_mark": [],
    "qos_cos_remark": [],
    "qos_queue": [],
    "qos_police": [],
    "qos_shape": [],
    "qos_trust": [],
    # Multicast
    "multicast_pim_sm": ["rp_address"],
    "multicast_pim_ssm": [],
    "igmp_snooping": [],
    "multicast_vrf": ["vrf"],
    "msdp": [],
    # Management
    "mgmt_ntp": ["servers"],
    "mgmt_dns_dhcp": [],
    "mgmt_snmp": [],
    "mgmt_syslog": ["servers"],
    "mgmt_netflow": [],
    "mgmt_telemetry": [],
    "mgmt_ssh": [],
    "mgmt_aaa_device": [],
    "mgmt_interface": [],
    "mgmt_lldp_cdp": [],
    "mgmt_stp_root": [],
    # Reachability sub-types
    "reachability_static": ["routes"],
    "reachability_bgp_network": ["local_asn", "networks"],
    "reachability_floating": ["routes"],
    "reachability_ip_sla": ["probes"],
    # Service sub-types
    "service_lb_vip": ["vip_address", "pool_members"],
    "service_dns": ["records"],
    "service_dhcp": ["pools"],
    "service_nat": ["static_mappings"],
    "service_proxy": [],
}


def validate_intent_data_for_type(intent_type: str, intent_data: dict) -> list[str]:
    """Validate that intent_data contains all required fields for the given type.

    Returns:
        list of error message strings (empty if valid).
    """
    required = INTENT_REQUIRED_FIELDS.get(intent_type)
    if required is None:
        return [f"Unknown intent type '{intent_type}' — no validator registered."]

    errors = []
    for field in required:
        if field not in intent_data:
            errors.append(f"Intent type '{intent_type}' requires field '{field}' in intent_data.")
    return errors


class IntentSerializer(NautobotModelSerializer):
    """Serializer for the Intent model.

    Validates intent_data fields based on intent_type before saving.
    """

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

    def validate(self, data):
        """Cross-field validation: check intent_data keys match the intent_type."""
        data = super().validate(data)
        intent_type = data.get("intent_type") or (self.instance.intent_type if self.instance else None)
        intent_data = data.get("intent_data") or (self.instance.intent_data if self.instance else {})
        if intent_type and intent_data:
            errors = validate_intent_data_for_type(intent_type, intent_data)
            if errors:
                raise serializers.ValidationError({"intent_data": errors})
        return data

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
    """Input for the sync-from-git endpoint.

    Validates that the intent_data JSON contains required fields
    for the declared intent type before the sync job is enqueued.
    """

    intent_data = serializers.JSONField(required=True)
    git_commit_sha = serializers.CharField(required=False, default="")
    git_branch = serializers.CharField(required=False, default="")
    git_pr_number = serializers.IntegerField(required=False, allow_null=True)

    def validate_intent_data(self, value):
        """Validate per-type required fields in the YAML payload."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("intent_data must be a JSON object.")
        intent_type = value.get("type")
        if intent_type:
            errors = validate_intent_data_for_type(intent_type, value)
            if errors:
                raise serializers.ValidationError(errors)
        return value


class DeploySerializer(serializers.Serializer):
    """Input for the deploy endpoint."""

    commit_sha = serializers.CharField(required=True)
    dry_run = serializers.BooleanField(default=False)
