# Upgrading the App

Here you will find any steps necessary to upgrade the App in your Nautobot environment.

## Upgrade Guide

When a new release comes out it may be necessary to run a migration of the database to account for any changes in the data models used by this app. Follow the steps below:

### Step 1 — Update the Package

```shell
pip install --upgrade nautobot-app-intent-networking
```

### Step 2 — Run Post-Upgrade

```shell
nautobot-server post_upgrade
```

This will automatically run any pending migrations and clear caches.

### Step 3 — Restart Services

```shell
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

## Version-Specific Notes

### Upgrading to v0.5 (IPAM Refactor)

v0.5 replaced the custom `RouteDistinguisherPool`, `RouteDistinguisher`, `RouteTargetPool`, and `RouteTarget` models with Nautobot's native `ipam.VRF`, `ipam.RouteTarget`, and `ipam.Namespace` models. **Migration 0006** handles this automatically.

**What happens during migration:**

1. Data from custom RD/RT models is migrated into Nautobot native IPAM objects.
2. The custom pool tables are dropped.
3. The `vrf_namespace` setting determines which `ipam.Namespace` is used (defaults to `"Global"`).

**Action required:**

- Ensure your `nautobot_config.py` includes the `vrf_namespace` and `default_bgp_asn` settings (see [Install Guide](install.md#required-settings)).
- After upgrading, verify in **IPAM → VRFs** that your VRFs were migrated correctly.
- Remove any references to `RouteDistinguisherPool` or `RouteTargetPool` from custom scripts or integrations.

### Upgrading to v0.4

v0.4 expanded the intent type taxonomy from 3 to 129 types. No manual action required — existing intents retain their original type values.