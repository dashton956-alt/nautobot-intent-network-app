# v2.0.15 Release Notes

## Release Date

2026-07-13

## Summary

v2.0.15 is a **feature release** adding two richer intent forms that real
deployments need — surfaced by a customer proof-of-concept corpus of 57
intents, which now resolves and renders cleanly end-to-end.

There are no new database migrations. Both existing (legacy) intent forms are
unchanged and continue to work.

## What's New

### Multi-tunnel GRE intents (`gre_tunnel`)

Hub routers commonly terminate many GRE tunnels; previously each needed its
own intent. `gre_tunnel` now reads a `security.gre.tunnels` list:

```yaml
security:
  gre:
    tunnels:
      - name: Tunnel1              # optional — pins the tunnel id
        description: "GRE_to_branch1"
        local: "10.0.100.1"        # tunnel source
        remote: "10.0.101.0"       # tunnel destination
        tunnel_ip: "100.64.1.2/30"
        keepalive:
          enabled: true            # false disables keepalive
          interval: 10
          retries: 3
        mtu: 1476
```

One GRE interface is rendered per entry per scoped device. An explicit
`name: TunnelN` pins the tunnel id; otherwise one is allocated from the
tunnel-id pool. The legacy flat single-tunnel form
(`tunnel_source`/`tunnel_destination`) is unchanged.

### Per-device eBGP EVPN overlays (`bgp_evpn_af`)

eBGP EVPN fabrics give every switch its own AS number — impossible to express
with the previous single fabric-wide `as_number`. `bgp_evpn_af` now reads
per-device blocks:

```yaml
routing:
  address_families:
    l2vpn_evpn:
      enabled: true
      devices:
        - hostname: dc-leaf1
          as_number: 65011
          router_id: "192.168.0.21"
          neighbors:
            - ip: "192.168.0.1"
              remote_as: 65001
              description: "spine1_evpn"
```

Each scoped device receives the block matching its hostname; scoped devices
without a block are skipped with a warning. Neighbour entries are normalised
to the full key set the platform templates read (both `remote_as` and
`remote_asn` spellings, `update_source`, `route_reflector_client`,
`send_community`). The fabric-wide form is unchanged.

### Corpus + test coverage

- Two new example intents exercise the new forms and are enforced by the
  render smoke test across all six platform template sets.
- Four new resolver unit tests cover both new forms and both legacy forms.

## Quality

- `invoke unittest`: 602 passing (11 browser-only skips).
- `invoke pylint`: 10.00/10; ruff, yamllint, markdownlint clean.
- Render smoke test: green across all six platform template sets.
- Validation corpus: a 57-intent customer POC resolves and renders cleanly.

## Upgrade

No database migrations.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.15
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**Full changelog:** [`v2.0.14...v2.0.15`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.14...v2.0.15)
