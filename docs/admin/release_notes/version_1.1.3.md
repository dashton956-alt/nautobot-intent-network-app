# v1.1.3

## Added

- **pyATS Extended Verification** — optional two-tier verification engine (basic → extended) using pyATS/Genie for deep device-state validation. Supports 10 check types: interface status, BGP neighbours, OSPF adjacency, VLAN database, VRF routes, ARP table, NTP sync, ACL entries, route-map verification, and LLDP/CDP neighbours.
- **Verification escalation** — basic verification warnings automatically trigger extended pyATS verification with full diff output.
- **Per-intent verification settings** — configurable verification level (basic/extended), trigger (on-deploy/scheduled/both), cron schedule, and fail action (alert/rollback/remediate) per intent.
- **Dashboard pyATS panel** — "Recent pyATS / Extended Verifications" panel on the dashboard showing the last 15 extended/escalated verification results with pass/fail status, engine label, check count, escalation reason, and timestamp.
- **Git-backed verification reports** — per-intent toggle to commit Markdown verification reports to a configurable Git repository at `verification-results/<intent_id>/<timestamp>.md` via the GitHub Contents API.

## Upgrade

```shell
pip install --upgrade nautobot-app-intent-networking==1.1.3
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

**pyATS extended verification (optional):**

```shell
pip install nautobot-app-intent-networking[extended]
```
