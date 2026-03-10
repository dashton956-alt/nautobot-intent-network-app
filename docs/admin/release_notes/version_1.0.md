# v1.0 Release Notes

## Release Overview

v1.0 is the first stable release of Intent Networking, marking a commitment to backward compatibility within the 1.x series. It includes comprehensive documentation, 253 passing tests, a production-hardened lifecycle engine, and a polished dashboard experience.

## [v1.0.0] - 2025-06-01

### Added

- **Comprehensive documentation** — all user, admin, developer, and model docs fully written
- **253 passing tests** — unit, integration, API, and lifecycle coverage
- **Compatibility matrix** — documented Nautobot version support and deprecation policy
- **Architecture Decision Records** — five ADRs documenting key design choices
- **Extension guide** — how to add custom intent types, adapters, templates, and policies

### Changed

- **Dashboard** — redesigned with status tiles, activity feed, and distribution charts
- **Navigation** — top-level menu reorganised into Intents, Resource Pools, Topology, and Dashboard
- **Documentation** — all boilerplate "Developer Note" warnings removed; every page has real content
- **README** — updated project structure, test count, and installation instructions to reflect current state

### Fixed

- **Status tile visibility** — fixed invisible tiles on the dashboard
- **Release notes index** — all versions now listed with correct dates and highlights
- **Stale references** — removed all references to deleted RD/RT pool models from docs and README

### Upgrade from v0.5

No database migrations required. Simply update the package and restart services:

```shell
pip install --upgrade nautobot-app-intent-networking
nautobot-server post_upgrade
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```
