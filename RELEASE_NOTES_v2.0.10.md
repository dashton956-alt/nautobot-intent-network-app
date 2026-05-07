# v2.0.10 Release Notes

## Release Date

2026-05-06

## Summary

v2.0.10 adds a comprehensive **network-as-code example library** — 33 fully documented YAML intent files covering all major intent domains. Every file documents every possible field with `MANDATORY` / `OPTIONAL` markers, valid values, defaults, and inline OPA compliance notes.

Also included: Bootstrap 5 fix for the grouped intent view, OPA policy hardening across four policy files, and a `warn[]`/`deny[]` split in the OPA client.

## What's New

- **33 example YAML intent files** in `network_as_code_example/intents/` covering Layer 2, Layer 3, MPLS, DC/EVPN/VXLAN, Security, WAN, Wireless, Cloud, QoS, Multicast, Management, Reachability, and Service domains
- Every field marked **MANDATORY** or **OPTIONAL** with valid values, defaults, and compliance notes inline
- OPA `warn[]`/`deny[]` split — advisory warnings no longer block deployments
- OPA PCI-DSS blind spot fixed for `ipsec_ikev2` intent type
- Grouped intent view collapsible panels now work correctly on Nautobot 3.x (Bootstrap 5)

## Upgrade

No database migrations. Drop-in replacement for v2.0.9.

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.10
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```
