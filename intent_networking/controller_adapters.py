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
