# network/compliance.rego
# Compliance-framework rules: PCI-DSS, HIPAA, SOC2.
# Called by opa_client.check_intent_policy() via /v1/data/network/compliance

package network.compliance

import future.keywords.in

pci_intent {
    input.intent.policy.compliance == "PCI-DSS"
}

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

deny[msg] {
    pci_intent
    input.intent.type in {"ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec"}
    input.intent.tunnel.ike_version != 2
    msg := "[PCI-DSS] IKEv2 is required for PCI-DSS IPSec tunnels"
}

deny[msg] {
    pci_intent
    input.intent.type in {"ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec"}
    input.intent.tunnel.encryption in {"aes-128-cbc", "aes-128-gcm"}
    msg := sprintf("[PCI-DSS] AES-256 is required for IPSec tunnels, got '%v'", [input.intent.tunnel.encryption])
}

deny[msg] {
    pci_intent
    input.intent.type in {"ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec"}
    input.intent.tunnel.integrity == "sha1"
    msg := "[PCI-DSS] SHA-1 is not permitted for IPSec tunnels — use sha256 or stronger"
}

deny[msg] {
    pci_intent
    input.intent.type in {"ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec"}
    input.intent.tunnel.dh_group < 14
    msg := sprintf("[PCI-DSS] DH group must be >= 14, got group %v", [input.intent.tunnel.dh_group])
}

hipaa_intent {
    input.intent.policy.compliance == "HIPAA"
}

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

soc2_intent {
    input.intent.policy.compliance == "SOC2"
}

deny[msg] {
    soc2_intent
    input.intent.type == "mgmt_snmp"
    input.intent.management.snmp_version == "v2c"
    msg := "[SOC2] SNMPv2c is not permitted — use SNMPv3"
}

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
