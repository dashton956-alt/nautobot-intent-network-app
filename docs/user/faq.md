# Frequently Asked Questions

## General

### What is an "intent"?

An intent is a declarative description of desired network state, expressed as a YAML file. Instead of specifying device-by-device CLI commands, you describe *what* you want (e.g. "L3VPN connecting sites A and B") and the app figures out *how* to achieve it.

### How many intent types are supported?

The app supports **129 intent types** across 14 network domains: Layer 2, Layer 3, MPLS/SP, DC/EVPN/VXLAN, Security, WAN/SD-WAN, Wireless, Cloud/Hybrid, QoS, Multicast, Management, Reachability, Service, and legacy types.

### Where are intents stored?

Intents are stored as YAML files in a Git repository. Nautobot syncs them via its native `GitRepository` integration and stores parsed copies in the database as `Intent` model records.

## Resource Allocation

### How are VRFs and Route Targets allocated?

The app uses Nautobot's native IPAM models (`ipam.VRF` and `ipam.RouteTarget`). When an intent requires a VRF, the allocator creates a VRF object within the configured Namespace with an auto-generated RD in `<ASN>:<counter>` format. Route Targets are similarly auto-created.

### What happened to the custom RD/RT pool models?

As of v0.5, the custom `RouteDistinguisherPool`, `RouteDistinguisher`, `RouteTargetPool`, and `RouteTarget` models were replaced with Nautobot's native IPAM models. This avoids data duplication and integrates seamlessly with the rest of Nautobot's IPAM features. See the [Upgrade Guide](../admin/upgrade.md#upgrading-to-v05-ipam-refactor) for migration details.

### What resource pools are still available?

The app still manages four custom pool types for resources not natively modelled in Nautobot:

- **VxlanVniPool / VniAllocation** — VXLAN Network Identifier ranges
- **TunnelIdPool / TunnelIdAllocation** — Tunnel interface IDs
- **ManagedLoopbackPool / ManagedLoopback** — /32 loopback IP ranges
- **WirelessVlanPool / WirelessVlanAllocation** — VLAN ID ranges for wireless SSIDs

## Deployment & Verification

### What happens if a deployment fails?

If any device in a deployment fails, the intent status moves to **Failed**. You can then trigger the `IntentRollbackJob` to revert all changes to the previous known-good configuration. The rollback is also audited.

### How does drift detection work?

The `IntentReconciliationJob` runs on a configurable schedule (default: hourly). It re-verifies every deployed intent against the live network. If drift is found, it emits an event and optionally auto-remediates (if OPA approves).

### Is OPA required?

No. OPA integration is optional. Without OPA, the policy-check step is skipped and intents proceed directly to deployment. If you want pre-deployment policy enforcement, configure an OPA endpoint.

## Integration

### Can I use the REST API instead of the UI?

Yes. Every model has full CRUD REST API endpoints, and the lifecycle actions (resolve, deploy, verify, rollback) are available as API actions. See [External Interactions](external_interactions.md#nautobot-rest-api-endpoints).

### How do I get notifications?

Configure one or more of the following in `PLUGINS_CONFIG`:

- `slack_webhook_url` — Slack incoming webhook
- `pagerduty_routing_key` — PagerDuty Events API
- `github_repo` + `github_api_url` — GitHub issue creation for drift
- `webhook_urls` — Generic webhooks for any event
