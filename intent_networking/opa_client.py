"""OPA integration for the Nautobot intent_networking plugin.

The plugin calls OPA at two points:
  1. During resolution — check policy before allocating resources
  2. During reconciliation — check if drift is auto-remediable

OPA still runs as a separate service (sidecar or standalone container).
The plugin calls it via HTTP, same as the CI pipeline does.

Custom Policies
───────────────
Users can add custom OPA policy packages in three ways:

1. **Per-tenant policies** — Automatically queried if they exist.
   Package: ``network.customers.<tenant_slug>``
   Example: ``network.customers.acme_corp``

2. **Per-intent-type policies** — Automatically queried if they exist.
   Package: ``network.intent_types.<intent_type>``
   Example: ``network.intent_types.fw_rule``

3. **Custom policy packages** — Configured via plugin config:
   ``PLUGINS_CONFIG["intent_networking"]["opa_custom_packages"]``
   A list of OPA package names to query for every intent evaluation.
   Example: ``["org.security.baseline", "org.compliance.pci"]``

All custom policies must return a ``deny`` set. If any ``deny`` rule
fires, the intent resolution is blocked.

Example OPA policy (Rego):
    package network.customers.acme_corp

    deny["ACME tenants require a change_ticket"] {
        not input.metadata.change_ticket
    }

    deny["Max 2 BGP peers per VRF for ACME"] {
        input.intent.type == "bgp_ebgp"
        count(input.intent.neighbors) > 2
    }
"""

import logging
import os

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OPA_URL = os.environ.get("OPA_URL", "https://opa:8181")


def _plugin_cfg(key: str, default=None):
    """Retrieve a value from the intent_networking plugin config."""
    return settings.PLUGINS_CONFIG.get("intent_networking", {}).get(key, default)


def check_intent_policy(intent, topology_context: dict) -> dict:
    """Run OPA policy checks on an intent before resolution.

    Called by IntentResolutionJob before allocating any resources.
    If OPA returns any deny reasons, resolution is aborted.

    Returns:
        {
            "allowed": True/False,
            "violations": ["violation message", ...]
        }
    """
    tenant_slug = intent.tenant.slug

    input_data = {
        "input": {
            "intent": intent.intent_data,
            "topology": topology_context,
            "tenant": tenant_slug,
            "metadata": {
                "intent_id": intent.intent_id,
                "version": intent.version,
                "change_ticket": intent.change_ticket,
                "approved_by": intent.approved_by,
            },
        }
    }

    violations = []

    # Common policies
    for package in ["network.common", "network.compliance", "network.capacity"]:
        result = _query_opa(package, input_data)
        if result:
            violations.extend(result.get("deny", []))

    # Customer-specific policy (if it exists)
    customer_package = f"network.customers.{tenant_slug.replace('-', '_')}"
    result = _query_opa(customer_package, input_data)
    if result:
        violations.extend(result.get("deny", []))

    # Per-intent-type policy (if it exists)
    intent_type = intent.intent_type
    if intent_type:
        type_package = f"network.intent_types.{intent_type.replace('-', '_')}"
        result = _query_opa(type_package, input_data)
        if result:
            violations.extend(result.get("deny", []))

    # User-configured custom policy packages
    custom_packages = _plugin_cfg("opa_custom_packages", [])
    for package in custom_packages:
        result = _query_opa(package, input_data)
        if result:
            violations.extend(result.get("deny", []))

    return {
        "allowed": len(violations) == 0,
        "violations": violations,
    }


def check_auto_remediation(intent, verify_result: dict) -> bool:
    """Ask OPA if this drift is safe to auto-remediate.

    Returns True if auto-remediation is approved, False if manual review needed.
    """
    input_data = {
        "input": {
            "intent": intent.intent_data,
            "verify_result": verify_result,
            "drift_type": _classify_drift(verify_result),
        }
    }

    result = _query_opa("network.remediation", input_data)
    if not result:
        return False

    return result.get("auto_remediate", False)


def _query_opa(package: str, input_data: dict) -> dict:
    """Query an OPA policy package.

    Package name e.g. "network.common" maps to OPA URL path
    /v1/data/network/common
    """
    path = package.replace(".", "/")
    url = f"{OPA_URL}/v1/data/{path}"

    try:
        verify = _plugin_cfg("opa_verify_ssl", True)
        ca_bundle = _plugin_cfg("opa_ca_bundle")
        resp = requests.post(url, json=input_data, timeout=10, verify=ca_bundle or verify)
        if resp.status_code == 404:
            # Package doesn't exist — not an error, just no policy
            return {}
        resp.raise_for_status()
        return resp.json().get("result", {})
    except requests.exceptions.ConnectionError:
        logger.error(
            "Cannot connect to OPA at %s. Check OPA_URL environment variable and that OPA is running.",
            OPA_URL,
        )
        return {}
    except Exception as exc:
        logger.error("OPA query failed for %s: %s", package, exc)
        return {}


def _classify_drift(verify_result: dict) -> str:
    """Classify drift type for OPA remediation decision."""
    failed = [c for c in verify_result.get("checks", []) if not c.get("passed")]
    if not failed:
        return "none"
    check_names = {c["check"] for c in failed}
    if check_names == {"vrf_present"}:
        return "vrf_missing"
    if check_names == {"bgp_established"}:
        return "bgp_down"
    if check_names <= {"bgp_established", "prefix_count"}:
        return "routing_issue"
    return "complex"
