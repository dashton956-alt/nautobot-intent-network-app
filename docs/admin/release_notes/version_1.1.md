# v1.1 Release Notes

## Release Overview

v1.1 expands the Management intent domain with four new intent types covering common device-wide configuration concerns: Banner/MOTD, NETCONF/RESTCONF enablement, DHCP Server, and a Global Config Bundle. Platform Jinja2 template coverage is extended across all supported vendors for these types. The deployment job also gains a first-class dry-run mode for safer lab testing and pre-change reviews.

## [v1.1.0] - 2026-03-12

### Added

- **4 new Management intent types** in `IntentType`:

    | Intent Type | Value | Description |
    |-------------|-------|-------------|
    | Banner / MOTD | `mgmt_motd` | Configures login, MOTD, and exec banners on all in-scope devices |
    | NETCONF / RESTCONF | `mgmt_netconf` | Enables or disables NETCONF (port 830), RESTCONF, and gNMI on devices |
    | DHCP Server | `mgmt_dhcp_server` | Configures DHCP server pools, excluded addresses, and lease times |
    | Global Config Bundle | `mgmt_global_config` | One-shot intent for hostname, NTP, DNS, syslog, SNMP, SSH, banners, NETCONF, DHCP pools, and LLDP/CDP in a single intent |

- **Resolver functions** — `resolve_mgmt_motd`, `resolve_mgmt_netconf`, `resolve_mgmt_dhcp_server`, `resolve_mgmt_global_config` added to `resolver.py`

- **Jinja2 templates** for all four new intent types across all supported platforms:

    | Platform | New templates |
    |----------|--------------|
    | Arista EOS | `motd.j2`, `netconf.j2`, `dhcp_server.j2`, `global_config.j2` |
    | Aruba AOS-CX | `motd.j2`, `netconf.j2`, `dhcp_server.j2`, `global_config.j2` |
    | Cisco IOS-XE | `motd.j2`, `netconf.j2`, `dhcp_server.j2`, `global_config.j2` |
    | Cisco IOS-XR | `motd.j2`, `netconf.j2`, `dhcp_server.j2`, `global_config.j2` |
    | Cisco NXOS | `motd.j2`, `netconf.j2`, `dhcp_server.j2`, `global_config.j2` |
    | Juniper JunOS | `motd.j2`, `netconf.j2`, `dhcp_server.j2`, `global_config.j2` |

- **Dry-run deployment mode** — `IntentDeploymentJob` now accepts a `commit` boolean variable (default `True`). When `commit=False`:
    - Jinja2 configs are rendered and stored in `intent.rendered_configs` without connecting to any device
    - Intent status is **not** changed (remains `Validated`)
    - An audit entry is created with `"dry_run": true` for traceability
    - Useful for lab testing, pre-change review, and CI config-diff workflows

- **`rendered_configs` field** on `Intent` — stores the last per-device rendered configuration output (populated by both dry-run and live deployments)

- **VLAN verification check** in `IntentVerificationJob` — verifies expected VLANs are present on target devices post-deployment

- **Datasource enhancements** — updated `datasources.py` to handle additional credential fields from `creds.example.env`

### Changed

- Intent type count increased from **129 → 133**
- `IntentDeploymentJob` approval check is now skipped for dry-run (`commit=False`) deployments with a logged warning instead of raising an error

### Fixed

- `views.py` — `ruff format` compliance: long `.prefetch_related().order_by()` chain reformatted to pass CI `ruff-format` check

### Upgrade from v1.0

No database migrations are required if `rendered_configs` is already a JSON field. Run post-upgrade to apply any pending migrations and clear cache:

```shell
pip install --upgrade nautobot-app-intent-networking==1.1.0
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```
