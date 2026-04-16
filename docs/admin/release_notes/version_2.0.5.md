# v2.0.5

## Release Date

2026-04-16

## Summary

v2.0.5 is a major feature and fix release — the largest since v2.0.0. It adds nine new platform capabilities (NUTS verification engine, `fw_rule` intent type with multi-vendor Jinja templates, Catalyst Center adapter, intent dependency graph, Approve/Reject workflow UI, `.intentignore` support, `Retired` intent status, four management intent types, and VXLAN VNI Pool UI) alongside four bug fixes covering credential resolution, PostgreSQL migration atomicity, Python 3.13 compatibility, and lifecycle status seeding on fresh installs.

## Added

- **Management intent types** — four new intent types for the Management & Operations domain: `mgmt_motd`, `mgmt_netconf`, `mgmt_dhcp_server`, and `mgmt_global_config`.

- **`Retired` intent status** — intents can be set to `Retired` to remain in Git but remain non-actionable. Reconciliation silently skips retired intents; the only permitted transition out of `Retired` is back to `Draft`.

- **`fw_rule` (Firewall Rule) intent type** — stateful and stateless firewall policy support with a resolver and Jinja2 templates for all six vendor platforms (Cisco IOS-XE, IOS-XR, NX-OS, Juniper Junos, Aruba AOS-CX, Arista EOS). Includes a `FirewallControllerAdapter` for centralized firewall management via Palo Alto Panorama and Fortinet FortiManager.

- **`.intentignore` file support** — place a `.intentignore` file in the repo root or an intent subdirectory to exclude files from Git sync using `fnmatch` glob patterns (same syntax as `.gitignore`).

- **Approve/Reject workflow UI** — Approve and Reject buttons are now displayed on the intent detail page. Added support for Nautobot native Approval Workflow callbacks (`on_workflow_approved`, `on_workflow_denied`, `on_workflow_canceled`). `is_approved` now accepts approval from either a custom `IntentApproval` record or a native Nautobot `ApprovalWorkflow`.

- **Catalyst Center adapter** — new `controller_type`, `controller_site`, and `controller_org` fields on the `Intent` model for targeting Cisco Catalyst Center (formerly DNA Center) as a deployment controller.

- **Intent dependency graph** — a new `ManyToManyField` on `Intent` allows operators to declare deployment ordering between intents. The reconciliation pipeline respects declared dependencies when sequencing deployments.

- **NUTS verification engine** — replaced pyATS/Genie with [NUTS (Network Unit Testing System)](https://nuts.readthedocs.io/). NUTS uses NAPALM and Netmiko for multi-vendor device-state validation and includes 20+ built-in test classes across 70+ network platforms (Arista EOS, Cisco IOS-XE/XR/NX-OS, Juniper JunOS, Nokia SR-OS, and more).

- **VXLAN VNI Pool management UI** — list, create, edit, and delete views for VNI Pools are now accessible from the Intent Engine nav menu under *VNI Pools*. Adds a `VxlanVniPoolSerializer` for the REST API at `/api/plugins/intent-networking/vxlan-vni-pools/`.

## Fixed

- **PostgreSQL migration atomicity** — migrations `0010` and `0013` now set `atomic = False`, resolving `"pending trigger events"` errors that occurred when running `post_upgrade` against PostgreSQL.

- **Python 3.13 compatibility** — pinned Python to `>=3.10,<3.13` in `pyproject.toml`. pyATS/Genie do not publish Python 3.13 wheels; builds now fail explicitly with a clear error rather than silently at install time.

- **Lifecycle status seeding** — data migration `0015_seed_intent_lifecycle_statuses` ensures all eight Intent lifecycle statuses (`Draft`, `Validated`, `Deploying`, `Deployed`, `Failed`, `Rolled Back`, `Deprecated`, `Retired`) are created during `post_upgrade` on any Nautobot instance. Previously these were only seeded by the development script, causing `Status.DoesNotExist` errors on fresh production installs.

- **Device credential resolution** — credentials are now resolved per-device from the SecretsGroup assigned to the device record in Nautobot using `access_type="SSH"` (the convention used by `nautobot_plugin_nornir`). Previously `access_type="Generic"` was used, causing a silent exception and unconditional fallback to environment variables even when `device_secrets_group` was configured. Lookup order:
    1. SecretsGroup on the device record in Nautobot (Device → *Secrets Group* field) — `access_type="SSH"`
    2. Global `device_secrets_group` from `PLUGINS_CONFIG` — `access_type="SSH"`
    3. `DEVICE_USERNAME` / `DEVICE_PASSWORD` environment variables as a last resort

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.5
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! note "Database migrations included"
    v2.0.5 includes several new migrations. `post_upgrade` will run them automatically, including `0015_seed_intent_lifecycle_statuses` which seeds the Intent lifecycle statuses on any instance that is missing them.

!!! tip "Action required if you use device_secrets_group"
    If you have `device_secrets_group` configured in `PLUGINS_CONFIG`, verify that the SecretsGroup assignments in Nautobot use **Access Type: SSH** (not Generic) for both the username and password secrets. This matches the convention expected by `nautobot_plugin_nornir`.

**Full changelog:** [`v2.0.4...v2.0.5`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.4...v2.0.5)
