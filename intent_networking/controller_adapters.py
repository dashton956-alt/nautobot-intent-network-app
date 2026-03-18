"""Controller adapter abstraction layer for intent_networking.

Some intent domains (wireless, SD-WAN, cloud) cannot be deployed via
Nornir + Netmiko SSH because the actual configuration lives on a central
controller or cloud API, not on individual network devices.

This module provides:
  1. ``ControllerAdapter`` — abstract base class
  2. ``WirelessControllerAdapter`` — Cisco WLC / Aruba Central / generic
  3. ``SdWanControllerAdapter`` — Cisco vManage / generic SD-WAN
  4. ``CloudAdapter`` — AWS / Azure / GCP cloud API abstraction

Design rules:
  - Each adapter receives **vendor-neutral primitives** produced by the
    resolvers — never raw CLI.
  - Adapters translate primitives into controller-specific API calls.
  - Adapter implementations are **pluggable** — the factory function
    ``get_adapter()`` reads the plugin config to decide which concrete
    adapter class to instantiate.
  - All adapters are idempotent: calling push() twice with the same
    primitives must produce the same result.
  - All adapters support ``push()``, ``verify()``, and ``rollback()``.
"""

import abc
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_plugin_config(key: str, default=None):
    """Read a value from PLUGINS_CONFIG['intent_networking']."""
    return settings.PLUGINS_CONFIG.get("intent_networking", {}).get(key, default)


# ---------------------------------------------------------------------------
# Abstract Base
# ---------------------------------------------------------------------------


class ControllerAdapter(abc.ABC):
    """Abstract base class for controller / cloud adapters.

    Every adapter wraps a single controller endpoint and exposes three
    lifecycle methods that mirror the intent deployment pipeline:

        push()      — apply the primitives to the controller
        verify()    — confirm the expected state is present
        rollback()  — remove the primitives from the controller
    """

    def __init__(self, controller_url: str, credentials: dict | None = None, **kwargs):
        """Initialise the adapter with a controller URL and optional credentials."""
        self.controller_url = controller_url.rstrip("/")
        self.credentials = credentials or {}
        self.extra = kwargs
        self._session = None
        logger.info("Adapter %s targeting %s", self.__class__.__name__, self.controller_url)

    # ----- abstract methods -----

    @abc.abstractmethod
    def push(self, primitives: list[dict], intent_id: str) -> dict:
        """Push primitives to the controller.

        Args:
            primitives: list of vendor-neutral primitive dicts from a resolver
            intent_id:  the intent identifier (for audit/tagging on the controller)

        Returns:
            dict with at least ``{"success": bool, "details": str | dict}``
        """

    @abc.abstractmethod
    def verify(self, primitives: list[dict], intent_id: str) -> dict:
        """Verify that the primitives are currently active on the controller.

        Returns:
            dict with ``{"verified": bool, "drift": list[str], "details": ...}``
        """

    @abc.abstractmethod
    def rollback(self, primitives: list[dict], intent_id: str) -> dict:
        """Remove / undo the primitives on the controller.

        Returns:
            dict with ``{"success": bool, "details": str | dict}``
        """

    # ----- optional lifecycle hooks -----

    def connect(self):
        """Establish a session to the controller.  Override in subclasses."""
        logger.debug("connect() not implemented for %s", self.__class__.__name__)

    def disconnect(self):
        """Close the controller session.  Override in subclasses."""
        logger.debug("disconnect() not implemented for %s", self.__class__.__name__)

    def __enter__(self):
        """Enter the context manager and connect to the controller."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager and disconnect from the controller."""
        self.disconnect()
        return False


# ---------------------------------------------------------------------------
# Wireless Controller Adapter
# ---------------------------------------------------------------------------


