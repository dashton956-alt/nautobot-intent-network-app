# v2.0.10

## Release Date

2026-05-06

## Summary

v2.0.10 adds a comprehensive **network-as-code example library** — 33 fully documented YAML intent files covering all major intent domains. Every file documents every possible field with `MANDATORY` / `OPTIONAL` markers, valid values, defaults, and inline notes on OPA compliance enforcement. Designed as a reference starting point for teams adopting intent-based networking.

Also included: fixes to the **grouped-by-domain** collapsible panel view (Bootstrap 3 → Bootstrap 5 data attributes), OPA policy hardening across compliance, common, and capacity rule sets, and a `warn[]` / `deny[]` split in the OPA client so advisory warnings no longer block deployments.

## Added

### Network-as-Code Example Library (`network_as_code_example/`)

33 reference YAML intent files organised by domain:

| Domain | Files |
|---|---|
| Layer 2 | `vlan_provision`, `l2_access_port`, `l2_trunk_port`, `lag` |
| Layer 3 | `static_route`, `ospf`, `bgp_ebgp`, `bgp_ibgp`, `vrf_basic`, `fhrp` |
| MPLS | `mpls_l3vpn`, `sr_mpls` |
| DC / EVPN / VXLAN | `evpn_vxlan_fabric`, `l2vni`, `l3vni` |
| Security | `acl`, `fw_rule`, `ipsec_s2s`, `ipsec_ikev2`, `aaa` |
| WAN | `wan_uplink`, `nat_pat` |
| Wireless | `wireless_ssid` |
| Cloud | `cloud_vpc_peer`, `cloud_direct_connect` |
| QoS | `qos_queue`, `qos_classify` |
| Multicast | `multicast_pim_sm` |
| Management | `mgmt_ntp`, `mgmt_snmp`, `mgmt_syslog` |
| Reachability | `reachability_ip_sla` |
| Service | `service_lb_vip` |

Each file includes:
- Every possible field for the intent type, derived directly from resolver and template source
- `MANDATORY` / `OPTIONAL` inline markers on every field
- Valid values for enumerated fields (e.g. `rolling | canary | all_at_once`)
- Default values noted where the resolver provides them
- OPA compliance notes where fields affect PCI-DSS, HIPAA, or SOC2 enforcement
- Commented-out alternative scope options (`devices`, `sites`, `roles`, `all_tenant_devices`)

## Fixed

### Grouped Intent View — collapsible panels not expanding (Bootstrap 3 → Bootstrap 5)

The **Intents → Grouped by Domain** view rendered the panel accordion but panels could not be opened or closed. Nautobot 3.x ships Bootstrap 5 which changed the JavaScript data attribute naming convention. Updated `intent_grouped.html`:

| Before (Bootstrap 3) | After (Bootstrap 5) |
|---|---|
| `data-toggle="collapse"` | `data-bs-toggle="collapse"` |
| `data-parent="#domain-accordion"` | `data-bs-parent="#domain-accordion"` |
| `data-target="#collapse-N"` | `data-bs-target="#collapse-N"` |
| `class="collapse in"` | `class="collapse show"` |

### OPA Policy Hardening

- **compliance.rego** — Added `warn[]` advisory set (SOC2 SNMPv2c, `preferred` encryption, `save_config: false`); fixed PCI-DSS blind spot for `ipsec_ikev2` type using `security.ipsec_ikev2.ikev2.proposal.*` path; added HIPAA IKEv2/cipher enforcement; universal deployment strategy enforcement for high-risk types; added verification trigger enforcement for PCI-DSS and HIPAA
- **common.rego** — Fixed `version: 0` double-fire using `is_number()` check; added version upper-bound (>9999); added scope presence validation; added plaintext credential enforcement (`encryption_type: 0`)
- **capacity.rego** — Removed `ipsec_ikev2` from tunnel block requirement (uses `security.*` path, not `tunnel.*`)
- **approval_gate.rego** — Removed redundant `approved_by` deny rule that was silently failing when the key was absent
- **bgp_ebgp.rego** — Fixed `sprintf` crash when `neighbor.ip` was undefined using `object.get()`

### OPA Client — `warn[]` / `deny[]` split

`check_intent_policy()` and `check_approval_gate()` now collect `warn[]` and `deny[]` separately. Advisory warnings are logged and returned in the response but no longer block deployments. The `allowed` flag is only set to `False` by `deny[]` violations.

## Upgrade

No database migrations are included in this release.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.10
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**Full changelog:** [`v2.0.9...v2.0.10`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.9...v2.0.10)
