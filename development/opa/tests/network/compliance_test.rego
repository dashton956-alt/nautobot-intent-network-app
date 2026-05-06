# compliance_test.rego
# OPA unit tests for network/compliance.rego rules.
# Run with: opa test ./development/opa/policies/ --v0-compatible -v

package network.compliance

import future.keywords.in

# ─── fixtures ────────────────────────────────────────────────────────────────

_pci_base := {
    "intent": {
        "type": "connectivity",
        "version": 1,
        "description": "PCI-DSS segmentation intent",
        "tenant": "payments",
        "scope": {"devices": ["fw-01"]},
        "policy": {
            "compliance": "PCI-DSS",
            "encryption": "required",
            "max_latency_ms": 10,
        },
        "isolation": {"deny_protocols": ["telnet", "http", "ftp"]},
        "verification": {"trigger": "both"},
        "deployment": {"strategy": "rolling"},
    },
    "metadata": {
        "intent_id": "pci-seg-001",
        "change_ticket": "CHG0020001",
        "approved_by": "security-team",
    },
}

_hipaa_base := {
    "intent": {
        "type": "connectivity",
        "version": 1,
        "description": "HIPAA PHI network segmentation",
        "tenant": "healthcare",
        "scope": {"devices": ["fw-02"]},
        "policy": {
            "compliance": "HIPAA",
            "encryption": "required",
        },
        "verification": {"trigger": "both"},
        "deployment": {"strategy": "rolling"},
    },
    "metadata": {
        "intent_id": "hipaa-seg-001",
        "change_ticket": "CHG0020002",
        "approved_by": "privacy-officer",
    },
}

_ipsec_tunnel_base := {
    "intent": {
        "type": "ipsec_s2s",
        "version": 1,
        "description": "PCI-DSS site-to-site IPSec tunnel",
        "tenant": "payments",
        "scope": {"devices": ["fw-01"]},
        "policy": {
            "compliance": "PCI-DSS",
            "encryption": "required",
        },
        "tunnel": {
            "ike_version": 2,
            "encryption": "aes-256-gcm",
            "integrity": "sha256",
            "dh_group": 14,
        },
        "verification": {"trigger": "both"},
        "deployment": {"strategy": "canary"},
    },
    "metadata": {
        "intent_id": "pci-ipsec-001",
        "change_ticket": "CHG0020003",
        "approved_by": "security-team",
    },
}

_ipsec_ikev2_base := {
    "intent": {
        "type": "ipsec_ikev2",
        "version": 1,
        "description": "PCI-DSS IKEv2 tunnel with proposal config",
        "tenant": "payments",
        "scope": {"devices": ["fw-01"]},
        "policy": {
            "compliance": "PCI-DSS",
            "encryption": "required",
        },
        "security": {
            "ipsec_ikev2": {
                "ikev2": {
                    "ike_version": 2,
                    "proposal": {
                        "encryption": "aes-256-gcm",
                        "dh_group": 14,
                    },
                },
            },
        },
        "verification": {"trigger": "both"},
        "deployment": {"strategy": "canary"},
    },
    "metadata": {
        "intent_id": "pci-ikev2-001",
        "change_ticket": "CHG0020004",
        "approved_by": "security-team",
    },
}

# ─── PCI-DSS — encryption field ──────────────────────────────────────────────

test_pci_valid_passes {
    count(deny) == 0 with input as _pci_base
}

test_pci_missing_encryption_denied {
    inp := json.remove(_pci_base, ["/intent/policy/encryption"])
    violations := deny with input as inp
    some v in violations
    contains(v, "[PCI-DSS] encryption field is required")
}

test_pci_encryption_not_required_denied {
    inp := json.patch(_pci_base, [{"op": "replace", "path": "/intent/policy/encryption", "value": "none"}])
    violations := deny with input as inp
    some v in violations
    contains(v, "[PCI-DSS] encryption must be 'required'")
}

# ─── PCI-DSS — protocol isolation ────────────────────────────────────────────

test_pci_telnet_allowed_denied {
    inp := json.patch(_pci_base, [{"op": "replace", "path": "/intent/isolation/deny_protocols", "value": ["http", "ftp"]}])
    violations := deny with input as inp
    some v in violations
    contains(v, "telnet must be explicitly denied")
}

# ─── PCI-DSS — latency ───────────────────────────────────────────────────────

test_pci_latency_too_high_denied {
    inp := json.patch(_pci_base, [{"op": "replace", "path": "/intent/policy/max_latency_ms", "value": 21}])
    violations := deny with input as inp
    some v in violations
    contains(v, "max_latency_ms must be <= 20ms")
}

# ─── PCI-DSS — verification trigger ─────────────────────────────────────────

test_pci_trigger_not_both_denied {
    inp := json.patch(_pci_base, [{"op": "replace", "path": "/intent/verification/trigger", "value": "on_deploy"}])
    violations := deny with input as inp
    some v in violations
    contains(v, "verification.trigger must be 'both'")
}

# ─── PCI-DSS — IPSec tunnel.* path ───────────────────────────────────────────

test_pci_ipsec_tunnel_valid_passes {
    count(deny) == 0 with input as _ipsec_tunnel_base
}

test_pci_ipsec_tunnel_ikev1_denied {
    inp := json.patch(_ipsec_tunnel_base, [{"op": "replace", "path": "/intent/tunnel/ike_version", "value": 1}])
    violations := deny with input as inp
    some v in violations
    contains(v, "IKEv2 is required")
}