class WirelessControllerAdapter(ControllerAdapter):
    """Adapter for centrally-managed wireless controllers.

    Supports Cisco WLC (AireOS & IOS-XE WLC), Aruba Central, and a
    generic REST-based wireless controller.

    Plugin config keys used:
        ``wireless_controller_url``   — e.g. ``https://wlc.example.com``
        ``wireless_controller_type``  — ``cisco_wlc`` | ``aruba_central`` | ``generic``
        ``wireless_controller_creds`` — dict with ``username`` / ``password`` / ``token``
    """

    PRIMITIVE_TYPES = frozenset(
        {
            "wireless_ssid",
            "wireless_vlan_map",
            "wireless_dot1x",
            "wireless_guest",
            "wireless_rf",
            "wireless_qos",
            "wireless_band_steer",
            "wireless_roam",
            "wireless_segment",
            "wireless_mesh",
            "wireless_flexconnect",
        }
    )

    def push(self, primitives: list[dict], intent_id: str) -> dict:
        """Push wireless primitives to the controller.

        Translates each primitive to the appropriate controller API call.
        """
        results = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                logger.warning("Skipping non-wireless primitive '%s'", ptype)
                continue

            logger.info(
                "[%s] Pushing %s to %s (intent=%s)",
                self.__class__.__name__,
                ptype,
                self.controller_url,
                intent_id,
            )

            # --- Concrete API calls go here per controller_type ---
            # This is the integration point.  Subclass or use if/elif
            # branches for cisco_wlc vs aruba_central vs generic.
            result = self._dispatch_push(ptype, prim, intent_id)
            results.append(result)

        success = all(r.get("ok") for r in results)
        return {
            "success": success,
            "details": results,
        }

    def verify(self, primitives: list[dict], intent_id: str) -> dict:
        """Verify wireless primitives are present on the controller."""
        drift: list[str] = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            if not self._check_present(ptype, prim, intent_id):
                drift.append(f"{ptype} missing on controller for intent {intent_id}")
        return {
            "verified": len(drift) == 0,
            "drift": drift,
            "details": f"Checked {len(primitives)} primitives",
        }

    def rollback(self, primitives: list[dict], intent_id: str) -> dict:
        """Roll back wireless primitives on the controller."""
        results = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            result = self._dispatch_rollback(ptype, prim, intent_id)
            results.append(result)
        return {
            "success": all(r.get("ok") for r in results),
            "details": results,
        }

    # ----- internal dispatch (override in vendor-specific subclass) -----

    def _dispatch_push(self, ptype: str, prim: dict, intent_id: str) -> dict:  # pylint: disable=unused-argument
        """Vendor-specific push logic — override in concrete subclass."""
        logger.warning(
            "WirelessControllerAdapter._dispatch_push not overridden; primitive '%s' for intent '%s' was NOT pushed.",
            ptype,
            intent_id,
        )
        return {"ok": False, "reason": "no vendor implementation"}

    def _check_present(self, ptype: str, prim: dict, intent_id: str) -> bool:  # pylint: disable=unused-argument
        """Vendor-specific verify — override in concrete subclass."""
        logger.warning(
            "WirelessControllerAdapter._check_present not overridden; returning False for '%s'.",
            ptype,
        )
        return False

    def _dispatch_rollback(self, ptype: str, prim: dict, intent_id: str) -> dict:  # pylint: disable=unused-argument
        """Vendor-specific rollback — override in concrete subclass."""
        logger.warning(
            "WirelessControllerAdapter._dispatch_rollback not overridden; "
            "primitive '%s' for intent '%s' was NOT rolled back.",
            ptype,
            intent_id,
        )
        return {"ok": False, "reason": "no vendor implementation"}


# ---------------------------------------------------------------------------
# SD-WAN Controller Adapter
# ---------------------------------------------------------------------------


