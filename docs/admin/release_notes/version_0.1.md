# v0.1 Release Notes

## v0.1.0 - 2024-01-01

### Added

- Initial release of the Intent Networking Nautobot app (`intent_networking`).
- `Intent` model for storing network intents as YAML-defined connectivity policies.
- `ResolutionPlan` model tracking resolved device/interface assignments for each intent.
- `VerificationResult` model storing post-deployment reachability verification outcomes.
- `RouteDistinguisherPool` / `RouteDistinguisher` and `RouteTargetPool` / `RouteTarget` models for atomic MPLS resource allocation.
- Six Nautobot Jobs: `IntentSyncFromGitJob`, `IntentResolutionJob`, `IntentDeploymentJob`, `IntentVerificationJob`, `IntentRollbackJob`, `IntentReconciliationJob`.
- REST API endpoints for intent lifecycle management (sync-from-git, resolve, deploy, status, rollback, verifications).
- Topology viewer API with live device data and intent-path highlighting.
- OPA policy gate integration for change-window and compliance enforcement.
- Slack notification support for deployment and rollback events.
- GitHub issue creation for non-auto-remediable drift detection.
