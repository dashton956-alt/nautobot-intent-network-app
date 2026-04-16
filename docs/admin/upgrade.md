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

### Upgrading to v2.0.5 (major feature release)

v2.0.5 is a **feature release** and includes multiple database migrations.

```shell
pip install --upgrade nautobot-app-intent-networking==2.0.5
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

`post_upgrade` will run all pending migrations, including `0015_seed_intent_lifecycle_statuses` which seeds the eight Intent lifecycle statuses on any instance that is missing them.

!!! tip "Action required if you use device_secrets_group"
    If you have `device_secrets_group` configured in `PLUGINS_CONFIG`, verify that SecretsGroup assignments in Nautobot use **Access Type: SSH** (not Generic) for username and password secrets.

See the [v2.0.5 release notes](../admin/release_notes/version_2.0.5.md) for details.

### Upgrading to v2.0.4 (VNI Pool UI)

v2.0.4 is a **patch release** — no database migrations are included.

```shell
pip install --upgrade nautobot-app-intent-networking==2.0.4
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

No breaking changes. The new VNI Pools page appears automatically in the Intent Engine nav menu after restart.
See the [v2.0.4 release notes](../admin/release_notes/version_2.0.4.md) for details.

### Upgrading to v2.0.3 (lifecycle status migration)

v2.0.3 is a **patch release** — includes one data migration (`0015_seed_intent_lifecycle_statuses`).

```shell
pip install --upgrade nautobot-app-intent-networking==2.0.3
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

The migration creates the eight Intent lifecycle statuses on any instance that is missing them. Instances already seeded via `seed_data.py` are unaffected.
See the [v2.0.3 release notes](../admin/release_notes/version_2.0.3.md) for details.

### Upgrading to v2.0.2 (NUTS expected shorthand)

v2.0.2 is a **patch release** — no database migrations are included.

```shell
pip install --upgrade nautobot-app-intent-networking==2.0.2
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

No breaking changes. Intent YAML files using the existing `test_data` format continue to work unchanged.
See the [v2.0.2 release notes](../admin/release_notes/version_2.0.2.md) for details on the new `expected` shorthand.

### Upgrading to v2.0.1 (Arista EOS template fixes)

v2.0.1 is a **patch release** — no database migrations are included.

```shell
pip install --upgrade nautobot-app-intent-networking==2.0.1
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**Check your intent YAML** if you use any of the following Arista EOS removal templates or `cloud_direct_connect`. Several fields that previously defaulted to `""` are now required:

| Template | Now-required fields |
|----------|---------------------|
| `evpn_mpls_removal` | `local_asn` |
| `evpn_multisite_removal` | `local_asn` |
| `6pe_6vpe_removal` | `local_asn` |
| `cloud_direct_connect` | `local_ip`, `peer_ip`, `bgp_asn`, `peer_asn` |
| `urpf_removal` | `interfaces` list of `{name, mode}` |
| `pseudowire_removal` | `pseudowires` list of `{interface}` |

See the [v2.0.1 release notes](../admin/release_notes/version_2.0.1.md) for the full list of template changes.

### Upgrading to v2.0 (NUTS Verification Engine, Bulk Actions, 847 Templates)

v2.0 is a **major release**. The pyATS/Genie verification engine is removed and replaced by NUTS.

**Migrations** `0014` is applied automatically by `post_upgrade`.

**Remove pyATS (optional but recommended):**

```shell
pip uninstall pyats genie
```

**Install NUTS extras:**

```shell
pip install "nautobot-app-intent-networking[nuts]==2.0.0"
```

**Update your intent YAML** — the `verification.tests` block now uses NUTS test bundle definitions instead of pyATS test specs. See the [Getting Started guide](../user/app_getting_started.md).

**Restart services after upgrade:**

```shell
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

### Upgrading to v1.1.5 (Docs + Deployment)

v1.1.5 is a documentation and deployment pipeline release. There are no database changes.

**Upgrade steps:**

```shell
pip install --upgrade nautobot-app-intent-networking==1.1.5
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

### Upgrading to v1.1.4 (Catalyst Center Adapter & DB Fixes)

v1.1.4 fixes PostgreSQL migration errors (`atomic = False` on migrations `0010` and `0013`), pins Python to 3.10–3.12 (pyATS/Genie compatibility), adds the Catalyst Center adapter, and adds the intent dependency graph.

**Migrations** `0013` is applied automatically by `post_upgrade`. If you previously encountered "pending trigger events" errors on PostgreSQL, this release resolves them.

**Optional dependencies:** To enable Catalyst Center support:

```shell
pip install nautobot-app-intent-networking[catalyst]
```

**Python version:** This release requires Python 3.10–3.12. If you are running Python 3.13, you must downgrade to 3.12.


v1.1.3 adds pyATS-based extended verification, a dashboard pyATS panel, and git-backed verification reports.

**Migrations** `0010` and `0011` are applied automatically by `post_upgrade`.

**Optional dependencies:** To enable extended verification, install the `[extended]` extras:

```shell
pip install nautobot-app-intent-networking[extended]
```

**New plugin settings (optional):**

- `verification_backup_branch` — Git branch for verification report backups (defaults to `"main"`).
- Ensure `github_repo` and a GitHub token are configured if you enable the "Backup verification to Git" toggle on any intent.

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