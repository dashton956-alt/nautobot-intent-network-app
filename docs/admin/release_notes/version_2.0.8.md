# v2.0.8

## Release Date

2026-04-21

## Summary

v2.0.8 is a bug-fix and UX release. It corrects four silent data-collection failures in the Arista EOS live topology collection pipeline and introduces a grouped-by-domain intent list view that organises all intents into collapsible domain panels for easier at-a-glance navigation.

## Added

- **Grouped intent view** — a new `/plugins/intent-networking/intents/grouped/` page groups all intents into collapsible domain panels (Layer 2, Layer 3, MPLS/SP, Data Centre, Security, WAN/SD-WAN, Wireless, Cloud, QoS, Multicast, Management, Reachability, Service). Each domain panel is colour-coded with a Material Design icon and shows a condensed table of intent ID, type, tenant, status, approval state, and deployed date. A **"Group by Domain"** button is added to the standard intent list view; active filter querystrings are preserved when switching between views.

## Fixed

- **Arista ARP table always empty** — the ntc-templates library ships no `arista_eos_show_arp.textfsm` template, so `netmiko_send_command` returned the raw command output as a plain string instead of a parsed list. The collection loop discarded any non-list result, resulting in an empty ARP panel on the topology device page. Fixed by preserving raw string output and adding a regex-based line parser in `_normalise_arp()` that extracts IP, age, MAC and interface columns from the plain text.

- **VRF names missing for Arista** — `_normalise_vrfs()` looked for dictionary key `name` to populate the VRF name field, but the `arista_eos_show_vrf.textfsm` template emits `vrf`. All VRF rows were normalised to an empty string. Fixed by adding `or row.get("vrf")` as a fallback.

- **BGP neighbor IP and AS number missing for Arista** — `_normalise_bgp()` used `bgp_neighbor` and `neighbor_as` / `remote_as` as dictionary keys. The Arista TextFSM template emits `bgp_neigh` and `neigh_as` respectively. All BGP panel rows appeared blank. Fixed by adding `or row.get("bgp_neigh")` and `or row.get("neigh_as")` fallbacks.

- **Route prefix mask and next-hop missing for Arista** — the `arista_eos_show_ip_route.textfsm` template emits `prefix_length` (not `mask`) and declares `NEXT_HOP` and `INTERFACE` as `List` values (Python lists, not strings). `_normalise_routes()` looked for a `mask` key (found nothing) and placed the list object directly into `nexthop` and `interface` fields, producing `[...]` strings in the UI. Fixed by adding `or row.get("prefix_length")` for the mask and joining list values with `", "` in both `nexthop` and `interface`.

- **Collection task silently skipped after any task failure** — `nornir.run()` calls in `_collect_live_data()` were missing `on_failed=True`, which causes Nornir to skip subsequent tasks on a host that was marked failed by a prior task. Added `on_failed=True` to the collection loop to ensure all commands are attempted independently.

## Upgrade

No database migrations are included in this release.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.8
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**Full changelog:** [`v2.0.7...v2.0.8`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.7...v2.0.8)
