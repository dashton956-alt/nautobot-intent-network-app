# Using the App

This document describes common use-cases and scenarios for the Intent Networking app.

## General Usage

The core workflow is always the same regardless of intent type:

1. **Author** — Write a declarative YAML file describing desired state
2. **Sync** — Push to Git; Nautobot auto-syncs via `GitRepository`
3. **Resolve** — The resolver translates the intent into a deployment plan with allocated resources
4. **Deploy** — Nornir pushes device configurations
5. **Verify** — Post-deployment checks confirm the intent is satisfied
6. **Reconcile** — Scheduled drift detection compares live state against the intent

## Use Cases and Common Workflows

### Enterprise L3VPN Connectivity

**Scenario:** Connect multiple branch offices to a data centre over MPLS L3VPN.

- **Intent type:** `mpls_l3vpn`
- **What the app does:** Allocates a VRF (with RD/RT values via Nautobot native IPAM), resolves PE-facing interface configurations, and deploys VRF + BGP peering to each PE router.
- **Resource allocation:** Automatic VRF, RD (`<ASN>:<counter>`), and RT allocation within the configured Namespace.

### Data Centre EVPN/VXLAN Fabric

**Scenario:** Provision a new tenant overlay across a leaf-spine VXLAN EVPN fabric.

- **Intent type:** `evpn_vxlan_fabric`
- **What the app does:** Allocates a VNI from a `VxlanVniPool`, creates VLAN-to-VNI mappings, resolves EVPN type-2/type-5 route configurations for each leaf switch.
- **Resource pools used:** `VxlanVniPool`, `TunnelIdPool`

### Security Segmentation

**Scenario:** Enforce PCI-DSS network segmentation between cardholder data environments and general corporate traffic.

- **Intent type:** `acl_ipv4` / `zone_based_firewall`
- **OPA integration:** An OPA policy verifies that the proposed ACL rules meet PCI-DSS requirements before deployment is allowed.
- **Audit trail:** Every approval and deployment action is recorded in `IntentAuditEntry`.

### WAN / SD-WAN Site Onboarding

**Scenario:** Onboard a new branch site with DMVPN or SD-WAN overlay connectivity.

- **Intent types:** `dmvpn_spoke`, `sdwan_edge`, `ipsec_tunnel`
- **What the app does:** Allocates a tunnel ID from `TunnelIdPool`, resolves crypto maps or SD-WAN templates, assigns a loopback from `ManagedLoopbackPool`.

### Wireless VLAN Provisioning

**Scenario:** Roll out a new SSID across all campus APs with a dedicated VLAN.

- **Intent type:** `wireless_ssid`
- **Resource pools used:** `WirelessVlanPool` — allocates a VLAN ID per site for the SSID.

### BGP Peering (eBGP / iBGP)

**Scenario:** Establish BGP peering between a customer edge and provider edge router.

- **Intent types:** `bgp_ebgp`, `bgp_ibgp`
- **What the app does:** Resolves the BGP session configuration including ASN, neighbor address, address families, and route policies.

### QoS Policy Deployment

**Scenario:** Apply consistent QoS marking and queuing policies across all WAN interfaces.

- **Intent types:** `qos_policy`, `traffic_shaping`, `dscp_marking`
- **What the app does:** Resolves class-map, policy-map, and service-policy configurations per-device.

### Continuous Compliance (Reconciliation)

**Scenario:** Detect and remediate configuration drift across all deployed intents.

- **How it works:** The `IntentReconciliationJob` runs on a configurable schedule (default: hourly). For each deployed intent, it re-verifies the live state. If drift is detected:
    1. An event is emitted (`intent.drift`)
    2. Slack/PagerDuty notifications are sent
    3. If `auto_remediation_enabled` is `True` and OPA approves, the app automatically re-deploys the intent
    4. If auto-remediation is not possible, a GitHub issue is created

### Multi-Tenant Isolation

**Scenario:** Ensure strict resource isolation between tenants.

- **Built-in guardrails:**
    - VRF allocation is scoped per-tenant within a Namespace
    - `max_vrfs_per_tenant` limits prevent resource exhaustion
    - Tenant isolation validation runs during resolution to detect conflicts

## Topology Viewer

The app includes an interactive, full-screen topology viewer accessible at **Intent Networking → Topology Viewer**. Features include:

- **vis.js graph** — Devices as nodes, links as edges, colour-coded by intent status
- **Intent highlighting** — Click an intent to highlight affected devices and links
- **Live data overlay** — Interface status, IP addresses, and VRF membership shown on hover
- **Filtering** — Filter by tenant, site, or intent type
