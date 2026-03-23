"""Nautobot development configuration file."""

import os
import sys

from nautobot.core.settings import *  # noqa: F403  # pylint: disable=wildcard-import,unused-wildcard-import
from nautobot.core.settings_funcs import is_truthy

#
# Debug
#

DEBUG = is_truthy(os.getenv("NAUTOBOT_DEBUG", "false"))
_TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

if DEBUG and not _TESTING:
    DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda _request: True}

    if "debug_toolbar" not in INSTALLED_APPS:  # noqa: F405
        INSTALLED_APPS.append("debug_toolbar")  # noqa: F405
    if "debug_toolbar.middleware.DebugToolbarMiddleware" not in MIDDLEWARE:  # noqa: F405
        MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

#
# Misc. settings
#

ALLOWED_HOSTS = os.getenv("NAUTOBOT_ALLOWED_HOSTS", "").split(" ")
SECRET_KEY = os.getenv("NAUTOBOT_SECRET_KEY", "")

#
# Database
#

nautobot_db_engine = os.getenv("NAUTOBOT_DB_ENGINE", "django.db.backends.postgresql")
default_db_settings = {
    "django.db.backends.postgresql": {
        "NAUTOBOT_DB_PORT": "5432",
    },
    "django.db.backends.mysql": {
        "NAUTOBOT_DB_PORT": "3306",
    },
}
DATABASES = {
    "default": {
        "NAME": os.getenv("NAUTOBOT_DB_NAME", "nautobot"),  # Database name
        "USER": os.getenv("NAUTOBOT_DB_USER", ""),  # Database username
        "PASSWORD": os.getenv("NAUTOBOT_DB_PASSWORD", ""),  # Database password
        "HOST": os.getenv("NAUTOBOT_DB_HOST", "localhost"),  # Database server
        "PORT": os.getenv(
            "NAUTOBOT_DB_PORT", default_db_settings[nautobot_db_engine]["NAUTOBOT_DB_PORT"]
        ),  # Database port, default to postgres
        "CONN_MAX_AGE": int(os.getenv("NAUTOBOT_DB_TIMEOUT", "300")),  # Database timeout
        "ENGINE": nautobot_db_engine,
    }
}

# Ensure proper Unicode handling for MySQL
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    DATABASES["default"]["OPTIONS"] = {"charset": "utf8mb4"}

#
# Redis
#

# The django-redis cache is used to establish concurrent locks using Redis.
# Inherited from nautobot.core.settings
# CACHES = {....}

#
# Celery settings are not defined here because they can be overloaded with
# environment variables. By default they use `CACHES["default"]["LOCATION"]`.
#

#
# Logging
#

LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

# Verbose logging during normal development operation, but quiet logging during unit test execution
if not _TESTING:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "normal": {
                "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s : %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "verbose": {
                "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-20s %(filename)-15s %(funcName)30s() : %(message)s",
                "datefmt": "%H:%M:%S",
            },
        },
        "handlers": {
            "normal_console": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "normal",
            },
            "verbose_console": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
        },
        "loggers": {
            "django": {"handlers": ["normal_console"], "level": "INFO"},
            "nautobot": {
                "handlers": ["verbose_console" if DEBUG else "normal_console"],
                "level": LOG_LEVEL,
            },
        },
    }

#
# Apps
#

# Enable installed Apps. Add the name of each App to the list.
PLUGINS = ["intent_networking"]

# Apps configuration settings. These settings are used by various Apps that the user may have installed.
# Each key in the dictionary is the name of an installed App and its value is a dictionary of settings.
PLUGINS_CONFIG = {
    "intent_networking": {
        # --- Required settings ---
        "vrf_namespace": "Global",
        "default_bgp_asn": 65000,
        # --- Optional settings (shown with their defaults) ---
        "max_vrfs_per_tenant": 100,
        "max_prefixes_per_vrf": 500,
        "reconciliation_interval_hours": 6,
        "auto_remediation_enabled": False,
        # --- Secrets Group integration (recommended over plaintext) ---
        # Each setting names a Nautobot SecretsGroup. Create the SecretsGroup
        # in Nautobot (Secrets → Secrets Groups) then reference its name here.
        "device_secrets_group": "Network Device Credentials",
        "nautobot_api_secrets_group": "Nautobot API Token",
        # "servicenow_secrets_group": "ServiceNow Credentials",
        # "github_secrets_group": "GitHub Token",
        # "slack_secrets_group": "Slack Webhook",
        # --- Legacy plaintext config (deprecated — migrate to Secrets Groups) ---
        # Slack webhook URL for drift notifications (leave empty to disable)
        "slack_webhook_url": "",
        # ServiceNow integration (deprecated — use servicenow_secrets_group)
        # "servicenow_instance": "",
        # "servicenow_user": "",
        # "servicenow_password": "",
        # GitHub integration for raising drift issues (leave empty to disable)
        "github_token": "",
        "github_repo": "your-org/your-repo",
        # --- OPA policy engine settings ---
        # "opa_verify_ssl": True,
        # "opa_ca_bundle": "/path/to/ca-bundle.crt",
        # Custom OPA policy packages evaluated for every intent:
        # "opa_custom_packages": ["org.security.baseline", "org.compliance.pci"],
        # Git integration — the preferred approach is to create a GitRepository
        # in the Nautobot UI (Extensibility → Git Repositories) with the
        # "intent definitions" content type. Nautobot will auto-discover and
        # sync intent YAML files from the repository on every pull.
        # The directories searched inside the repo are:
        #   intents/  |  intent_definitions/  |  intent-definitions/
    }
}
