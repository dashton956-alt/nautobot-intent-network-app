# Release Notes

All published release notes are listed below. Patch releases are included within their parent minor release document (e.g. `v0.2`).

| Version | Date | Highlights |
|---------|------|------------|
| [v2.0.8](version_2.0.8.md) | 2026-04-21 | Bug-fix release: Arista live collection (ARP raw-string fallback, VRF/BGP/route field keys, next_hop list join); adds grouped-by-domain intent list view |
| [v2.0.7](version_2.0.7.md) | 2026-04-17 | Bug-fix release: NUTS nornir-config flag, Netmiko platform key, VerificationResult detail view 500, cEOS credential bypass; adds save_config deployment flag and TestNapalmRunningConfigContains |
| [v2.0.6](version_2.0.6.md) | 2026-04-16 | Major feature release: NUTS verification, fw_rule intent type, Catalyst Center adapter, intent dependency graph, Approve/Reject UI, .intentignore, management intent types, VNI Pool UI, and 4 bug fixes |
| [v2.0.5](version_2.0.5.md) | 2026-04-15 | Fix device credential resolution — use SSH access type for SecretsGroups; per-device credential lookup |
| [v2.0.4](version_2.0.4.md) | 2026-04-14 | VXLAN VNI Pool management UI — create, edit and delete pools directly in Nautobot |
| [v2.0.3](version_2.0.3.md) | 2026-04-14 | Fix Status.DoesNotExist on fresh installs — lifecycle statuses now seeded by data migration |
| [v2.0.2](version_2.0.2.md) | 2026-04-13 | Expected shorthand in NUTS verification — define checks once, run on all scoped devices |
| [v2.0.1](version_2.0.1.md) | 2026-04-12 | Fix 14 Arista EOS removal templates (wrong negation commands, required-field enforcement, stub alignment) |
| [v2.0](version_2.0.md) | 2026-04-06 | NUTS verification engine (replaces pyATS), bulk intent actions, 847 Jinja2 templates, multi-vendor live topology (7 platforms), 141 intent types, new verification detail UI |
| [v1.1.8](version_1.1.8.md) | 2026-03-23 | Fix Nornir inventory plugin registration, correct plugin name to 'nautobot-inventory', add nautobot_plugin_nornir to PLUGINS |
| [v1.1.7](version_1.1.7.md) | 2026-03-21 | Nornir ORM inventory fix, nautobot-plugin-nornir v3 dependency, Secrets Group integration, intent data resolver corrections |
| [v1.1.6](version_1.1.6.md) | 2026-03-20 | Git sync error surfacing, verification_schedule NULL fix, .intentignore, Approve/Reject UI, Catalyst Center adapter, intent dependency graph, fw_rule intent type, Retired status |
| [v1.1.5](version_1.1.5.md) | 2026-03-19 | Documentation updates and deployment pipeline improvements |
| [v1.1.4](version_1.1.4.md) | 2026-03-19 | Fix PostgreSQL migrations, Python 3.12 pin, Catalyst Center adapter, intent dependency graph |
| [v1.1](version_1.1.md) | 2026-03-12 | 4 new global-config management intent types, dry-run deployment, extended platform templates |
| [v1.1.1](version_1.1.1.md) | 2026-03-16 | Firewall rule intent type, firewall controller adapter, expanded vendor templates |
| [v1.0](version_1.0.md) | 2025-06-01 | Stable release — comprehensive docs, 253 tests, production-ready |
| [v0.5](version_0.5.md) | 2025-05-01 | Native IPAM refactor — RD/RT via Nautobot VRF/RouteTarget/Namespace |
| [v0.4](version_0.4.md) | 2025-03-15 | 129 intent types, event-driven notifications, dashboard redesign |
| [v0.3](version_0.3.md) | 2025-02-15 | Code quality — pylint 10.00/10, ruff clean |
| [v0.2](version_0.2.md) | 2025-01-15 | Native GitRepository integration, expandable interface cards, topology legend, Nautobot 3.x compatibility |
| [v0.1](version_0.1.md) | 2024-01-01 | Initial release — intent lifecycle, resource allocation, topology viewer, OPA + Slack |
