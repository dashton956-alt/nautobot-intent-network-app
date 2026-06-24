# v2.0.11 Release Notes

## Release Date

2026-05-07

## Summary

v2.0.11 adds multi-port support for `l2_access_port` and `l2_trunk_port` intents. Previously, one intent was required per switchport. A single intent can now configure any number of ports in one deployment using a `ports` list — each entry specifying its own interface, VLAN(s), and optional per-port settings.

The change is fully backward-compatible. Existing intents using the single `interface` / `vlan_id` form continue to work without modification.

On startup, Nautobot will log `WARNING` messages indicating that serializers for `VniAllocation`, `TunnelIdPool`, `TunnelIdAllocation`, `ManagedLoopbackPool`, `ManagedLoopback`, `WirelessVlanPool`, and `WirelessVlanAllocation` are not found. These warnings are cosmetic — the models function correctly and no data is affected. API serializers for these models are absent; they will be added in a future release.

## What's New

- **Multi-port `l2_access_port`** — add a `ports` list where each entry has `interface`, `vlan_id`, and optional `voice_vlan`, `description`, `portfast`, `bpdu_guard`
- **Multi-port `l2_trunk_port`** — add a `ports` list where each entry has `interface`, and optional `allowed_vlans`, `native_vlan`, `description`
- **Example YAML files** — `network_as_code_example/intents/layer2/l2_access_port.yaml` and `l2_trunk_port.yaml` with full MANDATORY/OPTIONAL field documentation and legacy form reference

## Upgrade

No database migrations. Drop-in replacement for v2.0.10.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.11
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

No breaking changes. Existing `l2_access_port` and `l2_trunk_port` intents using the single `interface` / `vlan_id` form continue to work unchanged — no YAML edits required.

## Examples

### Multi-Port Access

```yaml
id: acme-l2-access-001
type: l2_access_port
version: 1
tenant: acme-corp
description: "Configure server access ports"
change_ticket: CHG0040001
scope:
  sites: [dc-east]
ports:
  - interface: GigabitEthernet0/1
    vlan_id: 100
    voice_vlan: 150
  - interface: GigabitEthernet0/2
    vlan_id: 100
  - interface: GigabitEthernet0/3
    vlan_id: 200
```

### Multi-Port Trunk

```yaml
id: acme-l2-trunk-001
type: l2_trunk_port
version: 1
tenant: acme-corp
description: "Configure uplink trunk ports"
change_ticket: CHG0040003
scope:
  sites: [dc-east]
ports:
  - interface: GigabitEthernet0/47
    allowed_vlans: [100, 200, 300]
    native_vlan: 1
  - interface: GigabitEthernet0/48
    allowed_vlans: [100, 200, 300]
    native_vlan: 1
```
