# network/compliance.rego
# Compliance-framework rules: PCI-DSS, HIPAA, SOC2.
# Called by opa_client.check_intent_policy() via /v1/data/network/compliance
#
# Two violation sets:
#   deny[msg]  — blocking; intent resolution is aborted if any fire.
#   warn[msg]  — advisory; surfaced to the operator but do not block resolution.

package network.compliance

import future.keywords.in

# ─── Helper predicates ────────────────────────────────────────────────────────

pci_intent {
    input.intent.policy.compliance == "PCI-DSS"
}

hipaa_intent {
    input.intent.policy.compliance == "HIPAA"
}

soc2_intent {
    input.intent.policy.compliance == "SOC2"
}

# IPSec intent types that use the tunnel.* key path (ipsec_s2s, gre_over_ipsec).
# ipsec_ikev2 uses security.ipsec_ikev2.ikev2.* and is handled by separate rules.
tunnel_ipsec_types := {"ipsec_s2s", "gre_over_ipsec"}

# High-risk intent types that must use canary or rolling deployment strategy.
# Mirrors the set in remediation.rego — kept here to avoid cross-package coupling.
high_risk_types := {
    "mpls_l3vpn", "connectivity", "evpn_vxlan_fabric",
    "ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec", "dmvpn",
    "dot1x_nac", "zbf", "copp",
    "cloud_vpc_peer", "cloud_transit_gw", "cloud_direct_connect",
}

# ─── PCI-DSS — encryption ─────────────────────────────────────────────────────

deny[msg] {
    pci_intent
    not input.intent.policy.encryption
    msg := "[PCI-DSS] encryption field is required for PCI-DSS intents"
}

deny[msg] {
    pci_intent
    input.intent.policy.encryption != "required"
    msg := sprintf("[PCI-DSS] encryption must be 'required', got '%v'", [input.intent.policy.encryption])
}

# ─── PCI-DSS — protocol isolation ────────────────────────────────────────────

deny[msg] {
    pci_intent
    input.intent.type in {"connectivity", "mpls_l3vpn"}
    not "telnet" in input.intent.isolation.deny_protocols
    msg := "[PCI-DSS] telnet must be explicitly denied in isolation.deny_protocols"
}

deny[msg] {
    pci_intent
    input.intent.type in {"connectivity", "mpls_l3vpn"}
    not "http" in input.intent.isolation.deny_protocols
    msg := "[PCI-DSS] http must be explicitly denied in isolation.deny_protocols"
}

deny[msg] {
    pci_intent
    input.intent.type in {"connectivity", "mpls_l3vpn"}
    not "ftp" in input.intent.isolation.deny_protocols
    msg := "[PCI-DSS] ftp must be explicitly denied in isolation.deny_protocols"
}

# ─── PCI-DSS — latency and wireless ──────────────────────────────────────────

deny[msg] {
    pci_intent
    input.intent.policy.max_latency_ms > 20
    msg := sprintf("[PCI-DSS] max_latency_ms must be <= 20ms, got %vms", [input.intent.policy.max_latency_ms])
}

deny[msg] {
    pci_intent
    input.intent.type == "wireless_ssid"
    input.intent.wireless.security_mode != "wpa3-enterprise"
    msg := sprintf("[PCI-DSS] wireless security must be wpa3-enterprise, got '%v'", [input.intent.wireless.security_mode])
}

# ─── PCI-DSS — IPSec: tunnel.* path (ipsec_s2s, gre_over_ipsec) ─────────────

deny[msg] {
    pci_intent
    input.intent.type in tunnel_ipsec_types
    input.intent.tunnel.ike_version != 2
    msg := "[PCI-DSS] IKEv2 is required for PCI-DSS IPSec tunnels"
}

deny[msg] {
    pci_intent
    input.intent.type in tunnel_ipsec_types
    input.intent.tunnel.encryption in {"aes-128-cbc", "aes-128-gcm"}
    msg := sprintf("[PCI-DSS] AES-256 is required for IPSec tunnels, got '%v'", [input.intent.tunnel.encryption])
}

