# Architecture Decision Records

This page documents significant architectural decisions and deviations from standard patterns.

## ADR-001: Native IPAM for RD/RT Allocation

**Status:** Accepted (v0.5)

**Context:** The original implementation (v0.1–v0.4) used custom `RouteDistinguisherPool` / `RouteDistinguisher` and `RouteTargetPool` / `RouteTarget` models for RD/RT allocation. This duplicated data that Nautobot already models natively in `ipam.VRF` (which has an `rd` field) and `ipam.RouteTarget`.

**Decision:** Replace the four custom models with Nautobot's native `ipam.VRF`, `ipam.RouteTarget`, and `ipam.Namespace` models. RD/RT values are auto-generated in `<ASN>:<counter>` format within the configured Namespace.

**Consequences:**

- ✅ Eliminates data duplication between custom pool models and Nautobot IPAM
- ✅ VRFs and RTs are visible in Nautobot's standard IPAM views and API
- ✅ Leverages Nautobot's built-in Namespace scoping for VRF uniqueness
- ✅ Reduces codebase complexity (4 fewer models, simplified allocations)
- ⚠️ Requires migration (0006) for existing deployments
- ⚠️ Custom pool UI pages removed — VRF management done through standard IPAM

## ADR-002: Description-Based Intent Tracking

**Status:** Accepted (v0.5)

**Context:** When allocating VRFs and RTs via native IPAM models, the app needs a way to track which intent owns each VRF/RT without adding custom fields.

**Decision:** Use the `description` field on `ipam.VRF` and `ipam.RouteTarget` to store the intent ID (e.g. `"Allocated by intent: fin-pci-connectivity-001"`). The allocator queries by description pattern to find existing allocations and detect the next available counter value.

**Consequences:**

- ✅ No custom fields or relationships needed on Nautobot core models
- ✅ Human-readable tracking visible in the Nautobot UI
- ⚠️ Description field must not be manually edited or the tracking breaks

## ADR-003: Event-Driven Architecture

**Status:** Accepted (v0.4)

**Context:** Multiple subsystems need to react to intent lifecycle events (notifications, metrics, audit logging, webhooks).

**Decision:** Implement an internal event bus (`events.py`) with named events (`intent.created`, `intent.deployed`, `intent.drift`, etc.) and a `dispatch_event()` function. Handlers are registered for each notification channel.

**Consequences:**

- ✅ Decoupled notification/metric logic from core lifecycle code
- ✅ Easy to add new event handlers without modifying existing code
- ✅ Consistent event naming and payload structure

## ADR-004: Atomic Resource Allocation

**Status:** Accepted (v0.1)

**Context:** Multiple Celery workers may attempt to allocate resources (VNIs, tunnel IDs, VRFs) simultaneously.

**Decision:** All resource allocation uses Django's `select_for_update()` within a database transaction to prevent race conditions. The allocator finds the next available value in the pool's range and creates an allocation record atomically.

**Consequences:**

- ✅ No duplicate allocations under concurrent load
- ✅ Works with both PostgreSQL and MySQL
- ⚠️ Brief lock contention on the pool table during high-concurrency allocation

## ADR-005: Git-Native Intent Sync

**Status:** Accepted (v0.2)

**Context:** The original v0.1 approach required a CI pipeline to POST intent YAML to the API. This added complexity for users.

**Decision:** Register an `"intent definitions"` provided-content type with Nautobot's `GitRepository` data source framework. Nautobot handles cloning, caching, and sync scheduling; the app's `datasources.py` callback scans for YAML files and creates/updates Intent records.

**Consequences:**

- ✅ Zero CI pipeline configuration needed — just add a Git repo in Nautobot
- ✅ Nautobot handles credentials, branch tracking, and webhook-triggered syncs
- ✅ Legacy CI push endpoint retained as fallback (`IntentSyncFromGitJob`)
- ⚠️ Requires intent files to be in specific directories (`intents/`, `intent_definitions/`, `intent-definitions/`)
