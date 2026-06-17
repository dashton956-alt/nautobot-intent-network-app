# compliance.rego
# OPA policy for intent validation.
# Evaluated at PR time (GitLab CI) and again before each deployment (Nautobot).
#
# Usage:
#   opa eval -d compliance.rego -I "data.intent.allow" --fail < intent.json

package intent

import future.keywords.if
import future.keywords.in

# ─────────────────────────────────────────────────────────────────────────────
# Main allow rule — intent is allowed only if no violations exist
# ─────────────────────────────────────────────────────────────────────────────

default allow := false

allow if {
    count(violations) == 0
}

# ─────────────────────────────────────────────────────────────────────────────
# Universal rules — apply to every intent regardless of type
# ─────────────────────────────────────────────────────────────────────────────

violations contains msg if {
    not input.intent.change_ticket
    msg := "BLOCK: change_ticket is required on all intents"
}

violations contains msg if {
    input.intent.change_ticket
    not regex.match(`^(CHG|INC|REQ|TASK)[0-9]{5,10}$`, input.intent.change_ticket)
    msg := sprintf("BLOCK: change_ticket '%v' does not match required format (CHG/INC/REQ/TASK + 5-10 digits)", [input.intent.change_ticket])
}

violations contains msg if {
    not input.intent.tenant
    msg := "BLOCK: tenant is required on all intents"
}

violations contains msg if {
    not input.intent.description
    msg := "BLOCK: description is required on all intents"
}

violations contains msg if {
    count(input.intent.description) < 10
    msg := "BLOCK: description must be at least 10 characters"
}

violations contains msg if {
    not input.intent.version
    msg := "BLOCK: version is required on all intents"
}

# ─────────────────────────────────────────────────────────────────────────────
# PCI-DSS rules — apply when compliance = PCI-DSS
# ─────────────────────────────────────────────────────────────────────────────

pci_intent if {
    input.intent.policy.compliance == "PCI-DSS"
}

violations contains msg if {
    pci_intent
    not input.intent.policy.encryption
    msg := "BLOCK [PCI-DSS]: encryption field is required for PCI-DSS intents"
}

violations contains msg if {
    pci_intent
    input.intent.policy.encryption != "required"
    msg := sprintf("BLOCK [PCI-DSS]: encryption must be 'required' for PCI-DSS intents, got '%v'", [input.intent.policy.encryption])
}

violations contains msg if {
    pci_intent
    input.intent.type in {"connectivity", "mpls_l3vpn"}
    isolation := input.intent.isolation
    deny_protocols := isolation.deny_protocols
    not "telnet" in deny_protocols
    msg := "BLOCK [PCI-DSS]: telnet must be explicitly denied in isolation.deny_protocols"
}

violations contains msg if {
    pci_intent
    input.intent.type in {"connectivity", "mpls_l3vpn"}
    isolation := input.intent.isolation
    deny_protocols := isolation.deny_protocols
    not "http" in deny_protocols
    msg := "BLOCK [PCI-DSS]: http must be explicitly denied in isolation.deny_protocols"
}

violations contains msg if {
    pci_intent
    input.intent.type in {"connectivity", "mpls_l3vpn"}
    isolation := input.intent.isolation
    deny_protocols := isolation.deny_protocols
    not "ftp" in deny_protocols
    msg := "BLOCK [PCI-DSS]: ftp must be explicitly denied in isolation.deny_protocols"
}

violations contains msg if {
    pci_intent
    input.intent.policy.max_latency_ms > 20
    msg := sprintf("BLOCK [PCI-DSS]: max_latency_ms must be <= 20ms for PCI-DSS intents, got %vms", [input.intent.policy.max_latency_ms])
}

violations contains msg if {
    pci_intent
    input.intent.type == "wireless_ssid"
    input.intent.wireless.security_mode != "wpa3-enterprise"
    msg := sprintf("BLOCK [PCI-DSS]: wireless security must be wpa3-enterprise for PCI-DSS intents, got '%v'", [input.intent.wireless.security_mode])
}

violations contains msg if {
    pci_intent
    input.intent.type in {"ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec"}
    input.intent.tunnel.ike_version != 2
    msg := "BLOCK [PCI-DSS]: IKEv2 is required for PCI-DSS IPSec tunnels"
}

violations contains msg if {
    pci_intent
    input.intent.type in {"ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec"}
    weak_ciphers := {"aes-128-cbc", "aes-128-gcm"}
    input.intent.tunnel.encryption in weak_ciphers
    msg := sprintf("BLOCK [PCI-DSS]: AES-256 encryption is required for PCI-DSS IPSec tunnels, got '%v'", [input.intent.tunnel.encryption])
}

violations contains msg if {
    pci_intent
    input.intent.type in {"ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec"}
    weak_integrity := {"sha1"}
    input.intent.tunnel.integrity in weak_integrity
    msg := "BLOCK [PCI-DSS]: SHA-1 is not permitted for PCI-DSS IPSec tunnels — use sha256 or stronger"
}

