# v2.0.12 Release Notes

## Release Date

2026-06-24

## Summary

v2.0.12 is a **correctness and consistency release** that aligns the intent
resolvers with the documented YAML schema, makes the example corpus the
canonical reference, and fixes live device data collection and config rendering
on Arista (and other non-Cisco-IOS) devices.

The headline themes:

- **Schema alignment** — ~25 resolvers now read the typed blocks the example
  intents actually use (`dc.*`, `routing.*`, `tunnel.*`, `vni.*`,
  `management.<subtype>`) instead of only flat top-level fields.
- **Management intents adopt a canonical wrapped form** — `mgmt_*` config now
  lives under `management.<subtype>` (e.g. `management.ssh`, `management.snmp`,
  `management.aaa_device`), read with a backward-compatible fallback to the
  legacy flat form.
- **Arista / multi-vendor fixes** — live routing-table collection, verification,
  and config rendering now identify the platform by `network_driver` rather than
  the human-facing platform name.
- **Schema + example hardening** — all 108 example intents validate against the
  pykwalify schema; several latent YAML bugs (duplicate keys, multi-document
  files, an `on` enum parsed as boolean) were fixed.

There are no new database migrations. A few **behaviour changes** are called out
under *Behaviour Changes* below — review them before upgrading.

## What's New

### Schema-aligned resolvers
- L3 routing intents read the nested `routing.*` block: `ospf` (areas/networks +
  passive/stub/nssa/default-originate tuning), `ospfv3`, `eigrp`, `isis`,
  `bgp_ipv6_af`, `bgp_evpn_af`, `route_redistribution` (list form), and
  `vrf_basic` (multi-VRF list form).
- DC/EVPN intents read the `dc.*` / `fabric.*` blocks: `dc_underlay`, `l3vni`,
  `vtep`, `anycast_gateway` (per-SVI list), `evpn_vxlan_fabric`, `l2vni`.
- `ipsec_s2s` reads the `tunnel.*` block; `mpls_l3vpn` now emits a renderable
  VRF primitive instead of blind-delegating; `service_lb_vip` resolves devices
  and renders per-device.

### Canonical `management.<subtype>` form
- All 15 `mgmt_*` resolvers read config via `management.<subtype>` with fallback
  to flat-under-`management` and legacy top-level fields.
- The example management corpus was migrated to the wrapped form.

### Device-management AAA (`aaa_device`)
- New structured `aaa_device` primitive (TACACS+/RADIUS, server groups,
  authentication/authorization/accounting, local fallback) with templates for
  all six platforms (cisco ios-xe / ios-xr / nxos, arista eos, juniper junos,
  aruba aos-cx), plus removal templates.

### Indirect device resolution
- `l2vni` / `l3vni` may reference a fabric by name (`fabric.name`) — devices are
  resolved from the matching `evpn_vxlan_fabric` intent's leaves.
- `ipsec_s2s` without an explicit `scope` resolves the device that owns
  `tunnel.local_endpoint` via Nautobot IPAM.

### Full scope contract
- `scope` now supports `all_tenant_devices`, `devices`/`device`, `sites`/`site`,
  `roles`/`role`, `tags`, and `platform`, with the documented resolution order.

## Bug Fixes

- **Arista live collection** — routing-table/VRF/BGP collection identified the
  platform by display name, returning "Unsupported platform" for devices named
  e.g. "Arista EOS"; and routes/VRFs/BGP silently returned empty when TextFSM
  produced raw text. Both fixed (network_driver resolution + raw-text fallback).
- **Config rendering** selected the template directory by platform name and fell
  through to cisco/ios-xe for devices named other than the slug — now resolves
  via `network_driver`.
- **Controller adapters** with no vendor implementation now raise
  `NotImplementedAdapterError` (treated as a hard deployment failure) instead of
  silently no-op'ing.
- **OPA** policy checks fail **closed** on resolution when OPA is unreachable
  (configurable via `opa_fail_open_on_resolution`).
- **Route-target allocation** race condition closed with `select_for_update()`.
- **Multi-document YAML** intent files now sync correctly.
- **Schema fixes** — added the `management` wrapper and missing root-level
  fields; fixed duplicate-key files, multi-document example files, and an `on`
  enum value that YAML parsed as boolean `True`.
- Resolver fixes for `prefix_list`, `static_route`, `ospf`, `bgp_ebgp/ibgp`,
  `route_policy`, `fhrp`, `gre_tunnel`, `l2vni`/`l3vni`, `storm_control`,
  `mgmt_ntp`/`mgmt_global_config`, and `reachability`/`service` sub-type
  validation (from the bug-report pass).
- CDP rendering added to the Arista `lldp_cdp` template.
- Reconciliation-schedule setup moved to the `nautobot_database_ready` signal,
  removing a "database access during app initialization" warning.

## Behaviour Changes

- **Empty/unrecognised `scope` now fails fast.** Previously an intent with no
  usable scope silently resolved to *all* active tenant devices. It now raises a
  clear error. Add an explicit scope (`all_tenant_devices: true` for fleet-wide
  intents).
- **Controller-adapter deployments fail hard** when no vendor implementation
  exists, instead of reporting success with no change.
- **OPA unreachable blocks resolution by default** (set
  `opa_fail_open_on_resolution: true` to restore fail-open).
- **Platform is resolved from `network_driver`** for live collection,
  verification, and rendering. Ensure your Nautobot Platforms set
  `network_driver` (e.g. `arista_eos`, `cisco_ios`).

## Quality

- `invoke unittest`: 589 passing.
- `invoke pylint`: 10.00/10.
- `invoke yamllint`: clean.
- `invoke check-migrations`: no changes, no warnings.
- pykwalify: all 108 example intents valid.

## Upgrade

No database migrations.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.12
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

Existing flat-form management and Layer 2 intents continue to work unchanged.
Review *Behaviour Changes* above — in particular, intents that previously relied
on an empty scope must now set an explicit scope.

**Full changelog:** [`v2.0.11...v2.0.12`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.11...v2.0.12)
