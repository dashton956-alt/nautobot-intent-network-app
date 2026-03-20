# v1.1.6

## Release Date

2026-03-20

## Added

- **`.intentignore` support** — place a `.intentignore` file in the repo root or intent directory to exclude files from Git sync using `fnmatch` glob patterns (e.g. `test_*.yaml`, `**/scratch/**`).
- **Approve/Reject UI** — Approve and Reject buttons on the intent detail page. Supports Nautobot native Approval Workflow (`on_workflow_approved`, `on_workflow_denied`, `on_workflow_canceled` callbacks). `is_approved` now accepts approval from either custom `IntentApproval` records or native `ApprovalWorkflow`.
- **Catalyst Center adapter** — new `controller_type`, `controller_site`, and `controller_org` fields on the `Intent` model; `CatalystCenterControllerAdapter` for Cisco DNA/Catalyst Center deployments.
- **Intent dependency graph** — `ManyToManyField` (`dependencies`) for declaring deployment ordering between intents. A second-pass resolver in the Git sync callback resolves `depends_on` IDs after all intents are created.
- **Management intent types** — `mgmt_motd`, `mgmt_netconf`, `mgmt_dhcp_server`, and `mgmt_global_config` intent types for the Management & Operations domain.
- **Retired status** — Retired intents remain in Git but are non-actionable. Reconciliation skips them and only a transition back to Draft is permitted.
- **`fw_rule` intent type** — Firewall Rule intent with stateful/stateless policy support. Includes resolver, Jinja templates for Cisco IOS-XE, IOS-XR, NX-OS, Juniper Junos, Aruba AOS-CX, and Arista EOS, plus `FirewallControllerAdapter` for centralised appliances (Palo Alto Panorama, Fortinet FortiManager).

## Fixed

- **Git sync error surfacing** — unhandled exceptions in the datasource callback are now written to the Nautobot job result (visible in the UI) and logged with a full traceback, instead of being swallowed and only appearing as the generic "Please see logs" message.
- **`verification_schedule` NOT NULL violation** — intent files without a `verification.schedule` key now correctly write an empty string `""` to the database column instead of `NULL`, resolving a PostgreSQL constraint error that caused all intents to fail during Git sync.
- **PostgreSQL "pending trigger events"** — migrations `0010` and `0013` now set `atomic = False` to avoid locking errors on large tables.
- **Python 3.13 Docker build** — pinned Python to `>=3.10,<3.13` as pyATS/Genie do not publish Python 3.13 wheels.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==1.1.6
nautobot-server migrate
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```
