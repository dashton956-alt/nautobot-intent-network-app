# v2.0

## Release Date

2026-04-06

## Summary

v2.0 is a major release that replaces the pyATS/Genie verification engine with **NUTS** (Network Unit Testing System), adds a fully redesigned verification UI, introduces bulk intent actions, ships complete Jinja2 template coverage across 847 production templates for 6 vendor platforms, and expands live topology collection to all 7 supported platforms. The verification subsystem is now entirely NAPALM/Netmiko-based — no pyATS dependency is required.

## Breaking Changes

- **pyATS/Genie removed.** The `[extended]` extra no longer installs pyATS. If you were using `nautobot-app-intent-networking[extended]`, switch to `nautobot-app-intent-networking[nuts]`. The `NutsVerifier` class replaces `PyATSVerifier`.
- **Migration `0014_replace_pyats_with_nuts`** is required. Run `nautobot-server post_upgrade` after upgrading — this migration converts existing pyATS verification fields to the NUTS schema.
- **Verification YAML schema change.** The `verification.tests` block now expects NUTS test bundle definitions (see [Extended Verification](../../user/app_use_cases.md)).

## Added

- **NUTS verification engine** — replaces pyATS/Genie with the [Network Unit Testing System](https://nuts.readthedocs.io/). NUTS uses NAPALM and Netmiko for multi-vendor device-state validation supporting 20+ built-in test classes (interfaces, LLDP/CDP neighbor counts, BGP neighbors and sessions, VLANs, startup/running config diff, users) across 70+ network platforms.
- **Verification detail page** — new `VerificationResultDetail` view with Bootstrap 3 panels, per-device grouping, NUTS outcome parsing, expandable check rows, and a colour-coded pass/fail/warning breakdown.
- **Dashboard NUTS panel** — verification results on the main dashboard show per-check rows with expandable detail, contextual error summaries, device name, and target extracted from NUTS test IDs.
- **Bulk intent actions** — the intent list page now provides four bulk action buttons: **Dry-run**, **Preview**, **Deploy**, and **Validate**. All four operate on the full current query (respecting any active filters) and enqueue the appropriate Nautobot Job.
- **847 Jinja2 templates** — complete production template coverage across 6 vendor platforms (Cisco IOS-XE, IOS-XR, NX-OS, Juniper JunOS, Aruba AOS-CX, Arista EOS) for every intent type including stale-config removal variants.
- **Multi-vendor live topology collection** — the topology viewer's on-hover live data panel now supports all 7 platforms: Arista EOS, Cisco IOS-XE, Cisco IOS-XR, Cisco NX-OS, Juniper JunOS, Nokia SR OS, and Aruba AOS-CX. ARP tables, routing tables, VRFs, and BGP neighbour states are collected via Netmiko.
- **141 intent types** — 7 new intent types added: `mgmt_motd`, `mgmt_netconf`, `mgmt_dhcp_server`, `mgmt_global_config`, `fw_rule`, `mgmt_lldp_cdp`, and `mgmt_snmp`.
- **`nuts_error_summary`, `nuts_test_label`, `nuts_device`, `nuts_context`, `nuts_outcome` template filters** — custom template tags that parse raw NUTS test IDs and detail strings into human-readable labels.

## Fixed

- **Skipped NUTS tests no longer inflate failure counts** — tests skipped because optional fields (`mac_address`, `mtu`, `speed`) are absent from `test_data` are now excluded from the checks list rather than being reported as failures.
- **`SimpleInventory` replaces `DictInventory`** in live topology Nornir initialisation — `DictInventory` is not registered in the installed Nornir distribution; the live collection now writes temporary `hosts.yaml` / `defaults.yaml` files and passes their paths to `SimpleInventory`.
- **Hadolint / Dockerfile quality** — added `SHELL ["/bin/bash", "-o", "pipefail", "-c"]`, double-quoted all shell variables, added `--no-cache-dir` to `pip install`, and consolidated consecutive `RUN` layers.
- **pylint 10.00/10** — removed stale `no-self-use` disable, fixed implicit string concatenations, suppressed `too-many-return-statements` for `_platform_commands` dispatcher.
- **ruff / djlint / hadolint clean** — all linting tools report zero errors.

## Upgrade

```bash
pip install --upgrade nautobot-app-intent-networking==2.0.0
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

!!! warning "pyATS removal"
    If your environment had `pyats` or `genie` installed as part of the `[extended]` extra, you can safely remove them. The new `[nuts]` extra installs `nuts>=3.5.0` and `pytest-json-report>=1.5.0`.

    ```bash
    pip uninstall pyats genie
    pip install "nautobot-app-intent-networking[nuts]==2.0.0"
    ```

!!! important "Verification YAML migration"
    Existing intents that reference the old `verification.pyats_tests` block must be updated to use `verification.tests` with NUTS test bundle definitions. See the [Getting Started guide](../../user/app_getting_started.md) for the new schema.

!!! note "Database migration"
    Migration `0014` is non-destructive — existing verification results are preserved. The migration adds new fields for NUTS output storage and removes the pyATS-specific fields.
