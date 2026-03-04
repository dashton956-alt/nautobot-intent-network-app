# v0.2 Release Notes

## v0.2.0 - 2025-01-15

### Added

- **Native Nautobot GitRepository integration** — intent YAML files are now auto-discovered and synced via Nautobot's built-in `GitRepository` datasource framework. Configure a Git Repository with the "intent definitions" content type and Nautobot handles the rest. Directories scanned: `intents/`, `intent_definitions/`, `intent-definitions/`.
- New `datasources.py` module registering the `DatasourceContent` callback for intent definitions.
- `git_repository` foreign key on the `Intent` model linking each intent to its source Git repository.
- Orphan detection — intents removed from a Git repository are automatically deprecated on the next sync.
- `git_repository` filter on the Intent list view and API, allowing filtering intents by their source repository.
- **Expandable interface detail cards** in the topology viewer — click any interface row to reveal a full detail grid showing status, type, speed, duplex, MTU, MAC address, mode, VRF, LAG, cable peer, IP addresses, and description.
- **Enriched topology API** — `_get_interface_inventory()` now returns 15 fields per interface (mac_address, description, status, mode, mgmt_only, speed, duplex, vrf, lag, cable_peer, and more).
- **Floating legend/key** in the topology viewer showing node colours (by intent status), node shapes (by device role), and edge types (physical vs intent-based).
- **Synthesised intent-based edges** — dashed blue edges in the topology graph representing logical intent connections between devices, in addition to physical cable connections.
- **Interface summary bar** in the topology right panel showing total interface count with up/down breakdown.
- Seed data scripts (`development/seed_data.py`, `development/seed_interfaces.py`) for populating a development environment with realistic test data (12 devices, 58 interfaces, 8 intents, 4 resolution plans, 9 verification results, RD/RT pools).
- Database migration `0003_add_git_repository_fk` for the new `git_repository` field.

### Changed

- **Nautobot 3.x compatibility** — all models, views, filters, and API endpoints updated for Nautobot 3.x:
  - `Device.role` replaces `device_role`
  - `Location` replaces `Site`
  - Slug fields replaced with name-based lookups
  - Cable generic foreign key queries updated (`_termination_a_device` / `_termination_b_device`)
  - IPAddress creation requires `parent` FK to an exact Prefix
- API base URL updated from `/api/plugins/intent-engine/` to `/api/plugins/intent-networking/`.
- Plugin Python module renamed from `nautobot_plugin_intent_engine` to `intent_networking`.
- Package name updated from `nautobot-plugin-intent-engine` to `intent-networking`.
- `PLUGINS_CONFIG` key changed from `nautobot_plugin_intent_engine` to `intent_networking`.
- Topology viewer physics parameters tuned (gravitationalConstant: -200, springLength: 260, avoidOverlap: 1.0) to reduce node overlap.
- `_device_colour()` in topology API now uses case-insensitive status comparison.
- `sync-from-git` REST API endpoint and `IntentSyncFromGitJob` marked as legacy — native GitRepository integration is now the recommended approach.
- README.md fully rewritten with accurate package names, API URLs, Nautobot 3.x requirements, Git integration documentation, and updated project structure.

### Fixed

- Fixed `TemplateDoesNotExist` errors for intent detail, resolution plan, and verification result views.
- Fixed right panel crash in topology viewer caused by missing `#detail-status-dot` element.
- Fixed empty interfaces tab in topology viewer — interfaces and management IPs now properly seeded and queried.
- Fixed status colour matching in topology viewer (now case-insensitive with space-to-underscore normalisation).
- Fixed Cable GFK queries for Nautobot 3.x (`_termination_a_device` / `_termination_b_device`).
- Fixed bulk edit form missing `nullable_fields` causing `NoneType` iteration error.
- Fixed JSON key ordering in API serialisers.
- Fixed `version` field type on Intent model.
- Fixed `drf_spectacular` import error.
- Fixed port conflict (changed from 8080 default).
- All 95 tests passing (6 skipped), ruff lint clean.

### Deprecated

- `IntentSyncFromGitJob` and the `/intents/sync-from-git/` REST endpoint are deprecated in favour of native GitRepository integration. They remain functional as a legacy fallback for CI pipeline workflows.