violations contains msg if {
    pci_intent
    input.intent.type in {"ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec"}
    input.intent.tunnel.dh_group < 14
    msg := sprintf("BLOCK [PCI-DSS]: DH group must be >= 14 for PCI-DSS IPSec tunnels, got group %v", [input.intent.tunnel.dh_group])
}

# ─────────────────────────────────────────────────────────────────────────────
# HIPAA rules — apply when compliance = HIPAA
# ─────────────────────────────────────────────────────────────────────────────

hipaa_intent if {
    input.intent.policy.compliance == "HIPAA"
}

violations contains msg if {
    hipaa_intent
    not input.intent.policy.encryption
    msg := "BLOCK [HIPAA]: encryption field is required for HIPAA intents"
}

violations contains msg if {
    hipaa_intent
    input.intent.policy.encryption == "none"
    msg := "BLOCK [HIPAA]: encryption cannot be 'none' for HIPAA intents"
}

violations contains msg if {
    hipaa_intent
    input.intent.type == "wireless_ssid"
    input.intent.wireless.security_mode in {"wpa2-psk", "open"}
    msg := sprintf("BLOCK [HIPAA]: wireless security mode '%v' is not permitted for HIPAA — use wpa2-enterprise or wpa3-enterprise", [input.intent.wireless.security_mode])
}

violations contains msg if {
    hipaa_intent
    input.intent.type in {"cloud_vpc_peer", "cloud_transit_gw", "cloud_direct_connect", "cloud_vpn_gw"}
    input.intent.cloud.provider == "generic"
    msg := "BLOCK [HIPAA]: cloud provider must be explicitly specified (not 'generic') for HIPAA intents"
}

# ─────────────────────────────────────────────────────────────────────────────
# SOC2 rules
# ─────────────────────────────────────────────────────────────────────────────

soc2_intent if {
    input.intent.policy.compliance == "SOC2"
}

violations contains msg if {
    soc2_intent
    input.intent.type in {"mgmt_snmp"}
    input.intent.management.snmp_version == "v2c"
    msg := "WARN [SOC2]: SNMPv2c is not recommended for SOC2 — use SNMPv3"
}

# ─────────────────────────────────────────────────────────────────────────────
# Security baseline — apply to all intents regardless of compliance tag
# ─────────────────────────────────────────────────────────────────────────────

violations contains msg if {
    input.intent.type == "wireless_ssid"
    input.intent.wireless.security_mode == "open"
    msg := "BLOCK: open wireless networks are not permitted — use at minimum wpa2-psk"
}

violations contains msg if {
    input.intent.type in {"mgmt_ssh", "mgmt_aaa_device"}
    input.intent.management.ssh_allowed_prefixes == ["0.0.0.0/0"]
    msg := "BLOCK: SSH access from 0.0.0.0/0 is not permitted — restrict to management prefixes"
}

violations contains msg if {
    input.intent.type in {"cloud_security_group"}
    rule := input.intent.cloud.rules[_]
    rule.action == "allow"
    rule.source == "0.0.0.0/0"
    rule.port == "22"
    msg := "BLOCK: allowing SSH (port 22) from 0.0.0.0/0 in a cloud security group is not permitted"
}

violations contains msg if {
    input.intent.type in {"cloud_security_group"}
    rule := input.intent.cloud.rules[_]
    rule.action == "allow"
    rule.source == "0.0.0.0/0"
    rule.port == "3389"
    msg := "BLOCK: allowing RDP (port 3389) from 0.0.0.0/0 in a cloud security group is not permitted"
}

violations contains msg if {
    input.intent.type in {"ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec"}
    input.intent.tunnel.auth_method == "psk"
    not input.intent.tunnel.encryption
    msg := "WARN: IPSec tunnel using PSK auth without explicit encryption specified — default may be weak"
}

violations contains msg if {
    input.intent.type == "dot1x_nac"
    not input.intent.routing.neighbors
    msg := "BLOCK: dot1x_nac intent requires at least one RADIUS server in routing.neighbors"
}

# ─────────────────────────────────────────────────────────────────────────────
# Auto-remediation policy — used by IntentReconciliationJob
# Drift is auto-remediable only for low-risk intent types
# ─────────────────────────────────────────────────────────────────────────────

package intent.remediation

default auto_remediate := false

low_risk_types := {
    "mgmt_ntp", "mgmt_syslog", "mgmt_snmp", "mgmt_netflow",
    "mgmt_telemetry", "mgmt_lldp_cdp",
    "qos_classify", "qos_dscp_mark", "qos_trust",
    "storm_control", "stp_policy",
}

high_risk_types := {
    "mpls_l3vpn", "connectivity", "evpn_vxlan_fabric",
    "ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec", "dmvpn",
    "dot1x_nac", "zbf", "copp",
    "cloud_vpc_peer", "cloud_transit_gw", "cloud_direct_connect",
}

auto_remediate if {
    input.intent.type in low_risk_types
    not input.intent.type in high_risk_types
}

auto_remediate if {
    input.intent.type in low_risk_types
    input.drift.check_name in {"mgmt_ntp", "mgmt_syslog"}
    input.drift.devices_affected <= 3
}