deny[msg] {
    pci_intent
    input.intent.type in tunnel_ipsec_types
    input.intent.tunnel.integrity == "sha1"
    msg := "[PCI-DSS] SHA-1 is not permitted for IPSec tunnels — use sha256 or stronger"
}

deny[msg] {
    pci_intent
    input.intent.type in tunnel_ipsec_types
    input.intent.tunnel.dh_group < 14
    msg := sprintf("[PCI-DSS] DH group must be >= 14, got group %v", [input.intent.tunnel.dh_group])
}

# ─── PCI-DSS — IPSec: security.ipsec_ikev2.* path (ipsec_ikev2) ──────────────
# ipsec_ikev2 stores crypto parameters under security.ipsec_ikev2.ikev2.proposal.*
# not under tunnel.* — without separate rules these checks are silently skipped.

deny[msg] {
    pci_intent
    input.intent.type == "ipsec_ikev2"
    input.intent.security.ipsec_ikev2.ikev2.ike_version != 2
    msg := "[PCI-DSS] IKEv2 is required for PCI-DSS IPSec tunnels"
}

deny[msg] {
    pci_intent
    input.intent.type == "ipsec_ikev2"
    enc := input.intent.security.ipsec_ikev2.ikev2.proposal.encryption
    enc in {"aes-128-cbc", "aes-128-gcm", "aes-gcm-128"}
    msg := sprintf("[PCI-DSS] AES-256 is required for IPSec tunnels, got '%v'", [enc])
}

deny[msg] {
    pci_intent
    input.intent.type == "ipsec_ikev2"
    dh := input.intent.security.ipsec_ikev2.ikev2.proposal.dh_group
    dh < 14
    msg := sprintf("[PCI-DSS] DH group must be >= 14, got group %v", [dh])
}

# ─── PCI-DSS — verification trigger ──────────────────────────────────────────

deny[msg] {
    pci_intent
    input.intent.verification.trigger != "both"
    msg := sprintf("[PCI-DSS] verification.trigger must be 'both' for continuous monitoring, got '%v'", [input.intent.verification.trigger])
}

# ─── HIPAA — encryption ───────────────────────────────────────────────────────

deny[msg] {
    hipaa_intent
    not input.intent.policy.encryption
    msg := "[HIPAA] encryption field is required for HIPAA intents"
}

deny[msg] {
    hipaa_intent
    input.intent.policy.encryption == "none"
    msg := "[HIPAA] encryption cannot be 'none' for HIPAA intents"
}

# ─── HIPAA — wireless and cloud ──────────────────────────────────────────────

deny[msg] {
    hipaa_intent
    input.intent.type == "wireless_ssid"
    input.intent.wireless.security_mode in {"wpa2-psk", "open"}
    msg := sprintf("[HIPAA] wireless security mode '%v' is not permitted — use wpa2-enterprise or wpa3-enterprise", [input.intent.wireless.security_mode])
}

deny[msg] {
    hipaa_intent
    input.intent.type in {"cloud_vpc_peer", "cloud_transit_gw", "cloud_direct_connect", "cloud_vpn_gw"}
    input.intent.cloud.provider == "generic"
    msg := "[HIPAA] cloud provider must be explicitly named (not 'generic')"
}

# ─── HIPAA — IPSec: tunnel.* path (ipsec_s2s, gre_over_ipsec) ───────────────

deny[msg] {
    hipaa_intent
    input.intent.type in tunnel_ipsec_types
    input.intent.tunnel.ike_version != 2
    msg := "[HIPAA] IKEv2 is required for HIPAA IPSec tunnels"
}

deny[msg] {
    hipaa_intent
    input.intent.type in tunnel_ipsec_types
    input.intent.tunnel.encryption in {"aes-128-cbc", "aes-128-gcm"}
    msg := sprintf("[HIPAA] AES-256 minimum is required for HIPAA IPSec tunnels, got '%v'", [input.intent.tunnel.encryption])
}