test_pci_ipsec_tunnel_weak_cipher_denied {
    inp := json.patch(_ipsec_tunnel_base, [{"op": "replace", "path": "/intent/tunnel/encryption", "value": "aes-128-cbc"}])
    violations := deny with input as inp
    some v in violations
    contains(v, "AES-256 is required")
}

test_pci_ipsec_tunnel_sha1_denied {
    inp := json.patch(_ipsec_tunnel_base, [{"op": "replace", "path": "/intent/tunnel/integrity", "value": "sha1"}])
    violations := deny with input as inp
    some v in violations
    contains(v, "SHA-1 is not permitted")
}

test_pci_ipsec_tunnel_weak_dh_denied {
    inp := json.patch(_ipsec_tunnel_base, [{"op": "replace", "path": "/intent/tunnel/dh_group", "value": 2}])
    violations := deny with input as inp
    some v in violations
    contains(v, "DH group must be >= 14")
}

# ─── PCI-DSS — ipsec_ikev2 security.* path ───────────────────────────────────

test_pci_ikev2_valid_passes {
    count(deny) == 0 with input as _ipsec_ikev2_base
}

test_pci_ikev2_weak_cipher_denied {
    inp := json.patch(_ipsec_ikev2_base, [{"op": "replace", "path": "/intent/security/ipsec_ikev2/ikev2/proposal/encryption", "value": "aes-128-cbc"}])
    violations := deny with input as inp
    some v in violations
    contains(v, "AES-256 is required")
}

test_pci_ikev2_weak_dh_denied {
    inp := json.patch(_ipsec_ikev2_base, [{"op": "replace", "path": "/intent/security/ipsec_ikev2/ikev2/proposal/dh_group", "value": 5}])
    violations := deny with input as inp
    some v in violations
    contains(v, "DH group must be >= 14")
}

test_pci_ikev2_aes_gcm_128_variant_denied {
    inp := json.patch(_ipsec_ikev2_base, [{"op": "replace", "path": "/intent/security/ipsec_ikev2/ikev2/proposal/encryption", "value": "aes-gcm-128"}])
    violations := deny with input as inp
    some v in violations
    contains(v, "AES-256 is required")
}

# ─── HIPAA ───────────────────────────────────────────────────────────────────

test_hipaa_valid_passes {
    count(deny) == 0 with input as _hipaa_base
}

test_hipaa_encryption_none_denied {
    inp := json.patch(_hipaa_base, [{"op": "replace", "path": "/intent/policy/encryption", "value": "none"}])
    violations := deny with input as inp
    some v in violations
    contains(v, "[HIPAA] encryption cannot be 'none'")
}

test_hipaa_trigger_not_both_denied {
    inp := json.patch(_hipaa_base, [{"op": "replace", "path": "/intent/verification/trigger", "value": "scheduled"}])
    violations := deny with input as inp
    some v in violations
    contains(v, "[HIPAA] verification.trigger must be 'both'")
}

test_hipaa_ipsec_ikev2_weak_cipher_denied {
    inp := json.patch(_ipsec_ikev2_base, [
        {"op": "replace", "path": "/intent/policy/compliance", "value": "HIPAA"},
        {"op": "replace", "path": "/intent/security/ipsec_ikev2/ikev2/proposal/encryption", "value": "aes-128-gcm"},
    ])
    violations := deny with input as inp
    some v in violations
    contains(v, "[HIPAA] AES-256 minimum")
}

# ─── Deployment strategy (universal) ─────────────────────────────────────────

test_high_risk_all_at_once_denied {
    inp := json.patch(_pci_base, [
        {"op": "replace", "path": "/intent/type", "value": "dmvpn"},
        {"op": "replace", "path": "/intent/deployment/strategy", "value": "all_at_once"},
    ])
    violations := deny with input as inp
    some v in violations
    contains(v, "canary or rolling")
}

test_high_risk_rolling_passes {
    # Universal rule should not fire for rolling strategy
    violations := deny with input as _ipsec_tunnel_base
    not_strategy_msg := [v | v := violations[_]; contains(v, "canary or rolling")]
    count(not_strategy_msg) == 0
}

# ─── SOC2 warn (non-blocking) ────────────────────────────────────────────────

test_soc2_snmpv2c_is_warn_not_deny {
    inp := {
        "intent": {
            "type": "mgmt_snmp",
            "version": 1,
            "description": "SOC2 SNMP management intent",
            "tenant": "lab",
            "scope": {"devices": ["leaf-01"]},
            "policy": {"compliance": "SOC2"},
            "management": {"snmp_version": "v2c"},
            "verification": {"trigger": "both"},
            "deployment": {"strategy": "rolling"},
        },
        "metadata": {
            "intent_id": "soc2-snmp-001",
            "change_ticket": "CHG0020005",
            "approved_by": "ops",
        },
    }
    # Must not block
    count(deny) == 0 with input as inp
    # Must produce an advisory warning
    warnings := warn with input as inp
    some w in warnings
    contains(w, "SNMPv2c is not recommended")
}

# ─── Advisory warnings ───────────────────────────────────────────────────────

test_save_config_false_is_warn {
    inp := json.patch(_pci_base, [{"op": "add", "path": "/intent/deployment/save_config", "value": false}])
    warnings := warn with input as inp
    some w in warnings
    contains(w, "save_config is false")
}

test_preferred_encryption_is_warn {
    inp := json.patch(_pci_base, [{"op": "replace", "path": "/intent/policy/encryption", "value": "preferred"}])
    warnings := warn with input as inp
    some w in warnings
    contains(w, "preferred bypasses all compliance")
}
