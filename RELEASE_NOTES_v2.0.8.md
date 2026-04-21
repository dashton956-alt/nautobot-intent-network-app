v2.0.8 is a bug-fix and UX release that resolves four silent data-collection failures in the Arista EOS live topology pipeline and adds a grouped-by-domain intent list view.

## What's New

### Grouped Intent View

A new page at `/plugins/intent-networking/intents/grouped/` organises all intents into collapsible, colour-coded domain panels. A **"Group by Domain"** button is added to the standard intent list. Active filter querystrings are preserved when switching between views.

### Arista Live Collection Fixed (4 bugs)

| Bug | Impact | Fix |
|---|---|---|
| No `arista_eos_show_arp.textfsm` template | ARP table always empty | Added regex fallback parser for raw string output |
| VRF key was `vrf` not `name` | VRF names blank | Added `or row.get("vrf")` fallback |
| BGP keys were `bgp_neigh` / `neigh_as` | BGP panel blank | Added correct key fallbacks |
| Route `prefix_length` vs `mask`; `NEXT_HOP` is a list | Route prefix/next-hop blank or `[...]` | Added `prefix_length` fallback; join lists with `", "` |

`on_failed=True` also added to all Nornir collection tasks so a failure on one command does not silently skip the remaining commands.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.8
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

No database migrations in this release.

**Full changelog:** [`v2.0.7...v2.0.8`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.7...v2.0.8)