# ─── HIPAA — IPSec: security.ipsec_ikev2.* path (ipsec_ikev2) ────────────────

deny[msg] {
    hipaa_intent
    input.intent.type == "ipsec_ikev2"
    input.intent.security.ipsec_ikev2.ikev2.ike_version != 2
    msg := "[HIPAA] IKEv2 is required for HIPAA IPSec tunnels"
}

deny[msg] {
    hipaa_intent
    input.intent.type == "ipsec_ikev2"
    enc := input.intent.security.ipsec_ikev2.ikev2.proposal.encryption
    enc in {"aes-128-cbc", "aes-128-gcm", "aes-gcm-128"}
    msg := sprintf("[HIPAA] AES-256 minimum is required for HIPAA IPSec tunnels, got '%v'", [enc])
}

# ─── HIPAA — verification ────────────────────────────────────────────────────

deny[msg] {
    hipaa_intent
    input.intent.verification.trigger != "both"
    msg := sprintf("[HIPAA] verification.trigger must be 'both' for continuous monitoring, got '%v'", [input.intent.verification.trigger])
}

# NOTE: HIPAA deployment strategy for high-risk types is enforced by the
# universal high_risk_types rule below — no HIPAA-scoped duplicate to avoid
# double-firing for HIPAA-tagged intents.

# ─── SOC2 — advisory warnings (non-blocking) ─────────────────────────────────

warn[msg] {
    soc2_intent
    input.intent.type == "mgmt_snmp"
    input.intent.management.snmp_version == "v2c"
    msg := "[SOC2][WARN] SNMPv2c is not recommended — use SNMPv3 for SOC2 compliance"
}

# ─── Universal rules ──────────────────────────────────────────────────────────

deny[msg] {
    input.intent.type == "wireless_ssid"
    input.intent.wireless.security_mode == "open"
    msg := "Open wireless networks are not permitted — use at minimum wpa2-psk"
}

deny[msg] {
    input.intent.type in {"mgmt_ssh", "mgmt_aaa_device"}
    input.intent.management.ssh_allowed_prefixes == ["0.0.0.0/0"]
    msg := "SSH access from 0.0.0.0/0 is not permitted — restrict to management prefixes"
}

deny[msg] {
    input.intent.type == "cloud_security_group"
    rule := input.intent.cloud.rules[_]
    rule.action == "allow"
    rule.source == "0.0.0.0/0"
    rule.port == "22"
    msg := "Allowing SSH (port 22) from 0.0.0.0/0 in a cloud security group is not permitted"
}

deny[msg] {
    input.intent.type == "cloud_security_group"
    rule := input.intent.cloud.rules[_]
    rule.action == "allow"
    rule.source == "0.0.0.0/0"
    rule.port == "3389"
    msg := "Allowing RDP (port 3389) from 0.0.0.0/0 in a cloud security group is not permitted"
}

# High-risk types must use canary or rolling — prevents all-at-once changes to
# production infrastructure with broad blast radius.
deny[msg] {
    input.intent.type in high_risk_types
    not input.intent.deployment.strategy in {"canary", "rolling"}
    msg := sprintf("high-risk intent type '%v' must use canary or rolling deployment strategy, got '%v'", [input.intent.type, input.intent.deployment.strategy])
}

# ─── Universal advisory warnings ─────────────────────────────────────────────

# save_config: false means running and startup diverge on reload.
warn[msg] {
    input.intent.deployment.save_config == false
    msg := "[WARN] deployment.save_config is false — running and startup configs will diverge on device reload"
}

# preferred encryption bypasses all compliance cipher enforcement.
warn[msg] {
    input.intent.policy.encryption == "preferred"
    msg := "[WARN] policy.encryption: preferred bypasses all compliance cipher enforcement — use 'required' for regulated workloads"
}
