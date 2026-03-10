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
    home_view_name = "plugins:intent_networking:dashboard"

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
        """Import jobs and job buttons so Nautobot discovers them at startup.

        super().ready() auto-discovers jobs.py via the `jobs = "jobs.jobs"`
        attribute and calls register_jobs() at import time. Job buttons live
        in a separate module and must be imported explicitly.
        """
        super().ready()
        import intent_networking.job_buttons  # noqa: F401  pylint:disable=unused-import,import-outside-toplevel

        self._ensure_reconciliation_schedule()

    @staticmethod
    def _ensure_reconciliation_schedule():
        """Create a default hourly schedule for IntentReconciliationJob if one does not exist.

        Uses a post-migrate-safe check; silently skips if database tables
        are not ready yet (e.g. during initial migration).
        """
        try:
            from django.conf import settings  # noqa: PLC0415
            from nautobot.extras.models import Job as JobModel  # noqa: PLC0415

            interval_hours = settings.PLUGINS_CONFIG.get("intent_networking", {}).get(
                "reconciliation_interval_hours", 1
            )

            job_model = JobModel.objects.filter(
                module_name="intent_networking.jobs",
                job_class_name="IntentReconciliationJob",
            ).first()

            if not job_model:
                return  # Job not registered yet — will run on next startup

            from nautobot.extras.models import ScheduledJob  # noqa: PLC0415

            if not ScheduledJob.objects.filter(
                name="Intent Reconciliation (auto)",
                task=job_model.class_path,
            ).exists():
                import json  # noqa: PLC0415

                from django.utils import timezone  # noqa: PLC0415

                ScheduledJob.objects.create(
                    name="Intent Reconciliation (auto)",
                    task=job_model.class_path,
                    interval="hours",
                    every=interval_hours,
                    start_time=timezone.now(),
                    kwargs=json.dumps({}),
                )
        except Exception:  # noqa: BLE001, S110
            # Gracefully handle missing tables during initial migration
            pass


config = IntentNetworkingConfig  # pylint:disable=invalid-name
