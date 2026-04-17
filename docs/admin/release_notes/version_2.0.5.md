# v2.0.5

## Release Date

2026-04-15

## Summary

v2.0.5 is a bug-fix release that corrects device credential resolution for NUTS verification and deployment jobs. No database migrations are required and there are no breaking changes.

## Fixed

- **Device credential resolution** — the app now correctly resolves SSH credentials from Nautobot SecretsGroups using `access_type="SSH"` (the Nautobot standard used by `nautobot_plugin_nornir`). Previously `access_type="Generic"` was used, causing a silent exception and unconditional fallback to `DEVICE_USERNAME`/`DEVICE_PASSWORD` environment variables even when `device_secrets_group` was configured in `PLUGINS_CONFIG`.

- **Per-device credentials** — credentials are now resolved individually for each device in the Nornir inventory. The lookup order is:
    1. SecretsGroup assigned directly to the device record in the Nautobot UI (Device → *Secrets Group* field)
    2. Global `device_secrets_group` from `PLUGINS_CONFIG` as a fallback
    3. `DEVICE_USERNAME` / `DEVICE_PASSWORD` environment variables as a last resort

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.5
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! note "No database migrations"
    v2.0.5 contains only code changes. No database migrations are included.

!!! tip "Action required if you use device_secrets_group"
    If you have `device_secrets_group` configured in `PLUGINS_CONFIG`, verify that the SecretsGroup assignments in Nautobot use **Access Type: SSH** (not Generic) for both the username and password secrets. This matches the convention used by `nautobot_plugin_nornir`.

**Full changelog:** [`v2.0.4...v2.0.5`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.4...v2.0.5)
