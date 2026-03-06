"""App declaration for intent_networking."""

# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

try:
    __version__ = metadata.version("nautobot-app-intent-networking")
except metadata.PackageNotFoundError:
    # Fallback for environments where package metadata isn't installed.
    __version__ = "0.0.0"


class IntentNetworkingConfig(NautobotAppConfig):
    """App configuration for the intent_networking app."""

    name = "intent_networking"
    verbose_name = "Intent Networking"
    version = __version__
    author = "Daniel Ashton"
    description = (
        "IBNaaS intent lifecycle management — stores, resolves, deploys "
        "and continuously verifies network intents expressed as YAML."
    )
    base_url = "intent-networking"

    # ── Settings ──────────────────────────────────────────────────────────
    default_settings = {
        # Resource allocation pools (must match names in Nautobot)
        "rd_pool_name": "default-rd-pool",
        "rt_pool_name": "default-rt-pool",
        # BGP
        "default_bgp_asn": 65000,
        # Capacity limits
        "max_vrfs_per_tenant": 50,
        "max_prefixes_per_vrf": 5000,
        # Reconciliation
        "reconciliation_interval_hours": 1,
        "auto_remediation_enabled": True,
        # Notifications (optional)
        "slack_webhook_url": None,
        "github_api_url": None,
        "github_repo": None,
        "github_token_env_var": "GITHUB_TOKEN",
    }

    # These MUST be set in nautobot_config.py — startup fails if missing
    required_settings = [
        "rd_pool_name",
        "default_bgp_asn",
    ]

    docs_view_name = "plugins:intent_networking:docs"
    searchable_models = ["intent"]

    def ready(self):
        """Called when the app is ready; import jobs to register them."""
        super().ready()
        # Import jobs module to register all Job classes with Nautobot
        from . import jobs  # noqa: F401 pylint:disable=unused-import


config = IntentNetworkingConfig  # pylint:disable=invalid-name
