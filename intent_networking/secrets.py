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


def get_secrets_group_value(group_name: str, access_type: str, secret_type: str) -> str:
    """Retrieve a single secret value from a named Nautobot SecretsGroup.

    Args:
        group_name: Name of the SecretsGroup in Nautobot.
        access_type: SecretsGroup access type (e.g. 'Generic', 'HTTP(S)').
        secret_type: SecretsGroup secret type (e.g. 'username', 'password', 'token', 'secret').

    Returns:
        The secret value string.

    Raises:
        LookupError: If the SecretsGroup or secret is not found.
    """
    from nautobot.extras.models import SecretsGroup  # noqa: PLC0415

    sg = SecretsGroup.objects.get(name=group_name)
    return sg.get_secret_value(
        access_type=access_type,
        secret_type=secret_type,
    )


def get_servicenow_credentials() -> tuple[str, str]:
    """Return (username, password) for ServiceNow integration.

    Lookup order:
      1. Nautobot SecretsGroup named in ``servicenow_secrets_group`` config
      2. Legacy plugin config ``servicenow_user`` / ``servicenow_password`` (deprecated)

    Returns:
        tuple[str, str]: (username, password)
    """
    group_name = _cfg("servicenow_secrets_group")
    if group_name:
        try:
            username = get_secrets_group_value(group_name, "Generic", "username")
            password = get_secrets_group_value(group_name, "Generic", "password")
            logger.debug("ServiceNow credentials loaded from SecretsGroup '%s'", group_name)
            return (username, password)
        except Exception as exc:
            logger.warning(
                "Failed to load ServiceNow credentials from SecretsGroup '%s': %s. "
                "Falling back to plugin config.",
                group_name,
                exc,
            )

    # Legacy fallback — plaintext in PLUGINS_CONFIG (deprecated)
    user = _cfg("servicenow_user")
    password = _cfg("servicenow_password")
    if user and password:
        logger.warning(
            "ServiceNow credentials loaded from PLUGINS_CONFIG (plaintext). "
            "Migrate to 'servicenow_secrets_group' for encrypted storage."
        )
        return (user, password)

    return ("", "")


def get_github_token() -> str:
    """Return the GitHub Personal Access Token.

    Lookup order:
      1. Nautobot SecretsGroup named in ``github_secrets_group`` config
      2. Environment variable ``GITHUB_TOKEN`` (deprecated)

    Returns:
        str: The token, or empty string if not configured.
    """
    group_name = _cfg("github_secrets_group")
    if group_name:
        try:
            token = get_secrets_group_value(group_name, "Generic", "token")
            logger.debug("GitHub token loaded from SecretsGroup '%s'", group_name)
            return token
        except Exception as exc:
            logger.warning(
                "Failed to load GitHub token from SecretsGroup '%s': %s. "
                "Falling back to GITHUB_TOKEN env var.",
                group_name,
                exc,
            )

    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        logger.warning(
            "GitHub token loaded from GITHUB_TOKEN env var. "
            "Migrate to 'github_secrets_group' for encrypted storage."
        )
    return token


def get_slack_webhook_url() -> str:
    """Return the Slack webhook URL.

    Lookup order:
      1. Nautobot SecretsGroup named in ``slack_secrets_group`` config
      2. Plugin config ``slack_webhook_url`` (deprecated)

    Returns:
        str: The webhook URL, or empty string if not configured.
    """
    group_name = _cfg("slack_secrets_group")
    if group_name:
        try:
            url = get_secrets_group_value(group_name, "Generic", "secret")
            logger.debug("Slack webhook URL loaded from SecretsGroup '%s'", group_name)
            return url
        except Exception as exc:
            logger.warning(
                "Failed to load Slack webhook URL from SecretsGroup '%s': %s. "
                "Falling back to plugin config.",
                group_name,
                exc,
            )

    url = _cfg("slack_webhook_url") or ""
    if url:
        logger.warning(
            "Slack webhook URL loaded from PLUGINS_CONFIG (plaintext). "
            "Migrate to 'slack_secrets_group' for encrypted storage."
        )
    return url


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
