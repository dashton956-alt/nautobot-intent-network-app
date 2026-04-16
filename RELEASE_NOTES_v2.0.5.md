v2.0.5 is a major feature and fix release — the largest since v2.0.0. It ships nine new platform capabilities and four bug fixes.

## Added

- **Management intent types** — `mgmt_motd`, `mgmt_netconf`, `mgmt_dhcp_server`, and `mgmt_global_config` intent types for the Management & Operations domain.
- **`Retired` intent status** — intents can be set to `Retired` to remain in Git but remain non-actionable. Reconciliation skips retired intents; the only permitted transition is back to `Draft`.
- **`fw_rule` (Firewall Rule) intent type** — stateful/stateless firewall policy support with a resolver, Jinja2 templates for six vendor platforms (Cisco IOS-XE/IOS-XR/NX-OS, Juniper Junos, Aruba AOS-CX, Arista EOS), and a `FirewallControllerAdapter` for Palo Alto Panorama and Fortinet FortiManager.
- **`.intentignore` file support** — place a `.intentignore` file in the repo root or an intent directory to exclude files from Git sync using `fnmatch` glob patterns.
- **Approve/Reject workflow UI** — Approve and Reject buttons on the intent detail page. Native Nautobot Approval Workflow callbacks (`on_workflow_approved/denied/canceled`). `is_approved` accepts both custom `IntentApproval` records and native Nautobot `ApprovalWorkflow`.
- **Catalyst Center adapter** — new `controller_type`, `controller_site`, and `controller_org` fields on `Intent` for targeting Cisco Catalyst Center as a deployment controller.
- **Intent dependency graph** — `ManyToManyField` on `Intent` for declaring deployment ordering. The reconciliation pipeline respects declared dependencies when sequencing deployments.
- **NUTS verification engine** — replaced pyATS/Genie with [NUTS (Network Unit Testing System)](https://nuts.readthedocs.io/). Uses NAPALM and Netmiko with 20+ test classes across 70+ platforms.
- **VXLAN VNI Pool management UI** — list/create/edit/delete views in the Intent Engine nav menu, plus `VxlanVniPoolSerializer` for the REST API at `/api/plugins/intent-networking/vxlan-vni-pools/`.

## Fixed

- **PostgreSQL migration atomicity** — migrations `0010` and `0013` now set `atomic = False`, fixing `"pending trigger events"` errors on PostgreSQL.
- **Python 3.13 compatibility** — pinned `python = ">=3.10,<3.13"` in `pyproject.toml` (pyATS/Genie do not publish 3.13 wheels).
- **Lifecycle status seeding** — data migration `0015_seed_intent_lifecycle_statuses` ensures all eight lifecycle statuses are created on any Nautobot instance during `post_upgrade`. Previously fresh production installs hit `Status.DoesNotExist` errors.
- **Device credential resolution** — credentials now resolve per-device from SecretsGroup with `access_type="SSH"`. Previously `access_type="Generic"` was used, causing silent failure and unconditional fallback to environment variables.

## Upgrade

```
pip install --upgrade nautobot-app-intent-networking==2.0.5
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

> **Action required if you use `device_secrets_group`:** verify your SecretsGroup assignments in Nautobot use **Access Type: SSH** (not Generic) for username and password secrets.

**Full changelog:** [`v2.0.4...v2.0.5`](https://github.com/dashton956-alt/nautobot-intent-network-app/compare/v2.0.4...v2.0.5)
