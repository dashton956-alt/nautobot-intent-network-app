# v2.0.13 Release Notes

## Release Date

2026-07-09

## Summary

v2.0.13 is a **reliability and coverage release** that closes the render-contract
gaps behind the "empty rendered config → deploy failed → rollback" incidents,
hardens the deployment pipeline against silent failures, and brings the example
corpus to full coverage of every dispatchable intent type.

The headline themes:

- **Full render-contract enforcement** — a new end-to-end smoke test resolves
  **every** example intent through the real resolvers and renders each resulting
  primitive under `StrictUndefined` across **all six** platform template sets
  (arista/eos, cisco/ios-xe, cisco/ios-xr, cisco/nxos, juniper/junos,
  aruba/aos-cx). Over **300 latent resolver↔template field mismatches** were
  found and fixed across every domain.
- **Complete example corpus** — 62 new example intents mean all **134**
  dispatchable intent types now have a validated, resolvable, renderable
  reference example (was 72). New `cloud/` and `sdwan/` corpus directories.
- **No more partial-config deploys** — a template render error now hard-fails
  the deployment (`ConfigRenderError`, intent marked *Failed*) instead of
  pushing whatever rendered with only a log warning.
- **Chained jobs no longer depend on a pre-existing service account** — the
  `intent-engine-svc` account is auto-provisioned (login-disabled) on first use,
  fixing `IntentVerificationJob` enqueue failures.
- **Topology viewer edge filter** — new *All Links / Physical / Logical* toolbar
  filter, and the full-screen viewer no longer sits under Nautobot's navbar.

There are no new database migrations. A few **behaviour changes** are called out
under *Behaviour Changes* below — review them before upgrading.

## What's New

### Render smoke test across all six platforms

- New `test_intent_render` suite: every example intent is resolved by the real
  resolver (only DB/device/allocation layers stubbed) and every emitted
  primitive is rendered through every platform template that exists, under
  `StrictUndefined`. The example → resolver → template contract can no longer
  silently drift.

### Full example corpus (134/134 intent types)

- 62 new example intents across wireless (10), cloud (8), SD-WAN (4),
  service (5), QoS (5), reachability (4), MPLS/SP (8), multicast (5),
  security (8) and WAN (5).
- Every corpus file (170 total) validates against the pykwalify schema; the
  schema now declares all type-specific fields the resolvers read (131 new key
  declarations) and the `type` enum is in exact sync with the dispatchable
  resolvers and model choices.

### Topology viewer: physical/logical edge filter

- New toolbar buttons — **All Links / Physical / Logical** — show only cabled
  links or only plan-derived logical links; the active filter survives a graph
  refresh.
- The full-screen viewer's z-index was raised above Nautobot's fixed navbar so
  it is no longer clipped by the toolbar.

### Service-account auto-provisioning for chained jobs

- `_enqueue_job` accepts the requesting user and otherwise uses a dedicated,
  login-disabled `intent-engine-svc` account, **created on demand** — chained
  verification/rollback/reconciliation jobs no longer fail when the account
  doesn't exist. The username is configurable via the new
  `intent_service_account` plugin setting.

## Bug Fixes

- **~300 resolver↔template contract fixes** surfaced by the smoke test,
  including:
    - L2: `lag`, `mlag`, `qinq`, `pvlan`, `storm_control`, `port_security`
      resolvers read their nested example blocks; `apply_to_all_access_ports`
      supported for storm-control/port-security.
    - L3: `static_route` accepts `routing.routes[].destination`; `route_policy`
      reads `route_policy.route_maps[]`; `pbr` reads `pbr.policies[]`;
      `route_redistribution` groups entries per target protocol; `eigrp`
      networks normalised to `{network, wildcard}`; prefix-list, IPv6
      dual-stack, FHRP, IS-IS, OSPF template contracts completed.
    - DC/EVPN: `vtep` emits VNI mapping lists (was an int the template tried to
      iterate); `evpn_multisite` emits `local_asn` + DCI neighbours;
      `anycast_gateway`, `l2vni`/`l3vni`, DC-underlay per-peer BGP fixed.
    - MPLS/SP: VPLS, pseudowire, RSVP-TE, SRv6, LDP, 6PE, EVPN-MPLS emit the
      full field sets their templates read.
    - Security/WAN: `ipsec_s2s`/`ipsec_ikev2`/`gre_over_ipsec` emit complete
      peer/PSK/ISAKMP/transform-set blocks; DMVPN emits both template dialects'
      NHRP fields; NAT64 v4 pool normalised from CIDR; wan-uplink, IP-SLA,
      dot1x, CoPP, MACsec key fields completed.
    - Service: per-record DNS primitives; NAT `static_mappings` shape; LB-VIP
      member `address → ip` mapping; DHCP `dns_servers` list collapsed for
      templates.
    - Cross-platform templates (aos-cx, junos, ios-xr, nxos): server lists
      accept both bare-string and `{ip|host}` dict forms (ntp/snmp/syslog);
      ACL/QoS/PBR loop guards; ipv6_interface rewritten to the interfaces-list
      shape; nxos vtep iterates VNI lists; ios-xr AAA and junos telemetry
      rewritten to the resolvers' output.
- **Schema enum corrections** — removed the bogus `mgmt_aaa` value (the real
  types are `aaa` / `mgmt_aaa_device`); added the legacy bare `reachability`
  and `service` types. Six shared keys whose shape legitimately differs by
  intent type (`vlans`, `zones`, `priority`, `isolation`, `dscp_map`,
  `probes[].type`) are now validated accordingly.
- **NUTS running-config check** distinguishes "no config collected" from
  "snippet genuinely absent" with actionable messages.

## Behaviour Changes

- **Deployments hard-fail on render errors.** If any primitive's template
  errors or is missing for the device's platform, the deploy raises
  `ConfigRenderError` (listing every failing primitive) and the intent is
  marked *Failed* — partial config is never pushed. Config previews fail
  loudly instead of caching incomplete output. Adapter-routed primitives
  (wireless/SD-WAN/cloud) are unaffected.
- **Missing removal templates now warn.** During upgrades/rollback, a missing
  `{type}_removal.j2` is still tolerated, but a warning naming the
  device/platform/type is logged so operators know config from a previous
  version may remain on the device.
- **Chained jobs run as `intent-engine-svc`** (auto-provisioned,
  login-disabled) when no requesting user is available — never an arbitrary
  superuser. Override the username with the `intent_service_account` plugin
  setting.
- **`mgmt_aaa` removed from the schema enum.** It was never dispatchable; use
  `mgmt_aaa_device` (device AAA) or `aaa` instead.

## Quality

- `invoke tests`: full gate passing (ruff, djlint, yamllint, markdownlint,
  poetry check, migrations check, pylint 10.00/10, mkdocs, app config schema).
- `invoke unittest`: 595 passing (11 browser-only skips).
- pykwalify: all 170 example intents valid.
- Render smoke test: green across all six platform template sets.

## Upgrade

No database migrations.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.13
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

Review *Behaviour Changes* above — in particular, intents whose templates
previously rendered partially now fail the deployment instead; fix the
intent/template contract rather than relying on partial pushes.

**Full changelog:** [`v2.0.12...v2.0.13`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.12...v2.0.13)
