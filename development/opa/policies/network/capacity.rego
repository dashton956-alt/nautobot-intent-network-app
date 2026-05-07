# network/capacity.rego
# Resource capacity and operational limits.
# Called by opa_client.check_intent_policy() via /v1/data/network/capacity

package network.capacity

import future.keywords.in

deny[msg] {
    input.intent.type == "bgp_ebgp"
    count(input.intent.routing.neighbors) > 8
    msg := sprintf("bgp_ebgp exceeds maximum of 8 eBGP peers per intent, got %v", [count(input.intent.routing.neighbors)])
}

deny[msg] {
    input.intent.type == "bgp_ibgp"
    count(input.intent.routing.neighbors) > 64
    msg := sprintf("bgp_ibgp exceeds maximum of 64 iBGP peers per intent, got %v", [count(input.intent.routing.neighbors)])
}

deny[msg] {
    input.intent.type in {"l2_access", "l2_trunk"}
    count(input.intent.vlans) > 100
    msg := sprintf("L2 intent exceeds maximum of 100 VLANs, got %v", [count(input.intent.vlans)])
}

deny[msg] {
    input.intent.type in {"l2_access", "l2_trunk"}
    vlan := input.intent.vlans[_]
    vlan.id > 4094
    msg := sprintf("VLAN ID %v is out of range (1-4094)", [vlan.id])
}

deny[msg] {
    input.intent.type in {"l2_access", "l2_trunk"}
    vlan := input.intent.vlans[_]
    vlan.id < 1
    msg := sprintf("VLAN ID %v is out of range (1-4094)", [vlan.id])
}

deny[msg] {
    # ipsec_ikev2 uses security.ipsec_ikev2.* not tunnel.* — excluded here
    input.intent.type in {"ipsec_s2s", "gre_over_ipsec"}
    not input.intent.tunnel
    msg := "IPSec intent requires a 'tunnel' block"
}

deny[msg] {
    input.intent.scope.devices
    count(input.intent.scope.devices) == 0
    msg := "intent scope.devices is empty — at least one device must be targeted"
}

deny[msg] {
    input.intent.scope.devices
    count(input.intent.scope.devices) > 50
    msg := sprintf("intent targets too many devices (%v) — maximum is 50 per intent", [count(input.intent.scope.devices)])
}
