# App Overview

This document provides an overview of the Intent Networking app including its purpose, architecture, and integration with Nautobot.

!!! note
    Throughout this documentation, the terms "app" and "plugin" will be used interchangeably.

## Description

Intent Networking brings **Intent-Based Networking as a Service (IBNaaS)** to Nautobot. It enables network engineers and operators to express desired network state as declarative YAML files (intents) stored in a Git repository, and then automatically resolves, deploys, verifies, and continuously reconciles those intents against the live network.

The full intent lifecycle is:

```
Git YAML → Sync → Validate (OPA) → Resolve → Deploy (Nornir) → Verify → Reconcile (drift detection)
```

Key capabilities:

- **141 intent types** across 14 network domains (L2/L3, MPLS, EVPN/VXLAN, Security, WAN, Wireless, Cloud, QoS, Management, and more)
- **Git-native workflow** — intents are synced from a Git repository via Nautobot's native `GitRepository` integration
- **Policy enforcement** — optional OPA (Open Policy Agent) integration for pre-deployment policy checks
- **Resource allocation** — automatic VRF, Route Target, VNI, Tunnel ID, Loopback IP, and VLAN allocation using Nautobot's native IPAM models
- **Staged deployment** — canary / staged rollout with automatic rollback on failure
- **Continuous verification** — scheduled reconciliation detects drift and optionally auto-remediates
- **Full audit trail** — every lifecycle action is logged with timestamp, user, and details
- **Approval workflow** — explicit approval records with reviewer comments
- **Rich notifications** — Slack, PagerDuty, ServiceNow, GitHub issue creation, and custom webhooks

## Audience (User Personas) — Who Should Use This App?

| Persona | How they use Intent Networking |
|---------|-------------------------------|
| **Network Engineer** | Authors intent YAML files, reviews deployment plans, monitors verification results |
| **NetDevOps / SRE** | Manages the Git-to-deploy pipeline, configures OPA policies, reviews drift reports |
| **Network Architect** | Defines intent types and resource allocation strategies, reviews architecture decisions |
| **Security / Compliance** | Authors OPA policies (PCI-DSS, HIPAA, SOX) that gate intent deployment |
| **NOC / Operations** | Monitors the dashboard, receives Slack/PagerDuty alerts, triggers rollbacks |

## Authors and Maintainers

- **Daniel Ashton** — Primary author and maintainer

## Nautobot Features Used

The app leverages the following Nautobot platform capabilities:

### Models & IPAM

- **`ipam.VRF`** — Route Distinguisher allocation (VRF `rd` field)
- **`ipam.RouteTarget`** — Route Target allocation
- **`ipam.Namespace`** — Scoping for VRF uniqueness
- **`tenancy.Tenant`** — Multi-tenant intent ownership
- **`dcim.Device`** — Target devices for deployment
- **`extras.Status`** — Intent lifecycle status tracking (Draft → Deployed)

### Jobs

The app registers seven Nautobot Jobs:

| Job | Description |
|-----|-------------|
| `IntentSyncFromGitJob` | Creates/updates Intent records from parsed YAML (CI fallback) |
| `IntentResolutionJob` | Resolves an intent into a vendor-neutral deployment plan |
| `IntentConfigPreviewJob` | Generates a config diff preview without deploying |
| `IntentDeploymentJob` | Deploys the resolved plan to devices via Nornir; supports `commit=False` dry-run mode to render configs without device changes |
| `IntentVerificationJob` | Verifies the intent is satisfied post-deployment |
| `IntentRollbackJob` | Rolls back a failed deployment to the previous good state |
| `IntentReconciliationJob` | Scheduled: checks all deployed intents for configuration drift |

### Git Integration

- **`extras.GitRepository`** — Native data source for intent YAML files. The app registers an `"intent definitions"` provided-content type.

### Extras

- **Custom fields** — None created by the app (all data stored in app-owned models)
- **Relationships** — None created (relationships modelled directly in app models)
- **Secrets Groups** — Used for device SSH credentials and Nautobot API tokens
