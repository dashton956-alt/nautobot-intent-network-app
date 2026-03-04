"""Production intent resolution logic for the intent_networking plugin.

Key differences from the POC FastAPI version:
  - Queries Nautobot ORM directly instead of receiving a TopologyContext dict
  - Uses atomic RD/RT allocation from the allocations module
  - Hard-fails (raises) instead of using fallbacks
  - Group-to-device mapping uses Nautobot device tags
  - BGP neighbour IPs come from Nautobot interface/IP data
"""

import logging

from django.conf import settings
from django.db import transaction
from nautobot.dcim.models import Device

from intent_networking.allocations import allocate_route_distinguisher, allocate_route_target
from intent_networking.models import Intent

logger = logging.getLogger(__name__)


def _get_plugin_config(key: str):
    """Retrieve a value from the intent_networking plugin config."""
    return settings.PLUGINS_CONFIG.get("intent_networking", {}).get(key)


# ─────────────────────────────────────────────────────────────────────────────
# VRF Naming
# ─────────────────────────────────────────────────────────────────────────────


def generate_vrf_name(intent: Intent) -> str:
    """Generate a deterministic VRF name from intent properties.

    Format: <TENANT_CODE>-<COMPLIANCE_TAG>
    e.g. ACMECORP-PCI, ACMECORP-HIPAA, WIDGETCO-001
    """
    tenant_code = intent.tenant.name.upper().replace(" ", "").replace("-", "")[:8]
    intent_data = intent.intent_data
    compliance = intent_data.get("policy", {}).get("compliance", "none")

    compliance_map = {
        "PCI-DSS": "PCI",
        "HIPAA": "HIPAA",
        "SOC2": "SOC2",
        "ISO27001": "ISO27K",
    }

    if compliance in compliance_map:
        return f"{tenant_code}-{compliance_map[compliance]}"
    # Use last segment of intent ID as shortcode
    short = intent.intent_id.split("-")[-1].upper()[:6]
    return f"{tenant_code}-{short}"


# ─────────────────────────────────────────────────────────────────────────────
# Device Resolution — Production Version
# ─────────────────────────────────────────────────────────────────────────────


def get_devices_for_group(group: str, sites: list, tenant) -> list:
    """
    Find Nautobot Device objects that serve a given group at specified sites.

    Uses Nautobot device tags for group membership:
      - Tag "service-group-{group}" on the device in Nautobot
      - e.g. tag "service-group-finance-servers" for group "finance-servers"

    Args:
        group:  Group name string from intent source.group
        sites:  List of site slug strings from intent source.sites
        tenant: Nautobot Tenant ORM object

    Returns:
        QuerySet of Device objects

    Raises:
        ValueError: if no devices found — hard fail, no fallback
    """
    devices = (
        Device.objects.filter(
            location__name__in=sites,
            tenant=tenant,
            tags__name=f"service-group-{group}",
            status__name__iexact="Active",
        )
        .exclude(status__name__iexact="Maintenance")
        .prefetch_related(
            "interfaces",
            "interfaces__ip_addresses",
            "tags",
            "platform",
        )
    )

    if not devices.exists():
        raise ValueError(
            f"No active devices found for group '{group}' "
            f"at sites {sites} for tenant '{tenant.name}'. "
            f"Check that devices in Nautobot have tag 'service-group-{group}' "
            f"and status 'active' at the specified sites."
        )

    logger.info(
        "Resolved group '%s' at %s \u2192 %s devices: %s",
        group,
        sites,
        devices.count(),
        [d.name for d in devices],
    )
    return list(devices)


def get_pe_neighbor_ip(device: Device, vrf_name: str) -> str:  # pylint: disable=unused-argument
    """
    Find the PE-facing BGP neighbour IP for a device.

    Looks for interfaces tagged 'pe-uplink' on the device and returns
    the IP address of the connected endpoint (the PE router interface).

    Args:
        device:   Nautobot Device object
        vrf_name: VRF name (used for logging)

    Returns:
        IP address string e.g. "10.0.0.1"

    Raises:
        ValueError: if no PE uplink interface found
    """
    pe_interfaces = device.interfaces.filter(
        tags__name="pe-uplink",
    ).prefetch_related("connected_endpoint", "connected_endpoint__ip_addresses")

    if not pe_interfaces.exists():
        raise ValueError(
            f"No interface tagged 'pe-uplink' found on device '{device.name}'. "
            f"Tag the PE-facing interface in Nautobot before deploying "
            f"connectivity intents to this device."
        )

    pe_iface = pe_interfaces.first()

    # Get the connected endpoint (the PE router's interface)
    connected = getattr(pe_iface, "connected_endpoint", None)
    if not connected:
        raise ValueError(
            f"PE uplink interface '{pe_iface.name}' on '{device.name}' "
            f"has no connected endpoint in Nautobot. "
            f"Cable the connection in Nautobot DCIM."
        )

    pe_ips = connected.ip_addresses.all()
    if not pe_ips.exists():
        raise ValueError(
            f"Connected PE interface '{connected.name}' on '{connected.device.name}' "
            f"has no IP addresses in Nautobot IPAM."
        )

    return str(pe_ips.first().address.ip)


