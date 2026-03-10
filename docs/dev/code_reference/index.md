# Code Reference

Auto-generated code reference documentation from docstrings.

The following modules have auto-generated API documentation:

- [Package](package.md) — App configuration and top-level module
- [API](api.md) — REST API serializers, viewsets, and URL routing

## Module Overview

| Module | Description |
|--------|-------------|
| `__init__.py` | `NautobotAppConfig` subclass, plugin metadata, settings |
| `models.py` | All database models (Intent, pools, audit, lifecycle) |
| `jobs.py` | Seven Nautobot Jobs (sync, resolve, preview, deploy, verify, rollback, reconcile) |
| `resolver.py` | Intent → vendor-neutral primitives translation |
| `allocations.py` | Atomic resource allocation (VRF, VNI, tunnel ID, loopback, VLAN) |
| `controller_adapters.py` | Vendor-specific configuration generation |
| `datasources.py` | Nautobot GitRepository callback for intent YAML sync |
| `events.py` | Internal event bus for lifecycle event dispatch |
| `notifications.py` | Slack, GitHub, PagerDuty, ServiceNow notification handlers |
| `opa_client.py` | OPA HTTP client for policy evaluation |
| `topology_api.py` | REST endpoints for topology graph data |
| `topology_view.py` | Django view for the interactive topology viewer |
| `views.py` | Nautobot UI views (CRUD, dashboard, detail pages) |
| `tables.py` | django-tables2 table definitions |
| `forms.py` | Django model forms and filter forms |
| `filters.py` | FilterSet definitions |
| `navigation.py` | Nautobot navigation menu configuration |
| `metrics.py` | Prometheus metrics and dashboard counters |
| `secrets.py` | Nautobot Secrets Group integration for credentials |
| `graphql.py` | GraphQL type definitions for all models |