class SdWanControllerAdapter(ControllerAdapter):
    """Adapter for SD-WAN controllers (e.g. Cisco vManage, Versa Director).

    Plugin config keys used:
        ``sdwan_controller_url``   — e.g. ``https://vmanage.example.com``
        ``sdwan_controller_type``  — ``cisco_vmanage`` | ``versa`` | ``generic``
        ``sdwan_controller_creds`` — dict
    """

    PRIMITIVE_TYPES = frozenset(
        {
            "sdwan_overlay",
            "sdwan_app_policy",
            "sdwan_qos",
            "sdwan_dia",
            "cloud_sdwan",
        }
    )

    def push(self, primitives: list[dict], intent_id: str) -> dict:
        """Push SD-WAN primitives to the controller."""
        results = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            logger.info(
                "[%s] Pushing %s to %s (intent=%s)",
                self.__class__.__name__,
                ptype,
                self.controller_url,
                intent_id,
            )
            result = self._dispatch_push(ptype, prim, intent_id)
            results.append(result)
        return {
            "success": all(r.get("ok") for r in results),
            "details": results,
        }

    def verify(self, primitives: list[dict], intent_id: str) -> dict:
        """Verify SD-WAN primitives are present on the controller."""
        drift: list[str] = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            if not self._check_present(ptype, prim, intent_id):
                drift.append(f"{ptype} missing on SD-WAN controller for intent {intent_id}")
        return {
            "verified": len(drift) == 0,
            "drift": drift,
            "details": f"Checked {len(primitives)} primitives",
        }

    def rollback(self, primitives: list[dict], intent_id: str) -> dict:
        """Roll back SD-WAN primitives on the controller."""
        results = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            result = self._dispatch_rollback(ptype, prim, intent_id)
            results.append(result)
        return {
            "success": all(r.get("ok") for r in results),
            "details": results,
        }

    def _dispatch_push(self, ptype: str, prim: dict, intent_id: str) -> dict:  # pylint: disable=unused-argument
        logger.warning(
            "SdWanControllerAdapter._dispatch_push not overridden; primitive '%s' for intent '%s' was NOT pushed.",
            ptype,
            intent_id,
        )
        return {"ok": False, "reason": "no vendor implementation"}

    def _check_present(self, ptype: str, prim: dict, intent_id: str) -> bool:  # pylint: disable=unused-argument
        logger.warning(
            "SdWanControllerAdapter._check_present not overridden; returning False for '%s'.",
            ptype,
        )
        return False

    def _dispatch_rollback(self, ptype: str, prim: dict, intent_id: str) -> dict:  # pylint: disable=unused-argument
        logger.warning(
            "SdWanControllerAdapter._dispatch_rollback not overridden; "
            "primitive '%s' for intent '%s' was NOT rolled back.",
            ptype,
            intent_id,
        )
        return {"ok": False, "reason": "no vendor implementation"}


# ---------------------------------------------------------------------------
# Cloud Adapter
# ---------------------------------------------------------------------------


class CloudAdapter(ControllerAdapter):
    """Adapter for cloud provider APIs (AWS, Azure, GCP).

    Plugin config keys used:
        ``cloud_provider``   — ``aws`` | ``azure`` | ``gcp``
        ``cloud_region``     — e.g. ``us-east-1``
        ``cloud_creds``      — provider-specific auth dict
    """

    PRIMITIVE_TYPES = frozenset(
        {
            "cloud_vpc_peer",
            "cloud_transit_gw",
            "cloud_direct_connect",
            "cloud_vpn_gw",
            "cloud_security_group",
            "cloud_nat",
            "cloud_route_table",
            "hybrid_dns",
            "cloud_sdwan",
        }
    )

    def push(self, primitives: list[dict], intent_id: str) -> dict:
        """Push cloud primitives to the provider API."""
        results = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            provider = prim.get("provider", "aws")
            logger.info(
                "[%s] Pushing %s to %s/%s (intent=%s)",
                self.__class__.__name__,
                ptype,
                provider,
                self.controller_url,
                intent_id,
            )
            result = self._dispatch_push(provider, ptype, prim, intent_id)
            results.append(result)
        return {
            "success": all(r.get("ok") for r in results),
            "details": results,
        }

    def verify(self, primitives: list[dict], intent_id: str) -> dict:
        """Verify cloud primitives are present on the provider."""
        drift: list[str] = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            provider = prim.get("provider", "aws")
            if not self._check_present(provider, ptype, prim, intent_id):
                drift.append(f"{ptype} missing on {provider} for intent {intent_id}")
        return {
            "verified": len(drift) == 0,
            "drift": drift,
            "details": f"Checked {len(primitives)} primitives",
        }

    def rollback(self, primitives: list[dict], intent_id: str) -> dict:
        """Roll back cloud primitives on the provider."""
        results = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            provider = prim.get("provider", "aws")
            result = self._dispatch_rollback(provider, ptype, prim, intent_id)
            results.append(result)
        return {
            "success": all(r.get("ok") for r in results),
            "details": results,
        }

    def _dispatch_push(self, provider: str, ptype: str, prim: dict, intent_id: str) -> dict:  # pylint: disable=unused-argument
        logger.warning(
            "CloudAdapter._dispatch_push not overridden; primitive '%s' for intent '%s' (provider=%s) was NOT pushed.",
            ptype,
            intent_id,
            provider,
        )
        return {"ok": False, "reason": "no provider implementation"}

    def _check_present(self, provider: str, ptype: str, prim: dict, intent_id: str) -> bool:  # pylint: disable=unused-argument
        logger.warning(
            "CloudAdapter._check_present not overridden; returning False for '%s' (provider=%s).",
            ptype,
            provider,
        )
        return False

    def _dispatch_rollback(self, provider: str, ptype: str, prim: dict, intent_id: str) -> dict:  # pylint: disable=unused-argument
        logger.warning(
            "CloudAdapter._dispatch_rollback not overridden; "
            "primitive '%s' for intent '%s' (provider=%s) was NOT rolled back.",
            ptype,
            intent_id,
            provider,
        )
        return {"ok": False, "reason": "no provider implementation"}