# ─────────────────────────────────────────────────────────────────────────────
# ACL Generation
# ─────────────────────────────────────────────────────────────────────────────


def build_acl_entries(intent: Intent, vrf_name: str) -> list:
    """Translate isolation rules from intent_data into concrete ACL entry dicts.

    These are passed into AclPrimitive objects.
    """
    intent_data = intent.intent_data
    isolation = intent_data.get("isolation", {})
    destination = intent_data.get("destination", {})
    entries = []

    # Deny prohibited protocols
    protocol_map = {
        "telnet": ("tcp", 23),
        "http": ("tcp", 80),
        "ftp": ("tcp", 21),
        "snmpv1": ("udp", 161),
        "snmpv2": ("udp", 161),
    }
    for protocol in isolation.get("deny_protocols", []):
        if protocol in protocol_map:
            proto, port = protocol_map[protocol]
            entries.append(
                {
                    "action": "deny",
                    "protocol": proto,
                    "source": "any",
                    "destination": "any",
                    "port": port,
                    "log": True,
                    "remark": f"Deny {protocol} per intent isolation policy",
                }
            )

    # Deny RFC1918 for external-facing intents
    if destination.get("external"):
        for rfc1918, wildcard in [
            ("10.0.0.0", "0.255.255.255"),
            ("172.16.0.0", "0.15.255.255"),
            ("192.168.0.0", "0.0.255.255"),
        ]:
            entries.append(
                {
                    "action": "deny",
                    "protocol": "ip",
                    "source": f"{rfc1918} {wildcard}",
                    "destination": "any",
                    "log": True,
                    "remark": f"Deny RFC1918 {rfc1918}/... (external intent)",
                }
            )

    # Permit required destination prefixes
    for prefix in destination.get("prefixes", []):
        entries.append(
            {
                "action": "permit",
                "protocol": "tcp",
                "source": "any",
                "destination": prefix,
                "port": 443,
                "log": False,
                "remark": f"Permit {prefix} (intent destination)",
            }
        )

    # Implicit deny all at the end (explicit for auditability)
    entries.append(
        {
            "action": "deny",
            "protocol": "ip",
            "source": "any",
            "destination": "any",
            "log": True,
            "remark": f"Implicit deny — {vrf_name} isolation",
        }
    )

    return entries


# ─────────────────────────────────────────────────────────────────────────────
# Connectivity Intent Resolver
# ─────────────────────────────────────────────────────────────────────────────


