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
        "vrf_namespace": "Global",       # Nautobot IPAM Namespace for VRF allocation
        "default_bgp_asn": 65000,        # ASN used in RD/RT values (e.g. 65000:1)

        # --- Optional (shown with defaults) ---
        "max_vrfs_per_tenant": 50,
        "max_prefixes_per_vrf": 5000,
        "reconciliation_interval_hours": 1,
        "auto_remediation_enabled": True,

        # Notifications — Slack (leave None to disable)
        "slack_webhook_url": None,

        # GitHub issue creation for non-remediable drift
        "github_api_url": None,          # defaults to https://api.github.com
        "github_repo": None,             # e.g. "your-org/network-as-code"
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

### Optional Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_vrfs_per_tenant` | `int` | `50` | Maximum VRFs that can be allocated per tenant |
| `max_prefixes_per_vrf` | `int` | `5000` | Maximum prefix count per VRF |
| `reconciliation_interval_hours` | `int` | `1` | How often the reconciliation job runs (hours) |
| `auto_remediation_enabled` | `bool` | `True` | Whether drift auto-remediation is enabled (requires OPA approval) |
| `slack_webhook_url` | `str` | `None` | Slack incoming webhook URL for deployment/rollback notifications |
| `github_api_url` | `str` | `None` | GitHub API base URL (defaults to `https://api.github.com`) |
| `github_repo` | `str` | `None` | GitHub repository for drift issue creation (e.g. `"your-org/network-as-code"`) |
| `github_token_env_var` | `str` | `"GITHUB_TOKEN"` | Environment variable name containing the GitHub token |
| `pagerduty_routing_key` | `str` | `None` | PagerDuty Events API routing key for critical alerts |
| `servicenow_instance` | `str` | `None` | ServiceNow instance URL |
| `servicenow_user` | `str` | `None` | ServiceNow API username |
| `servicenow_password` | `str` | `None` | ServiceNow API password |
| `webhook_urls` | `list` | `[]` | Additional webhook URLs for event notifications |
| `device_secrets_group` | `str` | `None` | Nautobot Secrets Group name for device SSH credentials |
| `nautobot_api_secrets_group` | `str` | `None` | Nautobot Secrets Group name for API tokens |

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

### Ensure a Namespace Exists

The app allocates VRFs within a Nautobot IPAM Namespace. Nautobot creates a `"Global"` namespace by default, which the app uses unless you override `vrf_namespace` in the configuration.

To verify:

1. Navigate to **IPAM → Namespaces**
2. Confirm the `"Global"` namespace exists (or whichever name you configured)

!!! note
    Route Distinguishers and Route Targets are allocated using Nautobot's native IPAM models (`ipam.VRF` and `ipam.RouteTarget`) and no longer require custom pool configuration. The app auto-generates RD/RT values in `<ASN>:<counter>` format within the configured Namespace.

### Create Resource Pools (Optional)

If your intents require VXLAN VNI, Tunnel ID, Loopback IP, or Wireless VLAN allocation, create the relevant pools via the Nautobot UI under **Intent Networking → Resource Pools**.

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
