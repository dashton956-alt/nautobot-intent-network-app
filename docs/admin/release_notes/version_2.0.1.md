# v2.0.1

## Release Date

2026-04-12

## Summary

v2.0.1 is a patch release that corrects 14 Arista EOS Jinja2 removal templates shipped in v2.0. All fixes align removal templates with their provision counterparts — no database migrations are required and there are no breaking changes.

## Fixed

- **`urpf_removal.j2`** — rewritten to loop over an `interfaces` list (matching `urpf.j2`). Each interface now emits `no ip verify unicast reachable-via rx` (strict) or `no ip verify unicast reachable-via any` (loose) rather than a single hard-coded interface variable.
- **`ipsec_tunnel_removal.j2`** — uses the `tunnel_interface`, `crypto_map_name`, `crypto_map_seq`, and `isakmp_policy` variables defined in `ipsec_tunnel.j2`. Optional fields (`tunnel_interface`, `isakmp_policy`) are guarded with `| default(none)` to avoid `StrictUndefined` errors.
- **`ldp_removal.j2`** — per-interface removal now emits `no mpls ip` (the correct EOS command) instead of the IOS-style `no mpls ldp interface`. The optional `router_id` field is guarded with `| default(none)`.
- **`copp_removal.j2`** — completely rewritten to mirror `copp.j2`: enters `system control-plane`, removes `no ip access-group` per class, then removes each `no ip access-list` entry. The previous template incorrectly tried to remove a `policy-map` that is never created by the provision template.
- **`zbf_removal.j2`** — `no zone-pair security` removed (provision template does not create zone-pairs). Zone removal now uses the correct EOS syntax `no security zone` instead of the IOS-style `no zone security`.
- **`pseudowire_removal.j2`** — loops over the `pseudowires` list and removes each interface by name (`pw.interface`), matching the provision template's variable structure.
- **`mvpn_removal.j2`** — removal is now expressed inside `router bgp {{ local_asn }}` using `no address-family ipv4 multicast`, mirroring `mvpn.j2`. The previous template used a non-existent `vrf instance` / `no mdt default` construct.
- **`evpn_mpls_removal.j2`** — `local_asn | default("")` removed; `local_asn` is now required. An empty default produced `router bgp ` (invalid EOS command).
- **`evpn_multisite_removal.j2`** — `local_asn | default("")` removed; `local_asn` is now required. A spurious `no multisite border-gateway interface` line (not emitted by `evpn_multisite.j2`) has also been removed.
- **`6pe_6vpe_removal.j2`** — `local_asn | default("")` removed; `local_asn` is now required. The `no neighbor activate` removal is now correctly placed inside `address-family ipv6`, matching `6pe_6vpe.j2`.
- **`nat_removal.j2`** — `no ip nat pool` is now conditional on `pool_name` being explicitly provided. Previously the line was always emitted using `pool_name | default("NAT-POOL")`, which would attempt to remove a pool that may never have been created.
- **`ssl_inspection_removal.j2`** — converted to a comment-only stub, matching `ssl_inspection.j2` which is itself a stub. The previous template emitted live `no ssl profile` CLI that could never apply.
- **`service_insertion_removal.j2`** — converted to a comment-only stub, matching `service_insertion.j2`. The previous template emitted `no policy-map type service-insertion` with an empty-default variable, producing invalid CLI.
- **`cloud_direct_connect.j2`** — `local_ip`, `peer_ip`, `bgp_asn`, and `peer_asn` are now required fields (empty-string defaults removed). These are BGP-session-critical values; silently defaulting to `""` produced invalid EOS configuration.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.1
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! note "No database migrations"
    v2.0.1 contains only Jinja2 template fixes. No database migrations are included — `post_upgrade` will complete immediately with no schema changes.

!!! warning "Intent YAML inputs"
    Several removal templates now require fields that were previously optional (defaulting to `""`). If you have intents that invoke these removal templates directly, ensure the following fields are present in your intent YAML:

    | Template | Now-required fields |
    |----------|---------------------|
    | `evpn_mpls_removal` | `local_asn` |
    | `evpn_multisite_removal` | `local_asn` |
    | `6pe_6vpe_removal` | `local_asn` |
    | `cloud_direct_connect` | `local_ip`, `peer_ip`, `bgp_asn`, `peer_asn` |
    | `urpf_removal` | `interfaces` (list of `{name, mode}`) — replaces `interface` + `mode` scalars |
    | `pseudowire_removal` | `pseudowires` (list of `{interface}`) — replaces `pw_id` + `remote_pe` scalars |
