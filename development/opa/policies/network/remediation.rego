# network/remediation.rego
# Auto-remediation approval policy.
# Called by opa_client.check_auto_remediation() via /v1/data/network/remediation

package network.remediation

import future.keywords.in

default auto_remediate = false

low_risk_types := {
    "mgmt_ntp", "mgmt_syslog", "mgmt_snmp", "mgmt_netflow",
    "mgmt_telemetry", "mgmt_lldp_cdp", "mgmt_motd",
    "qos_classify", "qos_dscp_mark", "qos_trust",
    "storm_control", "stp_policy",
}

high_risk_types := {
    "mpls_l3vpn", "connectivity", "evpn_vxlan_fabric",
    "ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec", "dmvpn",
    "dot1x_nac", "zbf", "copp",
    "cloud_vpc_peer", "cloud_transit_gw", "cloud_direct_connect",
}

auto_remediate = true {
    input.intent.type in low_risk_types
    not input.intent.type in high_risk_types
    input.drift_type != "complex"
}
