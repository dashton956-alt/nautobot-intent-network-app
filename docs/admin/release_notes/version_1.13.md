# v1.13 Release Notes

## [v1.13.0] - 2026-03-18

### Added

- **pyATS Extended Verification** — optional two-tier verification engine (basic → extended) using pyATS/Genie for deep device-state validation. Supports 10 check types: interface status, BGP neighbours, OSPF adjacency, VLAN database, VRF routes, ARP table, NTP sync, ACL entries, route-map verification, and LLDP/CDP neighbours.
- **Verification escalation** — basic verification warnings automatically trigger extended pyATS verification with full diff output.
- **Per-intent verification settings** — configurable verification level (basic/extended), trigger (on-deploy/scheduled/both), cron schedule, and fail action (alert/rollback/remediate) per intent.
- **Dashboard pyATS panel** — "Recent pyATS / Extended Verifications" panel on the dashboard showing the last 15 extended/escalated verification results with pass/fail status, engine label, check count, escalation reason, and timestamp.
- **Git-backed verification reports** — per-intent toggle to commit Markdown verification reports to a configurable Git repository at `verification-results/<intent_id>/<timestamp>.md` via the GitHub Contents API, similar to golden-config backup.
- **`.intentignore` file support** — users can place a `.intentignore` in the repo root or intent directory to exclude files from Git sync using fnmatch glob patterns.
- **Nautobot Approval Workflow integration** — Approve/Reject buttons on the intent detail page UI with support for Nautobot native `ApprovalWorkflow` callbacks (`on_workflow_approved`/`denied`/`canceled`).
- **Management intent types** — `mgmt_motd`, `mgmt_netconf`, `mgmt_dhcp_server`, and `mgmt_global_config` for the Management & Operations domain.
- **"Retired" intent status** — retired intents remain in Git but are non-actionable; reconciliation skips them and only a transition back to Draft is allowed.
- **Firewall rule intent type** — `fw_rule` with stateful/stateless firewall policy support, resolver, Jinja templates for all 6 vendor platforms, and `FirewallControllerAdapter` for centralized firewall appliances (Panorama, FortiManager).

### Upgrade from v1.1

```shell
pip install --upgrade nautobot-app-intent-networking==1.13.0
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**pyATS extended verification (optional):**

```shell
pip install nautobot-app-intent-networking[extended]
```

This installs `pyats`, `genie`, `netutils`, and `croniter` as optional dependencies. Extended verification is opt-in per intent — set the verification level to "Extended" on any intent to enable it.

**New migrations:** `0010_add_verification_level_fields` and `0011_intent_backup_verification_to_git` are applied automatically by `post_upgrade`. No manual action required.
