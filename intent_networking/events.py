"""Webhook / event dispatch for the intent_networking plugin (#8).

Provides a generic event system that fans out to multiple targets:
  - Slack (existing)
  - PagerDuty
  - ServiceNow
  - Generic webhook (any HTTP endpoint)

Events are fired from jobs and API views. Each event carries a type,
an intent reference, and a payload dict.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# Event types
# ────────────────────────────────────────────────────────────────────────────

EVENT_INTENT_CREATED = "intent.created"
EVENT_INTENT_RESOLVED = "intent.resolved"
EVENT_INTENT_APPROVED = "intent.approved"
EVENT_INTENT_REJECTED = "intent.rejected"
EVENT_INTENT_DEPLOYED = "intent.deployed"
EVENT_INTENT_FAILED = "intent.failed"
EVENT_INTENT_VERIFIED = "intent.verified"
EVENT_INTENT_DRIFT = "intent.drift_detected"
EVENT_INTENT_ROLLED_BACK = "intent.rolled_back"
EVENT_INTENT_CONFLICT = "intent.conflict_detected"
EVENT_INTENT_SCHEDULED = "intent.scheduled"

ALL_EVENTS = [
    EVENT_INTENT_CREATED,
    EVENT_INTENT_RESOLVED,
    EVENT_INTENT_APPROVED,
    EVENT_INTENT_REJECTED,
    EVENT_INTENT_DEPLOYED,
    EVENT_INTENT_FAILED,
    EVENT_INTENT_VERIFIED,
    EVENT_INTENT_DRIFT,
    EVENT_INTENT_ROLLED_BACK,
    EVENT_INTENT_CONFLICT,
    EVENT_INTENT_SCHEDULED,
]


def _cfg(key: str):
    """Retrieve a value from the plugin config."""
    return settings.PLUGINS_CONFIG.get("intent_networking", {}).get(key)


# ────────────────────────────────────────────────────────────────────────────
# Dispatch
# ────────────────────────────────────────────────────────────────────────────


def dispatch_event(event_type: str, intent=None, payload=None):
    """Fan out an event to all configured targets.

    Args:
        event_type: One of the EVENT_* constants.
        intent: Intent model instance (optional for system-level events).
        payload: dict with event-specific data.
    """
    payload = payload or {}
    event = {
        "event": event_type,
        "intent_id": intent.intent_id if intent else None,
        "tenant": intent.tenant.name if intent and intent.tenant else None,
        "status": str(intent.status) if intent else None,
        "payload": payload,
    }

    _send_slack(event)
    _send_pagerduty(event)
    _send_servicenow(event)
    _send_generic_webhooks(event)


# ────────────────────────────────────────────────────────────────────────────
# Targets
# ────────────────────────────────────────────────────────────────────────────


def _send_slack(event: dict):
    """Post to Slack webhook if configured."""
    url = _cfg("slack_webhook_url")
    if not url:
        return

    emoji = {
        EVENT_INTENT_DEPLOYED: "✅",
        EVENT_INTENT_FAILED: "❌",
        EVENT_INTENT_DRIFT: "⚠️",
        EVENT_INTENT_ROLLED_BACK: "↩️",
        EVENT_INTENT_APPROVED: "👍",
        EVENT_INTENT_REJECTED: "👎",
        EVENT_INTENT_CONFLICT: "⚡",
    }.get(event["event"], "ℹ️")

    text = f"{emoji} *{event['event']}*"
    if event.get("intent_id"):
        text += f" — `{event['intent_id']}`"
    if event.get("tenant"):
        text += f" (tenant: {event['tenant']})"
    detail = event.get("payload", {}).get("detail", "")
    if detail:
        text += f"\n{detail}"

    try:
        requests.post(url, json={"text": text}, timeout=10)
    except Exception as exc:
        logger.warning("Slack dispatch failed: %s", exc)


def _send_pagerduty(event: dict):
    """Send a PagerDuty event if configured.

    Only fires for failure / drift events — no point paging humans for
    successes.
    """
    routing_key = _cfg("pagerduty_routing_key")
    if not routing_key:
        return

    severity_map = {
        EVENT_INTENT_FAILED: "error",
        EVENT_INTENT_DRIFT: "warning",
        EVENT_INTENT_CONFLICT: "warning",
    }
    severity = severity_map.get(event["event"])
    if not severity:
        return  # Only page for failures

    pd_payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "payload": {
            "summary": f"Intent {event.get('intent_id', 'unknown')}: {event['event']}",
            "severity": severity,
            "source": "nautobot-intent-networking",
            "custom_details": event.get("payload", {}),
        },
    }

    try:
        requests.post(
            "https://events.pagerduty.com/v2/enqueue",
            json=pd_payload,
            timeout=10,
        )
    except Exception as exc:
        logger.warning("PagerDuty dispatch failed: %s", exc)


def _send_servicenow(event: dict):
    """Create a ServiceNow incident / change record if configured."""
    instance = _cfg("servicenow_instance")
    user = _cfg("servicenow_user")
    password = _cfg("servicenow_password")

    if not all([instance, user, password]):
        return

    sn_payload = {
        "short_description": f"Intent {event.get('intent_id', 'unknown')}: {event['event']}",
        "description": str(event.get("payload", {})),
        "urgency": "2",
        "category": "Network",
    }

    try:
        requests.post(
            f"https://{instance}.service-now.com/api/now/table/incident",
            json=sn_payload,
            auth=(user, password),
            timeout=15,
        )
    except Exception as exc:
        logger.warning("ServiceNow dispatch failed: %s", exc)


def _send_generic_webhooks(event: dict):
    """POST the event payload to any configured generic webhook URLs.

    Plugin config: ``webhook_urls`` — list of URL strings.
    """
    urls = _cfg("webhook_urls") or []
    for url in urls:
        try:
            requests.post(url, json=event, timeout=10)
        except Exception as exc:
            logger.warning("Webhook dispatch to %s failed: %s", url, exc)
