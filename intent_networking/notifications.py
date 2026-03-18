"""Slack notifications and GitHub issue creation for the intent_networking plugin."""

import logging

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
    from intent_networking.secrets import get_slack_webhook_url  # noqa: PLC0415

    webhook_url = get_slack_webhook_url()
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
    from intent_networking.secrets import get_github_token  # noqa: PLC0415

    token = get_github_token()
    repo = _get_plugin_config("github_repo")
    api = _get_plugin_config("github_api_url") or "https://api.github.com"

    if not token or not repo:
        logger.warning("GitHub issue creation skipped — GitHub token or github_repo plugin config not set.")
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


def backup_verification_to_git(intent, verification_result) -> bool:
    """Commit a pyATS verification report to the intent's Git repository.

    Creates a Markdown file at ``verification-results/<intent_id>/<timestamp>.md``
    in the repository, similar to how golden-config backs up device configs.

    Returns True if the commit succeeded.
    """
    import base64  # noqa: PLC0415

    from intent_networking.secrets import get_github_token  # noqa: PLC0415

    token = get_github_token()
    repo = _get_plugin_config("github_repo")
    api = _get_plugin_config("github_api_url") or "https://api.github.com"
    branch = _get_plugin_config("verification_backup_branch") or "main"

    if not token or not repo:
        logger.debug("Git backup skipped — no GitHub token or repo configured.")
        return False

    report = _render_verification_report(intent, verification_result)
    timestamp = verification_result.verified_at.strftime("%Y%m%d-%H%M%S")
    path = f"verification-results/{intent.intent_id}/{timestamp}.md"

    try:
        resp = requests.put(
            f"{api}/repos/{repo}/contents/{path}",
            json={
                "message": (
                    f"verification: {intent.intent_id} "
                    f"{'PASS' if verification_result.passed else 'FAIL'} "
                    f"({verification_result.verification_engine})"
                ),
                "content": base64.b64encode(report.encode()).decode(),
                "branch": branch,
            },
            headers={"Authorization": f"token {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Verification report backed up to git: %s", path)
        return True
    except Exception as exc:
        logger.error("Failed to back up verification report to git: %s", exc)
        return False


def _render_verification_report(intent, vr):
    """Render a human-readable Markdown report for a VerificationResult."""
    status = "PASS" if vr.passed else "FAIL"
    engine_label = vr.verification_engine.title()
    lines = [
        f"# Verification Report: `{intent.intent_id}`",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Intent** | `{intent.intent_id}` |",
        f"| **Version** | {intent.version} |",
        f"| **Tenant** | {intent.tenant.name if intent.tenant else '—'} |",
        f"| **Type** | {intent.get_intent_type_display()} |",
        f"| **Status** | {intent.status} |",
        f"| **Result** | {'✅' if vr.passed else '❌'} **{status}** |",
        f"| **Engine** | {engine_label} |",
        f"| **Triggered by** | {vr.triggered_by} |",
        f"| **Verified at** | {vr.verified_at:%Y-%m-%d %H:%M:%S UTC} |",
        "",
    ]

    if vr.escalation_reason:
        lines += [
            "## Escalation",
            "",
            f"> {vr.escalation_reason}",
            "",
        ]

    if vr.measured_latency_ms is not None:
        lines += [f"**Measured latency:** {vr.measured_latency_ms} ms", ""]

    # Checks table
    checks = vr.checks if isinstance(vr.checks, list) else []
    if checks:
        lines += [
            "## Check Results",
            "",
            "| # | Device | Check | Result | Detail |",
            "|---|--------|-------|--------|--------|",
        ]
        for i, c in enumerate(checks, 1):
            result_icon = "✅" if c.get("passed") else "❌"
            device = c.get("device", "—")
            check_name = c.get("check", c.get("check_name", "—"))
            detail = c.get("detail", "—")
            lines.append(f"| {i} | `{device}` | {check_name} | {result_icon} | {detail} |")
        lines.append("")

    # pyATS diff output
    if vr.pyats_diff_output:
        lines += [
            "## pyATS Diff Output",
            "",
            "```",
            vr.pyats_diff_output,
            "```",
            "",
        ]

    # Drift details
    if vr.drift_details:
        lines += [
            "## Drift Details",
            "",
        ]
        for device_name, diff in vr.drift_details.items():
            lines += [
                f"### `{device_name}`",
                "",
                "```diff",
                str(diff),
                "```",
                "",
            ]

    lines += [
        "---",
        f"*Generated by Intent Networking App — {vr.verified_at:%Y-%m-%d %H:%M:%S}*",
    ]
    return "\n".join(lines)