# ---------------------------------------------------------------------------
# Firewall Controller Adapter
# ---------------------------------------------------------------------------


class FirewallControllerAdapter(ControllerAdapter):
    """Adapter for centrally-managed firewall appliances.

    Supports Palo Alto Panorama, Fortinet FortiManager, and a generic
    REST-based firewall manager.

    Plugin config keys used:
        ``firewall_controller_url``   — e.g. ``https://panorama.example.com``
        ``firewall_controller_type``  — ``paloalto_panorama`` | ``fortinet_fortimanager`` | ``generic``
        ``firewall_controller_creds`` — dict with ``username`` / ``password`` / ``api_key``
    """

    PRIMITIVE_TYPES = frozenset(
        {
            "fw_rule",
        }
    )

    def push(self, primitives: list[dict], intent_id: str) -> dict:
        """Push firewall rule primitives to the controller."""
        results = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                logger.warning("Skipping non-firewall primitive '%s'", ptype)
                continue

            logger.info(
                "[%s] Pushing %s to %s (intent=%s)",
                self.__class__.__name__,
                ptype,
                self.controller_url,
                intent_id,
            )

            result = self._dispatch_push(ptype, prim, intent_id)
            results.append(result)

        success = all(r.get("ok") for r in results)
        return {
            "success": success,
            "details": results,
        }

    def verify(self, primitives: list[dict], intent_id: str) -> dict:
        """Verify firewall rules are present on the controller."""
        drift: list[str] = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            if not self._check_present(ptype, prim, intent_id):
                drift.append(f"{ptype} policy '{prim.get('policy_name', '')}' missing for intent {intent_id}")
        return {
            "verified": len(drift) == 0,
            "drift": drift,
            "details": f"Checked {len(primitives)} primitives",
        }

    def rollback(self, primitives: list[dict], intent_id: str) -> dict:
        """Roll back firewall rules on the controller."""
        results = []
        for prim in primitives:
            ptype = prim.get("primitive_type", "")
            if ptype not in self.PRIMITIVE_TYPES:
                continue
            result = self._dispatch_rollback(ptype, prim, intent_id)
            results.append(result)
        return {
            "success": all(r.get("ok") for r in results),
            "details": results,
        }

    def _dispatch_push(self, ptype: str, prim: dict, intent_id: str) -> dict:  # pylint: disable=unused-argument
        """Vendor-specific push logic — override in concrete subclass."""
        logger.warning(
            "FirewallControllerAdapter._dispatch_push not overridden; primitive '%s' for intent '%s' was NOT pushed.",
            ptype,
            intent_id,
        )
        return {"ok": False, "reason": "no vendor implementation"}

    def _check_present(self, ptype: str, prim: dict, intent_id: str) -> bool:  # pylint: disable=unused-argument
        """Vendor-specific verify — override in concrete subclass."""
        logger.warning(
            "FirewallControllerAdapter._check_present not overridden; returning False for '%s'.",
            ptype,
        )
        return False

    def _dispatch_rollback(self, ptype: str, prim: dict, intent_id: str) -> dict:  # pylint: disable=unused-argument
        """Vendor-specific rollback — override in concrete subclass."""
        logger.warning(
            "FirewallControllerAdapter._dispatch_rollback not overridden; "
            "primitive '%s' for intent '%s' was NOT rolled back.",
            ptype,
            intent_id,
        )
        return {"ok": False, "reason": "no vendor implementation"}


