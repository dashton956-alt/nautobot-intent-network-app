# network/intent_types/bgp_ebgp.rego
# Per-intent-type policy for bgp_ebgp intents.

package network.intent_types.bgp_ebgp

deny[msg] {
    not input.intent.routing.as_number
    msg := "[bgp_ebgp] routing.as_number is required"
}

deny[msg] {
    input.intent.routing.as_number <= 0
    msg := sprintf("[bgp_ebgp] routing.as_number must be positive, got %v", [input.intent.routing.as_number])
}

deny[msg] {
    not input.intent.routing.neighbors
    msg := "[bgp_ebgp] at least one neighbor must be specified in routing.neighbors"
}

deny[msg] {
    count(input.intent.routing.neighbors) == 0
    msg := "[bgp_ebgp] routing.neighbors must not be empty"
}

deny[msg] {
    neighbor := input.intent.routing.neighbors[_]
    not neighbor.remote_as
    ip := object.get(neighbor, "ip", "<unknown>")
    msg := sprintf("[bgp_ebgp] neighbor '%v' is missing remote_as", [ip])
}

deny[msg] {
    neighbor := input.intent.routing.neighbors[_]
    neighbor.remote_as == input.intent.routing.as_number
    ip := object.get(neighbor, "ip", "<unknown>")
    msg := sprintf("[bgp_ebgp] neighbor '%v' has same ASN as local router (%v) — use bgp_ibgp intent type instead", [ip, input.intent.routing.as_number])
}
