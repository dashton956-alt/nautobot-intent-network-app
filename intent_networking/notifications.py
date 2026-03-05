"""Slack notifications and GitHub issue creation for the intent_networking plugin."""

import logging
import os

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_plugin_config(key: str):
    """Retrieve a value from the intent_networking plugin config."""
    return settings.PLUGINS_CONFIG.get("intent_networking", {}).get(key)


def notify_slack(message: str) -> bool:
    """Post a message to the configured Slack webhook.

    Silently succeeds if no webhook is configured.
    """
    webhook_url = _get_plugin_config("slack_webhook_url")
    if not webhook_url:
        return False

    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Slack notification failed: %s", exc)
        return False


def raise_github_issue(intent, drift_details: list) -> str:
    """Create a GitHub issue for drift that requires manual review.

    Returns the issue URL, or empty string if GitHub is not configured.
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo = _get_plugin_config("github_repo")
    api = _get_plugin_config("github_api_url") or "https://api.github.com"

    if not token or not repo:
        logger.warning("GitHub issue creation skipped — GITHUB_TOKEN env var or github_repo plugin config not set.")
        return ""

    failed_checks = [c for c in drift_details if not c.get("passed")]
    body_lines = [
        f"## Drift Detected: `{intent.intent_id}`",
        "",
        f"**Tenant:** {intent.tenant.name}",
        f"**Intent version:** {intent.version}",
        f"**Status:** {intent.status}",
        "",
        "### Failed Checks",
        "",
    ]
    for check in failed_checks:
        body_lines.append(f"- **{check.get('device', 'network')}** — `{check['check']}`: {check['detail']}")

    body_lines += [
        "",
        "### Action Required",
        "Review the above drift and either:",
        "1. Re-deploy the intent to restore the desired state, or",
        "2. Update the intent YAML to reflect the new desired state (PR required)",
        "",
        f"Intent in Nautobot: `/plugins/intent-networking/intents/?intent_id={intent.intent_id}`",
    ]

    payload = {
        "title": f"[Intent Drift] {intent.intent_id} — manual review required",
        "body": "\n".join(body_lines),
        "labels": ["intent-drift", "network-automation"],
    }

    try:
        resp = requests.post(
            f"{api}/repos/{repo}/issues",
            json=payload,
            headers={"Authorization": f"token {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        url = resp.json().get("html_url", "")
        logger.info("GitHub issue created for drift: %s", url)
        return url
    except Exception as exc:
        logger.error("Failed to create GitHub issue for drift: %s", exc)
        return ""
