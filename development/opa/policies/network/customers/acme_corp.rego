# network/customers/acme_corp.rego
# Per-tenant policy for tenant "acme-corp" (slug becomes acme_corp).
# Called by opa_client.check_intent_policy() via /v1/data/network/customers/acme_corp

package network.customers.acme_corp

import future.keywords.in

deny[msg] {
    count(input.metadata.change_ticket) == 0
    msg := "[acme_corp] change_ticket is mandatory for all ACME Corp intents"
}

deny[msg] {
    input.intent.type == "bgp_ebgp"
    count(input.intent.routing.neighbors) > 2
    msg := sprintf("[acme_corp] ACME Corp policy limits eBGP peers to 2 per intent, got %v", [count(input.intent.routing.neighbors)])
}

deny[msg] {
    input.intent.policy.compliance == "PCI-DSS"
    not input.metadata.approved_by
    msg := "[acme_corp] approved_by is required for all PCI-DSS intents in ACME Corp"
}

deny[msg] {
    input.intent.policy.compliance == "PCI-DSS"
    input.metadata.approved_by == ""
    msg := "[acme_corp] approved_by is required for all PCI-DSS intents in ACME Corp"
}
