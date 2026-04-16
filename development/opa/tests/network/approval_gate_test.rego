# approval_gate_test.rego
# OPA unit tests for the approval gate policy.
# Run with: opa test ./development/opa/policies/ --v0-compatible -v
#
# Covers three scenarios:
#   PASS  — valid intent with correct change_ticket, description, tenant
#   FAIL  — missing ticket, wrong format, short description, high-impact no approver
#   Edge  — ticket prefix/length boundaries

package network.common

import future.keywords.in

# ─── test fixtures ────────────────────────────────────────────────────────────

_valid := {
    "intent": {
        "type": "acl",
        "version": 1,
        "description": "Management plane ACL for lab EOS devices",
        "tenant": "arista-lab",
    },
    "metadata": {
        "intent_id": "lab-acl-001",
        "version": 1,
        "change_ticket": "CHG0020015",
        "approved_by": "d.network",
    },
    "tenant": "arista-lab",
    "topology": {},
}

_no_ticket := json.patch(_valid, [{"op": "replace", "path": "/metadata/change_ticket", "value": ""}])

_bad_ticket := json.patch(_valid, [{"op": "replace", "path": "/metadata/change_ticket", "value": "TICKET-123"}])

_short_desc := json.patch(_valid, [{"op": "replace", "path": "/intent/description", "value": "Too short"}])

_zbf_no_approver := {
    "intent": {
        "type": "zbf",
        "version": 1,
        "description": "ZBF policy from INSIDE to OUTSIDE zones",
        "tenant": "arista-lab",
    },
    "metadata": {
        "intent_id": "lab-zbf-001",
        "version": 1,
        "change_ticket": "CHG0020016",
        "approved_by": "",
    },
    "tenant": "arista-lab",
    "topology": {},
}

# ─── PASS tests ───────────────────────────────────────────────────────────────

test_valid_intent_passes {
    count(deny) == 0 with input as _valid
}

test_ticket_chg_five_digits_passes {
    inp := json.patch(_valid, [{"op": "replace", "path": "/metadata/change_ticket", "value": "CHG00001"}])
    count(deny) == 0 with input as inp
}

test_ticket_req_ten_digits_passes {
    inp := json.patch(_valid, [{"op": "replace", "path": "/metadata/change_ticket", "value": "REQ1234567890"}])
    count(deny) == 0 with input as inp
}

test_ticket_task_prefix_passes {
    inp := json.patch(_valid, [{"op": "replace", "path": "/metadata/change_ticket", "value": "TASK0012345"}])
    count(deny) == 0 with input as inp
}

# ─── FAIL tests ───────────────────────────────────────────────────────────────

test_missing_change_ticket_denied {
    violations := deny with input as _no_ticket
    count(violations) > 0
    some v in violations
    contains(v, "change_ticket is required")
}

test_invalid_ticket_format_denied {
    violations := deny with input as _bad_ticket
    count(violations) > 0
    some v in violations
    contains(v, "does not match required format")
}

test_short_description_denied {
    violations := deny with input as _short_desc
    count(violations) > 0
    some v in violations
    contains(v, "description must be at least 10 characters")
}

test_high_impact_without_approver_denied {
    violations := deny with input as _zbf_no_approver
    count(violations) > 0
    some v in violations
    contains(v, "high-impact")
}
