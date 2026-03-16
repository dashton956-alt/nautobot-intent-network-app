# External Interactions

This document describes external dependencies and integrations for the Intent Networking app.

## External System Integrations

### From the App to Other Systems

| System | Direction | Protocol | Purpose |
|--------|-----------|----------|---------|
| **Network devices** | App → Device | SSH (Nornir/Netmiko) | Configuration deployment and verification |
| **OPA** (Open Policy Agent) | App → OPA | HTTP REST | Pre-deployment policy evaluation |
| **Slack** | App → Slack | HTTPS webhook | Event notifications (deploy, fail, rollback, drift) |
| **GitHub** | App → GitHub API | HTTPS REST | Automatic issue creation for non-remediable drift |
| **PagerDuty** | App → PagerDuty | HTTPS Events API | Critical alert escalation |
| **ServiceNow** | App → ServiceNow | HTTPS REST | ITSM ticket creation |
| **Custom webhooks** | App → Any endpoint | HTTPS POST | Configurable event forwarding |

### From Other Systems to the App

| System | Direction | Protocol | Purpose |
|--------|-----------|----------|---------|
| **Git hosting** (GitHub/GitLab) | Git → Nautobot | Git (HTTPS/SSH) | Intent YAML file synchronisation via `GitRepository` |
| **CI/CD pipeline** | CI → App API | HTTPS REST | Push intent sync requests via `IntentSyncFromGitJob` |
| **External monitoring** | External → App API | HTTPS REST | Query intent status, verification results |

## OPA (Open Policy Agent) Integration

The app can optionally validate intents against an OPA policy server before deployment.

### How It Works

1. During the resolution phase, the app constructs a policy input document containing the intent data, allocated resources, and target devices.
2. The app sends an HTTP POST to the OPA server's Data API (e.g. `http://opa:8181/v1/data/intent/allow`).
3. OPA evaluates the input against loaded Rego policies and returns an `allow`/`deny` decision.
4. If denied, the intent remains in **Draft** status and the denial reason is recorded.

### Example Rego Policy

```rego
package intent

default allow = false

# Allow L3VPN intents only if a change ticket is provided
allow {
    input.intent_type == "mpls_l3vpn"
    input.change_ticket != ""
}

# Deny any intent that crosses PCI boundary without PCI tag
deny["PCI compliance: intent crosses trust boundary without pci_compliant tag"] {
    input.parameters.sites[_].zone == "pci"
    not input.tags[_] == "pci_compliant"
}
```

### Configuration

The OPA endpoint is configured per-environment. See `opa_client.py` for the default endpoint resolution logic.

## Git Integration

The app leverages Nautobot's native `GitRepository` model to synchronise intent YAML files.

### Provided Content Type

The app registers an `"intent definitions"` provided-content type. When a `GitRepository` with this content type is synced, the app's `datasources.py` callback:

1. Scans `intents/`, `intent_definitions/`, and `intent-definitions/` directories
2. Loads `.intentignore` patterns (if present) to exclude matching files
3. Parses all `.yaml`, `.yml`, and `.json` files that are not ignored
4. Creates or updates `Intent` records in the database
5. Marks intents whose files were removed as **Deprecated**

### `.intentignore` {: #intentignore }

Place a `.intentignore` file in the **repository root** and/or inside the **intent directory** to exclude files from sync. The file uses `fnmatch`-style glob patterns, one per line.

**Supported syntax:**

| Pattern | Matches |
|---------|---------|
| `*.json` | Any `.json` file at any depth |
| `test_*.yaml` | Files starting with `test_` |
| `tests/*` | All files directly under `tests/` |
| `**/scratch/**` | Any file under any `scratch/` directory |
| `archive/*.yml` | `.yml` files directly under `archive/` |

Blank lines and lines starting with `#` are treated as comments.

**Example `.intentignore`:**

```text
# Test fixtures — don't sync to production
tests/**
test_*.yaml

# Scratch / WIP files
**/scratch/**
draft_*.yml

# Legacy JSON exports
*.json
```

!!! note
    The app checks both the full relative path (`subdir/file.yaml`) and the filename alone (`file.yaml`) against each pattern. This gives both directory-level and filename-level control.

!!! tip
    If both the repo root and the intent directory contain a `.intentignore`, patterns from **both** files are merged (duplicates removed).

### Continuous Delivery

Configure a webhook on your Git hosting provider to trigger a Nautobot sync on every push. This enables a fully automated pipeline:

```
git push → webhook → Nautobot sync → Intent created/updated → Resolve → Deploy → Verify
```

## Notification Channels

### Slack

Configure `slack_webhook_url` in `PLUGINS_CONFIG`. The app sends formatted messages for:

- Intent deployed successfully
- Deployment failed
- Rollback triggered
- Configuration drift detected

### GitHub Issues

Configure `github_repo` and optionally `github_api_url` in `PLUGINS_CONFIG`. When drift is detected that cannot be auto-remediated, the app creates a GitHub issue with:

- Intent ID and type
- Drift details (expected vs. actual)
- Affected devices
- Suggested remediation steps

### PagerDuty

Configure `pagerduty_routing_key` to escalate critical events (deployment failures, persistent drift) to your on-call rotation.

## Nautobot REST API Endpoints

The app exposes full CRUD REST API endpoints under `/api/plugins/intent-networking/`:

| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/plugins/intent-networking/intents/` | GET, POST, PUT, PATCH, DELETE | Intent CRUD |
| `/api/plugins/intent-networking/intents/<id>/resolve/` | POST | Trigger resolution |
| `/api/plugins/intent-networking/intents/<id>/deploy/` | POST | Trigger deployment |
| `/api/plugins/intent-networking/intents/<id>/verify/` | POST | Trigger verification |
| `/api/plugins/intent-networking/intents/<id>/rollback/` | POST | Trigger rollback |
| `/api/plugins/intent-networking/resolution-plans/` | GET | Resolution plan history |
| `/api/plugins/intent-networking/verification-results/` | GET | Verification result history |
| `/api/plugins/intent-networking/vxlan-vni-pools/` | GET, POST, PUT, PATCH, DELETE | VNI pool management |
| `/api/plugins/intent-networking/tunnel-id-pools/` | GET, POST, PUT, PATCH, DELETE | Tunnel ID pool management |
| `/api/plugins/intent-networking/managed-loopback-pools/` | GET, POST, PUT, PATCH, DELETE | Loopback pool management |
| `/api/plugins/intent-networking/wireless-vlan-pools/` | GET, POST, PUT, PATCH, DELETE | Wireless VLAN pool management |
| `/api/plugins/intent-networking/topology/` | GET | Topology graph data |
| `/api/plugins/intent-networking/topology/device/<id>/` | GET | Live device interface data |
| `/api/plugins/intent-networking/sync-from-git/` | POST | CI/CD intent sync endpoint |

### Authentication

All API endpoints require a valid Nautobot API token passed in the `Authorization` header:

```bash
curl -H "Authorization: Token $NAUTOBOT_TOKEN" \
     https://nautobot.example.com/api/plugins/intent-networking/intents/
```

### GraphQL

All Intent Networking models are exposed via Nautobot's GraphQL endpoint at `/api/graphql/`. Example query:

```graphql
{
  intents(intent_type: "mpls_l3vpn") {
    intent_id
    version
    status { name }
    tenant { name }
    resolution_plans {
      plan_data
      created
    }
  }
}
```

## Approval Workflow

Intents must be approved before deployment. The app supports **two approval paths** — use whichever fits your organisation's workflow, or both.

### Path 1: In-App Approval (UI + API)

**From the UI:** Open the intent detail page. Users with the `approve_intent` permission see **Approve** and **Reject** buttons in the Approval Status panel. Enter an optional comment and click the button.

**From the API:**

```bash
# Approve
curl -X POST -H "Authorization: Token $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"comment": "Reviewed and approved for production"}' \
     https://nautobot.example.com/api/plugins/intent-networking/intents/$INTENT_UUID/approve/

# Reject
curl -X POST -H "Authorization: Token $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"comment": "ACL rules do not meet PCI-DSS requirements"}' \
     https://nautobot.example.com/api/plugins/intent-networking/intents/$INTENT_UUID/reject/
```

Both methods require the `approve_intent` permission and create an `IntentApproval` record with full attribution.

### Path 2: Nautobot Native Approval Workflow

Nautobot 3.x provides a built-in multi-stage approval workflow system. To use it with intents:

1. **Create an Approval Workflow Definition:**
    - Navigate to **Approvals → Workflow Definitions → Add**.
    - Set **Model** to `intent_networking | intent`.
    - Optionally set **Constraints** to limit which intents require approval, e.g. `{"intent_type__in": ["evpn_vxlan_fabric", "fw_rule"]}`.
    - Set **Weight** (higher weight takes priority when multiple definitions match).

2. **Add Stage Definitions:**
    - Define one or more stages (e.g. "Peer Review", "Security Team Sign-off", "Change Manager").
    - For each stage, set the **Approver Group**, **Minimum Approvers**, and **Sequence**.

3. **Workflow triggers automatically** when an intent matching the constraints is updated (e.g. status changed to "Validated").

4. **Approvers review** via the **Approval Dashboard** (Approvals → Approval Dashboard → My Approvals tab), or via the API:

    ```bash
    # Approve a stage
    curl -X POST -H "Authorization: Token $TOKEN" \
         -H "Content-Type: application/json" \
         -d '{"comment": "LGTM"}' \
         https://nautobot.example.com/api/extras/approval-workflow-stages/$STAGE_ID/approve/
    ```

5. **When all stages pass**, Nautobot calls the intent's `on_workflow_approved()` callback, which automatically:
    - Creates an `IntentApproval` record (for backward compatibility)
    - Sets the `approved_by` field
    - Writes an audit trail entry
    - Dispatches the `intent.approved` event

6. **If denied**, Nautobot calls `on_workflow_denied()`, which records the rejection and blocks deployment.

!!! tip "Required Permissions for Native Approvals"
    - Object Operators: `extras.view_approvalworkflow`, `extras.view_approvalworkflowstage`
    - Approvers: add `extras.change_approvalworkflowstage`
    - Workflow Architects: add `extras.add/change/delete_approvalworkflowdefinition` and `extras.add/change/delete_approvalworkflowstagedefinition`

!!! note "Both paths work together"
    The `is_approved` check on the Intent model accepts approval from **either** a custom `IntentApproval` record or an approved native `ApprovalWorkflow`. You can use one or both methods.
