# Installing the App in Nautobot

Here you will find detailed instructions on how to **install** and **configure** the Intent Networking app within your Nautobot environment.

## Prerequisites

- **Nautobot 3.0.0** or higher
- **Python 3.10** or higher
- **PostgreSQL** (recommended) or **MySQL** database
- A functioning **Redis** instance (required by Nautobot's Celery workers)

!!! note
    Please check the [dedicated page](compatibility_matrix.md) for a full compatibility matrix and the deprecation policy.

### External Service Requirements

The app optionally integrates with several external systems:

| Service | Purpose | Required? |
|---------|---------|-----------|
| **OPA** (Open Policy Agent) | Policy evaluation before deployment (PCI-DSS, HIPAA, etc.) | Optional |
| **Git hosting** (GitHub, GitLab, etc.) | Source repository for intent YAML files | Recommended |
| **Slack** | Webhook notifications for deploy/fail/rollback events | Optional |
| **GitHub API** | Automatic issue creation for non-remediable drift | Optional |
| **PagerDuty** | Critical alert escalation | Optional |
| **ServiceNow** | ITSM ticket creation | Optional |

## Install Guide

!!! note
    Apps can be installed from the [Python Package Index](https://pypi.org/) or locally. See the [Nautobot documentation](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/installation/app-install/) for more details. The pip package name for this app is [`nautobot-app-intent-networking`](https://pypi.org/project/nautobot-app-intent-networking/).

### Step 1 — Install the Package

```shell
pip install nautobot-app-intent-networking
```

To ensure the app is automatically re-installed during future upgrades, create a file named `local_requirements.txt` (if not already existing) in the Nautobot root directory (alongside `requirements.txt`) and list the package:

```shell
echo nautobot-app-intent-networking >> local_requirements.txt
```

### Step 2 — Enable in `nautobot_config.py`

Append `"intent_networking"` to the `PLUGINS` list and add the `"intent_networking"` dictionary to `PLUGINS_CONFIG`:

```python
PLUGINS = ["intent_networking"]

PLUGINS_CONFIG = {
    "intent_networking": {
        # --- Required ---
        "vrf_namespace": "Global",       # must match an existing Nautobot Namespace
        "default_bgp_asn": 65000,        # ASN used in RD/RT values (e.g. 65000:1)
        "vni_pool_name": "my-vni-pool",  # name of a VxlanVniPool created in the UI

        # --- Secrets Groups (recommended — avoids plaintext credentials) ---
        # Create each group in Nautobot: Secrets → Secrets Groups
        # Device credentials are resolved per device first (see Credential Lookup Order),
        # then this group is used as the global fallback.
        "device_secrets_group": "Network Device Credentials",
        "nautobot_api_secrets_group": "Nautobot API Token",
        # "servicenow_secrets_group": "ServiceNow Credentials",
        # "github_secrets_group": "GitHub Token",
        # "slack_secrets_group": "Slack Webhook",

        # --- Optional (shown with defaults) ---
        "max_vrfs_per_tenant": 50,
        "max_prefixes_per_vrf": 5000,
        "reconciliation_interval_hours": 1,
        "auto_remediation_enabled": True,

        # --- OPA (leave unset to use built-in defaults) ---
        "opa_verify_ssl": True,
        "opa_ca_bundle": None,       # path to CA bundle PEM for self-signed OPA TLS
        "opa_custom_packages": [],   # additional Rego packages to query for every intent

        # --- Notifications (leave empty/None to disable) ---
        "slack_webhook_url": None,
        "github_repo": None,         # e.g. "your-org/network-as-code"
    },
}
```

See `development/nautobot_config.py` for the full reference with all available settings.

### Step 3 — Run Post-Upgrade

Run the `post_upgrade` command to execute migrations and clear cache:

```shell
nautobot-server post_upgrade
```

### Step 4 — Restart Services

```shell
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

## App Configuration

### Required Settings

| Setting | Type | Description |
|---------|------|-------------|
| `vrf_namespace` | `str` | Name of the Nautobot IPAM Namespace used for VRF allocation. Must match an existing `ipam.Namespace` object. Default: `"Global"` |
| `default_bgp_asn` | `int` | BGP Autonomous System Number used as the prefix for auto-generated RD and RT values (e.g. `65000:1`). |
| `vni_pool_name` | `str` | Name of a `VxlanVniPool` object (created via **Intent Engine → VNI Pools**). Required for any intent that allocates VNIs (EVPN/VXLAN fabrics, L2VNI, L3VNI). |

### Secrets Group Settings (Recommended)

Storing credentials as Nautobot Secrets Groups is strongly preferred over plaintext environment variables. Create each group in **Secrets → Secrets Groups** then reference the group name here.

| Setting | Type | Description |
|---------|------|-------------|
| `device_secrets_group` | `str` | Global fallback SecretsGroup name for device SSH credentials. See [Credential Lookup Order](#credential-lookup-order). |
| `nautobot_api_secrets_group` | `str` | SecretsGroup name for the Nautobot API token used by internal job calls. |
| `servicenow_secrets_group` | `str` | SecretsGroup name for ServiceNow API credentials. |
| `github_secrets_group` | `str` | SecretsGroup name for the GitHub API token. |
| `slack_secrets_group` | `str` | SecretsGroup name for the Slack webhook URL. |

### Optional Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_vrfs_per_tenant` | `int` | `50` | Maximum VRFs that can be allocated per tenant |
| `max_prefixes_per_vrf` | `int` | `5000` | Maximum prefix count per VRF |
| `reconciliation_interval_hours` | `int` | `1` | How often the reconciliation job runs (hours) |
| `auto_remediation_enabled` | `bool` | `True` | Whether drift auto-remediation is enabled (requires OPA approval) |
| `opa_verify_ssl` | `bool` | `True` | Verify TLS certificate of the OPA server |
| `opa_ca_bundle` | `str` | `None` | Path to a CA bundle PEM file for OPA TLS (useful for self-signed certs) |
| `opa_custom_packages` | `list` | `[]` | Additional Rego package paths queried for every intent |
| `slack_webhook_url` | `str` | `None` | Slack incoming webhook URL (legacy — prefer `slack_secrets_group`) |
| `github_repo` | `str` | `None` | GitHub repository for drift issue creation (e.g. `"your-org/network-as-code"`) |
| `pagerduty_routing_key` | `str` | `None` | PagerDuty Events API routing key for critical alerts |
| `servicenow_instance` | `str` | `None` | ServiceNow instance URL (legacy — prefer `servicenow_secrets_group`) |
| `webhook_urls` | `list` | `[]` | Additional webhook URLs for event notifications |

## Post-Install Setup

### Create Intent Lifecycle Statuses

Navigate to **Extras → Statuses** and create the following, assigning each to the **Intent** content type:

| Name | Colour | Description |
|------|--------|-------------|
| Draft | Grey | Newly synced from Git, not yet validated |
| Validated | Blue | Schema + OPA checks passed |
| Deploying | Amber | Deployment in progress |
| Deployed | Green | Successfully deployed and verified |
| Failed | Red | Deployment or verification failed |
| Rolled Back | Orange | Reverted to previous version |
| Deprecated | Grey | Removed from Git repo or superseded |
| Retired | Grey | Non-actionable — remains in Git, reconciliation skips it |

!!! note
    From v2.0.3 onwards these statuses are automatically seeded by the `0015_seed_intent_lifecycle_statuses` data migration. Manual creation is only required if you are upgrading from v2.0.2 or earlier.

### Ensure a Namespace Exists

The app allocates VRFs within a Nautobot IPAM Namespace. Nautobot creates a `"Global"` namespace by default, which the app uses unless you override `vrf_namespace` in the configuration.

To verify:

1. Navigate to **IPAM → Namespaces**
2. Confirm the `"Global"` namespace exists (or whichever name you configured)

!!! note
    Route Distinguishers and Route Targets are allocated using Nautobot's native IPAM models (`ipam.VRF` and `ipam.RouteTarget`) and no longer require custom pool configuration. The app auto-generates RD/RT values in `<ASN>:<counter>` format within the configured Namespace.

### Create a VNI Pool (Required for VXLAN/EVPN intents)

If you deploy any EVPN fabric, L2VNI, or L3VNI intents you must create at least one VNI Pool:

1. Navigate to **Plugins → Intent Engine → VNI Pools → + Add**
2. Enter a **Name** — this must match the `vni_pool_name` value in `PLUGINS_CONFIG`
3. Add one or more **VNI ranges** (e.g. `10000-19999`)
4. Optionally assign a **Tenant** to scope the pool
5. Click **Create**

VNIs are allocated atomically from these ranges at resolution time. If you do not use VXLAN/EVPN you can skip this step and leave `vni_pool_name` unset.

### Configure Git Integration (Recommended)

The preferred way to sync intent YAML files is via Nautobot's native Git integration:

1. Navigate to **Extensibility → Git Repositories → Add**
2. Enter the repository URL
3. Select the branch (e.g. `main`)
4. Configure credentials via a **Secrets Group** if the repo is private
5. In **Provided Contents**, tick **"intent definitions"**
6. Click **Create** then **Sync**

Nautobot will clone the repo and scan these directories for intent YAML files:

- `intents/`
- `intent_definitions/`
- `intent-definitions/`

## Environment Variables

The following environment variables must be set on the Nautobot worker container:

```bash
NAUTOBOT_TOKEN          # Nautobot API token for internal job calls
NAUTOBOT_URL            # Nautobot base URL (default: http://localhost:8080)
OPA_URL                 # OPA service URL (default: http://opa:8181)
TEMPLATES_DIR           # Path to Jinja2 templates directory
DEVICE_USERNAME         # SSH username — last-resort fallback (see below)
DEVICE_PASSWORD         # SSH password — last-resort fallback (see below)
```

Optional:

```bash
SLACK_WEBHOOK_URL       # Slack notifications on deploy/fail/rollback
GITHUB_TOKEN            # GitHub token for drift issue creation
```

### Credential Lookup Order

Device SSH credentials are resolved in this order for every deployment and verification job:

1. **Per-device SecretsGroup** — if the device record in Nautobot has a SecretsGroup assigned directly (Device detail → *Secrets Group* field), those credentials are used first.
2. **Global `device_secrets_group`** — the SecretsGroup named by `PLUGINS_CONFIG["intent_networking"]["device_secrets_group"]` is used as a fallback for devices without their own group.
3. **Environment variables** — `DEVICE_USERNAME` / `DEVICE_PASSWORD` are the last resort if neither a per-device nor a global SecretsGroup is configured.

!!! tip
    Using per-device or global SecretsGroups is strongly recommended over plaintext environment variables, especially in production.
    SecretsGroups must have their secrets assigned with **Access Type: SSH** and **Secret Type: username / password** — this matches the convention used by `nautobot_plugin_nornir`.
