# network/intent_types/fw_rule.rego
# Per-intent-type policy for fw_rule intents.

package network.intent_types.fw_rule

import future.keywords.in

deny[msg] {
    not input.intent.firewall.action
    msg := "[fw_rule] firewall.action is required (allow|deny|drop)"
}

deny[msg] {
    input.intent.firewall.action
    not input.intent.firewall.action in {"allow", "deny", "drop"}
    msg := sprintf("[fw_rule] firewall.action '%v' is invalid — must be allow, deny, or drop", [input.intent.firewall.action])
}

deny[msg] {
    input.intent.firewall.action == "allow"
    input.intent.firewall.source == "0.0.0.0/0"
    input.intent.firewall.destination == "0.0.0.0/0"
    msg := "[fw_rule] permit-any-any (0.0.0.0/0 -> 0.0.0.0/0 allow) is not permitted"
}

deny[msg] {
    input.intent.firewall.direction == "inbound"
    not input.intent.firewall.destination_zone
    msg := "[fw_rule] inbound firewall rules must specify a destination_zone"
}
