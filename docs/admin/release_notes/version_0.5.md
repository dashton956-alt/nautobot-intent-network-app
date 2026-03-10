# v0.5 Release Notes

## Release Overview

v0.5 is a significant architectural release that replaces the custom Route Distinguisher and Route Target pool models with Nautobot's native IPAM models. This eliminates data duplication, integrates seamlessly with Nautobot's IPAM views and API, and reduces codebase complexity.

## [v0.5.0] - 2025-05-01

### Added

- **Native IPAM integration** — VRF allocation now uses `ipam.VRF` with the native `rd` field
- **Route Target allocation** via `ipam.RouteTarget` with standard `import_targets` / `export_targets` relationships
- **Namespace scoping** — VRFs are created within a configurable `ipam.Namespace` (setting: `vrf_namespace`)
- **`default_bgp_asn` setting** — ASN used for auto-generated RD/RT values in `<ASN>:<counter>` format
- **Migration 0006** — Automatically migrates existing RD/RT data from custom models to Nautobot native IPAM

### Changed

- `allocations.py` — Completely rewritten to use Nautobot `ipam.VRF` and `ipam.RouteTarget` models
- `models.py` — Removed `RouteDistinguisherPool`, `RouteDistinguisher`, `RouteTargetPool`, `RouteTarget` classes
- `views.py` — Removed custom RD/RT pool CRUD views
- `tables.py` — Removed RD/RT pool table definitions
- `forms.py` — Removed RD/RT pool form definitions
- `filters.py` — Removed RD/RT pool filter definitions
- `navigation.py` — Removed RD/RT pool navigation entries
- `graphql.py` — Removed RD/RT pool GraphQL types
- `api/serializers.py` — Removed RD/RT pool serializers
- `api/views.py` — Removed RD/RT pool API viewsets
- `api/urls.py` — Removed RD/RT pool API routes
- `__init__.py` — Added `vrf_namespace` and `default_bgp_asn` to required settings

### Removed

- `RouteDistinguisherPool` model
- `RouteDistinguisher` model
- `RouteTargetPool` model
- `RouteTarget` model (custom — Nautobot's native `ipam.RouteTarget` is now used)
- RD/RT pool UI pages and navigation items

### Migration Guide

See the [Upgrade Guide](../upgrade.md#upgrading-to-v05-ipam-refactor) for detailed migration instructions.

**Key actions:**

1. Add `vrf_namespace` and `default_bgp_asn` to your `PLUGINS_CONFIG` before upgrading
2. Run `nautobot-server post_upgrade` to execute migration 0006
3. Verify migrated VRFs in **IPAM → VRFs**
4. Remove any references to custom RD/RT pool models from external scripts
