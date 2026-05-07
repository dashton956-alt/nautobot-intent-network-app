# common_test.rego
# OPA unit tests for network/common.rego rules.
# Run with: opa test ./development/opa/policies/ --v0-compatible -v

package network.common

import future.keywords.in

# ─── fixtures ────────────────────────────────────────────────────────────────

_base := {
    "intent": {
        "type": "acl",
        "version": 1,
        "description": "Management plane ACL for lab devices",
        "tenant": "lab",
        "scope": {"devices": ["leaf-01"]},
    },
    "metadata": {
        "intent_id": "lab-acl-001",
        "version": 1,
        "change_ticket": "CHG0020015",
        "approved_by": "d.network",
    },
    "tenant": "lab",
    "topology": {},
}

# ─── version ─────────────────────────────────────────────────────────────────

test_version_absent_denied {
    inp := json.remove(_base, ["/intent/version"])
    violations := deny with input as inp
    some v in violations
    contains(v, "version is required")
}

test_version_zero_denied {
    inp := json.patch(_base, [{"op": "replace", "path": "/intent/version", "value": 0}])
    violations := deny with input as inp
    some v in violations
    contains(v, "positive integer")
    # version: 0 must NOT also fire the "required" rule
    not_required_msg := [v | v := violations[_]; contains(v, "required")]
    count(not_required_msg) == 0
}

test_version_negative_denied {
    inp := json.patch(_base, [{"op": "replace", "path": "/intent/version", "value": -1}])
    violations := deny with input as inp
    some v in violations
    contains(v, "positive integer")
}

test_version_over_limit_denied {
    inp := json.patch(_base, [{"op": "replace", "path": "/intent/version", "value": 10000}])
    violations := deny with input as inp
    some v in violations
    contains(v, "9999")
}

test_version_valid_passes {
    count(deny) == 0 with input as _base
}

# ─── scope presence ──────────────────────────────────────────────────────────

test_no_scope_denied {
    inp := json.remove(_base, ["/intent/scope"])
    violations := deny with input as inp
    some v in violations
    contains(v, "scope")
}

test_scope_all_tenant_devices_passes {
    inp := json.patch(_base, [{"op": "replace", "path": "/intent/scope", "value": {"all_tenant_devices": true}}])
    # Scope rule should not fire
    violations := deny with input as inp
    not_scope_msg := [v | v := violations[_]; contains(v, "scope")]
    count(not_scope_msg) == 0
}

test_scope_sites_passes {
    inp := json.patch(_base, [{"op": "replace", "path": "/intent/scope", "value": {"sites": ["dc-east"]}}])
    violations := deny with input as inp
    not_scope_msg := [v | v := violations[_]; contains(v, "scope")]
    count(not_scope_msg) == 0
}

test_scope_roles_passes {
    inp := json.patch(_base, [{"op": "replace", "path": "/intent/scope", "value": {"roles": ["leaf"]}}])
    violations := deny with input as inp
    not_scope_msg := [v | v := violations[_]; contains(v, "scope")]
    count(not_scope_msg) == 0
}

# ─── plaintext credentials ───────────────────────────────────────────────────

test_plaintext_credential_denied {
    inp := json.patch(_base, [
        {"op": "replace", "path": "/intent/type", "value": "mgmt_aaa_device"},
        {"op": "add", "path": "/intent/management", "value": {
            "credentials": [{"username": "admin", "encryption_type": 0, "password": "cisco123"}]
        }},
    ])
    violations := deny with input as inp
    some v in violations
    contains(v, "plaintext credentials")
}

test_hashed_credential_passes {
    inp := json.patch(_base, [
        {"op": "replace", "path": "/intent/type", "value": "mgmt_aaa_device"},
        {"op": "add", "path": "/intent/management", "value": {
            "credentials": [{"username": "admin", "encryption_type": 7, "password": "0822455D0A16"}]
        }},
    ])
    violations := deny with input as inp
    not_cred_msg := [v | v := violations[_]; contains(v, "plaintext")]
    count(not_cred_msg) == 0
}