@transaction.atomic
def resolve_connectivity(intent: Intent) -> dict:
    """
    Resolve a connectivity intent.

    Queries Nautobot ORM for devices, allocates RD/RT atomically,
    builds primitives list.

    Returns:
        dict matching ResolutionPlan field layout
    """
    intent_data = intent.intent_data
    source = intent_data.get("source", {})

    if not source:
        raise ValueError(
            f"Intent {intent.intent_id} has no 'source' defined. "
            f"Connectivity intents require source.group and source.sites."
        )

    source_group = source.get("group")
    source_sites = source.get("sites", [])

    if not source_group or not source_sites:
        raise ValueError(f"Intent {intent.intent_id} source is missing 'group' or 'sites'.")

    # Resolve devices from Nautobot
    devices = get_devices_for_group(source_group, source_sites, intent.tenant)

    # Generate VRF name and allocate route targets (intent-level, once)
    vrf_name = generate_vrf_name(intent)
    rt_export, rt_import = allocate_route_target(intent)
    default_bgp_asn = _get_plugin_config("default_bgp_asn")

    primitives = []
    affected_device_names = []
    allocated_rds = {}

    for device in devices:
        affected_device_names.append(device.name)

        # Allocate RD for this device+VRF (atomic, idempotent)
        rd = allocate_route_distinguisher(device, vrf_name, intent)
        allocated_rds[device.name] = rd

        # Get real BGP neighbour IP from Nautobot topology
        neighbor_ip = get_pe_neighbor_ip(device, vrf_name)

        # VRF primitive
        primitives.append(
            {
                "primitive_type": "vrf",
                "device": device.name,
                "vrf_name": vrf_name,
                "route_distinguisher": rd,
                "rt_export": rt_export,
                "rt_import": rt_import,
                "description": f"{intent.intent_id} v{intent.version}",
                "bgp_asn": default_bgp_asn,
                "redistribute_connected": True,
                "redistribute_static": False,
            }
        )

        # BGP neighbor primitive
        tenant_asn = intent.intent_data.get("policy", {}).get("tenant_asn", default_bgp_asn + 1)
        primitives.append(
            {
                "primitive_type": "bgp_neighbor",
                "device": device.name,
                "vrf_name": vrf_name,
                "local_asn": default_bgp_asn,
                "neighbor_ip": neighbor_ip,
                "neighbor_asn": tenant_asn,
                "neighbor_description": f"{intent.tenant.name.upper().replace(' ', '').replace('-', '')[:8]}-{vrf_name}-PE",
                "route_map_in": f"RM-{vrf_name}-IN",
                "route_map_out": f"RM-{vrf_name}-OUT",
                "bfd_enabled": True,
                "max_prefix": 500,
            }
        )

        # ACL primitive
        acl_entries = build_acl_entries(intent, vrf_name)
        if acl_entries:
            primitives.append(
                {
                    "primitive_type": "acl",
                    "device": device.name,
                    "acl_name": f"ACL-{vrf_name}-INGRESS",
                    "acl_type": "extended",
                    "entries": acl_entries,
                    "intent_id": intent.intent_id,
                    "intent_version": intent.version,
                }
            )

    return {
        "affected_devices": affected_device_names,
        "vrf_name": vrf_name,
        "requires_new_vrf": True,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": allocated_rds,
        "allocated_rts": {"export": rt_export, "import": rt_import},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Security Intent Resolver
# ─────────────────────────────────────────────────────────────────────────────


@transaction.atomic
def resolve_security(intent: Intent) -> dict:
    """Resolve a security/segmentation intent.

    Applies ACLs to all devices in the tenant scope.
    """
    intent_data = intent.intent_data
    scope_sites = intent_data.get("scope", {}).get("sites", [])

    if scope_sites:
        devices = Device.objects.filter(
            location__name__in=scope_sites,
            tenant=intent.tenant,
            status__name__iexact="Active",
        )
    else:
        devices = Device.objects.filter(
            tenant=intent.tenant,
            status__name__iexact="Active",
        )

    if not devices.exists():
        raise ValueError(f"No devices found in scope for security intent {intent.intent_id}.")

    primitives = []
    affected_device_names = []

    for device in devices:
        affected_device_names.append(device.name)
        acl_entries = build_acl_entries(intent, intent.intent_id)
        primitives.append(
            {
                "primitive_type": "acl",
                "device": device.name,
                "acl_name": f"ACL-{intent.intent_id.upper().replace('-', '_')}-POLICY",
                "acl_type": "extended",
                "entries": acl_entries,
                "intent_id": intent.intent_id,
                "intent_version": intent.version,
            }
        )

    return {
        "affected_devices": affected_device_names,
        "requires_new_vrf": False,
        "requires_mpls": False,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Reachability Intent Resolver
# ─────────────────────────────────────────────────────────────────────────────


@transaction.atomic
def resolve_reachability(intent: Intent) -> dict:
    """Resolve a reachability intent (static routes / BGP network statements)."""
    raise NotImplementedError(
        "Reachability intent resolution is not yet implemented. "
        "Track: https://github.com/your-org/nautobot-intent-networking/issues/12"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

RESOLVERS = {
    "connectivity": resolve_connectivity,
    "security": resolve_security,
    "reachability": resolve_reachability,
}


def resolve_intent(intent: Intent) -> dict:
    """
    Main entry point — dispatches to the appropriate resolver.

    Args:
        intent: Intent ORM object

    Returns:
        dict with keys: affected_devices, primitives, vrf_name,
                        requires_new_vrf, requires_mpls,
                        allocated_rds, allocated_rts

    Raises:
        ValueError:          for bad intent data or missing Nautobot data
        NotImplementedError: for unimplemented intent types
    """
    resolver_fn = RESOLVERS.get(intent.intent_type)

    if not resolver_fn:
        raise ValueError(
            f"No resolver implemented for intent type '{intent.intent_type}'. " f"Known types: {list(RESOLVERS.keys())}"
        )

    logger.info(
        "Resolving intent %s (type=%s, tenant=%s)",
        intent.intent_id,
        intent.intent_type,
        intent.tenant.name,
    )

    plan_data = resolver_fn(intent)

    logger.info(
        "Resolution complete: %s \u2192 %s devices, %s primitives",
        intent.intent_id,
        len(plan_data["affected_devices"]),
        len(plan_data["primitives"]),
    )

    return plan_data