# ---------------------------------------------------------------------------
# Catalyst Center Adapter (optional — requires [catalyst] extra)
# ---------------------------------------------------------------------------

# Allowed controller values for YAML validation.
VALID_CONTROLLER_TYPES = frozenset({"nornir", "catalyst_center", "meraki", "mist"})


class UnsupportedIntentTypeError(ValueError):
    """Raised when an adapter does not support the given intent type."""


class CatalystCenterAdapter:
    """Adapter for Cisco Catalyst Center (formerly DNA Center).

    This adapter is an **optional extra**. The ``dnacentersdk`` package is
    imported lazily in ``__init__`` so that the rest of the plugin works
    without it. Install with::

        poetry add nautobot-app-intent-networking[catalyst]

    Supported intent types:
        - ``connectivity`` → virtual network + scalable group
        - ``segmentation`` → policy + contract
        - ``reachability`` → routing policy

    Auth credentials are read from the Nautobot SecretsGroup named in
    ``catalyst_center_secrets_group`` plugin config, falling back to env
    vars ``CATALYST_CENTER_URL``, ``CATALYST_CENTER_USERNAME``,
    ``CATALYST_CENTER_PASSWORD``.
    """

    SUPPORTED_INTENT_TYPES = frozenset({"connectivity", "segmentation", "reachability"})
    TASK_POLL_TIMEOUT = 300  # seconds
    TASK_POLL_INTERVAL = 5  # seconds

    def __init__(self, intent):
        """Initialise the adapter — lazy-imports dnacentersdk."""
        try:
            from dnacentersdk import DNACenterAPI  # noqa: F811,PLC0415
        except ImportError:
            raise ImportError(
                "Catalyst Center adapter requires the 'catalyst' extra. "
                "Install it with: poetry add nautobot-app-intent-networking[catalyst]"
            ) from None
        self.intent = intent
        self._api_cls = DNACenterAPI

        # Resolve credentials
        url, username, password = self._resolve_credentials()
        self.api = self._api_cls(
            base_url=url,
            username=username,
            password=password,
            verify=False,
        )

    @staticmethod
    def _resolve_credentials():
        """Resolve Catalyst Center credentials from Secrets or env vars."""
        import os  # noqa: PLC0415

        group_name = _get_plugin_config("catalyst_center_secrets_group")

        if group_name:
            from intent_networking.secrets import get_secrets_group_value  # noqa: PLC0415

            url = get_secrets_group_value(group_name, "HTTP(S)", "url")
            username = get_secrets_group_value(group_name, "Generic", "username")
            password = get_secrets_group_value(group_name, "Generic", "password")
            return url, username, password

        # Fallback to env vars
        url = os.environ.get("CATALYST_CENTER_URL", "")
        username = os.environ.get("CATALYST_CENTER_USERNAME", "")
        password = os.environ.get("CATALYST_CENTER_PASSWORD", "")
        if not all([url, username, password]):
            raise RuntimeError(
                "No Catalyst Center credentials available. Either:\n"
                "  1. Configure 'catalyst_center_secrets_group' in PLUGINS_CONFIG, or\n"
                "  2. Set CATALYST_CENTER_URL, CATALYST_CENTER_USERNAME, CATALYST_CENTER_PASSWORD env vars."
            )
        return url, username, password

    def deploy(self, resolution_plan) -> dict:
        """Deploy the intent via Catalyst Center SDK."""
        intent_type = self.intent.intent_type
        if intent_type not in self.SUPPORTED_INTENT_TYPES:
            raise UnsupportedIntentTypeError(
                f"Catalyst Center adapter does not support intent type '{intent_type}'. "
                f"Supported types: {', '.join(sorted(self.SUPPORTED_INTENT_TYPES))}"
            )

        intent_data = self.intent.intent_data
        site = self.intent.controller_site

        if intent_type == "connectivity":
            return self._deploy_connectivity(intent_data, site)
        if intent_type == "segmentation":
            return self._deploy_segmentation(intent_data, site)
        return self._deploy_reachability(intent_data, site)

    def _deploy_connectivity(self, intent_data, site):
        """Deploy a connectivity intent — virtual network + scalable groups."""
        vn_name = intent_data.get("vn_name", intent_data.get("source", self.intent.intent_id))
        sgt_list = intent_data.get("scalable_groups", [])

        payload = {
            "virtualNetworkName": vn_name,
            "isGuestVirtualNetwork": False,
            "scalableGroupNames": sgt_list,
        }

        response = self.api.sda.add_virtual_network_with_scalable_groups(payload=[payload])
        task_id = self._extract_task_id(response)
        task_result = self._poll_task(task_id)

        return {"success": task_result["completed"], "details": task_result, "task_id": task_id}

    def _deploy_segmentation(self, intent_data, site):
        """Deploy a segmentation intent — policy + contract."""
        policy_name = intent_data.get("policy_name", self.intent.intent_id)
        contract = intent_data.get("contract", {})

        response = self.api.sda.add_default_authentication_profile(
            payload=[
                {
                    "authenticateTemplateName": policy_name,
                    "siteNameHierarchy": site,
                }
            ]
        )
        task_id = self._extract_task_id(response)
        task_result = self._poll_task(task_id)

        return {
            "success": task_result["completed"],
            "details": {**task_result, "contract": contract},
            "task_id": task_id,
        }

    def _deploy_reachability(self, intent_data, site):
        """Deploy a reachability intent — routing policy."""
        response = self.api.sda.add_site(
            payload=[
                {
                    "fabricName": intent_data.get("fabric_name", "Default"),
                    "siteNameHierarchy": site,
                }
            ]
        )
        task_id = self._extract_task_id(response)
        task_result = self._poll_task(task_id)

        return {"success": task_result["completed"], "details": task_result, "task_id": task_id}

    def verify(self) -> dict:
        """Verify compliance of affected devices via Catalyst Center."""
        site = self.intent.controller_site
        compliance = self.api.compliance.get_compliance_detail(
            deviceUuid="",
            complianceStatus="NON_COMPLIANT",
        )

        non_compliant = []
        if hasattr(compliance, "response") and compliance.response:
            for item in compliance.response:
                device_name = getattr(item, "deviceName", "unknown")
                category = getattr(item, "complianceType", "unknown")
                non_compliant.append({"device": device_name, "category": category})

        return {
            "verified": len(non_compliant) == 0,
            "drift": non_compliant,
            "details": f"Checked compliance for site '{site}'",
        }

    def rollback(self, previous_version) -> dict:
        """Roll back to a previous intent version by removing current config."""
        intent_data = self.intent.intent_data
        intent_type = self.intent.intent_type

        if intent_type == "connectivity":
            vn_name = intent_data.get("vn_name", intent_data.get("source", self.intent.intent_id))
            response = self.api.sda.delete_virtual_network_with_scalable_groups(  # pylint: disable=no-value-for-parameter
                virtualNetworkName=vn_name,
            )
        elif intent_type == "segmentation":
            response = self.api.sda.delete_default_authentication_profile(  # pylint: disable=no-value-for-parameter
                siteNameHierarchy=self.intent.controller_site,
            )
        else:
            response = self.api.sda.delete_site(  # pylint: disable=no-value-for-parameter
                siteNameHierarchy=self.intent.controller_site,
            )

        task_id = self._extract_task_id(response)
        task_result = self._poll_task(task_id)

        return {"success": task_result["completed"], "details": task_result}

    def get_live_state(self) -> dict:
        """Pull live device data from Catalyst Center for topology viewer."""
        devices = self.api.devices.get_device_list()
        device_list = []
        if hasattr(devices, "response") and devices.response:
            for dev in devices.response:
                device_list.append(
                    {
                        "hostname": getattr(dev, "hostname", ""),
                        "managementIpAddress": getattr(dev, "managementIpAddress", ""),
                        "reachabilityStatus": getattr(dev, "reachabilityStatus", ""),
                        "role": getattr(dev, "role", ""),
                    }
                )
        return {"devices": device_list}

    @staticmethod
    def _extract_task_id(response):
        """Extract the task ID from a Catalyst Center API response."""
        if hasattr(response, "response") and hasattr(response.response, "taskId"):
            return response.response.taskId
        if isinstance(response, dict):
            return response.get("response", {}).get("taskId", "")
        return ""

    def _poll_task(self, task_id):
        """Poll a Catalyst Center task until completion or timeout."""
        import time  # noqa: PLC0415

        if not task_id:
            return {"completed": False, "error": "No task ID returned"}

        elapsed = 0
        while elapsed < self.TASK_POLL_TIMEOUT:
            task = self.api.task.get_task_by_id(task_id)
            if hasattr(task, "response"):
                resp = task.response
                if getattr(resp, "endTime", None):
                    is_error = getattr(resp, "isError", False)
                    return {
                        "completed": not is_error,
                        "error": getattr(resp, "failureReason", "") if is_error else "",
                        "progress": getattr(resp, "progress", ""),
                    }
            time.sleep(self.TASK_POLL_INTERVAL)
            elapsed += self.TASK_POLL_INTERVAL

        return {"completed": False, "error": f"Task {task_id} timed out after {self.TASK_POLL_TIMEOUT}s"}


