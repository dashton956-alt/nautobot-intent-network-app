"""Atomic resource allocation for VRFs (with RDs), Route Targets, VNIs, Tunnel IDs, Loopbacks & Wireless VLANs.

RD and RT allocation uses Nautobot's native ``ipam.VRF`` (which has an ``rd``
field), ``ipam.Namespace`` and ``ipam.RouteTarget`` models instead of custom
pool tables.  A Namespace acts as the organisational boundary (similar to the
old pool concept) and the plugin's ``default_bgp_asn`` setting supplies the
ASN prefix for the ``<ASN>:<counter>`` format.

VNIs, Tunnel IDs, Loopbacks and Wireless VLANs still use plugin-local pool
models because Nautobot core does not provide equivalent pool primitives.

Uses select_for_update() to lock rows at the database level, preventing two
concurrent resolution jobs from allocating the same value.

All allocation functions must be called inside a transaction.atomic() block.
The Jobs that call these already wrap their work in a transaction.
"""

import ipaddress
import logging

from django.conf import settings
from django.db import transaction
from nautobot.ipam.models import VRF, Namespace
from nautobot.ipam.models import RouteTarget as NautobotRouteTarget

from intent_networking.models import (
    Intent,
    ManagedLoopback,
    ManagedLoopbackPool,
    TunnelIdAllocation,
    TunnelIdPool,
    VniAllocation,
    VxlanVniPool,
    WirelessVlanAllocation,
    WirelessVlanPool,
)

logger = logging.getLogger(__name__)


def _get_plugin_config(key: str):
    """Retrieve a value from the intent_networking plugin config."""
    return settings.PLUGINS_CONFIG.get("intent_networking", {}).get(key)


# ─────────────────────────────────────────────────────────────────────────────
# VRF / Route Distinguisher Allocation (uses Nautobot ipam.VRF + Namespace)
# ─────────────────────────────────────────────────────────────────────────────


def allocate_route_distinguisher(device, vrf_name: str, intent: Intent) -> str:
    """Create or reuse a Nautobot VRF with an auto-generated RD value.

    The RD is formatted as ``<ASN>:<counter>`` where ``<ASN>`` comes from
    the plugin's ``default_bgp_asn`` setting and ``<counter>`` is derived
    from the VRF's primary key to guarantee uniqueness within the namespace.

    If a VRF with matching ``name`` + ``namespace`` already exists, return
    its existing RD (idempotent).

    Args:
        device:   Nautobot Device ORM object
        vrf_name: VRF name string e.g. "ACMECORP-PCI"
        intent:   Intent ORM object (used for tenant FK)

    Returns:
        RD string e.g. "65000:7823"

    Raises:
        ValueError: if the Namespace cannot be found
    """
    namespace_name = _get_plugin_config("vrf_namespace") or "Global"
    asn = _get_plugin_config("default_bgp_asn")

    with transaction.atomic():
        try:
            namespace = Namespace.objects.select_for_update().get(name=namespace_name)
        except Namespace.DoesNotExist as exc:
            raise ValueError(
                f"Namespace '{namespace_name}' not found. Create it in IPAM → Namespaces before allocating VRFs."
            ) from exc

        # Check for existing VRF (idempotent)
        existing = VRF.objects.filter(name=vrf_name, namespace=namespace).first()
        if existing:
            logger.info("Reusing existing VRF %s (RD=%s) for %s", vrf_name, existing.rd, device.name)
            # Assign device to VRF if not already
            if device not in existing.devices.all():
                existing.devices.add(device)
            return existing.rd or ""

        # Generate a unique counter for the RD
        max_rd_num = 0
        for vrf in VRF.objects.filter(namespace=namespace).exclude(rd__isnull=True).exclude(rd=""):
            try:
                _, num_str = vrf.rd.rsplit(":", 1)
                max_rd_num = max(max_rd_num, int(num_str))
            except (ValueError, AttributeError):
                continue

        rd_value = f"{asn}:{max_rd_num + 1}"

        vrf = VRF.objects.create(
            name=vrf_name,
            rd=rd_value,
            namespace=namespace,
            tenant=intent.tenant,
            description=f"Auto-allocated by intent {intent.intent_id}",
        )
        vrf.devices.add(device)

        logger.info(
            "Allocated VRF %s (RD=%s) in namespace %s for %s (intent: %s)",
            vrf_name,
            rd_value,
            namespace_name,
            device.name,
            intent.intent_id,
        )
        return rd_value


