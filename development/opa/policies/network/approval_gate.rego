# network/approval_gate.rego
# Rules specifically evaluated during the approval gate check.
# Called as part of check_intent_policy() via the network.common package,
# but kept separate for clarity so approval-specific logic is easy to find.
#
# Test cases (see development/opa/tests/test_approval_gate.rego):
#   PASS: intent has valid change_ticket (CHG + 7 digits), description >= 10 chars
#   FAIL: intent missing change_ticket
#   FAIL: intent with invalid change_ticket format (e.g. "TICKET-123")
#   FAIL: intent description too short (< 10 chars)
#   FAIL: high-impact intent type without approved_by set

package network.common

import future.keywords.in

# ─────────────────────────────────────────────────────────────────────────────
# Approval gate: high-impact types MUST have approved_by populated
# before the approval record is created. This prevents the same person
# who created the intent from also self-approving it without a second review.
# ─────────────────────────────────────────────────────────────────────────────

deny[msg] {
    input.intent.type in high_impact_types
    ab := input.metadata.approved_by
    count(ab) == 0
    msg := sprintf(
        "intent type '%v' is high-impact and requires a prior approved_by value before approval",
        [input.intent.type],
    )
}