# ---------------------------------------------------------------------------
# Adapter Factory
# ---------------------------------------------------------------------------

# Map of adapter type keys → concrete adapter classes
ADAPTER_REGISTRY: dict[str, type[ControllerAdapter]] = {
    "wireless": WirelessControllerAdapter,
    "sdwan": SdWanControllerAdapter,
    "cloud": CloudAdapter,
    "firewall": FirewallControllerAdapter,
}


def get_adapter(adapter_type: str, **overrides) -> ControllerAdapter:
    """Factory: instantiate the correct adapter from plugin config.

    Args:
        adapter_type: ``"wireless"`` | ``"sdwan"`` | ``"cloud"``
        **overrides:  override any parameter (url, creds, etc.)

    Returns:
        A ready-to-use ``ControllerAdapter`` subclass instance.

    Raises:
        ValueError: if adapter_type is unknown or required config is missing.
    """
    cls = ADAPTER_REGISTRY.get(adapter_type)
    if cls is None:
        raise ValueError(f"Unknown adapter type '{adapter_type}'. Valid types: {list(ADAPTER_REGISTRY.keys())}")

    # Read config keys by convention: {adapter_type}_controller_url, etc.
    url_key = f"{adapter_type}_controller_url"
    creds_key = f"{adapter_type}_controller_creds"

    controller_url = overrides.pop("controller_url", None) or _get_plugin_config(url_key)
    if not controller_url:
        raise ValueError(
            f"Plugin config key '{url_key}' is not set and no "
            f"controller_url override was provided for adapter '{adapter_type}'."
        )

    credentials = overrides.pop("credentials", None) or _get_plugin_config(creds_key) or {}

    return cls(
        controller_url=controller_url,
        credentials=credentials,
        **overrides,
    )


def classify_primitives(primitives: list[dict]) -> dict[str, list[dict]]:
    """Split a list of primitives into adapter-type buckets.

    Returns:
        dict mapping ``"nornir"`` | ``"wireless"`` | ``"sdwan"`` | ``"cloud"``
        to the subset of primitives that should be handled by that adapter.
    """
    buckets: dict[str, list[dict]] = {
        "nornir": [],
        "wireless": [],
        "sdwan": [],
        "cloud": [],
        "firewall": [],
    }

    for prim in primitives:
        ptype = prim.get("primitive_type", "")
        if ptype in WirelessControllerAdapter.PRIMITIVE_TYPES:
            buckets["wireless"].append(prim)
        elif ptype in SdWanControllerAdapter.PRIMITIVE_TYPES:
            buckets["sdwan"].append(prim)
        elif ptype in CloudAdapter.PRIMITIVE_TYPES:
            buckets["cloud"].append(prim)
        elif ptype in FirewallControllerAdapter.PRIMITIVE_TYPES:
            buckets["firewall"].append(prim)
        else:
            # Default: device-level config pushed via Nornir/Netmiko
            buckets["nornir"].append(prim)

    # Remove empty buckets
    return {k: v for k, v in buckets.items() if v}
