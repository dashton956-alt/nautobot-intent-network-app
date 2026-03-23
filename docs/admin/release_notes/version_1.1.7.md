# v1.1.7

## Release Date

2026-03-21

## Fixed

- **Nornir inventory plugin** — replaced `nornir-nautobot` (`NautobotInventory`) with `nautobot-plugin-nornir` v3.0.0 (`NautobotORMInventory`). The ORM-based inventory uses a Django queryset directly, eliminating the need for an API token and resolving `NautobotInventory.__init__() got unexpected keyword argument 'username'` errors.
- **Device credential handling** — removed hard-coded `username`/`password` parameters from Nornir inventory initialisation. Credentials are now managed through Nautobot Secrets Groups (`device_secrets_group`, `nautobot_api_secrets_group`) via the `nautobot-plugin-nornir` credential framework.
- **Intent data resolver mismatches** — corrected `intent_data` field structures for all 19 intent types to match resolver expectations (top-level keys instead of nested dicts). Affected resolvers: `mgmt_ntp`, `mgmt_snmp`, `mgmt_motd`, `mgmt_netconf`, `mgmt_dhcp_server`, `mgmt_global_config`, `l2_vlan`, `l3_bgp`, `evpn_fabric`, `l2vni`, `sr_mpls`, `ipsec`, `qos_policy`, `cloud_direct_connect`, `cloud_vpc_peer`, `wifi`, `security_segmentation`, `connectivity`, `reachability`.

## Added

- **`nautobot-plugin-nornir` dependency** — added `nautobot-plugin-nornir = "^3.0.0"` as a required dependency, replacing the previous `nornir-nautobot` package.
- **Nautobot Secrets Group integration** — enabled `device_secrets_group` and `nautobot_api_secrets_group` in the plugin configuration for production-ready credential management.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==1.1.7
nautobot-server migrate
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! note
    This release replaces `nornir-nautobot` with `nautobot-plugin-nornir`. If you previously installed `nornir-nautobot` manually, you may remove it:
    ```bash
    pip uninstall nornir-nautobot
    ```
    Ensure `"nautobot_plugin_nornir"` is listed in your `PLUGINS` setting in `nautobot_config.py`.