# ─────────────────────────────────────────────────────────────────────────────
# Route Target Allocation (uses Nautobot ipam.RouteTarget)
# ─────────────────────────────────────────────────────────────────────────────


def allocate_route_target(intent: Intent) -> tuple[str, str]:
    """Create or reuse a Nautobot RouteTarget for this intent.

    Route targets are intent-level (not per-device), so one RT serves all
    devices implementing the same intent. Export and import use the same
    value for simple VPN topologies.

    The RT name is formatted as ``<ASN>:<counter>`` using the plugin's
    ``default_bgp_asn`` setting.

    Returns:
        Tuple of (rt_export, rt_import) strings e.g. ("65000:100", "65000:100")

    Raises:
        ValueError: if RT creation fails
    """
    asn = _get_plugin_config("default_bgp_asn")

    # Build a deterministic RT name from the intent ID
    rt_description = f"Auto-allocated for intent {intent.intent_id}"

    # Check for existing RT tagged with this intent's description
    existing = NautobotRouteTarget.objects.filter(description=rt_description).first()
    if existing:
        logger.info("Reusing existing RT %s for %s", existing.name, intent.intent_id)
        return existing.name, existing.name

    with transaction.atomic():
        # Find the next available RT counter
        max_rt_num = 0
        for rt in NautobotRouteTarget.objects.filter(name__startswith=f"{asn}:"):
            try:
                _, num_str = rt.name.rsplit(":", 1)
                max_rt_num = max(max_rt_num, int(num_str))
            except (ValueError, AttributeError):
                continue

        rt_value = f"{asn}:{max_rt_num + 1}"

        NautobotRouteTarget.objects.create(
            name=rt_value,
            description=rt_description,
            tenant=intent.tenant,
        )

        logger.info("Allocated RT %s for intent %s", rt_value, intent.intent_id)
        return rt_value, rt_value


def release_allocations(intent: Intent) -> dict:
    """Release all resource allocations for an intent.

    Called when an intent is deprecated or when a rollback cleans up.
    Covers VRFs (native), RTs (native), VNIs, tunnel IDs, loopbacks and
    wireless VLANs.

    Returns:
        Dict with counts of released resources.
    """
    # Release Nautobot-native VRFs created for this intent
    intent_vrf_desc = f"Auto-allocated by intent {intent.intent_id}"
    vrfs_released = VRF.objects.filter(description=intent_vrf_desc).count()
    VRF.objects.filter(description=intent_vrf_desc).delete()

    # Release Nautobot-native Route Targets created for this intent
    intent_rt_desc = f"Auto-allocated for intent {intent.intent_id}"
    rts_released = NautobotRouteTarget.objects.filter(description=intent_rt_desc).count()
    NautobotRouteTarget.objects.filter(description=intent_rt_desc).delete()

    vnis_released = VniAllocation.objects.filter(intent=intent).count()
    VniAllocation.objects.filter(intent=intent).delete()

    tunnels_released = TunnelIdAllocation.objects.filter(intent=intent).count()
    TunnelIdAllocation.objects.filter(intent=intent).delete()

    loopbacks_released = ManagedLoopback.objects.filter(intent=intent).count()
    ManagedLoopback.objects.filter(intent=intent).delete()

    wireless_vlans_released = WirelessVlanAllocation.objects.filter(intent=intent).count()
    WirelessVlanAllocation.objects.filter(intent=intent).delete()

    logger.info(
        "Released allocations for %s: %s VRFs, %s RTs, %s VNIs, %s tunnel IDs, %s loopbacks, %s wireless VLANs",
        intent.intent_id,
        vrfs_released,
        rts_released,
        vnis_released,
        tunnels_released,
        loopbacks_released,
        wireless_vlans_released,
    )

    return {
        "vrfs_released": vrfs_released,
        "rts_released": rts_released,
        "vnis_released": vnis_released,
        "tunnels_released": tunnels_released,
        "loopbacks_released": loopbacks_released,
        "wireless_vlans_released": wireless_vlans_released,
    }


