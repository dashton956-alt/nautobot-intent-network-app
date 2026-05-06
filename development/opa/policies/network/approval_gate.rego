# network/approval_gate.rego
# Rules specifically evaluated during the approval gate check.
# Shares package network.common with common.rego — OPA merges both files at load time.
# high_impact_types is defined in common.rego and is in scope here.
#
# NOTE: The approved_by check for high-impact types is handled in common.rego
# (lines covering `not input.metadata.approved_by` and `== ""`). It is not
# duplicated here to avoid firing two violations for the same field.
#
# Test cases (see development/opa/tests/network/approval_gate_test.rego):
#   PASS: intent has valid change_ticket (CHG + 7 digits), description >= 10 chars
#   FAIL: intent missing change_ticket
#   FAIL: intent with invalid change_ticket format (e.g. "TICKET-123")
#   FAIL: intent description too short (< 10 chars)
#   FAIL: high-impact intent type without approved_by set

package network.common

import future.keywords.in
