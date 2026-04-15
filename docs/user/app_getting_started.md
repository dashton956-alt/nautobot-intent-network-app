# Getting Started with the App

This document provides a step-by-step tutorial on how to get the App going and how to use it.

## Install the App

To install the App, please follow the instructions detailed in the [Installation Guide](../admin/install.md).

## First Steps with the App

Once installed and configured, follow this walkthrough to create and deploy your first intent.

### 1. Verify the Dashboard

Navigate to **Intent Networking → Dashboard**. You should see the main dashboard with:

- **Status tiles** — counts of intents in each lifecycle state
- **Recent activity** — latest intent changes
- **Charts** — intent distribution by type and tenant

### 2. Ensure a Namespace Exists

Navigate to **IPAM → Namespaces** and verify the namespace configured in `vrf_namespace` (default: `"Global"`) exists. This is required for VRF/RD/RT allocation.

### 3. Create a VNI Pool (Required for VXLAN/EVPN intents)

If your intents include any EVPN fabric, L2VNI, or L3VNI types, create a VNI Pool before syncing:

1. Navigate to **Plugins → Intent Engine → VNI Pools → + Add**
2. Enter the pool name that matches `vni_pool_name` in your `PLUGINS_CONFIG`
3. Add at least one VNI range (e.g. `10000-19999`)
4. Click **Create**

If you are not using VXLAN/EVPN you can skip this step.

### 4. Create a Git Repository (Recommended)

1. Go to **Extensibility → Git Repositories → Add**
2. Enter your repository URL (e.g. `https://github.com/your-org/network-as-code.git`)
3. Select the branch (e.g. `main`)
4. Under **Provided Contents**, check **"intent definitions"**
5. Click **Create**, then click **Sync**

Nautobot will scan the repo for YAML files in `intents/`, `intent_definitions/`, or `intent-definitions/` directories.

!!! tip "Excluding files with `.intentignore`"
    If your intent directory contains test fixtures, scratch files, or other YAML you don't want synced,
    create a `.intentignore` file in the repository root or inside the intent directory.
    It uses the same glob syntax as `.gitignore`:

    ```text
    # Skip test data
    tests/**
    test_*.yaml

    # Skip work-in-progress
    **/scratch/**
    draft_*.yml
    ```

    See [External Interactions → Git Integration](external_interactions.md#intentignore) for full details.

### 4. Write Your First Intent YAML

Create a file in your Git repo at `intents/my-first-intent.yaml`:

```yaml
id: my-first-l3vpn-001
version: 1
type: mpls_l3vpn
tenant: engineering
change_ticket: CHG0000001
description: "L3VPN connecting NYC and LON sites"
parameters:
  vrf_name: ENG-L3VPN
  sites:
    - name: nyc-dc1
      device: nyc-dc1-pe1
      interface: GigabitEthernet0/0/0
      ipv4: 10.100.1.1/30
    - name: lon-dc1
      device: lon-dc1-pe1
      interface: GigabitEthernet0/0/0
      ipv4: 10.100.1.5/30
  route_targets:
    import: ["65000:100"]
    export: ["65000:100"]
```

Commit and push the file, then re-sync the Git repository in Nautobot.

### 5. View the Synced Intent

Navigate to **Intent Networking → Intents**. Your intent should appear with status **Draft**.

Click on the intent to see its detail view, which shows:

- The full parsed YAML data
- Git metadata (commit SHA, branch, PR number)
- Lifecycle timestamps
- Related resolution plans and verification results

### 6. Resolve the Intent

From the intent detail page, click the **Resolve** job button (or run the `IntentResolutionJob` from **Jobs → Intent Resolution Job**).

This translates the declarative intent into a concrete deployment plan — a `ResolutionPlan` record containing:

- Vendor-neutral network primitives
- Allocated resources (VRF, RD, RT values)
- Target devices and interfaces

### 7. Preview the Configuration

Click the **Preview** job button to generate a configuration diff without deploying. This shows exactly what would be pushed to each device.

### 8. Deploy the Intent

Click the **Deploy** job button. The intent moves through:

- **Validated** → OPA policy checks pass
- **Deploying** → Configuration pushed via Nornir
- **Deployed** → All devices configured successfully

### 9. Verify the Deployment

Click the **Verify** job button (or wait for the scheduled reconciliation). A `VerificationResult` record is created showing whether the live network state matches the intent.

### 10. Monitor on the Dashboard

Return to the dashboard to see your intent reflected in the status tiles and charts.

## What Are the Next Steps?

- **Add more intents** — explore the [141 supported intent types](app_use_cases.md)
- **Configure OPA** — add policy-as-code guardrails before deployment (see [External Interactions](external_interactions.md))
- **Set up notifications** — configure Slack webhooks or PagerDuty alerts (see [Installation Guide](../admin/install.md#optional-settings))
- **Explore the API** — use the REST API for CI/CD integration (see [External Interactions](external_interactions.md#nautobot-rest-api-endpoints))
- **Check out use cases** — see the [Use Cases](app_use_cases.md) section for more examples
