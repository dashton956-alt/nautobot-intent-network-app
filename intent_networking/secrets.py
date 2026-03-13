"""Secrets integration for the intent_networking plugin (#5).

Replaces plain environment variable credentials with Nautobot's native
Secrets framework. This allows credentials to be stored in:
  - Nautobot's encrypted database (built-in)
  - HashiCorp Vault (via nautobot-secrets-providers)
  - AWS Secrets Manager (via nautobot-secrets-providers)
  - CyberArk (via nautobot-secrets-providers)
  - Any other registered SecretsProvider

Usage:
  get_device_credentials() returns (username, password) by looking up
  the SecretsGroup named in plugin config ``device_secrets_group``.
"""

import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)


def _cfg(key: str, default=None):
    """Retrieve a value from the intent_networking plugin config."""
    return settings.PLUGINS_CONFIG.get("intent_networking", {}).get(key, default)


def get_device_credentials():
    """Return (username, password) for device access.

    Lookup order:
      1. Nautobot SecretsGroup named in ``device_secrets_group`` config
      2. Environment variables ``DEVICE_USERNAME`` / ``DEVICE_PASSWORD`` (legacy fallback)

    Returns:
        tuple[str, str]: (username, password)

    Raises:
        RuntimeError: If no credentials are available from any source.
    """
    # 1. Try Nautobot Secrets framework
    group_name = _cfg("device_secrets_group")
    if group_name:
        try:
            from nautobot.extras.models import SecretsGroup  # noqa: PLC0415

            sg = SecretsGroup.objects.get(name=group_name)
            username = sg.get_secret_value(
                access_type="Generic",
                secret_type="username",  # noqa: S106
            )
            password = sg.get_secret_value(
                access_type="Generic",
                secret_type="password",  # noqa: S106
            )
            logger.debug("Device credentials loaded from SecretsGroup '%s'", group_name)
            return (username, password)
        except Exception as exc:
            logger.warning(
                "Failed to load credentials from SecretsGroup '%s': %s. Falling back to environment variables.",
                group_name,
                exc,
            )

    # 2. Legacy fallback — environment variables
    username = os.environ.get("DEVICE_USERNAME", "")
    password = os.environ.get("DEVICE_PASSWORD", "")

    if not username or not password:
        if settings.DEBUG:
            logger.warning(
                "No device credentials configured; using debug fallback credentials (admin/admin). "
                "Set DEVICE_USERNAME/DEVICE_PASSWORD or configure device_secrets_group for non-lab usage."
            )
            return ("admin", "admin")

        raise RuntimeError(
            "No device credentials available. Either:\n"
            "  1. Configure 'device_secrets_group' in PLUGINS_CONFIG to use Nautobot Secrets, or\n"
            "  2. Set DEVICE_USERNAME and DEVICE_PASSWORD environment variables."
        )

    logger.warning(
        "Using environment variable credentials. Consider migrating to "
        "Nautobot Secrets (configure 'device_secrets_group' in PLUGINS_CONFIG)."
    )
    return (username, password)


def get_nautobot_token():
    """Return the Nautobot API token via Secrets or env var.

    Lookup order:
      1. Nautobot SecretsGroup named ``nautobot_api_secrets_group``
      2. Environment variable ``NAUTOBOT_TOKEN``
    """
    group_name = _cfg("nautobot_api_secrets_group")
    if group_name:
        try:
            from nautobot.extras.models import SecretsGroup  # noqa: PLC0415

            sg = SecretsGroup.objects.get(name=group_name)
            return sg.get_secret_value(
                access_type="Generic",
                secret_type="token",  # noqa: S106
            )
        except Exception as exc:
            logger.warning(
                "Failed to load API token from SecretsGroup '%s': %s",
                group_name,
                exc,
            )

    token = os.environ.get("NAUTOBOT_TOKEN")
    if not token:
        raise RuntimeError(
            "NAUTOBOT_TOKEN not set. Configure 'nautobot_api_secrets_group' "
            "or set the NAUTOBOT_TOKEN environment variable."
        )
    return token