# ─────────────────────────────────────────────────────────────────────────────
# VXLAN VNI Allocation
# ─────────────────────────────────────────────────────────────────────────────


def allocate_vxlan_vni(intent: Intent, vni_type: str) -> int:
    """Claim the next available VNI from the configured pool for this intent.

    If a VNI is already allocated for this intent + vni_type, return the
    existing one (idempotent).

    Args:
        intent:   Intent ORM object
        vni_type: ``'l2'`` or ``'l3'``

    Returns:
        VNI integer value e.g. 10042

    Raises:
        ValueError: if pool is exhausted or not found
    """
    existing = VniAllocation.objects.filter(intent=intent, vni_type=vni_type).first()
    if existing:
        logger.info("Reusing existing VNI %s (%s) for %s", existing.value, vni_type, intent.intent_id)
        return existing.value

    pool_name = _get_plugin_config("vni_pool_name")

    with transaction.atomic():
        try:
            pool = VxlanVniPool.objects.select_for_update().get(name=pool_name)
        except VxlanVniPool.DoesNotExist as exc:
            raise ValueError(
                f"VNI pool '{pool_name}' not found. Create it in Nautobot admin under Intent Engine → VXLAN VNI Pools."
            ) from exc

        used = set(VniAllocation.objects.filter(pool=pool).values_list("value", flat=True))

        for i in range(pool.range_start, pool.range_end + 1):
            if i not in used:
                alloc = VniAllocation.objects.create(
                    pool=pool,
                    value=i,
                    intent=intent,
                    vni_type=vni_type,
                )
                logger.info(
                    "Allocated VNI %s (%s) for intent %s",
                    i,
                    vni_type,
                    intent.intent_id,
                )
                return alloc.value

        raise ValueError(
            f"VNI pool '{pool_name}' exhausted. "
            f"Range {pool.range_start}-{pool.range_end} is fully allocated. "
            f"Expand the pool range or create a new pool."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tunnel ID Allocation
# ─────────────────────────────────────────────────────────────────────────────


def allocate_tunnel_id(device, intent: Intent, tunnel_type: str) -> int:
    """Claim the next available tunnel interface ID for a device.

    If a tunnel ID is already allocated for this device + intent + type,
    return the existing one (idempotent).

    Args:
        device:      Nautobot Device ORM object
        intent:      Intent ORM object
        tunnel_type: ``'ipsec'``, ``'gre'``, or ``'dmvpn'``

    Returns:
        Tunnel interface number e.g. 100

    Raises:
        ValueError: if pool is exhausted or not found
    """
    existing = TunnelIdAllocation.objects.filter(device=device, intent=intent, tunnel_type=tunnel_type).first()
    if existing:
        logger.info(
            "Reusing existing tunnel ID %s (%s) for %s on %s",
            existing.value,
            tunnel_type,
            intent.intent_id,
            device.name,
        )
        return existing.value

    pool_name = _get_plugin_config("tunnel_id_pool_name")

    with transaction.atomic():
        try:
            pool = TunnelIdPool.objects.select_for_update().get(name=pool_name)
        except TunnelIdPool.DoesNotExist as exc:
            raise ValueError(
                f"Tunnel ID pool '{pool_name}' not found. "
                f"Create it in Nautobot admin under "
                f"Intent Engine → Tunnel ID Pools."
            ) from exc

        used = set(TunnelIdAllocation.objects.filter(pool=pool, device=device).values_list("value", flat=True))

        for i in range(pool.range_start, pool.range_end + 1):
            if i not in used:
                alloc = TunnelIdAllocation.objects.create(
                    pool=pool,
                    value=i,
                    device=device,
                    intent=intent,
                    tunnel_type=tunnel_type,
                )
                logger.info(
                    "Allocated tunnel ID %s (%s) for %s on %s",
                    i,
                    tunnel_type,
                    intent.intent_id,
                    device.name,
                )
                return alloc.value

        raise ValueError(
            f"Tunnel ID pool '{pool_name}' exhausted for device '{device.name}'. "
            f"Range {pool.range_start}-{pool.range_end} is fully allocated. "
            f"Expand the pool range or create a new pool."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Managed Loopback IP Allocation
# ─────────────────────────────────────────────────────────────────────────────


def allocate_loopback_ip(device, intent: Intent) -> str:
    """Claim the next available /32 loopback IP for a device from the pool.

    If a loopback is already allocated for this device, return the
    existing one (idempotent).

    Args:
        device: Nautobot Device ORM object
        intent: Intent ORM object

    Returns:
        IP address string e.g. "192.0.2.1"

    Raises:
        ValueError: if pool is exhausted or not found
    """
    existing = ManagedLoopback.objects.filter(device=device, intent=intent).first()
    if existing:
        logger.info("Reusing existing loopback %s for %s", existing.ip_address, device.name)
        return existing.ip_address

    pool_name = _get_plugin_config("loopback_pool_name")

    with transaction.atomic():
        try:
            pool = ManagedLoopbackPool.objects.select_for_update().get(name=pool_name)
        except ManagedLoopbackPool.DoesNotExist as exc:
            raise ValueError(
                f"Loopback pool '{pool_name}' not found. "
                f"Create it in Nautobot admin under "
                f"Intent Engine → Managed Loopback Pools."
            ) from exc

        network = ipaddress.ip_network(pool.prefix, strict=False)
        used = set(ManagedLoopback.objects.filter(pool=pool).values_list("ip_address", flat=True))

        # Skip network and broadcast addresses
        for host in network.hosts():
            candidate = str(host)
            if candidate not in used:
                alloc = ManagedLoopback.objects.create(
                    pool=pool,
                    ip_address=candidate,
                    device=device,
                    intent=intent,
                )
                logger.info(
                    "Allocated loopback %s for %s (intent: %s)",
                    candidate,
                    device.name,
                    intent.intent_id,
                )
                return alloc.ip_address

        raise ValueError(
            f"Loopback pool '{pool_name}' ({pool.prefix}) exhausted. "
            f"All host addresses are allocated. "
            f"Expand the prefix or create a new pool."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Wireless VLAN Allocation
# ─────────────────────────────────────────────────────────────────────────────


def allocate_wireless_vlan(site, ssid_name: str, intent: Intent) -> int:
    """Claim the next available VLAN ID for a wireless SSID at a site.

    If a VLAN is already allocated for this SSID + intent, return the
    existing one (idempotent).

    Args:
        site:      Nautobot Location ORM object (or None for global pool)
        ssid_name: SSID name string
        intent:    Intent ORM object

    Returns:
        VLAN ID integer e.g. 201

    Raises:
        ValueError: if pool is exhausted or not found
    """
    existing = WirelessVlanAllocation.objects.filter(intent=intent, ssid_name=ssid_name).first()
    if existing:
        logger.info(
            "Reusing existing wireless VLAN %s for SSID '%s' (intent: %s)",
            existing.vlan_id,
            ssid_name,
            intent.intent_id,
        )
        return existing.vlan_id

    with transaction.atomic():
        # Try site-specific pool first, fall back to global
        pool = None
        if site:
            pool = WirelessVlanPool.objects.select_for_update().filter(site=site).first()
        if not pool:
            pool = WirelessVlanPool.objects.select_for_update().filter(site__isnull=True).first()

        if not pool:
            raise ValueError(
                f"No wireless VLAN pool found for site '{site}'. "
                f"Create one in Nautobot admin under "
                f"Intent Engine → Wireless VLAN Pools."
            )

        used = set(WirelessVlanAllocation.objects.filter(pool=pool).values_list("vlan_id", flat=True))

        for i in range(pool.range_start, pool.range_end + 1):
            if i not in used:
                alloc = WirelessVlanAllocation.objects.create(
                    pool=pool,
                    vlan_id=i,
                    ssid_name=ssid_name,
                    intent=intent,
                )
                logger.info(
                    "Allocated wireless VLAN %s for SSID '%s' (intent: %s)",
                    i,
                    ssid_name,
                    intent.intent_id,
                )
                return alloc.vlan_id

        raise ValueError(
            f"Wireless VLAN pool '{pool.name}' exhausted. "
            f"Range {pool.range_start}-{pool.range_end} is fully allocated. "
            f"Expand the pool range or create a new pool."
        )
