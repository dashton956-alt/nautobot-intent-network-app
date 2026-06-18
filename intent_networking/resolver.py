"""Production intent resolution logic for the intent_networking plugin.

Covers all 14 intent domains:
  1. Layer 2 / Switching         8. Cloud & Hybrid Cloud
  2. Layer 3 / Routing           9. QoS
  3. MPLS & Service Provider    10. Multicast
  4. Data Centre / EVPN / VXLAN 11. Management & Operations
  5. Security & Firewalling     12. Reachability
  6. WAN & SD-WAN               13. Service
  7. Wireless                   14. Controller adapter routing

Key design rules:
  - Queries Nautobot ORM directly — no hardcoded values
  - Atomic RD/RT/VNI/tunnel/loopback allocation
  - Hard-fails (raises ValueError) when required data is missing
  - Group-to-device mapping uses Nautobot device tags
  - All resolvers return a dict matching ResolutionPlan field layout
  - Vendor-neutral primitives only — no CLI in resolvers
"""

import ipaddress
import logging

from django.conf import settings
from django.db import transaction
from nautobot.dcim.models import Device

from intent_networking.allocations import (
    allocate_loopback_ip,
    allocate_route_distinguisher,
    allocate_route_target,
    allocate_tunnel_id,
    allocate_vxlan_vni,
    allocate_wireless_vlan,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_plugin_config(key: str):
    """Retrieve a value from the intent_networking plugin config."""
    return settings.PLUGINS_CONFIG.get("intent_networking", {}).get(key)


def _empty_plan(affected_devices: list, primitives: list) -> dict:
    """Return a plan dict with no VRF/MPLS requirements."""
    return {
        "affected_devices": affected_devices,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": False,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


def _get_scope_devices(intent, scope_key: str = "scope") -> list:
    """Resolve devices from the intent scope/source block.

    Implements the full scope contract documented in
    ``network_as_code_example/intents/examples/scope_options.yaml``. The
    following keys under ``intent_data[scope_key]`` are honoured:

    * ``all_tenant_devices`` (bool) — every active device for the tenant.
    * ``devices`` / ``device`` — explicit device name(s); highest specificity.
    * ``sites`` / ``site`` — restrict to one or more Nautobot locations.
    * ``roles`` / ``role`` — restrict to one or more Nautobot device roles.
    * ``tags`` — restrict to devices carrying all of the given tags.
    * ``platform`` — restrict to a Nautobot platform.
    * ``group`` — legacy ``service-group-<group>`` tag (used by the
      connectivity ``source`` block).

    Resolution order (per the documented contract):
        1. ``all_tenant_devices``         → all tenant devices
        2. ``devices`` / ``device``       → explicit list (overrides site/role)
        3. ``sites`` + ``roles`` (etc.)   → intersection of the given filters

    Returns:
        List of Device ORM objects.

    Raises:
        ValueError: if the scope is empty/unrecognised or no active device
            matches it.
    """
    intent_data = intent.intent_data
    scope = intent_data.get(scope_key, {}) or {}

    # Fabric intents (evpn_vxlan_fabric, dc_underlay, …) describe their device
    # set with a ``fabric`` block listing spines/leaves rather than a ``scope``.
    # Honour explicit device lists there when no scope is supplied.
    if not scope and scope_key == "scope":
        fabric = intent_data.get("fabric", {}) or {}
        fabric_devices = list(fabric.get("spines", [])) + list(fabric.get("leaves", []))
        # Fabric referenced by name (e.g. l2vni/l3vni) — look up the fabric intent.
        if not fabric_devices and fabric.get("name"):
            fabric_devices = _fabric_member_names(intent, fabric["name"])
        if fabric_devices:
            scope = {"devices": fabric_devices}

    all_tenant = bool(scope.get("all_tenant_devices", False))

    # Accept both list and singular-string forms.
    sites = list(scope.get("sites", []))
    if scope.get("site"):
        sites.append(scope["site"])
    explicit_devices = list(scope.get("devices", []))
    if scope.get("device"):
        explicit_devices.append(scope["device"])
    roles = list(scope.get("roles", []))
    if scope.get("role"):
        roles.append(scope["role"])
    tags = list(scope.get("tags", []))
    platform = scope.get("platform")
    group = scope.get("group")  # legacy connectivity source-block support

    base = Device.objects.filter(tenant=intent.tenant, status__name__iexact="Active")

    if all_tenant:
        qs = base
    elif explicit_devices:
        # Explicit device list overrides site/role per the contract.
        qs = base.filter(name__in=explicit_devices)
    elif sites or roles or group:
        qs = base
        if sites:
            qs = qs.filter(location__name__in=sites)
        if roles:
            qs = qs.filter(role__name__in=roles)
        if group:
            qs = qs.filter(tags__name=f"service-group-{group}")
    else:
        raise ValueError(
            f"Intent {intent.intent_id}: scope '{scope_key}' is empty or "
            f"unrecognised. Provide one of: all_tenant_devices, devices/device, "
            f"sites/site, roles/role (see scope_options.yaml)."
        )

    # Optional cross-cutting filters that apply on top of the selection above.
    if tags:
        qs = qs.filter(tags__name__in=tags)
    if platform:
        qs = qs.filter(platform__name__iexact=platform)

    qs = qs.prefetch_related("interfaces", "interfaces__ip_addresses", "tags", "platform").distinct()

    if not qs.exists():
        raise ValueError(
            f"No active devices found for intent {intent.intent_id} "
            f"(scope_key='{scope_key}', sites={sites}, roles={roles}, "
            f"devices={explicit_devices}, group='{group}', "
            f"all_tenant_devices={all_tenant}, tenant='{intent.tenant.name}'). "
            f"Check device roles, tags, status and location in Nautobot."
        )

    logger.info(
        "Resolved %s devices for intent %s (scope_key=%s)",
        qs.count(),
        intent.intent_id,
        scope_key,
    )
    return list(qs)


def _fabric_member_names(intent, fabric_name: str) -> list:
    """Resolve device names belonging to a named EVPN/VXLAN fabric.

    Looks up the ``evpn_vxlan_fabric`` intent (same tenant) whose
    ``fabric.name`` matches and returns its leaf (VTEP) devices — falling back
    to spines+leaves when no leaves are listed. Lets ``l2vni``/``l3vni`` intents
    reference a fabric by name instead of repeating the device list.
    """
    from intent_networking.models import Intent  # noqa: PLC0415

    fabric_intent = (
        Intent.objects.filter(tenant=intent.tenant, intent_type="evpn_vxlan_fabric")
        .filter(intent_data__fabric__name=fabric_name)
        .first()
    )
    if not fabric_intent:
        return []
    fab = fabric_intent.intent_data.get("fabric", {}) or {}
    leaves = list(fab.get("leaves", []))
    return leaves or (list(fab.get("spines", [])) + leaves)


def _devices_by_ip(intent, ip: str) -> list:
    """Resolve active, same-tenant device(s) that own a given IP address.

    Used by endpoint-addressed intents (e.g. ipsec_s2s ``tunnel.local_endpoint``)
    that identify the device by its address rather than a scope block.
    """
    if not ip:
        return []
    bare = str(ip).split("/", maxsplit=1)[0]
    qs = (
        Device.objects.filter(
            tenant=intent.tenant,
            status__name__iexact="Active",
            interfaces__ip_addresses__host=bare,
        )
        .prefetch_related("interfaces", "interfaces__ip_addresses", "tags", "platform")
        .distinct()
    )
    return list(qs)


def _mgmt_view(intent_data: dict, *subtypes: str) -> dict:
    """Return a merged field view for management (``mgmt_*``) intents.

    The canonical wrapped form is ``management.<subtype>`` (e.g.
    ``management.ssh.timeout_secs``). This helper flattens that wrapping so
    resolvers can read fields uniformly, with precedence (highest first):

        management.<subtype>.<field>   (canonical)
        management.<field>             (flat-under-management)
        <field>                        (legacy top-level)

    Multiple subtypes may be passed (e.g. ``"dns", "dhcp"``); each subtype
    block is overlaid, so later subtypes win on key collisions.
    """
    mgmt = intent_data.get("management", {})
    mgmt = mgmt if isinstance(mgmt, dict) else {}
    merged = dict(intent_data)  # legacy top-level (lowest precedence)
    merged.update(mgmt)  # management.* flat keys + subtype dicts
    for sub in subtypes:
        block = mgmt.get(sub)
        if isinstance(block, dict):
            merged.update(block)  # canonical subtype fields (highest)
    return merged


# ---------------------------------------------------------------------------
# VRF Naming
# ---------------------------------------------------------------------------


def generate_vrf_name(intent) -> str:
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
    short = intent.intent_id.split("-")[-1].upper()[:6]
    return f"{tenant_code}-{short}"


# ---------------------------------------------------------------------------
# Device Resolution — Production Version
# ---------------------------------------------------------------------------


def get_devices_for_group(group: str, sites: list, tenant) -> list:
    """Find Nautobot Device objects that serve a given group at specified sites.

    Uses Nautobot device tags for group membership:
      - Tag ``service-group-{group}`` on the device in Nautobot

    Raises:
        ValueError: if no devices found
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
        "Resolved group '%s' at %s -> %s devices: %s",
        group,
        sites,
        devices.count(),
        [d.name for d in devices],
    )
    return list(devices)


def get_pe_neighbor_ip(device, vrf_name: str) -> str:
    """Find the PE-facing BGP neighbour IP for a device.

    Looks for interfaces tagged ``pe-uplink`` on the device and returns
    the IP address of the connected endpoint (the PE router interface).

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


# ---------------------------------------------------------------------------
# ACL Generation
# ---------------------------------------------------------------------------


def build_acl_entries(intent, vrf_name: str) -> list:
    """Translate isolation rules from intent_data into concrete ACL entry dicts."""
    intent_data = intent.intent_data
    isolation = intent_data.get("isolation", {})
    destination = intent_data.get("destination", {})
    entries = []

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

    entries.append(
        {
            "action": "deny",
            "protocol": "ip",
            "source": "any",
            "destination": "any",
            "log": True,
            "remark": f"Implicit deny -- {vrf_name} isolation",
        }
    )

    return entries


# =========================================================================
# CONNECTIVITY INTENT RESOLVER (existing, working)
# =========================================================================


@transaction.atomic
def resolve_connectivity(intent) -> dict:
    """Resolve a connectivity intent (MPLS L3VPN).

    Queries Nautobot ORM for devices, allocates RD/RT atomically,
    builds VRF + BGP + ACL primitives.
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

    devices = get_devices_for_group(source_group, source_sites, intent.tenant)
    vrf_name = generate_vrf_name(intent)
    rt_export, rt_import = allocate_route_target(intent)
    default_bgp_asn = _get_plugin_config("default_bgp_asn")

    primitives = []
    affected_device_names = []
    allocated_rds = {}

    for device in devices:
        affected_device_names.append(device.name)
        rd = allocate_route_distinguisher(device, vrf_name, intent)
        allocated_rds[device.name] = rd
        neighbor_ip = get_pe_neighbor_ip(device, vrf_name)

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

        tenant_asn = intent.intent_data.get("policy", {}).get("tenant_asn", default_bgp_asn + 1)
        primitives.append(
            {
                "primitive_type": "bgp_neighbor",
                "device": device.name,
                "vrf_name": vrf_name,
                "local_asn": default_bgp_asn,
                "neighbor_ip": neighbor_ip,
                "neighbor_asn": tenant_asn,
                "neighbor_description": (
                    f"{intent.tenant.name.upper().replace(' ', '').replace('-', '')[:8]}-{vrf_name}-PE"
                ),
                "route_map_in": f"RM-{vrf_name}-IN",
                "route_map_out": f"RM-{vrf_name}-OUT",
                "bfd_enabled": True,
                "max_prefix": 500,
            }
        )

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


# =========================================================================
# SECURITY INTENT RESOLVER (existing, working)
# =========================================================================


@transaction.atomic
def resolve_security(intent) -> dict:
    """Resolve a security/segmentation intent. Applies ACLs to devices in scope."""
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

    return _empty_plan(affected_device_names, primitives)


# =========================================================================
# 1. LAYER 2 / SWITCHING RESOLVERS
# =========================================================================


@transaction.atomic
def resolve_vlan_provision(intent) -> dict:
    """Resolve a VLAN provisioning intent."""
    intent_data = intent.intent_data
    vlans = intent_data.get("vlans", [])
    if not vlans:
        raise ValueError(f"Intent {intent.intent_id}: 'vlans' list is required for vlan_provision.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for vlan in vlans:
            primitives.append(
                {
                    "primitive_type": "vlan",
                    "device": device.name,
                    "vlan_id": vlan["id"],
                    "vlan_name": vlan.get("name", f"VLAN{vlan['id']}"),
                    "description": vlan.get("description", ""),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_l2_access_port(intent) -> dict:
    """Resolve an access port intent.

    Supports two forms:
    - Multi-port (new): ``ports`` list where each entry has ``interface`` and ``vlan_id``.
    - Single-port (legacy): top-level ``interface`` and ``vlan_id`` fields.
    Both forms are fully equivalent and backward-compatible.
    """
    intent_data = intent.intent_data

    if intent_data.get("ports"):
        port_list = intent_data["ports"]
        for i, port in enumerate(port_list):
            if not port.get("interface") or not port.get("vlan_id"):
                raise ValueError(f"Intent {intent.intent_id}: ports[{i}] must have 'interface' and 'vlan_id'.")
    else:
        interface_name = intent_data.get("interface")
        vlan_id = intent_data.get("vlan_id")
        if not interface_name or not vlan_id:
            raise ValueError(f"Intent {intent.intent_id}: 'interface' and 'vlan_id' required for l2_access_port.")
        port_list = [
            {
                "interface": interface_name,
                "vlan_id": vlan_id,
                "voice_vlan": intent_data.get("voice_vlan"),
                "description": intent_data.get("interface_description") or intent_data.get("description", ""),
                "portfast": intent_data.get("portfast", False),
                "bpdu_guard": intent_data.get("bpdu_guard", False),
            }
        ]

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for port in port_list:
            primitives.append(
                {
                    "primitive_type": "l2_port",
                    "device": device.name,
                    "interface": port["interface"],
                    "mode": "access",
                    "access_vlan": port["vlan_id"],
                    "voice_vlan": port.get("voice_vlan"),
                    "description": port.get("description", ""),
                    "portfast": port.get("portfast", False),
                    "bpdu_guard": port.get("bpdu_guard", False),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_l2_trunk_port(intent) -> dict:
    """Resolve a trunk port intent. Configures allowed VLANs on an uplink.

    Supports two forms:
    - Multi-port (new): ``ports`` list where each entry has ``interface`` and optionally
      ``allowed_vlans`` and ``native_vlan``.
    - Single-port (legacy): top-level ``interface``, ``allowed_vlans``, ``native_vlan`` fields.
    Both forms are fully equivalent and backward-compatible.
    """
    intent_data = intent.intent_data

    if intent_data.get("ports"):
        port_list = intent_data["ports"]
        for i, port in enumerate(port_list):
            if not port.get("interface"):
                raise ValueError(f"Intent {intent.intent_id}: ports[{i}] must have 'interface'.")
    else:
        interface_name = intent_data.get("interface")
        if not interface_name:
            raise ValueError(f"Intent {intent.intent_id}: 'interface' required for l2_trunk_port.")
        port_list = [
            {
                "interface": interface_name,
                "allowed_vlans": intent_data.get("allowed_vlans", []),
                "native_vlan": intent_data.get("native_vlan"),
                "description": intent_data.get("interface_description") or intent_data.get("description", ""),
            }
        ]

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for port in port_list:
            primitives.append(
                {
                    "primitive_type": "l2_port",
                    "device": device.name,
                    "interface": port["interface"],
                    "mode": "trunk",
                    "allowed_vlans": port.get("allowed_vlans", []),
                    "native_vlan": port.get("native_vlan"),
                    "description": port.get("description", ""),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_lag(intent) -> dict:
    """Resolve a LAG / port-channel intent."""
    intent_data = intent.intent_data
    member_interfaces = intent_data.get("member_interfaces", [])
    channel_id = intent_data.get("channel_id")
    if not member_interfaces or not channel_id:
        raise ValueError(f"Intent {intent.intent_id}: 'member_interfaces' and 'channel_id' required for lag.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "lag",
                "device": device.name,
                "channel_id": channel_id,
                "member_interfaces": member_interfaces,
                "lacp_mode": intent_data.get("lacp_mode", "active"),
                "mode": intent_data.get("port_mode", "trunk"),
                "allowed_vlans": intent_data.get("allowed_vlans", []),
                "mtu": intent_data.get("mtu", 9216),
                "description": intent_data.get("interface_description") or intent_data.get("description", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mlag(intent) -> dict:
    """Resolve an MLAG / MC-LAG intent. Dual-chassis LAG across two switches."""
    intent_data = intent.intent_data
    peer_link_interfaces = intent_data.get("peer_link_interfaces", [])
    domain_id = intent_data.get("domain_id")
    if not peer_link_interfaces or not domain_id:
        raise ValueError(f"Intent {intent.intent_id}: 'peer_link_interfaces' and 'domain_id' required for mlag.")

    devices = _get_scope_devices(intent)
    if len(devices) < 2:
        raise ValueError(f"Intent {intent.intent_id}: MLAG requires at least 2 devices, found {len(devices)}.")

    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "mlag",
                "device": device.name,
                "domain_id": domain_id,
                "peer_link_interfaces": peer_link_interfaces,
                "peer_address": intent_data.get("peer_address", ""),
                "keepalive_vlan": intent_data.get("keepalive_vlan"),
                "peer_link_vlan": intent_data.get("peer_link_vlan"),
                "description": intent_data.get("interface_description") or intent_data.get("description", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_stp_policy(intent) -> dict:
    """Resolve a Spanning Tree Policy intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "stp",
                "device": device.name,
                "mode": intent_data.get("stp_mode", "rapid-pvst"),
                "priority": intent_data.get("priority", 32768),
                "portfast_default": intent_data.get("portfast_default", True),
                "bpdu_guard_default": intent_data.get("bpdu_guard_default", False),
                "loopguard_default": intent_data.get("loopguard_default", False),
                "vlans": intent_data.get("vlans", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_qinq(intent) -> dict:
    """Resolve a QinQ / double tagging intent."""
    intent_data = intent.intent_data
    interface_name = intent_data.get("interface")
    outer_vlan = intent_data.get("outer_vlan")
    inner_vlans = intent_data.get("inner_vlans", [])
    if not interface_name or not outer_vlan:
        raise ValueError(f"Intent {intent.intent_id}: 'interface' and 'outer_vlan' required for qinq.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "qinq",
                "device": device.name,
                "interface": interface_name,
                "outer_vlan": outer_vlan,
                "inner_vlans": inner_vlans,
                "ethertype": intent_data.get("ethertype", "0x8100"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_pvlan(intent) -> dict:
    """Resolve a Private VLAN intent."""
    intent_data = intent.intent_data
    primary_vlan = intent_data.get("primary_vlan")
    if not primary_vlan:
        raise ValueError(f"Intent {intent.intent_id}: 'primary_vlan' required for pvlan.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "pvlan",
                "device": device.name,
                "primary_vlan": primary_vlan,
                "isolated_vlans": intent_data.get("isolated_vlans", []),
                "community_vlans": intent_data.get("community_vlans", []),
                "promiscuous_ports": intent_data.get("promiscuous_ports", []),
                "isolated_ports": intent_data.get("isolated_ports", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_storm_control(intent) -> dict:
    """Resolve a storm control intent."""
    intent_data = intent.intent_data
    interfaces = intent_data.get("interfaces", [])
    if not interfaces and intent_data.get("interface"):
        interfaces = [intent_data["interface"]]
    if not interfaces:
        raise ValueError(f"Intent {intent.intent_id}: 'interfaces' or 'interface' required for storm_control.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for iface in interfaces:
            primitives.append(
                {
                    "primitive_type": "storm_control",
                    "device": device.name,
                    "interface": iface,
                    "broadcast_level": intent_data.get("broadcast_level", 80.0),
                    "multicast_level": intent_data.get("multicast_level", 80.0),
                    "unicast_level": intent_data.get("unicast_level", 80.0),
                    "action": intent_data.get("action", "shutdown"),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_port_security(intent) -> dict:
    """Resolve a port security / MAC limit intent."""
    intent_data = intent.intent_data
    interface_name = intent_data.get("interface")
    if not interface_name:
        raise ValueError(f"Intent {intent.intent_id}: 'interface' required for port_security.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "port_security",
                "device": device.name,
                "interface": interface_name,
                "max_mac": intent_data.get("max_mac", 1),
                "violation_action": intent_data.get("violation_action", "restrict"),
                "sticky": intent_data.get("sticky", False),
                "aging_time": intent_data.get("aging_time", 0),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_dhcp_snooping(intent) -> dict:
    """Resolve a DHCP snooping intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "dhcp_snooping",
                "device": device.name,
                "vlans": intent_data.get("vlans", []),
                "trusted_interfaces": intent_data.get("trusted_interfaces", []),
                "rate_limit": intent_data.get("rate_limit", 15),
                "verify_mac": intent_data.get("verify_mac", True),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_dai(intent) -> dict:
    """Resolve a Dynamic ARP Inspection intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "dai",
                "device": device.name,
                "vlans": intent_data.get("vlans", []),
                "trusted_interfaces": intent_data.get("trusted_interfaces", []),
                "validate_src_mac": intent_data.get("validate_src_mac", True),
                "validate_dst_mac": intent_data.get("validate_dst_mac", True),
                "validate_ip": intent_data.get("validate_ip", True),
                "rate_limit": intent_data.get("rate_limit", 15),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_ip_source_guard(intent) -> dict:
    """Resolve an IP Source Guard intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for iface in intent_data.get("interfaces", []):
            primitives.append(
                {
                    "primitive_type": "ip_source_guard",
                    "device": device.name,
                    "interface": iface,
                    "mode": intent_data.get("mode", "ip"),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_macsec(intent) -> dict:
    """Resolve a MACsec intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for iface in intent_data.get("interfaces", []):
            primitives.append(
                {
                    "primitive_type": "macsec",
                    "device": device.name,
                    "interface": iface,
                    "policy_name": intent_data.get("policy_name", f"MACSEC-{intent.intent_id}"),
                    "cipher_suite": intent_data.get("cipher_suite", "GCM-AES-256"),
                    "key_chain": intent_data.get("key_chain", ""),
                    "replay_protection": intent_data.get("replay_protection", True),
                    "replay_window": intent_data.get("replay_window", 0),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


# =========================================================================
# 2. LAYER 3 / ROUTING RESOLVERS
# =========================================================================


@transaction.atomic
def resolve_static_route(intent) -> dict:
    """Resolve a static route intent."""
    intent_data = intent.intent_data
    routes = intent_data.get("routing", {}).get("routes", intent_data.get("routes", []))
    if not routes:
        raise ValueError(f"Intent {intent.intent_id}: 'routes' list required for static_route.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for route in routes:
            primitives.append(
                {
                    "primitive_type": "static_route",
                    "device": device.name,
                    "prefix": route["prefix"],
                    "next_hop": route.get("next_hop", ""),
                    "exit_interface": route.get("exit_interface", ""),
                    "admin_distance": route.get("admin_distance", 1),
                    "vrf": route.get("vrf", ""),
                    "tag": route.get("tag"),
                    "track": route.get("track"),
                    "name": route.get("name", ""),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_ospf(intent) -> dict:
    """Resolve an OSPF adjacency/area intent."""
    intent_data = intent.intent_data
    routing = intent_data.get("routing", {})
    process_id = routing.get("process_id", intent_data.get("process_id", 1))
    area = routing.get("area", intent_data.get("area", "0.0.0.0"))  # noqa: S104  — OSPF area ID, not a bind address
    interfaces = routing.get("interfaces", intent_data.get("interfaces", []))

    # Nested form expresses membership as routing.areas[{area_id, type, networks}].
    areas = routing.get("areas", [])
    networks = list(intent_data.get("networks", []))
    stub_areas = list(intent_data.get("stub_areas", []))
    nssa_areas = list(intent_data.get("nssa_areas", []))
    for a in areas:
        area_id = a.get("area_id", "0.0.0.0")  # noqa: S104
        for cidr in a.get("networks", []):
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                networks.append({"network": str(net.network_address), "wildcard": str(net.hostmask), "area": area_id})
            except ValueError:
                logger.warning("Intent %s: invalid OSPF network '%s' — skipped", intent.intent_id, cidr)
        if a.get("type") == "stub":
            stub_areas.append(area_id)
        elif a.get("type") == "nssa":
            nssa_areas.append(area_id)

    if not interfaces and not networks:
        raise ValueError(f"Intent {intent.intent_id}: 'interfaces' or 'routing.areas'/'networks' required for ospf.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "ospf",
                "device": device.name,
                "process_id": process_id,
                "router_id": intent_data.get("router_id") or routing.get("router_id", ""),
                "area": area,
                "interfaces": interfaces,
                "networks": networks,
                "stub_areas": stub_areas,
                "nssa_areas": nssa_areas,
                "reference_bandwidth": intent_data.get("reference_bandwidth") or routing.get("reference_bandwidth"),
                "default_originate": intent_data.get("default_originate", routing.get("default_originate", False)),
                "always": intent_data.get("always", routing.get("always", False)),
                "passive_default": intent_data.get("passive_default", routing.get("passive_default", False)),
                "no_passive": intent_data.get("no_passive") or routing.get("no_passive", []),
                "hello_interval": intent_data.get("hello_interval", 10),
                "dead_interval": intent_data.get("dead_interval", 40),
                "authentication": intent_data.get("authentication") or routing.get("authentication"),
                "passive_interfaces": intent_data.get("passive_interfaces") or routing.get("passive_interfaces", []),
                "redistribute": intent_data.get("redistribute", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_bgp_ebgp(intent) -> dict:
    """Resolve an external BGP peering intent."""
    intent_data = intent.intent_data
    routing = intent_data.get("routing", {})
    local_asn = intent_data.get("local_asn") or routing.get("as_number")
    neighbor_ip = intent_data.get("neighbor_ip") or routing.get("neighbors", [{}])[0].get("ip")
    neighbor_asn = intent_data.get("neighbor_asn") or routing.get("neighbors", [{}])[0].get("remote_as")
    if not local_asn or not neighbor_ip or not neighbor_asn:
        raise ValueError(
            f"Intent {intent.intent_id}: 'local_asn', 'neighbor_ip', 'neighbor_asn' required for bgp_ebgp."
        )

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "bgp_neighbor",
                "device": device.name,
                "local_asn": local_asn,
                "neighbor_ip": neighbor_ip,
                "neighbor_asn": neighbor_asn,
                "neighbor_description": intent_data.get("neighbor_description")
                or intent_data.get("description", f"eBGP-{neighbor_asn}"),
                "vrf_name": intent_data.get("vrf", ""),
                "route_map_in": intent_data.get("route_map_in", ""),
                "route_map_out": intent_data.get("route_map_out", ""),
                "prefix_list_in": intent_data.get("prefix_list_in", ""),
                "prefix_list_out": intent_data.get("prefix_list_out", ""),
                "bfd_enabled": intent_data.get("bfd", True),
                "max_prefix": intent_data.get("max_prefix", 1000),
                "timers_keepalive": intent_data.get("timers_keepalive", 60),
                "timers_hold": intent_data.get("timers_hold", 180),
                "multihop": intent_data.get("multihop"),
                "password": intent_data.get("password", ""),
                "local_preference": intent_data.get("local_preference"),
                "send_community": intent_data.get("send_community", ""),
                "maximum_paths": intent_data.get("maximum_paths"),
                "graceful_restart": intent_data.get("graceful_restart", False),
                "default_originate": intent_data.get("default_originate", False),
                "allowas_in": intent_data.get("allowas_in"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_bgp_ibgp(intent) -> dict:
    """Resolve an internal BGP peering intent."""
    intent_data = intent.intent_data
    routing = intent_data.get("routing", {})
    local_asn = intent_data.get("local_asn") or routing.get("as_number")
    neighbor_ip = intent_data.get("neighbor_ip") or routing.get("neighbors", [{}])[0].get("ip")
    if not local_asn or not neighbor_ip:
        raise ValueError(f"Intent {intent.intent_id}: 'local_asn' and 'neighbor_ip' required for bgp_ibgp.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "bgp_neighbor",
                "device": device.name,
                "local_asn": local_asn,
                "neighbor_ip": neighbor_ip,
                "neighbor_asn": local_asn,
                "neighbor_description": intent_data.get("neighbor_description")
                or intent_data.get("description", "iBGP-peer"),
                "vrf_name": intent_data.get("vrf", ""),
                "update_source": intent_data.get("update_source", "Loopback0"),
                "next_hop_self": intent_data.get("next_hop_self", True),
                "route_reflector_client": intent_data.get("route_reflector_client", False),
                "bfd_enabled": intent_data.get("bfd", True),
                "route_map_in": intent_data.get("route_map_in", ""),
                "route_map_out": intent_data.get("route_map_out", ""),
                "local_preference": intent_data.get("local_preference"),
                "send_community": intent_data.get("send_community", ""),
                "maximum_paths": intent_data.get("maximum_paths"),
                "graceful_restart": intent_data.get("graceful_restart", False),
                "default_originate": intent_data.get("default_originate", False),
                "allowas_in": intent_data.get("allowas_in"),
                "max_prefix": intent_data.get("max_prefix"),
                "timers_keepalive": intent_data.get("timers_keepalive"),
                "timers_hold": intent_data.get("timers_hold"),
                "password": intent_data.get("password", ""),
                "prefix_list_in": intent_data.get("prefix_list_in", ""),
                "prefix_list_out": intent_data.get("prefix_list_out", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_isis(intent) -> dict:
    """Resolve an IS-IS intent."""
    intent_data = intent.intent_data
    routing = intent_data.get("routing", {})  # nested form uses 'net_address'
    net_address = intent_data.get("net") or routing.get("net_address")
    if not net_address:
        raise ValueError(f"Intent {intent.intent_id}: 'net' (or 'routing.net_address') required for isis.")

    # Nested form expresses level as an int (1/2); normalise to 'level-N'.
    level = intent_data.get("level")
    if not level:
        raw_level = routing.get("level", 2)
        level = f"level-{raw_level}" if str(raw_level) in ("1", "2") else raw_level

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "isis",
                "device": device.name,
                "process_tag": intent_data.get("process_tag") or routing.get("process_id", "CORE"),
                "net": net_address,
                "level": level,
                "interfaces": intent_data.get("interfaces") or routing.get("interfaces", []),
                "passive_interfaces": intent_data.get("passive_interfaces") or routing.get("passive_interfaces", []),
                "metric_style": intent_data.get("metric_style") or routing.get("metric_style", "wide"),
                "authentication": intent_data.get("authentication") or routing.get("authentication"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_eigrp(intent) -> dict:
    """Resolve an EIGRP intent."""
    intent_data = intent.intent_data
    routing = intent_data.get("routing", {})  # nested form
    as_number = intent_data.get("as_number") or routing.get("as_number")
    networks = intent_data.get("networks") or routing.get("networks", [])
    if not as_number or not networks:
        raise ValueError(
            f"Intent {intent.intent_id}: 'as_number' and 'networks' (or under 'routing') required for eigrp."
        )

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "eigrp",
                "device": device.name,
                "as_number": as_number,
                "networks": networks,
                "router_id": intent_data.get("router_id") or routing.get("router_id", ""),
                "stub": intent_data.get("stub", routing.get("stub")),
                "passive_interfaces": intent_data.get("passive_interfaces") or routing.get("passive_interfaces", []),
                "redistribute": intent_data.get("redistribute") or routing.get("redistribute", []),
                "authentication": routing.get("authentication"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_route_redistribution(intent) -> dict:
    """Resolve a route redistribution intent."""
    intent_data = intent.intent_data
    # Nested form: routing.redistribution = [{from, into, process_id, as_number, route_map, ...}]
    entries = intent_data.get("routing", {}).get("redistribution", [])

    # Legacy flat single form.
    if not entries and intent_data.get("source_protocol") and intent_data.get("dest_protocol"):
        entries = [
            {
                "from": intent_data["source_protocol"],
                "into": intent_data["dest_protocol"],
                "process_id": intent_data.get("dest_process") or intent_data.get("source_process"),
                "metric": intent_data.get("metric"),
                "metric_type": intent_data.get("metric_type"),
                "route_map": intent_data.get("route_map", ""),
            }
        ]

    if not entries:
        raise ValueError(
            f"Intent {intent.intent_id}: 'routing.redistribution' (or legacy 'source_protocol'/'dest_protocol') required."
        )

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for entry in entries:
            primitives.append(
                {
                    "primitive_type": "route_redistribution",
                    "device": device.name,
                    "source_protocol": entry.get("from"),
                    "dest_protocol": entry.get("into"),
                    "process_id": entry.get("process_id"),
                    "as_number": entry.get("as_number"),
                    "metric": entry.get("metric"),
                    "metric_type": entry.get("metric_type"),
                    "route_map": entry.get("route_map", ""),
                    "subnets": entry.get("subnets", True),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_route_policy(intent) -> dict:
    """Resolve a route policy / route-map intent."""
    intent_data = intent.intent_data
    routing = intent_data.get("routing", {})
    policy_name = intent_data.get("policy_name") or routing.get("policy_name")
    entries = intent_data.get("entries") or routing.get("entries", [])
    if not policy_name or not entries:
        raise ValueError(f"Intent {intent.intent_id}: 'policy_name' and 'entries' required for route_policy.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "route_policy",
                "device": device.name,
                "policy_name": policy_name,
                "entries": entries,
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_prefix_list(intent) -> dict:
    """Resolve a prefix list intent."""
    intent_data = intent.intent_data
    prefix_lists = intent_data.get("routing", {}).get("prefix_lists", [])
    if not prefix_lists:
        raise ValueError(f"Intent {intent.intent_id}: 'routing.prefix_lists' required for prefix_list.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for pl in prefix_lists:
            primitives.append(
                {
                    "primitive_type": "prefix_list",
                    "device": device.name,
                    "list_name": pl["name"],
                    "address_family": intent_data.get("address_family", "ipv4"),
                    "entries": pl.get("entries", []),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_vrf_basic(intent) -> dict:
    """Resolve a VRF (non-MPLS) intent for segmentation."""
    intent_data = intent.intent_data
    # Nested form: routing.vrfs = [{name, description, rd, address_families, interfaces}]
    vrfs = intent_data.get("routing", {}).get("vrfs", [])

    # Legacy flat single-VRF form.
    if not vrfs and intent_data.get("vrf_name"):
        vrfs = [
            {
                "name": intent_data["vrf_name"],
                "rd": intent_data.get("rd", ""),
                "rt_export": intent_data.get("rt_export", ""),
                "rt_import": intent_data.get("rt_import", ""),
                "description": intent_data.get("description"),
                "interfaces": intent_data.get("interfaces", []),
            }
        ]

    if not vrfs:
        raise ValueError(f"Intent {intent.intent_id}: 'routing.vrfs' (or legacy 'vrf_name') required for vrf_basic.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for vrf in vrfs:
            name = vrf["name"]
            primitives.append(
                {
                    "primitive_type": "vrf",
                    "device": device.name,
                    "vrf_name": name,
                    "route_distinguisher": vrf.get("rd", ""),
                    "rt_export": vrf.get("rt_export", ""),
                    "rt_import": vrf.get("rt_import", ""),
                    "address_families": vrf.get("address_families", []),
                    "description": vrf.get("description") or f"VRF {name} via intent",
                    "interfaces": vrf.get("interfaces", []),
                    "redistribute_connected": vrf.get("redistribute_connected", False),
                    "redistribute_static": vrf.get("redistribute_static", False),
                    "intent_id": intent.intent_id,
                }
            )

    return {
        "affected_devices": affected,
        "vrf_name": vrfs[0]["name"],
        "requires_new_vrf": True,
        "requires_mpls": False,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


@transaction.atomic
def resolve_bfd(intent) -> dict:
    """Resolve a BFD intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "bfd",
                "device": device.name,
                "interval": intent_data.get("interval", 300),
                "min_rx": intent_data.get("min_rx", 300),
                "multiplier": intent_data.get("multiplier", 3),
                "interfaces": intent_data.get("interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_pbr(intent) -> dict:
    """Resolve a Policy-Based Routing intent."""
    intent_data = intent.intent_data
    policy_name = intent_data.get("policy_name")
    if not policy_name:
        raise ValueError(f"Intent {intent.intent_id}: 'policy_name' required for pbr.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "pbr",
                "device": device.name,
                "policy_name": policy_name,
                "entries": intent_data.get("entries", []),
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_ipv6_dual_stack(intent) -> dict:
    """Resolve an IPv6 dual-stack interface intent."""
    intent_data = intent.intent_data
    interfaces = intent_data.get("interfaces", [])
    if not interfaces:
        raise ValueError(f"Intent {intent.intent_id}: 'interfaces' list required for ipv6_dual_stack.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for iface_cfg in interfaces:
            primitives.append(
                {
                    "primitive_type": "ipv6_interface",
                    "device": device.name,
                    "interface": iface_cfg["name"],
                    "ipv6_address": iface_cfg.get("ipv6_address", ""),
                    "ipv6_eui64": iface_cfg.get("eui64", False),
                    "ipv6_link_local": iface_cfg.get("link_local", ""),
                    "ra_suppress": iface_cfg.get("ra_suppress", False),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_ospfv3(intent) -> dict:
    """Resolve an OSPFv3 (IPv6) intent."""
    intent_data = intent.intent_data
    routing = intent_data.get("routing", {})  # nested form
    process_id = intent_data.get("process_id") or routing.get("process_id", 1)
    # Nested form expresses areas as a list; fall back to the first area id.
    area = intent_data.get("area")
    if not area:
        areas = routing.get("areas", [])
        area = areas[0].get("area_id", "0.0.0.0") if areas else "0.0.0.0"  # noqa: S104

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "ospfv3",
                "device": device.name,
                "process_id": process_id,
                "router_id": intent_data.get("router_id") or routing.get("router_id", ""),
                "area": area,
                "address_family": intent_data.get("address_family", "ipv6"),
                "interfaces": intent_data.get("interfaces") or routing.get("interfaces", []),
                "passive_interfaces": intent_data.get("passive_interfaces") or routing.get("passive_interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_bgp_ipv6_af(intent) -> dict:
    """Resolve a BGP IPv6 address family intent."""
    intent_data = intent.intent_data
    # Nested form: routing.{as_number, address_families.ipv6_unicast.{neighbors,networks,redistribute}}
    routing = intent_data.get("routing", {})
    ipv6_af = routing.get("address_families", {}).get("ipv6_unicast", {})
    local_asn = intent_data.get("local_asn") or routing.get("as_number")
    if not local_asn:
        raise ValueError(f"Intent {intent.intent_id}: 'local_asn' (or 'routing.as_number') required for bgp_ipv6_af.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "bgp_ipv6_af",
                "device": device.name,
                "local_asn": local_asn,
                "router_id": intent_data.get("router_id") or routing.get("router_id", ""),
                "neighbors": intent_data.get("neighbors") or ipv6_af.get("neighbors", []),
                "networks": intent_data.get("networks") or ipv6_af.get("networks", []),
                "redistribute": intent_data.get("redistribute") or ipv6_af.get("redistribute", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_fhrp(intent) -> dict:
    """Resolve an FHRP (HSRP/VRRP/GLBP) intent.

    Canonical form: ``fhrp.groups[{vlan|interface, group_id, virtual_ip,
    active_priority, standby_priority, preempt, preempt_delay, track[]}]``.
    The first in-scope device is treated as active (gets ``active_priority``);
    the rest are standby. Emits the ``groups`` list consumed by ``fhrp.j2``.
    """
    intent_data = intent.intent_data
    fhrp = intent_data.get("fhrp", {})
    protocol = fhrp.get("protocol") or intent_data.get("protocol", "hsrp")
    version = fhrp.get("version") or intent_data.get("version", 2)
    groups_in = fhrp.get("groups", [])

    # Legacy flat single-group form.
    if not groups_in and intent_data.get("group_id") and intent_data.get("virtual_ip") and intent_data.get("interface"):
        prios = intent_data.get("priorities", [110, 100])
        groups_in = [
            {
                "group_id": intent_data["group_id"],
                "virtual_ip": intent_data["virtual_ip"],
                "interface": intent_data["interface"],
                "active_priority": prios[0] if prios else 110,
                "standby_priority": prios[1] if len(prios) > 1 else 100,
                "preempt": intent_data.get("preempt", True),
            }
        ]

    if not groups_in:
        raise ValueError(
            f"Intent {intent.intent_id}: 'fhrp.groups' (or legacy group_id/virtual_ip/interface) required for fhrp."
        )

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for idx, device in enumerate(devices):
        affected.append(device.name)
        is_active = idx == 0
        groups_out = []
        for g in groups_in:
            iface = g.get("interface") or (f"Vlan{g['vlan']}" if g.get("vlan") else "")
            priority = g.get("active_priority") if is_active else g.get("standby_priority")
            if priority is None:
                priority = g.get("priority", 100)
            # Track may be a list of {interface, decrement} or a legacy scalar.
            track_iface, track_decr = "", 10
            track = g.get("track")
            if isinstance(track, list) and track:
                track_iface = track[0].get("interface", "")
                track_decr = track[0].get("decrement", 10)
            elif isinstance(track, str):
                track_iface, track_decr = track, g.get("decrement", 10)
            groups_out.append(
                {
                    "interface": iface,
                    "group_id": g.get("group_id"),
                    "virtual_ip": g.get("virtual_ip"),
                    "priority": priority,
                    "preempt": g.get("preempt", True),
                    "preempt_delay": g.get("preempt_delay"),
                    "track": track_iface,
                    "decrement": track_decr,
                    "authentication": g.get("authentication"),
                }
            )
        primitives.append(
            {
                "primitive_type": "fhrp",
                "device": device.name,
                "protocol": protocol,
                "version": version,
                "groups": groups_out,
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


# =========================================================================
# 3. MPLS & SERVICE PROVIDER RESOLVERS
# =========================================================================


@transaction.atomic
def resolve_mpls_l3vpn(intent) -> dict:
    """Resolve an MPLS L3VPN intent into per-PE VRF primitives.

    The VRF (with RD/RT and redistribution) is emitted per PE device using the
    existing ``vrf`` primitive/template. CE-facing routing is configured
    separately by dedicated routing intents.
    """
    intent_data = intent.intent_data
    vrf_name = intent_data.get("vrf_name")
    if not vrf_name:
        raise ValueError(f"Intent {intent.intent_id}: 'vrf_name' required for mpls_l3vpn.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "vrf",
                "device": device.name,
                "vrf_name": vrf_name,
                "route_distinguisher": intent_data.get("rd", ""),
                "rt_export": intent_data.get("rt_export", ""),
                "rt_import": intent_data.get("rt_import", ""),
                "redistribute_connected": intent_data.get("redistribute_connected", False),
                "redistribute_static": intent_data.get("redistribute_static", False),
                "description": f"MPLS L3VPN {vrf_name} via intent {intent.intent_id}",
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": vrf_name,
        "requires_new_vrf": True,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


@transaction.atomic
def resolve_mpls_l2vpn(intent) -> dict:
    """Resolve an MPLS L2VPN / VPLS intent."""
    intent_data = intent.intent_data
    vpls_instance = intent_data.get("vpls_instance")
    if not vpls_instance:
        raise ValueError(f"Intent {intent.intent_id}: 'vpls_instance' required for mpls_l2vpn.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "l2vpn_vpls",
                "device": device.name,
                "vpls_instance": vpls_instance,
                "vpn_id": intent_data.get("vpn_id"),
                "bridge_domain": intent_data.get("bridge_domain", ""),
                "pw_class": intent_data.get("pw_class", ""),
                "mtu": intent_data.get("mtu", 1500),
                "mac_limit": intent_data.get("mac_limit"),
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


@transaction.atomic
def resolve_pseudowire(intent) -> dict:
    """Resolve a pseudowire / EoMPLS intent."""
    intent_data = intent.intent_data
    pw_id = intent_data.get("pw_id")
    remote_pe = intent_data.get("remote_pe")
    if not pw_id or not remote_pe:
        raise ValueError(f"Intent {intent.intent_id}: 'pw_id' and 'remote_pe' required for pseudowire.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "pseudowire",
                "device": device.name,
                "pw_id": pw_id,
                "remote_pe": remote_pe,
                "encapsulation": intent_data.get("encapsulation", "mpls"),
                "interface": intent_data.get("interface", ""),
                "vlan": intent_data.get("vlan"),
                "mtu": intent_data.get("mtu", 1500),
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


@transaction.atomic
def resolve_evpn_mpls(intent) -> dict:
    """Resolve an EVPN over MPLS intent."""
    intent_data = intent.intent_data
    evi = intent_data.get("evi")
    if not evi:
        raise ValueError(f"Intent {intent.intent_id}: 'evi' (EVPN Instance) required for evpn_mpls.")

    devices = _get_scope_devices(intent)
    rt_export, rt_import = allocate_route_target(intent)
    primitives = []
    affected = []
    allocated_rds = {}

    for device in devices:
        affected.append(device.name)
        rd = allocate_route_distinguisher(device, f"EVI-{evi}", intent)
        allocated_rds[device.name] = rd
        primitives.append(
            {
                "primitive_type": "evpn_mpls",
                "device": device.name,
                "evi": evi,
                "rd": rd,
                "rt_export": rt_export,
                "rt_import": rt_import,
                "esi": intent_data.get("esi", ""),
                "encapsulation": "mpls",
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": allocated_rds,
        "allocated_rts": {"export": rt_export, "import": rt_import},
    }


@transaction.atomic
def resolve_ldp(intent) -> dict:
    """Resolve an LDP intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "ldp",
                "device": device.name,
                "router_id": intent_data.get("router_id", ""),
                "interfaces": intent_data.get("interfaces", []),
                "targeted_sessions": intent_data.get("targeted_sessions", []),
                "label_allocation": intent_data.get("label_allocation", "default"),
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


@transaction.atomic
def resolve_rsvp_te(intent) -> dict:
    """Resolve an RSVP-TE tunnel intent."""
    intent_data = intent.intent_data
    tunnel_dest = intent_data.get("tunnel_destination")
    if not tunnel_dest:
        raise ValueError(f"Intent {intent.intent_id}: 'tunnel_destination' required for rsvp_te.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        tunnel_id = allocate_tunnel_id(device, intent, "rsvp")
        primitives.append(
            {
                "primitive_type": "rsvp_te_tunnel",
                "device": device.name,
                "tunnel_id": tunnel_id,
                "tunnel_destination": tunnel_dest,
                "bandwidth": intent_data.get("bandwidth", ""),
                "path_option": intent_data.get("path_option", "dynamic"),
                "setup_priority": intent_data.get("setup_priority", 7),
                "hold_priority": intent_data.get("hold_priority", 7),
                "affinity": intent_data.get("affinity"),
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


@transaction.atomic
def resolve_sr_mpls(intent) -> dict:
    """Resolve a Segment Routing MPLS intent."""
    intent_data = intent.intent_data
    srgb_start = intent_data.get("srgb_start", 16000)
    srgb_end = intent_data.get("srgb_end", 23999)

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "sr_mpls",
                "device": device.name,
                "srgb_start": srgb_start,
                "srgb_end": srgb_end,
                "prefix_sid": intent_data.get("prefix_sids", {}).get(device.name),
                "adjacency_sids": intent_data.get("adjacency_sids", {}).get(device.name, []),
                "ti_lfa": intent_data.get("ti_lfa", True),
                "ti_lfa_mode": intent_data.get("ti_lfa_mode", ""),
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


@transaction.atomic
def resolve_srv6(intent) -> dict:
    """Resolve an SRv6 intent."""
    intent_data = intent.intent_data
    locator_block = intent_data.get("locator_block")
    if not locator_block:
        raise ValueError(f"Intent {intent.intent_id}: 'locator_block' required for srv6.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "srv6",
                "device": device.name,
                "locator_name": intent_data.get("locator_name", "MAIN"),
                "locator_block": locator_block,
                "function_length": intent_data.get("function_length", 16),
                "encapsulation": intent_data.get("encapsulation", "reduced"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_6pe_6vpe(intent) -> dict:
    """Resolve a 6PE/6VPE intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "6pe_6vpe",
                "device": device.name,
                "mode": intent_data.get("mode", "6pe"),
                "vrf": intent_data.get("vrf", ""),
                "ipv6_networks": intent_data.get("ipv6_networks", []),
                "neighbor_ip": intent_data.get("neighbor_ip", ""),
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": intent_data.get("vrf", ""),
        "requires_new_vrf": False,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


@transaction.atomic
def resolve_mvpn(intent) -> dict:
    """Resolve a multicast VPN (mVPN) intent."""
    intent_data = intent.intent_data
    vrf_name = intent_data.get("vrf")
    mdt_group = intent_data.get("mdt_default_group")
    if not vrf_name or not mdt_group:
        raise ValueError(f"Intent {intent.intent_id}: 'vrf' and 'mdt_default_group' required for mvpn.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "mvpn",
                "device": device.name,
                "vrf": vrf_name,
                "mdt_default_group": mdt_group,
                "mdt_data_group": intent_data.get("mdt_data_group", ""),
                "mdt_data_threshold": intent_data.get("mdt_data_threshold"),
                "pim_mode": intent_data.get("pim_mode", "sparse-mode"),
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": vrf_name,
        "requires_new_vrf": False,
        "requires_mpls": True,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


# =========================================================================
# 4. DATA CENTRE / EVPN / VXLAN RESOLVERS
# =========================================================================


@transaction.atomic
def resolve_evpn_vxlan_fabric(intent) -> dict:
    """Resolve a full VXLAN EVPN fabric intent.

    Allocates loopback IPs for underlay and VNIs for overlay.
    """
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        loopback_ip = allocate_loopback_ip(device, intent)
        l2_vni = allocate_vxlan_vni(intent, "l2")
        l3_vni = allocate_vxlan_vni(intent, "l3")

        # Underlay loopback
        primitives.append(
            {
                "primitive_type": "loopback",
                "device": device.name,
                "interface": "Loopback0",
                "ip_address": f"{loopback_ip}/32",
                "description": "VTEP Source -- fabric underlay",
                "intent_id": intent.intent_id,
            }
        )

        # VTEP NVE interface
        primitives.append(
            {
                "primitive_type": "vtep",
                "device": device.name,
                "nve_interface": "nve1",
                "source_interface": "Loopback0",
                "l2_vni": l2_vni,
                "l3_vni": l3_vni,
                "replication_mode": intent_data.get("replication_mode", "ingress-replication"),
                "intent_id": intent.intent_id,
            }
        )

        # BGP EVPN address family
        fabric = intent_data.get("fabric", {})
        primitives.append(
            {
                "primitive_type": "bgp_evpn_af",
                "device": device.name,
                "local_asn": (
                    intent_data.get("local_asn") or fabric.get("overlay_asn") or _get_plugin_config("default_bgp_asn")
                ),
                "advertise_all_vni": True,
                "route_target_auto": True,
                "neighbors": intent_data.get("evpn_neighbors", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_l2vni(intent) -> dict:
    """Resolve an L2VNI provisioning intent."""
    intent_data = intent.intent_data
    vlan_id = intent_data.get("vlan_id") or intent_data.get("vni", {}).get("vlan_id")
    if not vlan_id:
        raise ValueError(f"Intent {intent.intent_id}: 'vlan_id' (or 'vni.vlan_id') required for l2vni.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        vni = allocate_vxlan_vni(intent, "l2")
        primitives.append(
            {
                "primitive_type": "l2vni",
                "device": device.name,
                "vlan_id": vlan_id,
                "vni": vni,
                "vlan_name": intent_data.get("vlan_name", f"L2VNI-{vni}"),
                "replication_mode": intent_data.get("replication_mode", "ingress-replication"),
                "mcast_group": intent_data.get("mcast_group", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_l3vni(intent) -> dict:
    """Resolve an L3VNI / IP VRF over VXLAN intent."""
    intent_data = intent.intent_data
    # Nested form: dc.l3vni.{vrf_name, vni, rd, rt_import, rt_export, vlan_id, svi.{...}}
    l3 = intent_data.get("dc", {}).get("l3vni", {})
    vrf_name = intent_data.get("vrf_name") or intent_data.get("vni", {}).get("vrf_name") or l3.get("vrf_name")
    if not vrf_name:
        raise ValueError(f"Intent {intent.intent_id}: 'vrf_name' (or 'dc.l3vni.vrf_name') required for l3vni.")

    # Honour an explicitly-specified VNI; otherwise allocate one.
    vni = intent_data.get("vni_id") or l3.get("vni") or allocate_vxlan_vni(intent, "l3")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "l3vni",
                "device": device.name,
                "vrf_name": vrf_name,
                "vni": vni,
                "vlan_id": intent_data.get("transit_vlan") or l3.get("vlan_id") or (3900 + (vni % 100)),
                "anycast_gateway_mac": intent_data.get("anycast_gateway_mac", "0000.0000.0001"),
                "redistribute_connected": intent_data.get("redistribute_connected", True),
                "rd": l3.get("rd", ""),
                "rt_import": l3.get("rt_import", []),
                "rt_export": l3.get("rt_export", []),
                "intent_id": intent.intent_id,
            }
        )

    return {
        "affected_devices": affected,
        "vrf_name": vrf_name,
        "requires_new_vrf": True,
        "requires_mpls": False,
        "primitives": primitives,
        "allocated_rds": {},
        "allocated_rts": {},
    }


@transaction.atomic
def resolve_bgp_evpn_af(intent) -> dict:
    """Resolve a BGP EVPN address family intent."""
    intent_data = intent.intent_data
    # Nested form: routing.{as_number, router_id, address_families.l2vpn_evpn.{neighbors:[...]}}
    routing = intent_data.get("routing", {})
    evpn_af = routing.get("address_families", {}).get("l2vpn_evpn", {})
    local_asn = intent_data.get("local_asn") or routing.get("as_number")
    if not local_asn:
        raise ValueError(f"Intent {intent.intent_id}: 'local_asn' (or 'routing.as_number') required for bgp_evpn_af.")

    neighbors = intent_data.get("neighbors") or evpn_af.get("neighbors", [])
    router_id = intent_data.get("router_id") or routing.get("router_id", "")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "bgp_evpn_af",
                "device": device.name,
                "local_asn": local_asn,
                "router_id": router_id,
                "neighbors": neighbors,
                "advertise_all_vni": intent_data.get("advertise_all_vni", True),
                "route_target_auto": intent_data.get("route_target_auto", True),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_anycast_gateway(intent) -> dict:
    """Resolve an anycast gateway intent."""
    intent_data = intent.intent_data
    # Nested form: dc.anycast_gateway.{mac, svls/svis:[{vlan, ip, vni}]}
    ag = intent_data.get("dc", {}).get("anycast_gateway", {})
    anycast_mac = ag.get("mac") or intent_data.get("anycast_mac", "0000.0000.0001")
    svis = ag.get("svls") or ag.get("svis") or []

    # Legacy flat single-SVI form.
    if not svis and intent_data.get("virtual_ip") and intent_data.get("vlan_id"):
        svis = [{"vlan": intent_data["vlan_id"], "ip": intent_data["virtual_ip"]}]

    if not svis:
        raise ValueError(
            f"Intent {intent.intent_id}: anycast_gateway requires 'dc.anycast_gateway.svls' "
            f"(or legacy 'virtual_ip' + 'vlan_id')."
        )

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for svi in svis:
            primitives.append(
                {
                    "primitive_type": "anycast_gateway",
                    "device": device.name,
                    "vlan_id": svi.get("vlan"),
                    "virtual_ip": svi.get("ip"),
                    "vni": svi.get("vni"),
                    "subnet_mask": intent_data.get("subnet_mask", "255.255.255.0"),
                    "anycast_mac": anycast_mac,
                    "vrf": svi.get("vrf", intent_data.get("vrf", "")),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_vtep(intent) -> dict:
    """Resolve a VTEP configuration intent."""
    intent_data = intent.intent_data
    # Nested form: dc.vtep.{source_interface, udp_port, flood_mode, ingress_replication.{...}, vni_map:[...]}
    vtep = intent_data.get("dc", {}).get("vtep", {})
    ingress_replication = vtep.get("ingress_replication", {}).get("enabled")
    replication_mode = intent_data.get("replication_mode")
    if not replication_mode:
        replication_mode = (
            "ingress-replication" if ingress_replication else (vtep.get("flood_mode") or "ingress-replication")
        )
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "vtep",
                "device": device.name,
                "nve_interface": intent_data.get("nve_interface", "nve1"),
                "source_interface": intent_data.get("source_interface") or vtep.get("source_interface", "Loopback0"),
                "vni_map": intent_data.get("vni_map") or vtep.get("vni_map", []),
                "udp_port": vtep.get("udp_port", 4789),
                "replication_mode": replication_mode,
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_evpn_multisite(intent) -> dict:
    """Resolve a multi-site EVPN intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "evpn_multisite",
                "device": device.name,
                "site_id": intent_data.get("site_id"),
                "dci_interface": intent_data.get("dci_interface", ""),
                "bgp_peers": intent_data.get("bgp_peers", []),
                "anycast_gateway_mac": intent_data.get("anycast_gateway_mac", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_dc_underlay(intent) -> dict:
    """Resolve a DC underlay (OSPF/BGP) intent.

    Allocates loopback IPs and configures point-to-point links + routing.
    """
    intent_data = intent.intent_data
    # Nested form: dc.underlay.{protocol, bgp.{as_base,...}, loopback.{interface}, ...}
    underlay = intent_data.get("dc", {}).get("underlay", {})
    underlay_bgp = underlay.get("bgp", {})
    underlay_protocol = intent_data.get("protocol") or underlay.get("protocol", "ospf")
    loopback_intf = intent_data.get("loopback_interface") or underlay.get("loopback", {}).get("interface", "Loopback0")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        loopback_ip = allocate_loopback_ip(device, intent)

        primitives.append(
            {
                "primitive_type": "loopback",
                "device": device.name,
                "interface": loopback_intf,
                "ip_address": f"{loopback_ip}/32",
                "description": "DC underlay router-ID",
                "intent_id": intent.intent_id,
            }
        )

        if underlay_protocol == "ospf":
            primitives.append(
                {
                    "primitive_type": "ospf",
                    "device": device.name,
                    "process_id": intent_data.get("process_id", 1),
                    "area": intent_data.get("area", "0.0.0.0"),  # noqa: S104  — OSPF area ID
                    "router_id": loopback_ip,
                    "interfaces": intent_data.get("interfaces", []),
                    "intent_id": intent.intent_id,
                }
            )
        else:
            primitives.append(
                {
                    "primitive_type": "bgp_neighbor",
                    "device": device.name,
                    "local_asn": (
                        intent_data.get("local_asn")
                        or underlay_bgp.get("as_base")
                        or _get_plugin_config("default_bgp_asn")
                    ),
                    "neighbors": intent_data.get("neighbors", []),
                    "router_id": loopback_ip,
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_dc_mlag(intent) -> dict:
    """Resolve an MLAG in DC fabric intent."""
    return resolve_mlag(intent)


# =========================================================================
# 5. SECURITY & FIREWALLING RESOLVERS
# =========================================================================


@transaction.atomic
def resolve_fw_rule(intent) -> dict:
    """Resolve a firewall rule intent into vendor-neutral primitives.

    Expected intent_data keys:
        policy_name (str):  Name of the firewall policy / rule-set.
        rules (list[dict]): Ordered list of firewall rule dicts, each with:
            - name (str):          Rule/entry name.
            - action (str):        "permit" | "deny" | "drop" | "reject".
            - source (str):        Source address / CIDR / object-group / "any".
            - destination (str):   Destination address / CIDR / object-group / "any".
            - protocol (str):      "tcp" | "udp" | "icmp" | "ip" | …
            - port (int|str):      Destination port or port-range (optional).
            - source_port (int|str): Source port (optional).
            - log (bool):          Enable logging (default False).
            - description (str):   Human-readable rule description (optional).
        default_action (str): Policy default action: "deny" | "permit" (default "deny").
        address_family (str): "ipv4" | "ipv6" | "dual" (default "ipv4").
        apply_interfaces (list): Interfaces to bind the policy to (optional).
        direction (str):  "in" | "out" | "both" (default "in").
        firewall_type (str): "stateful" | "stateless" (default "stateful").
    """
    intent_data = intent.intent_data
    policy_name = intent_data.get("policy_name")
    if not policy_name:
        raise ValueError(f"Intent {intent.intent_id}: 'policy_name' required for fw_rule.")

    rules = intent_data.get("rules", [])
    if not rules:
        raise ValueError(f"Intent {intent.intent_id}: 'rules' list required for fw_rule (got empty/missing).")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "fw_rule",
                "device": device.name,
                "policy_name": policy_name,
                "rules": rules,
                "default_action": intent_data.get("default_action", "deny"),
                "address_family": intent_data.get("address_family", "ipv4"),
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "direction": intent_data.get("direction", "in"),
                "firewall_type": intent_data.get("firewall_type", "stateful"),
                "intent_id": intent.intent_id,
                "intent_version": intent.version,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_acl(intent) -> dict:
    """Resolve an ACL intent (extended, with IPv6 and object-group support)."""
    intent_data = intent.intent_data
    acl_name = intent_data.get("acl_name")
    if not acl_name:
        raise ValueError(f"Intent {intent.intent_id}: 'acl_name' required for acl.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    entries = intent_data.get("entries", [])
    if not entries:
        entries = build_acl_entries(intent, acl_name)

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "acl",
                "device": device.name,
                "acl_name": acl_name,
                "acl_type": intent_data.get("acl_type", "extended"),
                "address_family": intent_data.get("address_family", "ipv4"),
                "entries": entries,
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "direction": intent_data.get("direction", "in"),
                "intent_id": intent.intent_id,
                "intent_version": intent.version,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_zbf(intent) -> dict:
    """Resolve a Zone-Based Firewall intent."""
    intent_data = intent.intent_data
    zone_pairs = intent_data.get("zone_pairs", [])
    if not zone_pairs:
        raise ValueError(f"Intent {intent.intent_id}: 'zone_pairs' required for zbf.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "zbf",
                "device": device.name,
                "zones": intent_data.get("zones", []),
                "zone_pairs": zone_pairs,
                "class_maps": intent_data.get("class_maps", []),
                "policy_maps": intent_data.get("policy_maps", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_ipsec_s2s(intent) -> dict:
    """Resolve an IPSec site-to-site tunnel intent."""
    intent_data = intent.intent_data
    # Nested form: tunnel.{local_endpoint, remote_endpoint, ike_version, encryption,
    # integrity, dh_group, lifetime_seconds, pfs_group}
    tunnel = intent_data.get("tunnel", {})
    remote_peer = intent_data.get("remote_peer") or tunnel.get("remote_endpoint")
    if not remote_peer:
        raise ValueError(
            f"Intent {intent.intent_id}: 'remote_peer' (or 'tunnel.remote_endpoint') required for ipsec_s2s."
        )

    # Devices come from an explicit scope, or — for endpoint-addressed tunnels —
    # the device that owns tunnel.local_endpoint.
    if intent_data.get("scope"):
        devices = _get_scope_devices(intent)
    else:
        local_endpoint = intent_data.get("local_endpoint") or tunnel.get("local_endpoint")
        devices = _devices_by_ip(intent, local_endpoint)
        if not devices:
            raise ValueError(
                f"Intent {intent.intent_id}: no 'scope' set and no active device owns "
                f"tunnel.local_endpoint '{local_endpoint}'. Set scope.devices or register "
                f"the endpoint IP on a device interface in Nautobot."
            )
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        tunnel_id = allocate_tunnel_id(device, intent, "ipsec")
        primitives.append(
            {
                "primitive_type": "ipsec_tunnel",
                "device": device.name,
                "tunnel_id": tunnel_id,
                "remote_peer": remote_peer,
                "local_endpoint": intent_data.get("local_endpoint") or tunnel.get("local_endpoint", ""),
                "ike_version": intent_data.get("ike_version") or tunnel.get("ike_version", 2),
                "encryption": intent_data.get("encryption") or tunnel.get("encryption", "aes-256-gcm"),
                "integrity": intent_data.get("integrity") or tunnel.get("integrity", "sha256"),
                "dh_group": intent_data.get("dh_group") or tunnel.get("dh_group", 14),
                "lifetime": intent_data.get("lifetime") or tunnel.get("lifetime_seconds", 86400),
                "psk": intent_data.get("psk", ""),
                "local_network": intent_data.get("local_network", ""),
                "remote_network": intent_data.get("remote_network", ""),
                "pfs_group": intent_data.get("pfs_group") or tunnel.get("pfs_group", 14),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_ipsec_ikev2(intent) -> dict:
    """Resolve an IPSec with IKEv2 intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "ipsec_ikev2",
                "device": device.name,
                "proposal_name": intent_data.get("proposal_name", f"IKEV2-{intent.intent_id}"),
                "encryption": intent_data.get("encryption", "aes-cbc-256"),
                "integrity": intent_data.get("integrity", "sha256"),
                "dh_group": intent_data.get("dh_group", 14),
                "prf": intent_data.get("prf", "sha256"),
                "policy_name": intent_data.get("policy_name", ""),
                "keyring_name": intent_data.get("keyring_name", ""),
                "profile_name": intent_data.get("profile_name", ""),
                "peers": intent_data.get("peers", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_gre_tunnel(intent) -> dict:
    """Resolve a GRE tunnel intent."""
    intent_data = intent.intent_data
    tunnel_dest = intent_data.get("tunnel_destination") or intent_data.get("tunnel", {}).get("remote_endpoint")
    tunnel_source = intent_data.get("tunnel_source") or intent_data.get("tunnel", {}).get("local_endpoint")
    if not tunnel_dest or not tunnel_source:
        raise ValueError(
            f"Intent {intent.intent_id}: 'tunnel_destination' and 'tunnel_source' required for gre_tunnel."
        )

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        tunnel_id = allocate_tunnel_id(device, intent, "gre")
        primitives.append(
            {
                "primitive_type": "gre_tunnel",
                "device": device.name,
                "tunnel_id": tunnel_id,
                "tunnel_source": tunnel_source,
                "tunnel_destination": tunnel_dest,
                "ip_address": intent_data.get("tunnel_ip", ""),
                "keepalive": intent_data.get("keepalive", 10),
                "mtu": intent_data.get("mtu", 1400),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_gre_over_ipsec(intent) -> dict:
    """Resolve a GRE over IPSec intent."""
    intent_data = intent.intent_data
    tunnel_dest = intent_data.get("tunnel_destination")
    if not tunnel_dest:
        raise ValueError(f"Intent {intent.intent_id}: 'tunnel_destination' required for gre_over_ipsec.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        tunnel_id = allocate_tunnel_id(device, intent, "gre")
        primitives.append(
            {
                "primitive_type": "gre_tunnel",
                "device": device.name,
                "tunnel_id": tunnel_id,
                "tunnel_source": intent_data.get("tunnel_source", ""),
                "tunnel_destination": tunnel_dest,
                "ip_address": intent_data.get("tunnel_ip", ""),
                "ipsec_profile": intent_data.get("ipsec_profile", f"IPSEC-PROF-{intent.intent_id}"),
                "intent_id": intent.intent_id,
            }
        )
        primitives.append(
            {
                "primitive_type": "ipsec_tunnel",
                "device": device.name,
                "tunnel_id": tunnel_id,
                "remote_peer": tunnel_dest,
                "ike_version": intent_data.get("ike_version", 2),
                "encryption": intent_data.get("encryption", "aes-256-gcm"),
                "integrity": intent_data.get("integrity", "sha256"),
                "dh_group": intent_data.get("dh_group", 14),
                "mode": "tunnel_protection",
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_dmvpn(intent) -> dict:
    """Resolve a DMVPN intent."""
    intent_data = intent.intent_data
    nhs_address = intent_data.get("nhs_address")
    if not nhs_address:
        raise ValueError(f"Intent {intent.intent_id}: 'nhs_address' (hub) required for dmvpn.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        tunnel_id = allocate_tunnel_id(device, intent, "dmvpn")
        primitives.append(
            {
                "primitive_type": "dmvpn",
                "device": device.name,
                "tunnel_id": tunnel_id,
                "nhs_address": nhs_address,
                "tunnel_source": intent_data.get("tunnel_source", ""),
                "tunnel_key": intent_data.get("tunnel_key", 100),
                "phase": intent_data.get("phase", 3),
                "role": intent_data.get("roles", {}).get(device.name, "spoke"),
                "ipsec_profile": intent_data.get("ipsec_profile", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_macsec_policy(intent) -> dict:
    """Resolve a MACsec policy intent."""
    return resolve_macsec(intent)


@transaction.atomic
def resolve_copp(intent) -> dict:
    """Resolve a CoPP (Control Plane Policing) intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "copp",
                "device": device.name,
                "classes": intent_data.get("classes", []),
                "policy_name": intent_data.get("policy_name", "COPP-POLICY"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_urpf(intent) -> dict:
    """Resolve a uRPF intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for iface in intent_data.get("interfaces", []):
            primitives.append(
                {
                    "primitive_type": "urpf",
                    "device": device.name,
                    "interface": iface,
                    "mode": intent_data.get("mode", "strict"),
                    "allow_self_ping": intent_data.get("allow_self_ping", True),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_dot1x_nac(intent) -> dict:
    """Resolve an 802.1X / NAC intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "dot1x",
                "device": device.name,
                "system_auth_control": True,
                "interfaces": intent_data.get("interfaces", []),
                "host_mode": intent_data.get("host_mode", "single-host"),
                "radius_server_group": intent_data.get("radius_server_group", ""),
                "reauth_period": intent_data.get("reauth_period", 3600),
                "guest_vlan": intent_data.get("guest_vlan"),
                "auth_fail_vlan": intent_data.get("auth_fail_vlan"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_aaa(intent) -> dict:
    """Resolve a RADIUS / TACACS AAA intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "aaa",
                "device": device.name,
                "auth_methods": intent_data.get("auth_methods", "local"),
                "enable_auth": intent_data.get("enable_auth", ""),
                "authorization": intent_data.get("authorization", ""),
                "accounting": intent_data.get("accounting", ""),
                "radius_servers": intent_data.get("radius_servers", []),
                "tacacs_servers": intent_data.get("tacacs_servers", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_ra_guard(intent) -> dict:
    """Resolve an IPv6 RA Guard intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "ra_guard",
                "device": device.name,
                "policy_name": intent_data.get("policy_name", f"RA-GUARD-{intent.intent_id}"),
                "trusted_ports": intent_data.get("trusted_ports", []),
                "untrusted_ports": intent_data.get("untrusted_ports", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_ssl_inspection(intent) -> dict:
    """Resolve an SSL/TLS inspection intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "ssl_inspection",
                "device": device.name,
                "policy_name": intent_data.get("policy_name", f"SSL-INSPECT-{intent.intent_id}"),
                "ca_cert": intent_data.get("ca_cert", ""),
                "bypass_categories": intent_data.get("bypass_categories", []),
                "decrypt_categories": intent_data.get("decrypt_categories", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


# =========================================================================
# 6. WAN & SD-WAN RESOLVERS
# =========================================================================


@transaction.atomic
def resolve_wan_uplink(intent) -> dict:
    """Resolve a WAN uplink / dual ISP intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for uplink in intent_data.get("uplinks", []):
            primitives.append(
                {
                    "primitive_type": "wan_uplink",
                    "device": device.name,
                    "interface": uplink["interface"],
                    "ip_address": uplink.get("ip_address", "dhcp"),
                    "isp_name": uplink.get("isp_name", ""),
                    "bandwidth": uplink.get("bandwidth", ""),
                    "default_route": uplink.get("default_route", True),
                    "admin_distance": uplink.get("admin_distance", 1),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_bgp_isp(intent) -> dict:
    """Resolve a BGP to ISP intent."""
    return resolve_bgp_ebgp(intent)


@transaction.atomic
def resolve_sdwan_overlay(intent) -> dict:
    """Resolve an SD-WAN overlay intent (controller-based)."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "sdwan_overlay",
                "device": device.name,
                "fabric_name": intent_data.get("fabric_name", ""),
                "site_id": intent_data.get("site_id"),
                "system_ip": intent_data.get("system_ip", ""),
                "transport_colors": intent_data.get("transport_colors", []),
                "control_connections": intent_data.get("control_connections", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_sdwan_app_policy(intent) -> dict:
    """Resolve an SD-WAN application policy intent (controller-based)."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "sdwan_app_policy",
                "device": device.name,
                "policy_name": intent_data.get("policy_name", ""),
                "applications": intent_data.get("applications", []),
                "sla_classes": intent_data.get("sla_classes", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_sdwan_qos(intent) -> dict:
    """Resolve an SD-WAN QoS policy intent (controller-based)."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "sdwan_qos",
                "device": device.name,
                "policy_name": intent_data.get("policy_name", ""),
                "classes": intent_data.get("classes", []),
                "scheduler": intent_data.get("scheduler", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_sdwan_dia(intent) -> dict:
    """Resolve an SD-WAN DIA (Direct Internet Access) intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "sdwan_dia",
                "device": device.name,
                "nat_interface": intent_data.get("nat_interface", ""),
                "breakout_applications": intent_data.get("breakout_applications", []),
                "dns_redirect": intent_data.get("dns_redirect", False),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_nat_pat(intent) -> dict:
    """Resolve a NAT/PAT intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "nat",
                "device": device.name,
                "nat_type": intent_data.get("nat_type", "overload"),
                "inside_interface": intent_data.get("inside_interface", ""),
                "outside_interface": intent_data.get("outside_interface", ""),
                "pool_name": intent_data.get("pool_name", ""),
                "pool_start": intent_data.get("pool_start", ""),
                "pool_end": intent_data.get("pool_end", ""),
                "acl": intent_data.get("acl", ""),
                "static_mappings": intent_data.get("static_mappings", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_nat64(intent) -> dict:
    """Resolve a NAT64 intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "nat64",
                "device": device.name,
                "prefix": intent_data.get("prefix", "64:ff9b::/96"),
                "mode": intent_data.get("mode", "stateful"),
                "v4_pool": intent_data.get("v4_pool", ""),
                "interfaces": intent_data.get("interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wan_failover(intent) -> dict:
    """Resolve a WAN failover intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        # IP SLA probes
        for probe in intent_data.get("probes", []):
            primitives.append(
                {
                    "primitive_type": "ip_sla",
                    "device": device.name,
                    "sla_id": probe.get("sla_id", 1),
                    "probe_type": probe.get("type", "icmp-echo"),
                    "target": probe.get("target", ""),
                    "frequency": probe.get("frequency", 5),
                    "threshold": probe.get("threshold", 1000),
                    "timeout": probe.get("timeout", 2000),
                    "intent_id": intent.intent_id,
                }
            )

        # Backup static routes with tracking
        for route in intent_data.get("backup_routes", []):
            primitives.append(
                {
                    "primitive_type": "static_route",
                    "device": device.name,
                    "prefix": route["prefix"],
                    "next_hop": route.get("next_hop", ""),
                    "admin_distance": route.get("admin_distance", 250),
                    "track": route.get("track"),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


# =========================================================================
# 7. WIRELESS RESOLVERS (produce primitives for controller_adapters.py)
# =========================================================================


@transaction.atomic
def resolve_wireless_ssid(intent) -> dict:
    """Resolve a wireless SSID provisioning intent."""
    intent_data = intent.intent_data
    ssid_name = intent_data.get("ssid_name")
    if not ssid_name:
        raise ValueError(f"Intent {intent.intent_id}: 'ssid_name' required for wireless_ssid.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_ssid",
                "device": device.name,
                "ssid_name": ssid_name,
                "security_mode": intent_data.get("security_mode", "wpa3-enterprise"),
                "psk": intent_data.get("psk", ""),
                "vlan_id": intent_data.get("vlan_id"),
                "band": intent_data.get("band", "dual"),
                "broadcast_ssid": intent_data.get("broadcast_ssid", True),
                "client_isolation": intent_data.get("client_isolation", False),
                "max_clients": intent_data.get("max_clients"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_vlan_map(intent) -> dict:
    """Resolve a VLAN-to-SSID mapping intent. Allocates wireless VLAN."""
    intent_data = intent.intent_data
    ssid_name = intent_data.get("ssid_name")
    if not ssid_name:
        raise ValueError(f"Intent {intent.intent_id}: 'ssid_name' required for wireless_vlan_map.")

    devices = _get_scope_devices(intent)
    site = devices[0].location if devices else None
    vlan_id = allocate_wireless_vlan(site, ssid_name, intent)

    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_vlan_map",
                "device": device.name,
                "ssid_name": ssid_name,
                "vlan_id": vlan_id,
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_dot1x(intent) -> dict:
    """Resolve an 802.1X wireless intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_dot1x",
                "device": device.name,
                "ssid_name": intent_data.get("ssid_name", ""),
                "radius_servers": intent_data.get("radius_servers", []),
                "eap_method": intent_data.get("eap_method", "PEAP"),
                "certificate_profile": intent_data.get("certificate_profile", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_guest(intent) -> dict:
    """Resolve a guest wireless / captive portal intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_guest",
                "device": device.name,
                "ssid_name": intent_data.get("ssid_name", "Guest"),
                "captive_portal_url": intent_data.get("captive_portal_url", ""),
                "rate_limit_down": intent_data.get("rate_limit_down", 5000),
                "rate_limit_up": intent_data.get("rate_limit_up", 2000),
                "session_timeout": intent_data.get("session_timeout", 3600),
                "isolation": intent_data.get("isolation", True),
                "vlan_id": intent_data.get("vlan_id"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_rf(intent) -> dict:
    """Resolve an RF policy intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_rf",
                "device": device.name,
                "channels_2g": intent_data.get("channels_2g", [1, 6, 11]),
                "channels_5g": intent_data.get("channels_5g", []),
                "channels_6g": intent_data.get("channels_6g", []),
                "tx_power_min": intent_data.get("tx_power_min"),
                "tx_power_max": intent_data.get("tx_power_max"),
                "dca_enabled": intent_data.get("dca_enabled", True),
                "tpc_enabled": intent_data.get("tpc_enabled", True),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_qos(intent) -> dict:
    """Resolve a wireless QoS (WMM) intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_qos",
                "device": device.name,
                "wmm_enabled": intent_data.get("wmm_enabled", True),
                "dscp_map": intent_data.get("dscp_map", {}),
                "priority": intent_data.get("priority", "silver"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_band_steer(intent) -> dict:
    """Resolve a band steering intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_band_steer",
                "device": device.name,
                "preferred_band": intent_data.get("preferred_band", "5ghz"),
                "probe_suppression": intent_data.get("probe_suppression", False),
                "load_balance_threshold": intent_data.get("load_balance_threshold"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_roam(intent) -> dict:
    """Resolve a fast roaming / 802.11r intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_roam",
                "device": device.name,
                "ft_enabled": intent_data.get("ft_enabled", True),
                "ft_over_ds": intent_data.get("ft_over_ds", True),
                "pmk_cache": intent_data.get("pmk_cache", True),
                "okc_enabled": intent_data.get("okc_enabled", True),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_segment(intent) -> dict:
    """Resolve a wireless segmentation intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_segment",
                "device": device.name,
                "ssid_name": intent_data.get("ssid_name", ""),
                "client_isolation": intent_data.get("client_isolation", True),
                "inter_vlan_acl": intent_data.get("inter_vlan_acl", ""),
                "group_policy": intent_data.get("group_policy", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_mesh(intent) -> dict:
    """Resolve a mesh wireless intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_mesh",
                "device": device.name,
                "backhaul_ssid": intent_data.get("backhaul_ssid", "MESH-BACKHAUL"),
                "mesh_role": intent_data.get("roles", {}).get(device.name, "map"),
                "preferred_parent": intent_data.get("preferred_parents", {}).get(device.name, ""),
                "bridge_group": intent_data.get("bridge_group", 1),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_wireless_flexconnect(intent) -> dict:
    """Resolve a FlexConnect / local switching intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "wireless_flexconnect",
                "device": device.name,
                "local_switching": intent_data.get("local_switching", True),
                "vlan_mapping": intent_data.get("vlan_mapping", {}),
                "ap_group": intent_data.get("ap_group", ""),
                "native_vlan": intent_data.get("native_vlan"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


# =========================================================================
# 8. CLOUD & HYBRID CLOUD RESOLVERS (produce primitives for CloudAdapter)
# =========================================================================


@transaction.atomic
def resolve_cloud_vpc_peer(intent) -> dict:
    """Resolve a VPC / VNet peering intent."""
    intent_data = intent.intent_data
    requester_vpc = intent_data.get("requester_vpc")
    accepter_vpc = intent_data.get("accepter_vpc")
    if not requester_vpc or not accepter_vpc:
        raise ValueError(f"Intent {intent.intent_id}: 'requester_vpc' and 'accepter_vpc' required for cloud_vpc_peer.")

    primitives = [
        {
            "primitive_type": "cloud_vpc_peer",
            "requester_vpc": requester_vpc,
            "accepter_vpc": accepter_vpc,
            "requester_account": intent_data.get("requester_account", ""),
            "accepter_account": intent_data.get("accepter_account", ""),
            "requester_region": intent_data.get("requester_region", ""),
            "accepter_region": intent_data.get("accepter_region", ""),
            "auto_accept": intent_data.get("auto_accept", True),
            "dns_resolution": intent_data.get("dns_resolution", False),
            "provider": intent_data.get("provider", "aws"),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


@transaction.atomic
def resolve_cloud_transit_gw(intent) -> dict:
    """Resolve a transit gateway / hub-spoke intent."""
    intent_data = intent.intent_data
    transit_gw_id = intent_data.get("transit_gateway_id")
    if not transit_gw_id:
        raise ValueError(f"Intent {intent.intent_id}: 'transit_gateway_id' required for cloud_transit_gw.")

    primitives = [
        {
            "primitive_type": "cloud_transit_gw",
            "transit_gateway_id": transit_gw_id,
            "attachments": intent_data.get("attachments", []),
            "route_tables": intent_data.get("route_tables", []),
            "propagation": intent_data.get("propagation", True),
            "provider": intent_data.get("provider", "aws"),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


@transaction.atomic
def resolve_cloud_direct_connect(intent) -> dict:
    """Resolve a Cloud Direct Connect intent."""
    intent_data = intent.intent_data
    connection_id = intent_data.get("connection_id")
    if not connection_id:
        raise ValueError(f"Intent {intent.intent_id}: 'connection_id' required for cloud_direct_connect.")

    primitives = [
        {
            "primitive_type": "cloud_direct_connect",
            "connection_id": connection_id,
            "vlan": intent_data.get("vlan"),
            "bgp_asn": intent_data.get("bgp_asn"),
            "bgp_auth_key": intent_data.get("bgp_auth_key", ""),
            "address_family": intent_data.get("address_family", "ipv4"),
            "bfd": intent_data.get("bfd", True),
            "provider": intent_data.get("provider", "aws"),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


@transaction.atomic
def resolve_cloud_vpn_gw(intent) -> dict:
    """Resolve a Cloud VPN Gateway intent."""
    intent_data = intent.intent_data
    primitives = [
        {
            "primitive_type": "cloud_vpn_gw",
            "vpn_gateway_id": intent_data.get("vpn_gateway_id", ""),
            "customer_gateway_ip": intent_data.get("customer_gateway_ip", ""),
            "tunnel_ips": intent_data.get("tunnel_ips", []),
            "ike_version": intent_data.get("ike_version", 2),
            "encryption": intent_data.get("encryption", "aes-256-gcm"),
            "bgp_asn": intent_data.get("bgp_asn"),
            "provider": intent_data.get("provider", "aws"),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


@transaction.atomic
def resolve_cloud_bgp(intent) -> dict:
    """Resolve a BGP to Cloud Provider intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "bgp_neighbor",
                "device": device.name,
                "local_asn": intent_data.get("local_asn"),
                "neighbor_ip": intent_data.get("cloud_peer_ip", ""),
                "neighbor_asn": intent_data.get("cloud_asn"),
                "neighbor_description": f"Cloud-{intent_data.get('provider', 'cloud')}",
                "bfd_enabled": intent_data.get("bfd", True),
                "route_map_out": intent_data.get("route_map_out", ""),
                "communities": intent_data.get("communities", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_cloud_security_group(intent) -> dict:
    """Resolve a cloud firewall / security group intent."""
    intent_data = intent.intent_data
    sg_name = intent_data.get("security_group_name")
    if not sg_name:
        raise ValueError(f"Intent {intent.intent_id}: 'security_group_name' required for cloud_security_group.")

    primitives = [
        {
            "primitive_type": "cloud_security_group",
            "security_group_name": sg_name,
            "vpc_id": intent_data.get("vpc_id", ""),
            "inbound_rules": intent_data.get("inbound_rules", []),
            "outbound_rules": intent_data.get("outbound_rules", []),
            "provider": intent_data.get("provider", "aws"),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


@transaction.atomic
def resolve_cloud_nat(intent) -> dict:
    """Resolve a Cloud NAT intent."""
    intent_data = intent.intent_data
    primitives = [
        {
            "primitive_type": "cloud_nat",
            "nat_gateway_name": intent_data.get("nat_gateway_name", ""),
            "subnet_id": intent_data.get("subnet_id", ""),
            "eip_allocation": intent_data.get("eip_allocation", ""),
            "provider": intent_data.get("provider", "aws"),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


@transaction.atomic
def resolve_cloud_route_table(intent) -> dict:
    """Resolve a Cloud Route Table intent."""
    intent_data = intent.intent_data
    primitives = [
        {
            "primitive_type": "cloud_route_table",
            "route_table_id": intent_data.get("route_table_id", ""),
            "vpc_id": intent_data.get("vpc_id", ""),
            "routes": intent_data.get("routes", []),
            "associations": intent_data.get("associations", []),
            "provider": intent_data.get("provider", "aws"),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


@transaction.atomic
def resolve_hybrid_dns(intent) -> dict:
    """Resolve a Hybrid DNS intent."""
    intent_data = intent.intent_data
    primitives = [
        {
            "primitive_type": "hybrid_dns",
            "forward_zones": intent_data.get("forward_zones", []),
            "resolver_endpoints": intent_data.get("resolver_endpoints", []),
            "private_zones": intent_data.get("private_zones", []),
            "vpc_id": intent_data.get("vpc_id", ""),
            "provider": intent_data.get("provider", "aws"),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


@transaction.atomic
def resolve_cloud_sdwan(intent) -> dict:
    """Resolve a Cloud SD-WAN integration intent."""
    intent_data = intent.intent_data
    primitives = [
        {
            "primitive_type": "cloud_sdwan",
            "cloud_region": intent_data.get("cloud_region", ""),
            "vpc_id": intent_data.get("vpc_id", ""),
            "vhub_name": intent_data.get("vhub_name", ""),
            "sdwan_policy": intent_data.get("sdwan_policy", ""),
            "provider": intent_data.get("provider", "aws"),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


# =========================================================================
# 9. QoS RESOLVERS
# =========================================================================


@transaction.atomic
def resolve_qos_classify(intent) -> dict:
    """Resolve a traffic classification intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "qos_classify",
                "device": device.name,
                "class_maps": intent_data.get("class_maps", []),
                "policy_map": intent_data.get("policy_map", ""),
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "direction": intent_data.get("direction", "input"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_qos_dscp_mark(intent) -> dict:
    """Resolve a DSCP marking intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "qos_dscp_mark",
                "device": device.name,
                "policy_map": intent_data.get("policy_map", ""),
                "markings": intent_data.get("markings", []),
                "trust_boundary": intent_data.get("trust_boundary", "dscp"),
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_qos_cos_remark(intent) -> dict:
    """Resolve a CoS remarking intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "qos_cos_remark",
                "device": device.name,
                "trust_cos": intent_data.get("trust_cos", True),
                "cos_map": intent_data.get("cos_map", {}),
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_qos_queue(intent) -> dict:
    """Resolve a queuing policy (LLQ / CBWFQ) intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "qos_queue",
                "device": device.name,
                "policy_map": intent_data.get("policy_map", "WAN-QOS"),
                "queues": intent_data.get("queues", []),
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "direction": intent_data.get("direction", "output"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_qos_police(intent) -> dict:
    """Resolve a policing intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "qos_police",
                "device": device.name,
                "policy_map": intent_data.get("policy_map", ""),
                "rate_bps": intent_data.get("rate_bps"),
                "burst_bytes": intent_data.get("burst_bytes"),
                "conform_action": intent_data.get("conform_action", "transmit"),
                "exceed_action": intent_data.get("exceed_action", "drop"),
                "violate_action": intent_data.get("violate_action", "drop"),
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_qos_shape(intent) -> dict:
    """Resolve a traffic shaping intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "qos_shape",
                "device": device.name,
                "policy_map": intent_data.get("policy_map", ""),
                "rate_bps": intent_data.get("rate_bps"),
                "burst_bytes": intent_data.get("burst_bytes"),
                "child_policy": intent_data.get("child_policy", ""),
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_qos_trust(intent) -> dict:
    """Resolve a QoS trust boundary intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "qos_trust",
                "device": device.name,
                "trust_type": intent_data.get("trust_type", "dscp"),
                "apply_interfaces": intent_data.get("apply_interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


# =========================================================================
# 10. MULTICAST RESOLVERS
# =========================================================================


@transaction.atomic
def resolve_multicast_pim_sm(intent) -> dict:
    """Resolve a PIM Sparse Mode intent."""
    intent_data = intent.intent_data
    rp_address = intent_data.get("rp_address")
    if not rp_address:
        raise ValueError(f"Intent {intent.intent_id}: 'rp_address' required for multicast_pim_sm.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "pim",
                "device": device.name,
                "mode": "sparse-mode",
                "rp_address": rp_address,
                "rp_type": intent_data.get("rp_type", "static"),
                "interfaces": intent_data.get("interfaces", []),
                "bsr_candidate": intent_data.get("bsr_candidate"),
                "anycast_rp_set": intent_data.get("anycast_rp_set", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_multicast_pim_ssm(intent) -> dict:
    """Resolve a PIM SSM (Source-Specific Multicast) intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "pim",
                "device": device.name,
                "mode": "ssm",
                "ssm_range": intent_data.get("ssm_range", "232.0.0.0/8"),
                "interfaces": intent_data.get("interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_igmp_snooping(intent) -> dict:
    """Resolve an IGMP snooping intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "igmp_snooping",
                "device": device.name,
                "vlans": intent_data.get("vlans", []),
                "querier_enabled": intent_data.get("querier_enabled", False),
                "querier_address": intent_data.get("querier_address", ""),
                "fast_leave": intent_data.get("fast_leave", False),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_multicast_vrf(intent) -> dict:
    """Resolve a multicast VRF intent."""
    intent_data = intent.intent_data
    vrf_name = intent_data.get("vrf")
    if not vrf_name:
        raise ValueError(f"Intent {intent.intent_id}: 'vrf' required for multicast_vrf.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "multicast_vrf",
                "device": device.name,
                "vrf": vrf_name,
                "pim_mode": intent_data.get("pim_mode", "sparse-mode"),
                "rp_address": intent_data.get("rp_address", ""),
                "mdt_default_group": intent_data.get("mdt_default_group", ""),
                "interfaces": intent_data.get("interfaces", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_msdp(intent) -> dict:
    """Resolve an MSDP intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "msdp",
                "device": device.name,
                "peers": intent_data.get("peers", []),
                "originator_id": intent_data.get("originator_id", ""),
                "default_peer": intent_data.get("default_peer", ""),
                "sa_filter": intent_data.get("sa_filter", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


# =========================================================================
# 11. MANAGEMENT & OPERATIONS RESOLVERS
# =========================================================================


@transaction.atomic
def resolve_mgmt_ntp(intent) -> dict:
    """Resolve an NTP intent."""
    data = _mgmt_view(intent.intent_data, "ntp")
    servers = data.get("ntp_servers") or data.get("servers", [])
    if not servers:
        raise ValueError(f"Intent {intent.intent_id}: 'ntp_servers' (under management) required for mgmt_ntp.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "ntp",
                "device": device.name,
                "servers": servers,
                "prefer": data.get("ntp_prefer") or data.get("prefer", servers[0] if servers else ""),
                "authentication": data.get("authentication", False),
                "source_interface": data.get("ntp_source_interface") or data.get("source_interface", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_dns_dhcp(intent) -> dict:
    """Resolve a DNS/DHCP intent."""
    intent_data = intent.intent_data
    # Canonical wrapped form nests config under management.dns / management.dhcp.
    dns_block = (
        intent_data.get("management", {}).get("dns", {}) if isinstance(intent_data.get("management"), dict) else {}
    )
    dns_servers = dns_block.get("servers") or intent_data.get("dns_servers", [])
    dns_domain = dns_block.get("domain_name") or intent_data.get("domain_name", "")
    dns_domain_list = dns_block.get("search_domains") or intent_data.get("domain_list", [])
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        # DNS resolver config
        if dns_servers:
            primitives.append(
                {
                    "primitive_type": "dns",
                    "device": device.name,
                    "servers": dns_servers,
                    "domain_name": dns_domain,
                    "domain_list": dns_domain_list,
                    "source_interface": intent_data.get("source_interface", ""),
                    "intent_id": intent.intent_id,
                }
            )

        # DHCP pool config
        for pool in intent_data.get("dhcp_pools", []):
            primitives.append(
                {
                    "primitive_type": "dhcp_pool",
                    "device": device.name,
                    "pool_name": pool["name"],
                    "network": pool["network"],
                    "default_router": pool.get("default_router", ""),
                    "dns_server": pool.get("dns_server", ""),
                    "lease_time": pool.get("lease_time", 86400),
                    "excluded_addresses": pool.get("excluded_addresses", []),
                    "intent_id": intent.intent_id,
                }
            )

        # DHCP relay
        for relay in intent_data.get("dhcp_relays", []):
            primitives.append(
                {
                    "primitive_type": "dhcp_relay",
                    "device": device.name,
                    "interface": relay["interface"],
                    "helper_address": relay["helper_address"],
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_snmp(intent) -> dict:
    """Resolve an SNMP intent."""
    data = _mgmt_view(intent.intent_data, "snmp")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "snmp",
                "device": device.name,
                "version": data.get("snmp_version") or data.get("version", "v3"),
                "community": data.get("snmp_community") or data.get("community", ""),
                "users": data.get("users", []),
                "groups": data.get("groups", []),
                "views": data.get("views", []),
                "trap_targets": data.get("snmp_trap_targets") or data.get("trap_targets", []),
                "location": data.get("snmp_location") or data.get("location", ""),
                "contact": data.get("snmp_contact") or data.get("contact", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_syslog(intent) -> dict:
    """Resolve a syslog intent."""
    data = _mgmt_view(intent.intent_data, "syslog")
    servers = data.get("servers") or data.get("syslog_servers", [])
    if not servers:
        raise ValueError(f"Intent {intent.intent_id}: 'servers' list required for mgmt_syslog.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "syslog",
                "device": device.name,
                "servers": servers,
                "facility": data.get("facility", "local7"),
                "severity": data.get("severity", "informational"),
                "buffered_size": data.get("buffered_size"),
                "buffered_severity": data.get("buffered_severity"),
                "timestamps": data.get("timestamps"),
                "timestamps_format": data.get("timestamps_format"),
                "source_interface": data.get("source_interface") or data.get("syslog_source_interface", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_netflow(intent) -> dict:
    """Resolve a NetFlow / IPFIX intent."""
    # Structured form: collectors[], sampling.{mode,rate}, flow_cache.{...}, interfaces[]
    # — canonically under management.netflow.
    data = _mgmt_view(intent.intent_data, "netflow")
    collectors = data.get("collectors", [])
    first_collector = collectors[0] if collectors else {}
    sampling = data.get("sampling", {})
    flow_cache = data.get("flow_cache", {})
    apply_interfaces = data.get("apply_interfaces") or data.get("interfaces", [])
    intent_data = data

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "netflow",
                "device": device.name,
                "exporter_name": intent_data.get("exporter_name", "FLOW-EXPORT"),
                "collectors": collectors,
                "collector_ip": intent_data.get("collector_ip") or first_collector.get("ip", ""),
                "collector_port": intent_data.get("collector_port") or first_collector.get("port", 9995),
                "source_interface": intent_data.get("source_interface", ""),
                "sampler_rate": intent_data.get("sampler_rate") or sampling.get("rate", 1),
                "sampler_mode": sampling.get("mode", ""),
                "flow_cache": flow_cache,
                "version": intent_data.get("version", 9),
                "apply_interfaces": apply_interfaces,
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_telemetry(intent) -> dict:
    """Resolve a gRPC / streaming telemetry intent."""
    intent_data = _mgmt_view(intent.intent_data, "telemetry")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "telemetry",
                "device": device.name,
                "destination_ip": intent_data.get("destination_ip", ""),
                "destination_port": intent_data.get("destination_port", 57000),
                "protocol": intent_data.get("protocol", "grpc"),
                "encoding": intent_data.get("encoding", "gpb"),
                "subscriptions": intent_data.get("subscriptions", []),
                "source_interface": intent_data.get("source_interface", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_ssh(intent) -> dict:
    """Resolve an SSH access control intent."""
    intent_data = _mgmt_view(intent.intent_data, "ssh")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "ssh",
                "device": device.name,
                "version": intent_data.get("version", 2),
                "acl_name": intent_data.get("acl") or intent_data.get("acl_name", "SSH-ACCESS"),
                "allowed_networks": intent_data.get("allowed_networks", []),
                "timeout": intent_data.get("timeout_secs") or intent_data.get("timeout", 60),
                "retries": intent_data.get("authentication_retries") or intent_data.get("retries", 3),
                "key_type": intent_data.get("key_type", "rsa"),
                "key_size": intent_data.get("key_bits") or intent_data.get("key_size", 4096),
                "idle_timeout_mins": intent_data.get("idle_timeout_mins"),
                "algorithms": intent_data.get("algorithms", {}),
                "vty_lines": intent_data.get("vty_lines", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_aaa_device(intent) -> dict:
    """Resolve a TACACS/RADIUS device-management AAA intent.

    Canonical wrapped form: ``management.aaa_device.{tacacs_servers,
    server_group, authentication, authorization, accounting, local_fallback}``.
    Emits a structured ``aaa_device`` primitive (rendered by ``aaa_device.j2``),
    distinct from the simpler ``aaa`` primitive used by the security ``aaa`` type.
    """
    data = _mgmt_view(intent.intent_data, "aaa_device")
    tacacs_servers = data.get("tacacs_servers", [])
    if not tacacs_servers and not data.get("radius_servers"):
        raise ValueError(
            f"Intent {intent.intent_id}: 'tacacs_servers' (or 'radius_servers') required for mgmt_aaa_device."
        )

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "aaa_device",
                "device": device.name,
                "tacacs_servers": tacacs_servers,
                "radius_servers": data.get("radius_servers", []),
                "server_group": data.get("server_group", ""),
                "authentication": data.get("authentication", {}),
                "authorization": data.get("authorization", {}),
                "accounting": data.get("accounting", {}),
                "local_fallback": data.get("local_fallback", {}),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_interface(intent) -> dict:
    """Resolve a loopback / management interface intent."""
    intent_data = intent.intent_data
    # Canonical wrapped form: management.interfaces.{loopback, oob_management}
    interfaces = (
        intent_data.get("management", {}).get("interfaces", {})
        if isinstance(intent_data.get("management"), dict)
        else {}
    )
    loopback = interfaces.get("loopback") or intent_data.get("loopback")
    oob = interfaces.get("oob_management") or intent_data.get("mgmt_interface")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        if loopback:
            primitives.append(
                {
                    "primitive_type": "loopback",
                    "device": device.name,
                    "interface": loopback.get("name") or loopback.get("interface", "Loopback0"),
                    "ip_address": loopback.get("ip_address") or loopback.get("ip_range", ""),
                    "description": loopback.get("description", "Router-ID / Management"),
                    "intent_id": intent.intent_id,
                }
            )

        if oob:
            primitives.append(
                {
                    "primitive_type": "mgmt_interface",
                    "device": device.name,
                    "interface": oob.get("name") or oob.get("interface", "GigabitEthernet0"),
                    "ip_address": oob.get("ip_address", ""),
                    "vrf": oob.get("vrf", "Mgmt"),
                    "gateway": oob.get("gateway", ""),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_lldp_cdp(intent) -> dict:
    """Resolve an LLDP/CDP policy intent."""
    intent_data = _mgmt_view(intent.intent_data, "lldp_cdp")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "lldp_cdp",
                "device": device.name,
                "lldp_global": intent_data.get("lldp_global", True),
                "cdp_global": intent_data.get("cdp_global", False),
                "lldp_interfaces": intent_data.get("lldp_interfaces", []),
                "cdp_interfaces": intent_data.get("cdp_interfaces", []),
                "disable_on": intent_data.get("disable_on", []),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_stp_root(intent) -> dict:
    """Resolve a Spanning Tree root bridge intent."""
    intent_data = _mgmt_view(intent.intent_data, "stp_root")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        secondary = intent_data.get("secondary", {})
        primitives.append(
            {
                "primitive_type": "stp_root",
                "device": device.name,
                "mode": intent_data.get("mode"),
                "primary_vlans": intent_data.get("primary_vlans") or intent_data.get("root_vlans", []),
                "secondary_vlans": intent_data.get("secondary_vlans", []),
                "priority": intent_data.get("priority"),
                "secondary_priority": (
                    secondary.get("priority") if isinstance(secondary, dict) else intent_data.get("secondary_priority")
                ),
                "hello_time": intent_data.get("hello_time"),
                "forward_delay": intent_data.get("forward_delay"),
                "max_age": intent_data.get("max_age"),
                "diameter": intent_data.get("diameter"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_motd(intent) -> dict:
    """Resolve a Message-of-the-Day / banner intent."""
    intent_data = _mgmt_view(intent.intent_data, "motd", "banners")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "motd",
                "device": device.name,
                "login_banner": intent_data.get("login_banner", ""),
                "motd_banner": intent_data.get("motd_banner", ""),
                "exec_banner": intent_data.get("exec_banner", ""),
                "delimiter": intent_data.get("delimiter", "^"),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_netconf(intent) -> dict:
    """Resolve a NETCONF / RESTCONF enablement intent."""
    intent_data = _mgmt_view(intent.intent_data, "netconf")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "netconf",
                "device": device.name,
                "netconf_enabled": intent_data.get("netconf_enabled", True),
                "port": intent_data.get("netconf_port", 830),
                "vrf": intent_data.get("netconf_vrf", ""),
                "enable_restconf": intent_data.get("restconf_enabled", False),
                "restconf_port": intent_data.get("restconf_port", 443),
                "restconf_vrf": intent_data.get("restconf_vrf", ""),
                "gnmi_enabled": intent_data.get("gnmi_enabled", False),
                "gnmi_port": intent_data.get("gnmi_port", 6030),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_dhcp_server(intent) -> dict:
    """Resolve a DHCP server / pool intent."""
    intent_data = _mgmt_view(intent.intent_data, "dhcp_server")
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    pools = intent_data.get("pools", [])
    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "dhcp_server",
                "device": device.name,
                "pools": pools,
                "excluded_addresses": intent_data.get("excluded_addresses", []),
                "lease_time": intent_data.get("lease_time", 86400),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_mgmt_global_config(intent) -> dict:
    """Resolve a global / day-0 management config bundle intent.

    This is a *composite* resolver that emits a single ``global_config``
    primitive containing **all** management knobs so the template can
    render a complete management section in one pass.
    """
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    mgmt = intent_data.get("management", {})

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "global_config",
                "device": device.name,
                # Hostname / domain
                "hostname": mgmt.get("hostname", device.name),
                "domain_name": mgmt.get("domain_name", ""),
                # NTP
                "ntp_servers": mgmt.get("ntp_servers", []),
                "ntp_prefer": mgmt.get("ntp_prefer", ""),
                "ntp_source_interface": mgmt.get("ntp_source_interface", ""),
                "timezone": mgmt.get("timezone", "UTC"),
                "timezone_offset": mgmt.get("timezone_offset", 0),
                # DNS
                "dns_servers": mgmt.get("dns_servers", []),
                "dns_domain_list": mgmt.get("dns_domain_list", []),
                # Syslog
                "syslog_servers": mgmt.get("syslog_servers", []),
                "syslog_source_interface": mgmt.get("syslog_source_interface", ""),
                "syslog_trap_level": mgmt.get("syslog_trap_level", "informational"),
                # SNMP
                "snmp_community": mgmt.get("snmp_community", ""),
                "snmp_location": mgmt.get("snmp_location", ""),
                "snmp_contact": mgmt.get("snmp_contact", ""),
                "snmp_trap_targets": mgmt.get("snmp_trap_targets", []),
                "snmp_version": mgmt.get("snmp_version", "2c"),
                # SSH
                "enable_ssh": mgmt.get("enable_ssh", True),
                "ssh_version": mgmt.get("ssh_version", 2),
                "ssh_timeout": mgmt.get("ssh_timeout", 60),
                # Banners
                "login_banner": mgmt.get("login_banner", ""),
                "motd_banner": mgmt.get("motd_banner", ""),
                # NETCONF / RESTCONF
                "enable_netconf": mgmt.get("netconf_enabled", False),
                "netconf_port": mgmt.get("netconf_port", 830),
                "enable_restconf": mgmt.get("restconf_enabled", False),
                # DHCP pools
                "dhcp_pools": mgmt.get("dhcp_pools", []),
                # LLDP / CDP
                "enable_lldp": mgmt.get("lldp_enabled", True),
                "cdp_enabled": mgmt.get("cdp_enabled", False),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


# =========================================================================
# 12. REACHABILITY RESOLVERS (FIX EXISTING BROKEN STUB)
# =========================================================================


@transaction.atomic
def resolve_reachability(intent) -> dict:
    """Resolve a reachability intent. Dispatches to sub-type based on intent_data.

    Supports: static routes, BGP network statements, floating statics, IP SLA.
    """
    intent_data = intent.intent_data
    sub_type = intent_data.get("reachability_type")
    if not sub_type:
        raise ValueError(f"Intent {intent.intent_id}: 'reachability_type' required for reachability.")

    dispatch = {
        "static": resolve_reachability_static,
        "bgp_network": resolve_reachability_bgp_network,
        "floating": resolve_reachability_floating,
        "ip_sla": resolve_reachability_ip_sla,
    }

    resolver_fn = dispatch.get(sub_type)
    if not resolver_fn:
        raise ValueError(
            f"Intent {intent.intent_id}: unknown reachability sub-type '{sub_type}'. "
            f"Valid types: {list(dispatch.keys())}"
        )

    return resolver_fn(intent)


@transaction.atomic
def resolve_reachability_static(intent) -> dict:
    """Resolve a static reachability intent."""
    intent_data = intent.intent_data
    routes = intent_data.get("routes", [])
    if not routes:
        raise ValueError(f"Intent {intent.intent_id}: 'routes' list required for reachability_static.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for route in routes:
            primitives.append(
                {
                    "primitive_type": "static_route",
                    "device": device.name,
                    "prefix": route["prefix"],
                    "next_hop": route.get("next_hop", ""),
                    "exit_interface": route.get("exit_interface", ""),
                    "admin_distance": route.get("admin_distance", 1),
                    "vrf": route.get("vrf", ""),
                    "track": route.get("track"),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_reachability_bgp_network(intent) -> dict:
    """Resolve a BGP network statement reachability intent."""
    intent_data = intent.intent_data
    local_asn = intent_data.get("local_asn")
    networks = intent_data.get("networks", [])
    if not local_asn or not networks:
        raise ValueError(
            f"Intent {intent.intent_id}: 'local_asn' and 'networks' required for reachability_bgp_network."
        )

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "bgp_network",
                "device": device.name,
                "local_asn": local_asn,
                "networks": networks,
                "vrf": intent_data.get("vrf", ""),
                "route_map": intent_data.get("route_map", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_reachability_floating(intent) -> dict:
    """Resolve a floating static / backup route reachability intent."""
    intent_data = intent.intent_data
    routes = intent_data.get("routes", [])
    if not routes:
        raise ValueError(f"Intent {intent.intent_id}: 'routes' list required for reachability_floating.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for route in routes:
            primitives.append(
                {
                    "primitive_type": "static_route",
                    "device": device.name,
                    "prefix": route["prefix"],
                    "next_hop": route.get("next_hop", ""),
                    "admin_distance": route.get("admin_distance", 250),
                    "track": route.get("track"),
                    "name": route.get("name", "floating-backup"),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_reachability_ip_sla(intent) -> dict:
    """Resolve an IP SLA probe intent."""
    intent_data = intent.intent_data
    probes = intent_data.get("probes", [])
    if not probes:
        raise ValueError(f"Intent {intent.intent_id}: 'probes' list required for reachability_ip_sla.")

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for probe in probes:
            primitives.append(
                {
                    "primitive_type": "ip_sla",
                    "device": device.name,
                    "sla_id": probe["sla_id"],
                    "probe_type": probe.get("type", "icmp-echo"),
                    "target": probe["target"],
                    "frequency": probe.get("frequency", 5),
                    "threshold": probe.get("threshold", 1000),
                    "timeout": probe.get("timeout", 2000),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


# =========================================================================
# 13. SERVICE RESOLVERS (FIX EXISTING MISSING RESOLVER)
# =========================================================================


@transaction.atomic
def resolve_service(intent) -> dict:
    """Resolve a service intent. Dispatches to sub-type based on intent_data.

    Supports: LB VIP, DNS record, DHCP pool, NAT entry, service proxy.
    """
    intent_data = intent.intent_data
    sub_type = intent_data.get("service_type")
    if not sub_type:
        raise ValueError(f"Intent {intent.intent_id}: 'service_type' required for service.")

    dispatch = {
        "lb_vip": resolve_service_lb_vip,
        "dns": resolve_service_dns,
        "dhcp": resolve_service_dhcp,
        "nat": resolve_service_nat,
        "proxy": resolve_service_proxy,
    }

    resolver_fn = dispatch.get(sub_type)
    if not resolver_fn:
        raise ValueError(
            f"Intent {intent.intent_id}: unknown service sub-type '{sub_type}'. Valid types: {list(dispatch.keys())}"
        )

    return resolver_fn(intent)


@transaction.atomic
def resolve_service_lb_vip(intent) -> dict:
    """Resolve a Load Balancer VIP intent."""
    intent_data = intent.intent_data
    vip = intent_data.get("vip_address")
    # Newer schema uses 'members'; legacy uses 'pool_members'.
    members = intent_data.get("members") or intent_data.get("pool_members", [])
    if not vip or not members:
        raise ValueError(
            f"Intent {intent.intent_id}: 'vip_address' and 'members' (or 'pool_members') required for service_lb_vip."
        )

    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "lb_vip",
                "device": device.name,
                "vip_name": intent_data.get("vip_name", ""),
                "vip_address": vip,
                "vip_port": intent_data.get("vip_port", 443),
                "protocol": intent_data.get("protocol", "tcp"),
                "pool_name": intent_data.get("pool_name", ""),
                "pool_members": members,
                "health_check": intent_data.get("health_monitor")
                or intent_data.get("health_check", {"type": "tcp", "interval": 30}),
                "persistence": intent_data.get("persistence", "source-ip"),
                "algorithm": intent_data.get("load_balancing_method") or intent_data.get("algorithm", "round-robin"),
                "ssl_offload": intent_data.get("ssl_offload", False),
                "ssl_cert": intent_data.get("ssl_cert", ""),
                "ssl_key": intent_data.get("ssl_key", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_service_dns(intent) -> dict:
    """Resolve a DNS record intent."""
    intent_data = intent.intent_data
    records = intent_data.get("records", [])
    if not records:
        raise ValueError(f"Intent {intent.intent_id}: 'records' list required for service_dns.")

    primitives = [
        {
            "primitive_type": "dns_record",
            "records": records,
            "zone": intent_data.get("zone", ""),
            "ttl": intent_data.get("ttl", 300),
            "intent_id": intent.intent_id,
        }
    ]

    return _empty_plan([], primitives)


@transaction.atomic
def resolve_service_dhcp(intent) -> dict:
    """Resolve a DHCP pool / scope intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for pool in intent_data.get("pools", []):
            primitives.append(
                {
                    "primitive_type": "dhcp_pool",
                    "device": device.name,
                    "pool_name": pool["name"],
                    "network": pool["network"],
                    "default_router": pool.get("default_router", ""),
                    "dns_server": pool.get("dns_server", ""),
                    "lease_time": pool.get("lease_time", 86400),
                    "excluded_addresses": pool.get("excluded_addresses", []),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_service_nat(intent) -> dict:
    """Resolve a NAT entry (service) intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        for mapping in intent_data.get("static_mappings", []):
            primitives.append(
                {
                    "primitive_type": "nat",
                    "device": device.name,
                    "nat_type": "static",
                    "inside_local": mapping["inside_local"],
                    "inside_global": mapping["inside_global"],
                    "protocol": mapping.get("protocol", ""),
                    "port": mapping.get("port"),
                    "intent_id": intent.intent_id,
                }
            )

    return _empty_plan(affected, primitives)


@transaction.atomic
def resolve_service_proxy(intent) -> dict:
    """Resolve a proxy / service insertion intent."""
    intent_data = intent.intent_data
    devices = _get_scope_devices(intent)
    primitives = []
    affected = []

    for device in devices:
        affected.append(device.name)
        primitives.append(
            {
                "primitive_type": "service_insertion",
                "device": device.name,
                "service_node": intent_data.get("service_node", ""),
                "service_type": intent_data.get("insertion_type", "transparent"),
                "redirect_acl": intent_data.get("redirect_acl", ""),
                "pbr_policy": intent_data.get("pbr_policy", ""),
                "intent_id": intent.intent_id,
            }
        )

    return _empty_plan(affected, primitives)


# =========================================================================
# RESOLVERS DISPATCH MAP
# =========================================================================

RESOLVERS = {
    # Legacy / original
    "connectivity": resolve_connectivity,
    "security": resolve_security,
    "reachability": resolve_reachability,
    "service": resolve_service,
    # 1. Layer 2 / Switching
    "vlan_provision": resolve_vlan_provision,
    "l2_access_port": resolve_l2_access_port,
    "l2_trunk_port": resolve_l2_trunk_port,
    "lag": resolve_lag,
    "mlag": resolve_mlag,
    "stp_policy": resolve_stp_policy,
    "qinq": resolve_qinq,
    "pvlan": resolve_pvlan,
    "storm_control": resolve_storm_control,
    "port_security": resolve_port_security,
    "dhcp_snooping": resolve_dhcp_snooping,
    "dai": resolve_dai,
    "ip_source_guard": resolve_ip_source_guard,
    "macsec": resolve_macsec,
    # 2. Layer 3 / Routing
    "static_route": resolve_static_route,
    "ospf": resolve_ospf,
    "bgp_ebgp": resolve_bgp_ebgp,
    "bgp_ibgp": resolve_bgp_ibgp,
    "isis": resolve_isis,
    "eigrp": resolve_eigrp,
    "route_redistribution": resolve_route_redistribution,
    "route_policy": resolve_route_policy,
    "prefix_list": resolve_prefix_list,
    "vrf_basic": resolve_vrf_basic,
    "bfd": resolve_bfd,
    "pbr": resolve_pbr,
    "ipv6_dual_stack": resolve_ipv6_dual_stack,
    "ospfv3": resolve_ospfv3,
    "bgp_ipv6_af": resolve_bgp_ipv6_af,
    "fhrp": resolve_fhrp,
    # 3. MPLS & SP
    "mpls_l3vpn": resolve_mpls_l3vpn,
    "mpls_l2vpn": resolve_mpls_l2vpn,
    "pseudowire": resolve_pseudowire,
    "evpn_mpls": resolve_evpn_mpls,
    "ldp": resolve_ldp,
    "rsvp_te": resolve_rsvp_te,
    "sr_mpls": resolve_sr_mpls,
    "srv6": resolve_srv6,
    "6pe_6vpe": resolve_6pe_6vpe,
    "mvpn": resolve_mvpn,
    # 4. DC / EVPN / VXLAN
    "evpn_vxlan_fabric": resolve_evpn_vxlan_fabric,
    "l2vni": resolve_l2vni,
    "l3vni": resolve_l3vni,
    "bgp_evpn_af": resolve_bgp_evpn_af,
    "anycast_gateway": resolve_anycast_gateway,
    "vtep": resolve_vtep,
    "evpn_multisite": resolve_evpn_multisite,
    "dc_underlay": resolve_dc_underlay,
    "dc_mlag": resolve_dc_mlag,
    # 5. Security & Firewalling
    "acl": resolve_acl,
    "zbf": resolve_zbf,
    "fw_rule": resolve_fw_rule,
    "ipsec_s2s": resolve_ipsec_s2s,
    "ipsec_ikev2": resolve_ipsec_ikev2,
    "gre_tunnel": resolve_gre_tunnel,
    "gre_over_ipsec": resolve_gre_over_ipsec,
    "dmvpn": resolve_dmvpn,
    "macsec_policy": resolve_macsec_policy,
    "copp": resolve_copp,
    "urpf": resolve_urpf,
    "dot1x_nac": resolve_dot1x_nac,
    "aaa": resolve_aaa,
    "ra_guard": resolve_ra_guard,
    "ssl_inspection": resolve_ssl_inspection,
    # 6. WAN & SD-WAN
    "wan_uplink": resolve_wan_uplink,
    "bgp_isp": resolve_bgp_isp,
    "sdwan_overlay": resolve_sdwan_overlay,
    "sdwan_app_policy": resolve_sdwan_app_policy,
    "sdwan_qos": resolve_sdwan_qos,
    "sdwan_dia": resolve_sdwan_dia,
    "nat_pat": resolve_nat_pat,
    "nat64": resolve_nat64,
    "wan_failover": resolve_wan_failover,
    # 7. Wireless
    "wireless_ssid": resolve_wireless_ssid,
    "wireless_vlan_map": resolve_wireless_vlan_map,
    "wireless_dot1x": resolve_wireless_dot1x,
    "wireless_guest": resolve_wireless_guest,
    "wireless_rf": resolve_wireless_rf,
    "wireless_qos": resolve_wireless_qos,
    "wireless_band_steer": resolve_wireless_band_steer,
    "wireless_roam": resolve_wireless_roam,
    "wireless_segment": resolve_wireless_segment,
    "wireless_mesh": resolve_wireless_mesh,
    "wireless_flexconnect": resolve_wireless_flexconnect,
    # 8. Cloud & Hybrid
    "cloud_vpc_peer": resolve_cloud_vpc_peer,
    "cloud_transit_gw": resolve_cloud_transit_gw,
    "cloud_direct_connect": resolve_cloud_direct_connect,
    "cloud_vpn_gw": resolve_cloud_vpn_gw,
    "cloud_bgp": resolve_cloud_bgp,
    "cloud_security_group": resolve_cloud_security_group,
    "cloud_nat": resolve_cloud_nat,
    "cloud_route_table": resolve_cloud_route_table,
    "hybrid_dns": resolve_hybrid_dns,
    "cloud_sdwan": resolve_cloud_sdwan,
    # 9. QoS
    "qos_classify": resolve_qos_classify,
    "qos_dscp_mark": resolve_qos_dscp_mark,
    "qos_cos_remark": resolve_qos_cos_remark,
    "qos_queue": resolve_qos_queue,
    "qos_police": resolve_qos_police,
    "qos_shape": resolve_qos_shape,
    "qos_trust": resolve_qos_trust,
    # 10. Multicast
    "multicast_pim_sm": resolve_multicast_pim_sm,
    "multicast_pim_ssm": resolve_multicast_pim_ssm,
    "igmp_snooping": resolve_igmp_snooping,
    "multicast_vrf": resolve_multicast_vrf,
    "msdp": resolve_msdp,
    # 11. Management
    "mgmt_ntp": resolve_mgmt_ntp,
    "mgmt_dns_dhcp": resolve_mgmt_dns_dhcp,
    "mgmt_snmp": resolve_mgmt_snmp,
    "mgmt_syslog": resolve_mgmt_syslog,
    "mgmt_netflow": resolve_mgmt_netflow,
    "mgmt_telemetry": resolve_mgmt_telemetry,
    "mgmt_ssh": resolve_mgmt_ssh,
    "mgmt_aaa_device": resolve_mgmt_aaa_device,
    "mgmt_interface": resolve_mgmt_interface,
    "mgmt_lldp_cdp": resolve_mgmt_lldp_cdp,
    "mgmt_stp_root": resolve_mgmt_stp_root,
    "mgmt_motd": resolve_mgmt_motd,
    "mgmt_netconf": resolve_mgmt_netconf,
    "mgmt_dhcp_server": resolve_mgmt_dhcp_server,
    "mgmt_global_config": resolve_mgmt_global_config,
    # 12. Reachability (expanded)
    "reachability_static": resolve_reachability_static,
    "reachability_bgp_network": resolve_reachability_bgp_network,
    "reachability_floating": resolve_reachability_floating,
    "reachability_ip_sla": resolve_reachability_ip_sla,
    # 13. Service (expanded)
    "service_lb_vip": resolve_service_lb_vip,
    "service_dns": resolve_service_dns,
    "service_dhcp": resolve_service_dhcp,
    "service_nat": resolve_service_nat,
    "service_proxy": resolve_service_proxy,
}


def resolve_intent(intent) -> dict:
    """Main entry point -- dispatches to the appropriate resolver.

    Args:
        intent: Intent ORM object

    Returns:
        dict with keys: affected_devices, primitives, vrf_name,
                        requires_new_vrf, requires_mpls,
                        allocated_rds, allocated_rts

    Raises:
        ValueError: for bad intent data or missing Nautobot data
    """
    resolver_fn = RESOLVERS.get(intent.intent_type)

    if not resolver_fn:
        raise ValueError(
            f"No resolver implemented for intent type '{intent.intent_type}'. Known types: {list(RESOLVERS.keys())}"
        )

    logger.info(
        "Resolving intent %s (type=%s, tenant=%s)",
        intent.intent_id,
        intent.intent_type,
        intent.tenant.name,
    )

    plan_data = resolver_fn(intent)

    logger.info(
        "Resolution complete: %s -> %s devices, %s primitives",
        intent.intent_id,
        len(plan_data["affected_devices"]),
        len(plan_data["primitives"]),
    )

    return plan_data
