# v2.0.16 Release Notes

## Release Date

2026-07-23

## Summary

v2.0.16 bundles a **security hardening** pass, a **DC-underlay correctness fix**,
and **two new intent types** that let the app describe a complete eBGP-VXLAN
fabric end-to-end (surfaced validating a real customer POC).

There are no new database migrations.

## Security

- **Topology viewer stored/DOM XSS fixed.** The viewer built HTML from raw
  server data (intent metadata and live device-collected fields — interface
  descriptions, ARP/route/BGP tables) via `innerHTML` with no escaping. All
  interpolated values are now HTML-escaped, and the inline `onclick` handlers
  that embedded values in a JS-string context read from `data-*` attributes
  instead.
- **Catalyst Center TLS verification is on by default.** The adapter previously
  hardcoded `verify=False` while sending controller admin credentials (MITM
  risk). Verification now defaults on; a self-signed DNAC is handled by trusting
  a CA bundle (`catalyst_center_ca_bundle`), and it can be disabled only via an
  explicit opt-out (`catalyst_center_verify_ssl: false`).

## What's New

### `routed_interface` intent type (Layer 3)

Configures physical interfaces as **routed** (`no switchport`) with IPv4/IPv6
addresses, MTU and optional VRF — the spine-leaf point-to-point `/31` fabric
links and WAN uplinks that BGP/OSPF underlay sessions peer over. Supports
per-device blocks (`devices[].interfaces`) or a fabric-wide `interfaces` list,
and emits both CIDR (EOS/XR/NXOS) and dotted `addr mask` (IOS-XE) forms.

### `vrf_route_leak` intent type (DC/EVPN)

Bridges routes between a VRF and the global table (or another VRF) via
route-target import/export and/or explicit static leaks — e.g. a border spine
handing tenant EVPN VRF routes to a WAN/GRE path.

Both types ship with templates + removal for arista/eos and cisco/ios-xe, are
in the schema, and are enforced by the render smoke test across all six
platform template sets.

## Bug Fixes

- **`dc_underlay` honours explicit per-device loopbacks.** The resolver
  unconditionally allocated loopbacks from a pool, ignoring the `loopback`/
  `router_id` the intent already specifies per device — so eBGP fabrics failed
  with `Loopback pool 'None' not found`, and even with a pool the sequential
  allocation would not match the design's router-ids. It now reads
  `dc.underlay.devices[]` per-device blocks (same pattern as `bgp_evpn_af`) and
  uses the explicit loopback as-is; the legacy fabric-wide form still allocates
  from the pool.

## Behaviour Changes

- **Catalyst Center connections verify TLS by default.** If you rely on the old
  no-verify behaviour with a self-signed DNAC, set `catalyst_center_ca_bundle`
  (preferred) or `catalyst_center_verify_ssl: false`.

## Quality

- `invoke unittest`: 607 passing (11 browser-only skips).
- `invoke pylint`: 10.00/10; ruff, djlint, yamllint, markdownlint clean.
- Render smoke test: green across all six platform template sets.
- Validation corpus: a 74-intent customer POC fabric resolves and renders
  cleanly end-to-end.

## Upgrade

No database migrations.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.16
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**Full changelog:** [`v2.0.15...v2.0.16`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.15...v2.0.16)
