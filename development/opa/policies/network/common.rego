# network/common.rego
# Universal rules that apply to every intent regardless of type or compliance tag.
# Called by opa_client.check_intent_policy() via /v1/data/network/common
#
# Input shape (from opa_client.py):
#   input.intent      — raw intent dict (parsed YAML, the content under the "intent:" key)
#   input.metadata    — {intent_id, version, change_ticket, approved_by}
#   input.tenant      — tenant slug string
#   input.topology    — current topology context dict

package network.common

import future.keywords.in

# ─────────────────────────────────────────────────────────────────────────────
# Change ticket — required, must match CHG/INC/REQ/TASK + 5-10 digits
# ─────────────────────────────────────────────────────────────────────────────

deny[msg] {
    ct := input.metadata.change_ticket
    count(ct) == 0
    msg := "change_ticket is required on all intents"
}

deny[msg] {
    ct := input.metadata.change_ticket
    ct != ""
    not regex.match(`^(CHG|INC|REQ|TASK)[0-9]{5,10}$`, ct)
    msg := sprintf("change_ticket '%v' does not match required format (CHG/INC/REQ/TASK + 5-10 digits)", [ct])
}

# ─────────────────────────────────────────────────────────────────────────────
# Version — must be present and a positive integer
# ─────────────────────────────────────────────────────────────────────────────

deny[msg] {
    not is_number(input.intent.version)
    msg := "version is required on all intents and must be a number"
}

deny[msg] {
    is_number(input.intent.version)
    input.intent.version <= 0
    msg := sprintf("version must be a positive integer, got %v", [input.intent.version])
}

deny[msg] {
    is_number(input.intent.version)
    input.intent.version > 9999
    msg := sprintf("version must be <= 9999, got %v — check for a typo", [input.intent.version])
}

# ─────────────────────────────────────────────────────────────────────────────
# Description — required, minimum 10 characters
# ─────────────────────────────────────────────────────────────────────────────

deny[msg] {
    not input.intent.description
    msg := "description is required on all intents"
}

deny[msg] {
    d := input.intent.description
    count(d) < 10
    msg := sprintf("description must be at least 10 characters, got %v", [count(d)])
}

# ─────────────────────────────────────────────────────────────────────────────
# Tenant — must be present
# ─────────────────────────────────────────────────────────────────────────────

deny[msg] {
    not input.intent.tenant
    msg := "tenant is required on all intents"
}

# ─────────────────────────────────────────────────────────────────────────────
# Approved-by — required for high-impact intent types
# ─────────────────────────────────────────────────────────────────────────────

high_impact_types := {
    "mpls_l3vpn", "connectivity", "evpn_vxlan_fabric",
    "ipsec_s2s", "ipsec_ikev2", "gre_over_ipsec", "dmvpn",
    "cloud_vpc_peer", "cloud_transit_gw", "cloud_direct_connect",
    "dot1x_nac", "zbf", "copp",
}

deny[msg] {
    input.intent.type in high_impact_types
    not input.metadata.approved_by
    msg := sprintf("approved_by is required for high-impact intent type '%v'", [input.intent.type])
}

deny[msg] {
    input.intent.type in high_impact_types
    input.metadata.approved_by == ""
    msg := sprintf("approved_by is required for high-impact intent type '%v'", [input.intent.type])
}

# ─────────────────────────────────────────────────────────────────────────────
# Scope — at least one targeting mechanism must be present
# ─────────────────────────────────────────────────────────────────────────────

scope_present {
    input.intent.scope.all_tenant_devices == true
}

scope_present {
    count(input.intent.scope.devices) > 0
}

scope_present {
    count(input.intent.scope.sites) > 0
}

scope_present {
    count(input.intent.scope.roles) > 0
}

deny[msg] {
    not scope_present
    msg := "at least one scope field must be present (scope.devices, scope.sites, scope.roles, or scope.all_tenant_devices: true)"
}

# ─────────────────────────────────────────────────────────────────────────────
# Plaintext credentials — type 0 passwords are never permitted
# ─────────────────────────────────────────────────────────────────────────────

deny[msg] {
    input.intent.type in {"mgmt_aaa_device", "mgmt_global_config"}
    cred := input.intent.management.credentials[_]
    cred.encryption_type == 0
    msg := sprintf("plaintext credentials (encryption_type: 0) are not permitted in intent '%v' — use type 7 or hashed credentials", [input.metadata.intent_id])
}
