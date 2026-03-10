# v0.4 Release Notes

## v0.4.0 - 2025-03-06

### Added

- Jinja2 config templates for all 4 platforms (IOS-XE, IOS-XR, Junos, AOS-CX) with VRF, BGP neighbor, ACL, and VRF removal templates
- Real Nornir ping execution in `_measure_latency()`
- Rollback removal config generation (replaces TODO placeholder)
- JobButtonReceiver hooks (Resolve, Deploy, Dry-Run, Verify, Rollback) for one-click job execution from Intent detail page
- Intent detail template showing identity, timestamps, git source, resolution plans, verification history, and action buttons
- RD/RT Pool management views (CRUD UI via NautobotUIViewSet)
- Auto-scheduled reconciliation job on startup
- Plugin dashboard with status counts, pool utilisation, and recent activity
- Dry-run deploy available from UI via dedicated job button
- Bulk operations API (bulk-resolve, bulk-deploy, bulk-verify)
- GraphQL schema for all 7 models
- FilterSets for RD/RT pool ViewSets

### Changed

- Intent status workflow enforced via `clean()` validation
- Approval gate enforced — deploy requires `approved_by` to be set
- Jobs registered with Nautobot 3.x via `register_jobs()` at module level
- Dashboard template uses `base.html` instead of non-existent `generic/home.html`

<!-- towncrier release notes start -->
