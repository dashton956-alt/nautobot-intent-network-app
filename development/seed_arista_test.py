"""Seed Nautobot with Arista-focused test data for the Intent Networking plugin.

Creates a single Arista EOS device (lab-arista-sw01) with realistic
interfaces, management IPs, and a broad set of intents covering many
intent types so every part of the plugin can be exercised.

Usage (inside nautobot shell / nbshell):
    exec(open("development/seed_arista_test.py").read())
"""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

# ─── Nautobot core models ────────────────────────────────────────────────────
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
)
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import VRF, IPAddress, IPAddressToInterface, Namespace, Prefix
from nautobot.ipam.models import RouteTarget as NautobotRouteTarget
from nautobot.tenancy.models import Tenant

# ─── Plugin models ───────────────────────────────────────────────────────────
from intent_networking.models import (
    DeploymentStage,
    Intent,
    IntentAuditEntry,
    IntentTypeChoices,
    ManagedLoopback,
    ManagedLoopbackPool,
    ResolutionPlan,
    TunnelIdPool,
    VerificationResult,
    VniAllocation,
    VxlanVniPool,
    WirelessVlanPool,
)

now = timezone.now()

print("=" * 60)
print("  Intent Networking — Arista Single-Device Test Seed")
print("=" * 60)

# ═════════════════════════════════════════════════════════════════════════════
# 1. Statuses
# ═════════════════════════════════════════════════════════════════════════════
print("\n[1/14] Creating statuses...")
intent_ct = ContentType.objects.get_for_model(Intent)

INTENT_STATUSES = [
    "Draft",
    "Validated",
    "Deploying",
    "Deployed",
    "Failed",
    "Rolled Back",
    "Deprecated",
]
status_map = {}
for name in INTENT_STATUSES:
    s, created = Status.objects.get_or_create(name=name)
    s.content_types.add(intent_ct)
    status_map[name] = s
    print(f"  {'Created' if created else 'Exists '} status: {name}")

for model_class in (Device, Location, Interface, IPAddress, Prefix):
    ct = ContentType.objects.get_for_model(model_class)
    for name in ["Active", "Planned", "Staging", "Decommissioning"]:
        s, _ = Status.objects.get_or_create(name=name)
        s.content_types.add(ct)

active_status = Status.objects.get(name="Active")

# ═════════════════════════════════════════════════════════════════════════════
# 2. Tenant
# ═════════════════════════════════════════════════════════════════════════════
print("\n[2/14] Creating tenant...")
tenant, created = Tenant.objects.get_or_create(name="Arista Lab")
print(f"  {'Created' if created else 'Exists '} tenant: Arista Lab")

# ═════════════════════════════════════════════════════════════════════════════
# 3. Locations
# ═════════════════════════════════════════════════════════════════════════════
print("\n[3/14] Creating locations...")
region_type, _ = LocationType.objects.get_or_create(name="Region")
site_type, _ = LocationType.objects.get_or_create(name="Site", parent=region_type)
site_type.content_types.add(ContentType.objects.get_for_model(Device))

region, _ = Location.objects.get_or_create(
    name="Lab-Region",
    location_type=region_type,
    defaults={"status": active_status},
)
site, created = Location.objects.get_or_create(
    name="LAB-DC1",
    location_type=site_type,
    defaults={"status": active_status, "parent": region},
)
print(f"  {'Created' if created else 'Exists '} location: Lab-Region / LAB-DC1")

# ═════════════════════════════════════════════════════════════════════════════
# 4. Manufacturer, Platform, Device Type, Role, Device
# ═════════════════════════════════════════════════════════════════════════════
print("\n[4/14] Creating Arista device...")
arista, _ = Manufacturer.objects.get_or_create(name="Arista")

platform, _ = Platform.objects.get_or_create(
    name="arista-eos",
    defaults={
        "manufacturer": arista,
        "network_driver": "arista_eos",
        "napalm_driver": "eos",
    },
)

dt_7280, _ = DeviceType.objects.get_or_create(
    model="DCS-7280SR-48C6",
    defaults={"manufacturer": arista},
)

device_ct = ContentType.objects.get_for_model(Device)
leaf_role, _ = Role.objects.get_or_create(name="Leaf Switch")
leaf_role.content_types.add(device_ct)

device, created = Device.objects.get_or_create(
    name="lab-arista-sw01",
    defaults={
        "device_type": dt_7280,
        "role": leaf_role,
        "location": site,
        "status": active_status,
        "tenant": tenant,
        "platform": platform,
    },
)
print(f"  {'Created' if created else 'Exists '} device: lab-arista-sw01 (DCS-7280SR-48C6) @ LAB-DC1")

# ── Additional devices for spine-leaf fabric ─────────────────────────
spine_role, _ = Role.objects.get_or_create(name="Spine Switch")
spine_role.content_types.add(device_ct)

dt_7500, _ = DeviceType.objects.get_or_create(
    model="DCS-7500R3-36CQ",
    defaults={"manufacturer": arista},
)

device2, created = Device.objects.get_or_create(
    name="lab-arista-sw02",
    defaults={
        "device_type": dt_7280,
        "role": leaf_role,
        "location": site,
        "status": active_status,
        "tenant": tenant,
        "platform": platform,
    },
)
print(f"  {'Created' if created else 'Exists '} device: lab-arista-sw02 (DCS-7280SR-48C6) @ LAB-DC1")

spine1, created = Device.objects.get_or_create(
    name="lab-spine-01",
    defaults={
        "device_type": dt_7500,
        "role": spine_role,
        "location": site,
        "status": active_status,
        "tenant": tenant,
        "platform": platform,
    },
)
print(f"  {'Created' if created else 'Exists '} device: lab-spine-01 (DCS-7500R3-36CQ) @ LAB-DC1")

spine2, created = Device.objects.get_or_create(
    name="lab-spine-02",
    defaults={
        "device_type": dt_7500,
        "role": spine_role,
        "location": site,
        "status": active_status,
        "tenant": tenant,
        "platform": platform,
    },
)
print(f"  {'Created' if created else 'Exists '} device: lab-spine-02 (DCS-7500R3-36CQ) @ LAB-DC1")

# ═════════════════════════════════════════════════════════════════════════════
# 5. Interfaces & Management IP
# ═════════════════════════════════════════════════════════════════════════════
print("\n[5/14] Creating interfaces...")
ns, _ = Namespace.objects.get_or_create(name="Global")

# Ensure prefixes exist for IP allocation
PREFIXES = [
    "10.0.0.0/8",
    "10.0.0.0/24",  # Loopbacks
    "10.255.0.0/24",  # Management
    "10.10.0.0/24",  # P2P links
    "10.20.0.0/16",  # Server VLANs supernet
    "10.20.0.0/24",  # Server VLAN 100 — PROD
    "10.20.1.0/24",  # Server VLAN 101 — DEV
    "10.20.2.0/24",  # Server VLAN 200 — STORAGE
    "10.20.3.0/24",  # Server VLAN 300 — MGMT
    "10.30.0.0/24",  # Guest network
    "10.10.1.0/24",  # Inter-spine P2P links
    "172.20.20.0/24",  # containerlab management
    "192.168.100.0/24",  # IPSec endpoints
]
for pfx_str in PREFIXES:
    Prefix.objects.get_or_create(
        prefix=pfx_str,
        defaults={"namespace": ns, "status": active_status},
    )


def _get_parent_prefix(ip_str):
    """Return the correct parent prefix for an IP."""
    host = ip_str.split("/")[0]
    if host.startswith("192.168.100."):
        return Prefix.objects.get(prefix="192.168.100.0/24")
    if host.startswith("172.20.20."):
        return Prefix.objects.get(prefix="172.20.20.0/24")
    if host.startswith("10.30."):
        return Prefix.objects.get(prefix="10.30.0.0/24")
    if host.startswith("10.20.3."):
        return Prefix.objects.get(prefix="10.20.3.0/24")
    if host.startswith("10.20.2."):
        return Prefix.objects.get(prefix="10.20.2.0/24")
    if host.startswith("10.20.1."):
        return Prefix.objects.get(prefix="10.20.1.0/24")
    if host.startswith("10.20.0."):
        return Prefix.objects.get(prefix="10.20.0.0/24")
    if host.startswith("10.10.1."):
        return Prefix.objects.get(prefix="10.10.1.0/24")
    if host.startswith("10.10."):
        return Prefix.objects.get(prefix="10.10.0.0/24")
    if host.startswith("10.255."):
        return Prefix.objects.get(prefix="10.255.0.0/24")
    if host.startswith("10.0.0."):
        return Prefix.objects.get(prefix="10.0.0.0/24")
    return Prefix.objects.get(prefix="10.0.0.0/8")


def _get_or_create_ip(ip_str):
    """Create an IPAddress in Nautobot (needs parent prefix)."""
    parent = _get_parent_prefix(ip_str)
    host_part = ip_str.split("/")[0]
    mask_part = int(ip_str.split("/")[1])
    try:
        ip_obj = IPAddress.objects.get(host=host_part, mask_length=mask_part, parent=parent)
        return ip_obj, False
    except IPAddress.DoesNotExist:
        ip_obj = IPAddress(address=ip_str, parent=parent, status=active_status)
        ip_obj.validated_save()
        return ip_obj, True


# Arista cEOS interface naming (containerlab — no breakout ports):
# Management0, Loopback0, Ethernet1-48, Ethernet49-54 (uplinks), Vlan*, Port-Channel*
INTERFACES = [
    # (name, type, enabled, ip, description, mtu, mac, speed_kbps)
    ("Loopback0", "virtual", True, "10.0.0.100/32", "Router-ID / VTEP source", None, None, None),
    ("Loopback1", "virtual", True, "10.0.0.101/32", "VXLAN VTEP loopback", None, None, None),
    ("Management0", "1000base-t", True, "172.20.20.3/24", "OOB Management", 1500, "00:1C:73:01:00:00", 1000000),
    # Uplinks to spines
    (
        "Ethernet49",
        "100gbase-x-qsfp28",
        True,
        "10.10.0.1/31",
        "TO lab-spine-01 Ethernet1",
        9214,
        "00:1C:73:01:00:31",
        100000000,
    ),
    (
        "Ethernet50",
        "100gbase-x-qsfp28",
        True,
        "10.10.0.3/31",
        "TO lab-spine-02 Ethernet1",
        9214,
        "00:1C:73:01:00:32",
        100000000,
    ),
    # Server-facing access ports
    ("Ethernet1", "10gbase-x-sfpp", True, None, "Server-01 NIC1 — PROD", 9000, "00:1C:73:01:00:01", 10000000),
    ("Ethernet2", "10gbase-x-sfpp", True, None, "Server-02 NIC1 — PROD", 9000, "00:1C:73:01:00:02", 10000000),
    ("Ethernet3", "10gbase-x-sfpp", True, None, "Server-03 NIC1 — DEV", 9000, "00:1C:73:01:00:03", 10000000),
    ("Ethernet4", "10gbase-x-sfpp", True, None, "Server-04 NIC1 — STORAGE", 9000, "00:1C:73:01:00:04", 10000000),
    ("Ethernet5", "10gbase-x-sfpp", True, None, "Server-05 NIC1 — MGMT", 9000, "00:1C:73:01:00:05", 10000000),
    ("Ethernet6", "10gbase-x-sfpp", False, None, "SPARE — not provisioned", 9000, "00:1C:73:01:00:06", 10000000),
    ("Ethernet7", "10gbase-x-sfpp", False, None, "SPARE — not provisioned", 9000, "00:1C:73:01:00:07", 10000000),
    ("Ethernet8", "10gbase-x-sfpp", False, None, "SPARE — not provisioned", 9000, "00:1C:73:01:00:08", 10000000),
    # MLAG peer-link
    ("Ethernet51", "100gbase-x-qsfp28", True, None, "MLAG peer-link member", 9214, "00:1C:73:01:00:33", 100000000),
    ("Ethernet52", "100gbase-x-qsfp28", True, None, "MLAG peer-link member", 9214, "00:1C:73:01:00:34", 100000000),
    # Port-Channels
    ("Port-Channel1", "lag", True, None, "MLAG peer-link", 9214, None, None),
    ("Port-Channel10", "lag", True, None, "Server-01 bond (LACP)", 9000, None, None),
    # VXLAN tunnel interface
    ("Vxlan1", "virtual", True, None, "VXLAN tunnel interface", None, None, None),
    # SVIs
    ("Vlan100", "virtual", True, "10.20.0.1/24", "SVI — SERVERS-PROD", 9000, None, None),
    ("Vlan101", "virtual", True, "10.20.1.1/24", "SVI — SERVERS-DEV", 9000, None, None),
    ("Vlan200", "virtual", True, "10.20.2.1/24", "SVI — STORAGE", 9000, None, None),
    ("Vlan300", "virtual", True, "10.20.3.1/24", "SVI — OOB-MGMT", 1500, None, None),
    ("Vlan999", "virtual", True, None, "QUARANTINE — no IP", 1500, None, None),
]

mgmt_ip_obj = None
for iface_name, iface_type, enabled, ip_str, desc, mtu, mac, speed in INTERFACES:
    iface, ic = Interface.objects.get_or_create(
        device=device,
        name=iface_name,
        defaults={
            "type": iface_type,
            "enabled": enabled,
            "status": active_status,
            "description": desc or "",
            "mtu": mtu,
            "mac_address": mac,
            "speed": speed,
        },
    )
    if ip_str:
        ip_obj, ip_created = _get_or_create_ip(ip_str)
        IPAddressToInterface.objects.get_or_create(ip_address=ip_obj, interface=iface)
        if iface_name == "Management0":
            mgmt_ip_obj = ip_obj
    tag = "Created" if ic else "Exists "
    print(f"  {tag} interface: {iface_name}")

if mgmt_ip_obj and not device.primary_ip4:
    device.primary_ip4 = mgmt_ip_obj
    device.validated_save()
    print("  Set primary_ip4 → 172.20.20.3")

# ── Interfaces for lab-arista-sw02 (leaf-02) ─────────────────────────────
print("\n[5b/14] Creating interfaces for lab-arista-sw02...")
INTERFACES_SW02 = [
    ("Loopback0", "virtual", True, "10.0.0.102/32", "Router-ID / VTEP source", None, None, None),
    ("Loopback1", "virtual", True, "10.0.0.103/32", "VXLAN VTEP loopback", None, None, None),
    ("Management0", "1000base-t", True, "172.20.20.4/24", "OOB Management", 1500, None, 1000000),
    ("Ethernet49", "100gbase-x-qsfp28", True, "10.10.0.5/31", "TO lab-spine-01 Ethernet2", 9214, None, 100000000),
    ("Ethernet50", "100gbase-x-qsfp28", True, "10.10.0.7/31", "TO lab-spine-02 Ethernet2", 9214, None, 100000000),
    ("Ethernet1", "10gbase-x-sfpp", True, None, "Server-06 NIC1 — PROD", 9000, None, 10000000),
    ("Ethernet2", "10gbase-x-sfpp", True, None, "Server-07 NIC1 — PROD", 9000, None, 10000000),
    ("Ethernet3", "10gbase-x-sfpp", True, None, "Server-08 NIC1 — DEV", 9000, None, 10000000),
    ("Ethernet4", "10gbase-x-sfpp", True, None, "Server-09 NIC1 — STORAGE", 9000, None, 10000000),
    ("Ethernet5", "10gbase-x-sfpp", True, None, "Server-10 NIC1 — MGMT", 9000, None, 10000000),
    ("Ethernet51", "100gbase-x-qsfp28", True, None, "MLAG peer-link member", 9214, None, 100000000),
    ("Ethernet52", "100gbase-x-qsfp28", True, None, "MLAG peer-link member", 9214, None, 100000000),
    ("Port-Channel1", "lag", True, None, "MLAG peer-link", 9214, None, None),
    ("Vxlan1", "virtual", True, None, "VXLAN tunnel interface", None, None, None),
    ("Vlan100", "virtual", True, "10.20.0.2/24", "SVI — SERVERS-PROD", 9000, None, None),
    ("Vlan101", "virtual", True, "10.20.1.2/24", "SVI — SERVERS-DEV", 9000, None, None),
]
sw02_mgmt_ip = None
for iface_name, iface_type, enabled, ip_str, desc, mtu, mac, speed in INTERFACES_SW02:
    iface, ic = Interface.objects.get_or_create(
        device=device2, name=iface_name,
        defaults={"type": iface_type, "enabled": enabled, "status": active_status,
                  "description": desc or "", "mtu": mtu, "mac_address": mac, "speed": speed},
    )
    if ip_str:
        ip_obj, _ = _get_or_create_ip(ip_str)
        IPAddressToInterface.objects.get_or_create(ip_address=ip_obj, interface=iface)
        if iface_name == "Management0":
            sw02_mgmt_ip = ip_obj
    print(f"  {'Created' if ic else 'Exists '} interface: sw02/{iface_name}")
if sw02_mgmt_ip and not device2.primary_ip4:
    device2.primary_ip4 = sw02_mgmt_ip
    device2.validated_save()
    print("  Set sw02 primary_ip4 → 172.20.20.4")

# ── Interfaces for lab-spine-01 ──────────────────────────────────────────
print("\n[5c/14] Creating interfaces for lab-spine-01...")
INTERFACES_SPINE1 = [
    ("Loopback0", "virtual", True, "10.0.0.200/32", "Router-ID", None, None, None),
    ("Management0", "1000base-t", True, "172.20.20.5/24", "OOB Management", 1500, None, 1000000),
    ("Ethernet1", "100gbase-x-qsfp28", True, "10.10.0.0/31", "TO lab-arista-sw01 Ethernet49", 9214, None, 100000000),
    ("Ethernet2", "100gbase-x-qsfp28", True, "10.10.0.4/31", "TO lab-arista-sw02 Ethernet49", 9214, None, 100000000),
    ("Ethernet3", "100gbase-x-qsfp28", True, "10.10.1.0/31", "TO lab-spine-02 Ethernet3", 9214, None, 100000000),
]
spine1_mgmt_ip = None
for iface_name, iface_type, enabled, ip_str, desc, mtu, mac, speed in INTERFACES_SPINE1:
    iface, ic = Interface.objects.get_or_create(
        device=spine1, name=iface_name,
        defaults={"type": iface_type, "enabled": enabled, "status": active_status,
                  "description": desc or "", "mtu": mtu, "mac_address": mac, "speed": speed},
    )
    if ip_str:
        ip_obj, _ = _get_or_create_ip(ip_str)
        IPAddressToInterface.objects.get_or_create(ip_address=ip_obj, interface=iface)
        if iface_name == "Management0":
            spine1_mgmt_ip = ip_obj
    print(f"  {'Created' if ic else 'Exists '} interface: spine1/{iface_name}")
if spine1_mgmt_ip and not spine1.primary_ip4:
    spine1.primary_ip4 = spine1_mgmt_ip
    spine1.validated_save()
    print("  Set spine1 primary_ip4 → 172.20.20.5")

# ── Interfaces for lab-spine-02 ──────────────────────────────────────────
print("\n[5d/14] Creating interfaces for lab-spine-02...")
INTERFACES_SPINE2 = [
    ("Loopback0", "virtual", True, "10.0.0.201/32", "Router-ID", None, None, None),
    ("Management0", "1000base-t", True, "172.20.20.6/24", "OOB Management", 1500, None, 1000000),
    ("Ethernet1", "100gbase-x-qsfp28", True, "10.10.0.2/31", "TO lab-arista-sw01 Ethernet50", 9214, None, 100000000),
    ("Ethernet2", "100gbase-x-qsfp28", True, "10.10.0.6/31", "TO lab-arista-sw02 Ethernet50", 9214, None, 100000000),
    ("Ethernet3", "100gbase-x-qsfp28", True, "10.10.1.1/31", "TO lab-spine-01 Ethernet3", 9214, None, 100000000),
]
spine2_mgmt_ip = None
for iface_name, iface_type, enabled, ip_str, desc, mtu, mac, speed in INTERFACES_SPINE2:
    iface, ic = Interface.objects.get_or_create(
        device=spine2, name=iface_name,
        defaults={"type": iface_type, "enabled": enabled, "status": active_status,
                  "description": desc or "", "mtu": mtu, "mac_address": mac, "speed": speed},
    )
    if ip_str:
        ip_obj, _ = _get_or_create_ip(ip_str)
        IPAddressToInterface.objects.get_or_create(ip_address=ip_obj, interface=iface)
        if iface_name == "Management0":
            spine2_mgmt_ip = ip_obj
    print(f"  {'Created' if ic else 'Exists '} interface: spine2/{iface_name}")
if spine2_mgmt_ip and not spine2.primary_ip4:
    spine2.primary_ip4 = spine2_mgmt_ip
    spine2.validated_save()
    print("  Set spine2 primary_ip4 → 172.20.20.6")

# ═════════════════════════════════════════════════════════════════════════════
# 6. Intents — broad coverage of intent types all targeting lab-arista-sw01
# ═════════════════════════════════════════════════════════════════════════════
print("\n[6/14] Creating intents...")

INTENTS = [
    # ── EVPN/VXLAN Fabric ─────────────────────────────────────────────────
    {
        "intent_id": "lab-dc-evpn-fabric-001",
        "intent_type": IntentTypeChoices.EVPN_VXLAN_FABRIC,
        "status": "Deployed",
        "version": 2,
        "change_ticket": "CHG0050001",
        "approved_by": "d.network",
        "git_commit_sha": "aabbccdd11223344556677889900aabbccddeeff",
        "git_branch": "main",
        "git_pr_number": 301,
        "deployed_at": now - timedelta(days=14),
        "last_verified_at": now - timedelta(hours=1),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "extended",
        "verification_trigger": "both",
        "verification_fail_action": "rollback",
        "verification_schedule": "0 */6 * * *",
        "intent_data": {
            "type": "evpn_vxlan_fabric",
            "name": "Lab DC EVPN Fabric",
            "description": "VXLAN EVPN spine-leaf fabric for Lab DC1 — BGP underlay and overlay",
            "sites": ["LAB-DC1"],
            "fabric": {
                "name": "lab-dc1-fabric",
                "spines": ["lab-spine-01", "lab-spine-02"],
                "leaves": ["lab-arista-sw01", "lab-arista-sw02"],
                "underlay_protocol": "ebgp",
                "spine_asn": 65000,
                "leaf_asn_start": 65001,
                "overlay_asn": 65000,
                "anycast_gateway_mac": "00:00:00:aa:bb:cc",
                "replication_mode": "ingress",
                "vtep_loopback": "Loopback1",
            },
        },
    },
    # ── L2VNI Provisioning ────────────────────────────────────────────────
    {
        "intent_id": "lab-dc-l2vni-prod-001",
        "intent_type": IntentTypeChoices.L2VNI,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050002",
        "approved_by": "d.network",
        "git_commit_sha": "1122334455667788990011223344556677889900",
        "git_branch": "main",
        "git_pr_number": 302,
        "deployed_at": now - timedelta(days=12),
        "last_verified_at": now - timedelta(hours=2),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "l2vni",
            "name": "SERVERS-PROD L2VNI",
            "description": "Map VLAN 100 (SERVERS-PROD) to VNI 10100 across Lab DC1 fabric",
            "scope": {"sites": ["LAB-DC1"]},
            "vlan_id": 100,
            "vlan_name": "SERVERS-PROD",
            "replication_mode": "ingress-replication",
        },
    },
    # ── L3VNI / Tenant VRF over VXLAN ─────────────────────────────────────
    {
        "intent_id": "lab-dc-l3vni-tenant-001",
        "intent_type": IntentTypeChoices.L3VNI,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050003",
        "approved_by": "d.network",
        "git_commit_sha": "2233445566778899001122334455667788990011",
        "git_branch": "main",
        "git_pr_number": 303,
        "deployed_at": now - timedelta(days=11),
        "last_verified_at": now - timedelta(hours=3),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "extended",
        "verification_trigger": "both",
        "verification_fail_action": "rollback",
        "verification_schedule": "0 */4 * * *",
        "intent_data": {
            "type": "l3vni",
            "name": "Tenant VRF over VXLAN",
            "description": "L3VNI for VRF TENANT-A — inter-VLAN routing over VXLAN fabric",
            "scope": {"sites": ["LAB-DC1"]},
            "vrf_name": "VRF-TENANT-A",
            "anycast_gateway_mac": "0000.00aa.bbcc",
            "redistribute_connected": True,
        },
    },
    # ── VLAN Provisioning ─────────────────────────────────────────────────
    {
        "intent_id": "lab-vlans-dc1-001",
        "intent_type": IntentTypeChoices.VLAN_PROVISION,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050004",
        "approved_by": "d.network",
        "git_commit_sha": "3344556677889900112233445566778899001122",
        "git_branch": "main",
        "git_pr_number": 304,
        "deployed_at": now - timedelta(days=20),
        "last_verified_at": now - timedelta(hours=1),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "vlan_provision",
            "name": "Lab DC1 Server VLANs",
            "description": "Provision standard server VLANs on all leaf switches",
            "scope": {"sites": ["LAB-DC1"], "roles": ["Leaf Switch"]},
            "vlans": [
                {"id": 100, "name": "SERVERS-PROD", "description": "Production server VLAN"},
                {"id": 101, "name": "SERVERS-DEV", "description": "Development server VLAN"},
                {"id": 200, "name": "STORAGE", "description": "Storage network VLAN"},
                {"id": 300, "name": "MGMT", "description": "Out-of-band management VLAN"},
                {"id": 999, "name": "QUARANTINE", "description": "Quarantine VLAN"},
            ],
        },
    },
    # ── BGP eBGP (Underlay) ───────────────────────────────────────────────
    {
        "intent_id": "lab-bgp-underlay-001",
        "intent_type": IntentTypeChoices.BGP_EBGP,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050005",
        "approved_by": "d.network",
        "git_commit_sha": "4455667788990011223344556677889900112233",
        "git_branch": "main",
        "git_pr_number": 305,
        "deployed_at": now - timedelta(days=14),
        "last_verified_at": now - timedelta(minutes=30),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "extended",
        "verification_trigger": "both",
        "verification_fail_action": "rollback",
        "verification_schedule": "*/15 * * * *",
        "intent_data": {
            "type": "bgp_ebgp",
            "name": "DC Underlay eBGP — Spine 1",
            "description": "eBGP underlay peering from leaf lab-arista-sw01 to spine-01",
            "scope": {"devices": ["lab-arista-sw01"]},
            "local_asn": 65001,
            "neighbor_ip": "10.10.0.0",
            "neighbor_asn": 65000,
            "peer_description": "lab-spine-01 Ethernet1",
            "bfd": True,
            "max_prefix": 100,
        },
    },
    # ── MLAG ──────────────────────────────────────────────────────────────
    {
        "intent_id": "lab-mlag-pair-001",
        "intent_type": IntentTypeChoices.MLAG,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050006",
        "approved_by": "d.network",
        "git_commit_sha": "5566778899001122334455667788990011223344",
        "git_branch": "main",
        "git_pr_number": 306,
        "deployed_at": now - timedelta(days=14),
        "last_verified_at": now - timedelta(hours=1),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mlag",
            "name": "Leaf MLAG Pair",
            "description": "MLAG between lab-arista-sw01 and lab-arista-sw02",
            "scope": {"sites": ["LAB-DC1"]},
            "peer_link_interfaces": ["Ethernet51", "Ethernet52"],
            "domain_id": "MLAG-LAB-01",
            "peer_address": "10.10.255.2",
            "keepalive_vlan": 4094,
        },
    },
    # ── ACL / Security ────────────────────────────────────────────────────
    {
        "intent_id": "lab-acl-server-segment-001",
        "intent_type": IntentTypeChoices.ACL,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050007",
        "approved_by": "s.security",
        "git_commit_sha": "6677889900112233445566778899001122334455",
        "git_branch": "main",
        "git_pr_number": 307,
        "deployed_at": now - timedelta(days=10),
        "last_verified_at": now - timedelta(hours=2),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "extended",
        "verification_trigger": "both",
        "verification_fail_action": "rollback",
        "verification_schedule": "0 */4 * * *",
        "intent_data": {
            "type": "acl",
            "name": "Server Segmentation ACLs",
            "description": "Restrict dev servers from reaching production and storage VLANs",
            "scope": {"devices": ["lab-arista-sw01"]},
            "acl_name": "DEV-SEGMENTATION",
            "acl_type": "extended",
            "entries": [
                {
                    "seq": 10,
                    "action": "deny",
                    "protocol": "ip",
                    "source": "10.20.1.0/24",
                    "destination": "10.20.0.0/24",
                },
                {
                    "seq": 20,
                    "action": "deny",
                    "protocol": "ip",
                    "source": "10.20.1.0/24",
                    "destination": "10.20.2.0/24",
                },
                {"seq": 1000, "action": "permit", "protocol": "ip", "source": "any", "destination": "any"},
            ],
            "apply_interfaces": ["Vlan101"],
            "direction": "out",
        },
    },
    # ── NTP Management ────────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-ntp-001",
        "intent_type": IntentTypeChoices.MGMT_NTP,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050008",
        "approved_by": "d.network",
        "git_commit_sha": "7788990011223344556677889900112233445566",
        "git_branch": "main",
        "git_pr_number": 308,
        "deployed_at": now - timedelta(days=30),
        "last_verified_at": now - timedelta(hours=6),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_ntp",
            "name": "NTP Configuration",
            "description": "NTP configuration — all lab devices — primary and secondary servers",
            "scope": {"all_tenant_devices": True},
            "servers": ["10.255.0.1", "10.255.0.2", "pool.ntp.org"],
            "prefer": "10.255.0.1",
            "source_interface": "Management0",
        },
    },
    # ── SNMP Management ───────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-snmp-001",
        "intent_type": IntentTypeChoices.MGMT_SNMP,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050009",
        "approved_by": "d.network",
        "git_commit_sha": "8899001122334455667788990011223344556677",
        "git_branch": "main",
        "git_pr_number": 309,
        "deployed_at": now - timedelta(days=30),
        "last_verified_at": now - timedelta(hours=6),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_snmp",
            "name": "SNMPv3 Configuration",
            "description": "SNMPv3 — all lab devices — trap to central collector",
            "scope": {"all_tenant_devices": True},
            "version": "v3",
            "views": [{"name": "labview", "oid": "1.3.6.1"}],
            "groups": [{"name": "labgroup", "security_level": "priv", "read_view": "labview", "write_view": "labview"}],
            "users": [{"name": "labmonitor", "group": "labgroup", "auth_protocol": "sha256", "auth_password": "AuthP@ss123!", "priv_protocol": "aes256", "priv_password": "PrivP@ss123!"}],
            "trap_targets": ["10.255.0.50", "10.255.0.51"],
            "location": "LAB-DC1",
            "contact": "noc@arista-lab.local",
        },
    },
    # ── MOTD Banner ───────────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-motd-001",
        "intent_type": IntentTypeChoices.MGMT_MOTD,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050010",
        "approved_by": "d.network",
        "git_commit_sha": "9900112233445566778899001122334455667788",
        "git_branch": "main",
        "git_pr_number": 310,
        "deployed_at": now - timedelta(days=30),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_motd",
            "name": "Login Banner",
            "description": "Standard login banner for all lab devices",
            "scope": {"all_tenant_devices": True},
            "motd_banner": "*** AUTHORIZED ACCESS ONLY — Arista Lab ***\nManaged by Intent Networking — All sessions logged.\n",
            "login_banner": "*** WARNING: Unauthorized access prohibited ***\n",
        },
    },
    # ── LLDP / CDP Policy ─────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-lldp-001",
        "intent_type": IntentTypeChoices.MGMT_LLDP_CDP,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050011",
        "approved_by": "d.network",
        "git_commit_sha": "0011223344556677889900112233445566778899",
        "git_branch": "main",
        "git_pr_number": 311,
        "deployed_at": now - timedelta(days=30),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_lldp_cdp",
            "name": "LLDP/CDP Policy",
            "description": "Enable LLDP, disable CDP on all lab devices",
            "scope": {"all_tenant_devices": True},
            "lldp_global": True,
            "cdp_global": False,
        },
    },
    # ── QoS Classification ────────────────────────────────────────────────
    {
        "intent_id": "lab-qos-classify-001",
        "intent_type": IntentTypeChoices.QOS_CLASSIFY,
        "status": "Validated",
        "version": 1,
        "change_ticket": "CHG0050012",
        "approved_by": "d.network",
        "git_branch": "feature/qos-policy",
        "git_pr_number": 312,
        "controller_type": "nornir",
        "deployment_strategy": "canary",
        "verification_level": "extended",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "rollback",
        "intent_data": {
            "type": "qos_classify",
            "name": "QoS Traffic Classification",
            "description": "Classify storage and production traffic into QoS queues",
            "scope": {"devices": ["lab-arista-sw01"]},
            "class_maps": [
                {
                    "name": "PROD-CRITICAL",
                    "acl": "ACL-PROD-CRITICAL",
                    "rules": [{"action": "permit", "protocol": "ip", "source": "any", "destination": "10.20.0.0/24"}],
                    "set_dscp": "ef",
                },
                {
                    "name": "STORAGE",
                    "acl": "ACL-STORAGE",
                    "rules": [{"action": "permit", "protocol": "ip", "source": "any", "destination": "10.20.2.0/24"}],
                    "set_dscp": "af41",
                },
                {
                    "name": "DEV-BEST-EFFORT",
                    "acl": "ACL-DEV-BE",
                    "rules": [{"action": "permit", "protocol": "ip", "source": "any", "destination": "10.20.1.0/24"}],
                    "set_dscp": "default",
                },
            ],
            "policy_map": "QOS-POLICY",
            "apply_interfaces": ["Ethernet49", "Ethernet50"],
            "direction": "input",
        },
    },
    # ── Port Security ─────────────────────────────────────────────────────
    {
        "intent_id": "lab-port-security-001",
        "intent_type": IntentTypeChoices.PORT_SECURITY,
        "status": "Deploying",
        "version": 1,
        "change_ticket": "CHG0050013",
        "approved_by": "s.security",
        "git_commit_sha": "aabb112233445566778899001122334455667788",
        "git_branch": "main",
        "git_pr_number": 313,
        "controller_type": "nornir",
        "deployment_strategy": "rolling",
        "verification_level": "extended",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "rollback",
        "intent_data": {
            "type": "port_security",
            "name": "Server Port Security",
            "description": "MAC limit on server-facing ports — max 4 MACs per port",
            "scope": {"devices": ["lab-arista-sw01"]},
            "interface": "Ethernet1",
            "max_mac": 4,
            "violation_action": "restrict",
            "aging_time": 3600,
        },
    },
    # ── STP Policy ────────────────────────────────────────────────────────
    {
        "intent_id": "lab-stp-policy-001",
        "intent_type": IntentTypeChoices.STP_POLICY,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050014",
        "approved_by": "d.network",
        "git_commit_sha": "bbcc112233445566778899001122334455667788",
        "git_branch": "main",
        "git_pr_number": 314,
        "deployed_at": now - timedelta(days=20),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "stp_policy",
            "name": "Spanning Tree Policy",
            "description": "MSTP with BPDU guard on access ports",
            "scope": {"devices": ["lab-arista-sw01"]},
            "stp_mode": "mstp",
            "mst_region": "LAB-DC1",
            "mst_revision": 1,
            "bpdu_guard_interfaces": ["Ethernet1", "Ethernet2", "Ethernet3", "Ethernet4", "Ethernet5"],
        },
    },
    # ── Global Config Bundle ──────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-global-config-001",
        "intent_type": IntentTypeChoices.MGMT_GLOBAL_CONFIG,
        "status": "Deployed",
        "version": 2,
        "change_ticket": "CHG0050015",
        "approved_by": "d.network",
        "git_commit_sha": "ccdd112233445566778899001122334455667788",
        "git_branch": "main",
        "git_pr_number": 315,
        "deployed_at": now - timedelta(days=30),
        "last_verified_at": now - timedelta(hours=6),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "extended",
        "verification_trigger": "both",
        "verification_fail_action": "alert",
        "verification_schedule": "0 0 * * *",
        "intent_data": {
            "type": "mgmt_global_config",
            "name": "Day-0 Global Config",
            "description": "Global management bundle — NTP, DNS, Syslog, SSH, banners, NETCONF",
            "scope": {"all_tenant_devices": True},
            "management": {
                "domain_name": "arista-lab.local",
                "ntp_servers": ["10.255.0.1", "10.255.0.2"],
                "dns_servers": ["10.255.0.10", "10.255.0.11"],
                "syslog_servers": [
                    {"host": "10.255.0.50", "port": 514, "protocol": "udp"},
                ],
                "ssh_version": 2,
                "ssh_timeout": 60,
                "netconf_enabled": True,
                "netconf_port": 830,
                "lldp_enabled": True,
                "cdp_enabled": False,
            },
        },
    },
    # ── DHCP Snooping ─────────────────────────────────────────────────────
    {
        "intent_id": "lab-dhcp-snooping-001",
        "intent_type": IntentTypeChoices.DHCP_SNOOPING,
        "status": "Draft",
        "version": 1,
        "git_branch": "feature/dhcp-snooping",
        "controller_type": "nornir",
        "deployment_strategy": "canary",
        "verification_level": "extended",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "rollback",
        "intent_data": {
            "type": "dhcp_snooping",
            "name": "DHCP Snooping",
            "description": "Enable DHCP snooping on server VLANs — trust uplinks only",
            "scope": {"devices": ["lab-arista-sw01"]},
            "vlans": [100, 101, 200],
            "trusted_interfaces": ["Ethernet49", "Ethernet50", "Port-Channel1"],
        },
    },
    # ── Storm Control ─────────────────────────────────────────────────────
    {
        "intent_id": "lab-storm-control-001",
        "intent_type": IntentTypeChoices.STORM_CONTROL,
        "status": "Failed",
        "version": 1,
        "change_ticket": "CHG0050017",
        "approved_by": "d.network",
        "git_commit_sha": "eeff112233445566778899001122334455667788",
        "git_branch": "main",
        "git_pr_number": 317,
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "storm_control",
            "name": "Storm Control on Access Ports",
            "description": "Broadcast/multicast storm control on server-facing Ethernet ports",
            "scope": {"devices": ["lab-arista-sw01"]},
            "interfaces": ["Ethernet1", "Ethernet2", "Ethernet3", "Ethernet4", "Ethernet5"],
            "broadcast_level": 10.0,
            "multicast_level": 10.0,
            "action": "trap",
        },
    },
    # ── Anycast Gateway ───────────────────────────────────────────────────
    {
        "intent_id": "lab-anycast-gw-001",
        "intent_type": IntentTypeChoices.ANYCAST_GATEWAY,
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0050018",
        "approved_by": "d.network",
        "git_commit_sha": "ff00112233445566778899001122334455667788",
        "git_branch": "main",
        "git_pr_number": 318,
        "deployed_at": now - timedelta(days=11),
        "last_verified_at": now - timedelta(hours=2),
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "anycast_gateway",
            "name": "Anycast Gateway — VLAN 100",
            "description": "Anycast gateway on VLAN 100 SVI for seamless VXLAN mobility",
            "scope": {"devices": ["lab-arista-sw01"]},
            "virtual_ip": "10.20.0.1",
            "vlan_id": 100,
            "subnet_mask": "255.255.255.0",
            "anycast_mac": "0000.00aa.bbcc",
            "vrf": "VRF-TENANT-A",
        },
    },
    # ── Rolled Back intent ────────────────────────────────────────────────
    {
        "intent_id": "lab-macsec-uplinks-001",
        "intent_type": IntentTypeChoices.MACSEC,
        "status": "Rolled Back",
        "version": 1,
        "change_ticket": "CHG0050019",
        "approved_by": "s.security",
        "git_commit_sha": "00aa112233445566778899001122334455667788",
        "git_branch": "main",
        "git_pr_number": 319,
        "deployed_at": now - timedelta(days=2),
        "controller_type": "nornir",
        "deployment_strategy": "canary",
        "verification_level": "extended",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "rollback",
        "intent_data": {
            "type": "macsec",
            "name": "MACsec on Spine Uplinks",
            "description": "MACsec encryption on spine-facing uplinks (rolled back — key mismatch)",
            "scope": {"devices": ["lab-arista-sw01"]},
            "interfaces": ["Ethernet49", "Ethernet50"],
            "cipher_suite": "GCM-AES-256",
            "policy_name": "MACSEC-UPLINK",
            "replay_protection": True,
        },
    },
    # ── Syslog Management ─────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-syslog-001",
        "intent_type": IntentTypeChoices.MGMT_SYSLOG,
        "status": "Draft",
        "version": 1,
        "change_ticket": "CHG0050020",
        "git_branch": "main",
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_syslog",
            "name": "Syslog Configuration",
            "description": "Syslog forwarding to central collectors — all lab devices",
            "scope": {"all_tenant_devices": True},
            "servers": ["10.255.0.50", "10.255.0.51"],
            "facility": "local7",
            "severity": "informational",
            "source_interface": "Management0",
        },
    },
    # ── NetFlow / IPFIX ───────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-netflow-001",
        "intent_type": IntentTypeChoices.MGMT_NETFLOW,
        "status": "Draft",
        "version": 1,
        "change_ticket": "CHG0050021",
        "git_branch": "main",
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_netflow",
            "name": "NetFlow Export",
            "description": "NetFlow v9 export from uplinks to central collector",
            "scope": {"devices": ["lab-arista-sw01"]},
            "collector_ip": "10.255.0.60",
            "collector_port": 9995,
            "source_interface": "Loopback0",
            "sampler_rate": 1000,
            "apply_interfaces": ["Ethernet49", "Ethernet50"],
        },
    },
    # ── Streaming Telemetry ───────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-telemetry-001",
        "intent_type": IntentTypeChoices.MGMT_TELEMETRY,
        "status": "Draft",
        "version": 1,
        "change_ticket": "CHG0050022",
        "git_branch": "main",
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_telemetry",
            "name": "gRPC Streaming Telemetry",
            "description": "gRPC dial-out telemetry for interface and BGP counters",
            "scope": {"devices": ["lab-arista-sw01"]},
            "destination_ip": "10.255.0.70",
            "destination_port": 57000,
            "protocol": "grpc",
            "encoding": "gpb",
            "subscriptions": [
                {"path": "/interfaces/interface/state/counters", "interval_ms": 10000},
                {"path": "/network-instances/network-instance/protocols/protocol/bgp", "interval_ms": 30000},
            ],
            "source_interface": "Management0",
        },
    },
    # ── SSH Access Control ────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-ssh-001",
        "intent_type": IntentTypeChoices.MGMT_SSH,
        "status": "Draft",
        "version": 1,
        "change_ticket": "CHG0050023",
        "git_branch": "main",
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_ssh",
            "name": "SSH Hardening",
            "description": "SSH access restricted to management subnet — all lab devices",
            "scope": {"all_tenant_devices": True},
            "allowed_networks": ["10.255.0.0/24", "10.0.0.0/24"],
            "timeout": 60,
            "retries": 3,
            "key_type": "rsa",
            "key_size": 4096,
            "acl_name": "SSH-MGMT-ONLY",
        },
    },
    # ── NETCONF / RESTCONF ────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-netconf-001",
        "intent_type": IntentTypeChoices.MGMT_NETCONF,
        "status": "Draft",
        "version": 1,
        "change_ticket": "CHG0050024",
        "git_branch": "main",
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_netconf",
            "name": "NETCONF and RESTCONF Enablement",
            "description": "Enable NETCONF and RESTCONF for automation — all lab devices",
            "scope": {"all_tenant_devices": True},
            "netconf_enabled": True,
            "netconf_port": 830,
            "netconf_vrf": "",
            "restconf_enabled": True,
            "restconf_port": 6020,
            "gnmi_enabled": False,
            "gnmi_port": 6030,
        },
    },
    # ── DHCP Server ───────────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-dhcp-server-001",
        "intent_type": IntentTypeChoices.MGMT_DHCP_SERVER,
        "status": "Draft",
        "version": 1,
        "change_ticket": "CHG0050025",
        "git_branch": "main",
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_dhcp_server",
            "name": "DHCP Server — Server MGMT Pool",
            "description": "DHCP pool for server management VLAN on lab-arista-sw01",
            "scope": {"devices": ["lab-arista-sw01"]},
            "pools": [
                {
                    "name": "SERVER-MGMT",
                    "network": "10.20.3.0/24",
                    "default_router": "10.20.3.1",
                    "dns_server": "10.255.0.10",
                    "lease_time": 86400,
                    "domain_name": "mgmt.arista-lab.local",
                },
            ],
            "excluded_addresses": [
                {"start": "10.20.3.1", "end": "10.20.3.10"},
            ],
            "lease_time": 86400,
        },
    },
    # ── DNS Configuration ─────────────────────────────────────────────────
    {
        "intent_id": "lab-mgmt-dns-001",
        "intent_type": IntentTypeChoices.MGMT_DNS_DHCP,
        "status": "Draft",
        "version": 1,
        "change_ticket": "CHG0050026",
        "git_branch": "main",
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "mgmt_dns_dhcp",
            "name": "DNS Resolver Configuration",
            "description": "DNS resolvers and domain search list — all lab devices",
            "scope": {"all_tenant_devices": True},
            "dns_servers": ["10.255.0.10", "10.255.0.11"],
            "domain_name": "arista-lab.local",
            "domain_list": ["arista-lab.local", "dc1.arista-lab.local"],
        },
    },
    # ── Firewall Rules ────────────────────────────────────────────────────
    {
        "intent_id": "lab-fw-rule-001",
        "intent_type": IntentTypeChoices.FW_RULE,
        "status": "Draft",
        "version": 1,
        "change_ticket": "CHG0050027",
        "git_branch": "main",
        "controller_type": "nornir",
        "deployment_strategy": "all_at_once",
        "verification_level": "basic",
        "verification_trigger": "on_deploy",
        "verification_fail_action": "alert",
        "intent_data": {
            "type": "fw_rule",
            "name": "Server Ingress Firewall Rules",
            "description": "Stateful firewall rules on server-facing interfaces",
            "scope": {"devices": ["lab-arista-sw01"]},
            "policy_name": "SERVER-INGRESS",
            "firewall_type": "stateful",
            "default_action": "deny",
            "rules": [
                {
                    "description": "Allow SSH from management",
                    "action": "permit",
                    "protocol": "tcp",
                    "source": "10.255.0.0/24",
                    "destination": "10.20.0.0/16",
                    "port": 22,
                    "log": False,
                },
                {
                    "description": "Allow HTTPS from any",
                    "action": "permit",
                    "protocol": "tcp",
                    "source": "any",
                    "destination": "10.20.0.0/24",
                    "port": 443,
                    "log": True,
                },
                {
                    "description": "Allow ICMP",
                    "action": "permit",
                    "protocol": "icmp",
                    "source": "any",
                    "destination": "any",
                    "log": False,
                },
                {
                    "description": "Deny all other traffic",
                    "action": "deny",
                    "protocol": "ip",
                    "source": "any",
                    "destination": "any",
                    "log": True,
                },
            ],
            "apply_interfaces": ["Ethernet1", "Ethernet2"],
            "direction": "in",
        },
    },
]

intents = {}
for data in INTENTS:
    intent, created = Intent.objects.get_or_create(
        intent_id=data["intent_id"],
        defaults={
            "intent_type": data["intent_type"],
            "tenant": tenant,
            "status": status_map[data["status"]],
            "version": data["version"],
            "change_ticket": data.get("change_ticket", ""),
            "approved_by": data.get("approved_by", ""),
            "git_commit_sha": data.get("git_commit_sha", ""),
            "git_branch": data.get("git_branch", ""),
            "git_pr_number": data.get("git_pr_number"),
            "deployed_at": data.get("deployed_at"),
            "last_verified_at": data.get("last_verified_at"),
            "intent_data": data["intent_data"],
            "controller_type": data.get("controller_type", "nornir"),
            "controller_site": data.get("controller_site", ""),
            "controller_org": data.get("controller_org", ""),
            "deployment_strategy": data.get("deployment_strategy", "all_at_once"),
            "verification_level": data.get("verification_level", "basic"),
            "verification_trigger": data.get("verification_trigger", "on_deploy"),
            "verification_fail_action": data.get("verification_fail_action", "alert"),
            "verification_schedule": data.get("verification_schedule", ""),
        },
    )
    if not created:
        # Reset intent to Draft so user can re-test full lifecycle
        intent.intent_data = data["intent_data"]
        intent.status = status_map["Draft"]
        intent.version = 1
        intent.deployed_at = None
        intent.last_verified_at = None
        intent.rendered_configs = {}
        intent.save(update_fields=[
            "intent_data", "status", "version",
            "deployed_at", "last_verified_at", "rendered_configs",
        ])
    intents[data["intent_id"]] = intent
    print(f"  {'Created' if created else 'Reset  '} intent: {data['intent_id']} → Draft")

# ── Set dependencies: L2VNI depends on fabric, L3VNI depends on fabric ────
intents["lab-dc-l2vni-prod-001"].dependencies.add(intents["lab-dc-evpn-fabric-001"])
intents["lab-dc-l3vni-tenant-001"].dependencies.add(intents["lab-dc-evpn-fabric-001"])
intents["lab-anycast-gw-001"].dependencies.add(intents["lab-dc-l3vni-tenant-001"])
print("  Set intent dependencies (fabric → l2vni, l3vni → anycast-gw)")

# ═════════════════════════════════════════════════════════════════════════════
# 7. Resolution Plans
# ═════════════════════════════════════════════════════════════════════════════
print("\n[7/14] Creating resolution plans...")
PLANS = [
    {
        "intent_id": "lab-dc-evpn-fabric-001",
        "intent_version": 2,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": False,
        "allocated_rds": {},
        "allocated_rts": {},
        "resolved_by": "IntentResolverJob",
        "primitives": [
            {
                "type": "BgpPrimitive",
                "protocol": "ebgp",
                "local_as": 65001,
                "peer_as": 65000,
                "device": "lab-arista-sw01",
            },
            {"type": "VtepPrimitive", "source_interface": "Loopback1", "device": "lab-arista-sw01"},
            {"type": "EvpnOverlayPrimitive", "overlay_asn": 65000, "device": "lab-arista-sw01"},
        ],
    },
    {
        "intent_id": "lab-dc-l2vni-prod-001",
        "intent_version": 1,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": False,
        "allocated_rds": {},
        "allocated_rts": {},
        "resolved_by": "IntentResolverJob",
        "primitives": [
            {"type": "VlanPrimitive", "vlan_id": 100, "name": "SERVERS-PROD", "device": "lab-arista-sw01"},
            {"type": "VniMapPrimitive", "vni": 10100, "vlan_id": 100, "vni_type": "l2", "device": "lab-arista-sw01"},
        ],
    },
    {
        "intent_id": "lab-dc-l3vni-tenant-001",
        "intent_version": 1,
        "vrf_name": "VRF-TENANT-A",
        "requires_new_vrf": True,
        "requires_mpls": False,
        "allocated_rds": {"lab-arista-sw01": "10.0.0.100:50001"},
        "allocated_rts": {"export": "65000:50001", "import": "65000:50001"},
        "resolved_by": "IntentResolverJob",
        "primitives": [
            {"type": "VrfPrimitive", "name": "VRF-TENANT-A", "rd": "10.0.0.100:50001", "device": "lab-arista-sw01"},
            {"type": "VniMapPrimitive", "vni": 50001, "vrf": "VRF-TENANT-A", "vni_type": "l3", "device": "lab-arista-sw01"},
        ],
    },
    {
        "intent_id": "lab-bgp-underlay-001",
        "intent_version": 1,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": False,
        "allocated_rds": {},
        "allocated_rts": {},
        "resolved_by": "IntentResolverJob",
        "primitives": [
            {
                "type": "BgpNeighborPrimitive",
                "local_device": "lab-arista-sw01",
                "peer_ip": "10.10.0.0",
                "peer_as": 65000,
                "address_family": "ipv4",
            },
            {
                "type": "BgpNeighborPrimitive",
                "local_device": "lab-arista-sw01",
                "peer_ip": "10.10.0.2",
                "peer_as": 65000,
                "address_family": "ipv4",
            },
        ],
    },
    {
        "intent_id": "lab-acl-server-segment-001",
        "intent_version": 1,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": False,
        "allocated_rds": {},
        "allocated_rts": {},
        "resolved_by": "IntentResolverJob",
        "primitives": [
            {"type": "AclPrimitive", "name": "DENY-DEV-TO-PROD", "direction": "inbound", "device": "lab-arista-sw01"},
            {
                "type": "AclPrimitive",
                "name": "DENY-DEV-TO-STORAGE",
                "direction": "inbound",
                "device": "lab-arista-sw01",
            },
        ],
    },
    {
        "intent_id": "lab-macsec-uplinks-001",
        "intent_version": 1,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": False,
        "allocated_rds": {},
        "allocated_rts": {},
        "resolved_by": "IntentResolverJob",
        "primitives": [
            {
                "type": "MacsecPrimitive",
                "cipher": "gcm-aes-256",
                "interface": "Ethernet49",
                "device": "lab-arista-sw01",
            },
            {
                "type": "MacsecPrimitive",
                "cipher": "gcm-aes-256",
                "interface": "Ethernet50",
                "device": "lab-arista-sw01",
            },
        ],
    },
]

for plan_data in PLANS:
    intent = intents[plan_data["intent_id"]]
    plan, created = ResolutionPlan.objects.get_or_create(
        intent=intent,
        intent_version=plan_data["intent_version"],
        defaults={
            "primitives": plan_data["primitives"],
            "vrf_name": plan_data["vrf_name"],
            "requires_new_vrf": plan_data["requires_new_vrf"],
            "requires_mpls": plan_data["requires_mpls"],
            "allocated_rds": plan_data["allocated_rds"],
            "allocated_rts": plan_data["allocated_rts"],
            "resolved_by": plan_data["resolved_by"],
        },
    )
    if created:
        plan.affected_devices.add(device)
        # Add all devices to fabric and MLAG plans
        if plan_data["intent_id"] in ("lab-dc-evpn-fabric-001", "lab-mlag-pair-001"):
            plan.affected_devices.add(device2, spine1, spine2)
        elif plan_data["intent_id"] == "lab-bgp-underlay-001":
            plan.affected_devices.add(spine1)
    print(
        f"  {'Created' if created else 'Exists '} plan: {plan_data['intent_id']} "
        f"v{plan_data['intent_version']} ({len(plan_data['primitives'])} primitives)"
    )

# ═════════════════════════════════════════════════════════════════════════════
# 8. Verification Results
# ═════════════════════════════════════════════════════════════════════════════
print("\n[8/14] Creating verification results...")
VERIFICATIONS = [
    # (intent_id, passed, trigger, latency_ms, bgp_exp, bgp_est, pfx_exp, pfx_rcv, drift, engine)
    # EVPN fabric — all pass
    ("lab-dc-evpn-fabric-001", True, "deployment", 8, 2, 2, 4, 4, {}, "extended"),
    ("lab-dc-evpn-fabric-001", True, "reconciliation", 7, 2, 2, 4, 4, {}, "extended"),
    ("lab-dc-evpn-fabric-001", True, "reconciliation", 9, 2, 2, 4, 4, {}, "extended"),
    # BGP underlay — pass
    ("lab-bgp-underlay-001", True, "deployment", 5, 2, 2, 6, 6, {}, "extended"),
    ("lab-bgp-underlay-001", True, "reconciliation", 4, 2, 2, 6, 6, {}, "extended"),
    # L2VNI — pass
    ("lab-dc-l2vni-prod-001", True, "deployment", None, 0, 0, 0, 0, {}, "basic"),
    # L3VNI — pass
    ("lab-dc-l3vni-tenant-001", True, "deployment", None, 0, 0, 0, 0, {}, "extended"),
    ("lab-dc-l3vni-tenant-001", True, "reconciliation", None, 0, 0, 0, 0, {}, "extended"),
    # ACL — pass
    ("lab-acl-server-segment-001", True, "deployment", None, 0, 0, 0, 0, {}, "extended"),
    ("lab-acl-server-segment-001", True, "reconciliation", None, 0, 0, 0, 0, {}, "extended"),
    # Storm control — FAILED
    (
        "lab-storm-control-001",
        False,
        "deployment",
        None,
        0,
        0,
        0,
        0,
        {"lab-arista-sw01": "Storm control configuration rejected — unsupported level granularity on DCS-7280SR-48C6"},
        "basic",
    ),
    # MACsec — FAILED then rolled back
    (
        "lab-macsec-uplinks-001",
        False,
        "deployment",
        None,
        0,
        0,
        0,
        0,
        {"lab-arista-sw01": "MACsec key mismatch on Ethernet49 — peer not configured. Session down."},
        "extended",
    ),
    # Anycast GW — pass
    ("lab-anycast-gw-001", True, "deployment", None, 0, 0, 0, 0, {}, "basic"),
    # NTP — pass
    ("lab-mgmt-ntp-001", True, "deployment", None, 0, 0, 0, 0, {}, "basic"),
    # Global config — pass
    ("lab-mgmt-global-config-001", True, "deployment", None, 0, 0, 0, 0, {}, "extended"),
    ("lab-mgmt-global-config-001", True, "reconciliation", None, 0, 0, 0, 0, {}, "extended"),
]

for i, (iid, passed, trigger, latency, bgp_exp, bgp_est, pfx_exp, pfx_rcv, drift, engine) in enumerate(VERIFICATIONS):
    intent = intents[iid]
    checks = []
    if bgp_exp > 0:
        checks.append(
            {
                "device": "lab-arista-sw01",
                "check_name": "bgp_sessions",
                "passed": bgp_est == bgp_exp,
                "detail": f"{bgp_est}/{bgp_exp} established",
            }
        )
        checks.append(
            {
                "device": "lab-arista-sw01",
                "check_name": "prefix_count",
                "passed": pfx_rcv >= pfx_exp,
                "detail": f"{pfx_rcv}/{pfx_exp} received",
            }
        )
    if drift:
        for dev, detail in drift.items():
            checks.append({"device": dev, "check_name": "config_drift", "passed": False, "detail": detail})

    VerificationResult.objects.create(
        intent=intent,
        passed=passed,
        triggered_by=trigger,
        checks=checks,
        measured_latency_ms=latency,
        bgp_sessions_expected=bgp_exp,
        bgp_sessions_established=bgp_est,
        prefixes_expected=pfx_exp,
        prefixes_received=pfx_rcv,
        drift_details=drift,
        verification_engine=engine,
        remediation_triggered=bool(drift),
        github_issue_url=f"https://github.com/arista-lab/intents/issues/{400 + i}" if drift else "",
    )
    print(f"  Created verification: {iid} — {'PASS' if passed else 'FAIL'} ({trigger})")

# ═════════════════════════════════════════════════════════════════════════════
# 9. Audit Trail
# ═════════════════════════════════════════════════════════════════════════════
print("\n[9/14] Creating audit trail entries...")
AUDIT_ENTRIES = [
    # EVPN Fabric lifecycle
    (
        "lab-dc-evpn-fabric-001",
        "created",
        "git-sync",
        {"source": "git_webhook", "commit": "aabbccdd11223344556677889900aabbccddeeff"},
    ),
    ("lab-dc-evpn-fabric-001", "resolved", "IntentResolverJob", {"primitives_count": 3}),
    ("lab-dc-evpn-fabric-001", "approved", "d.network", {"comment": "Fabric config reviewed and approved"}),
    ("lab-dc-evpn-fabric-001", "deployed", "IntentDeployJob", {"devices": ["lab-arista-sw01"], "duration_sec": 12}),
    ("lab-dc-evpn-fabric-001", "verified", "IntentVerificationJob", {"passed": True, "checks": 4}),
    # ACL lifecycle
    ("lab-acl-server-segment-001", "created", "git-sync", {"source": "git_webhook"}),
    ("lab-acl-server-segment-001", "resolved", "IntentResolverJob", {"primitives_count": 2}),
    ("lab-acl-server-segment-001", "approved", "s.security", {"comment": "Security review passed"}),
    ("lab-acl-server-segment-001", "deployed", "IntentDeployJob", {"devices": ["lab-arista-sw01"], "duration_sec": 5}),
    ("lab-acl-server-segment-001", "verified", "IntentVerificationJob", {"passed": True, "checks": 2}),
    # Storm control — failed
    ("lab-storm-control-001", "created", "git-sync", {"source": "git_webhook"}),
    ("lab-storm-control-001", "resolved", "IntentResolverJob", {"primitives_count": 1}),
    ("lab-storm-control-001", "approved", "d.network", {"comment": "Approved for deployment"}),
    (
        "lab-storm-control-001",
        "deployed",
        "IntentDeployJob",
        {"devices": ["lab-arista-sw01"], "error": "Configuration rejected by device"},
    ),
    # MACsec — deployed then rolled back
    ("lab-macsec-uplinks-001", "created", "git-sync", {"source": "git_webhook"}),
    ("lab-macsec-uplinks-001", "resolved", "IntentResolverJob", {"primitives_count": 2}),
    ("lab-macsec-uplinks-001", "approved", "s.security", {"comment": "MACsec policy approved"}),
    ("lab-macsec-uplinks-001", "deployed", "IntentDeployJob", {"devices": ["lab-arista-sw01"], "duration_sec": 8}),
    ("lab-macsec-uplinks-001", "verified", "IntentVerificationJob", {"passed": False, "drift": "key mismatch"}),
    (
        "lab-macsec-uplinks-001",
        "rolled_back",
        "IntentRollbackJob",
        {"reason": "Auto-rollback triggered by verification failure"},
    ),
    # QoS — validated, not yet deployed
    ("lab-qos-classify-001", "created", "git-sync", {"source": "git_webhook"}),
    ("lab-qos-classify-001", "resolved", "IntentResolverJob", {"primitives_count": 4}),
    ("lab-qos-classify-001", "config_preview", "IntentDryRunJob", {"devices": ["lab-arista-sw01"], "preview": True}),
]

for iid, action, actor, detail in AUDIT_ENTRIES:
    IntentAuditEntry.objects.create(
        intent=intents[iid],
        action=action,
        actor=actor,
        detail=detail,
        git_commit_sha=intents[iid].git_commit_sha,
    )
    print(f"  Created audit: {iid} — {action} by {actor}")

# ═════════════════════════════════════════════════════════════════════════════
# 10. Deployment Stages (for canary/rolling intents)
# ═════════════════════════════════════════════════════════════════════════════
print("\n[10/14] Creating deployment stages...")
# Port security — rolling deployment (currently deploying)
for i, stage_data in enumerate(
    [
        {"status": "verified", "started_at": now - timedelta(hours=2), "completed_at": now - timedelta(hours=1)},
        {"status": "deploying", "started_at": now - timedelta(minutes=10), "completed_at": None},
    ]
):
    stage, created = DeploymentStage.objects.get_or_create(
        intent=intents["lab-port-security-001"],
        stage_order=i,
        defaults={
            "location": site,
            "status": stage_data["status"],
            "started_at": stage_data["started_at"],
            "completed_at": stage_data["completed_at"],
            "rendered_configs": {
                "lab-arista-sw01": f"! Port security stage {i}\ninterface Ethernet{i*3+1}\n switchport port-security maximum 4\n",
            },
        },
    )
    if created:
        stage.devices.add(device)
    print(f"  {'Created' if created else 'Exists '} stage: port-security stage {i} [{stage_data['status']}]")

# MACsec — canary failed then rolled back
for i, stage_data in enumerate(
    [
        {
            "status": "rolled_back",
            "started_at": now - timedelta(days=2),
            "completed_at": now - timedelta(days=2, hours=-1),
        },
    ]
):
    stage, created = DeploymentStage.objects.get_or_create(
        intent=intents["lab-macsec-uplinks-001"],
        stage_order=i,
        defaults={
            "location": site,
            "status": stage_data["status"],
            "started_at": stage_data["started_at"],
            "completed_at": stage_data["completed_at"],
            "rendered_configs": {
                "lab-arista-sw01": "! MACsec canary\ninterface Ethernet49\n macsec profile UPLINK\n",
            },
        },
    )
    if created:
        stage.devices.add(device)
    print(f"  {'Created' if created else 'Exists '} stage: macsec stage {i} [{stage_data['status']}]")

# ═════════════════════════════════════════════════════════════════════════════
# 11. VRF & Route Targets (Nautobot native)
# ═════════════════════════════════════════════════════════════════════════════
print("\n[11/14] Creating VRFs & Route Targets...")
vrf, created = VRF.objects.get_or_create(
    name="VRF-TENANT-A",
    namespace=ns,
    defaults={
        "rd": "10.0.0.100:50001",
        "tenant": tenant,
        "description": "Auto-allocated by intent lab-dc-l3vni-tenant-001",
    },
)
vrf.devices.add(device, device2)
print(f"  {'Created' if created else 'Exists '} VRF: VRF-TENANT-A")

for rt_value in ["65000:50001"]:
    rt, created = NautobotRouteTarget.objects.get_or_create(
        name=rt_value,
        defaults={
            "description": "Auto-allocated for intent lab-dc-l3vni-tenant-001",
            "tenant": tenant,
        },
    )
    print(f"  {'Created' if created else 'Exists '} RT: {rt_value}")

# ═════════════════════════════════════════════════════════════════════════════
# 12. Resource Pools — VNI, Tunnel ID, Loopback, Wireless VLAN
# ═════════════════════════════════════════════════════════════════════════════
print("\n[12/14] Creating resource pools...")

# VNI Pool
vni_pool, created = VxlanVniPool.objects.get_or_create(
    name="lab-dc1-vni-pool",
    defaults={"range_start": 10000, "range_end": 19999, "tenant": tenant},
)
print(f"  {'Created' if created else 'Exists '} VNI Pool: lab-dc1-vni-pool (10000-19999)")

# VNI Allocations
for vni_value, vni_type, iid in [
    (10100, "l2", "lab-dc-l2vni-prod-001"),
    (50001, "l3", "lab-dc-l3vni-tenant-001"),
]:
    alloc, created = VniAllocation.objects.get_or_create(
        value=vni_value,
        defaults={"pool": vni_pool, "intent": intents[iid], "vni_type": vni_type},
    )
    print(f"  {'Created' if created else 'Exists '} VNI: {vni_value} ({vni_type}) → {iid}")

# Tunnel ID Pool
tunnel_pool, created = TunnelIdPool.objects.get_or_create(
    name="lab-ipsec-tunnel-pool",
    defaults={"range_start": 100, "range_end": 999},
)
print(f"  {'Created' if created else 'Exists '} Tunnel Pool: lab-ipsec-tunnel-pool (100-999)")

# Loopback Pool
lb_pool, created = ManagedLoopbackPool.objects.get_or_create(
    name="lab-dc1-loopbacks",
    defaults={"prefix": "10.0.0.0/24", "tenant": tenant},
)
print(f"  {'Created' if created else 'Exists '} Loopback Pool: lab-dc1-loopbacks (10.0.0.0/24)")

# Loopback Allocations (one per device+pool unique constraint)
for ip, dev, iid in [
    ("10.0.0.100", device, "lab-dc-evpn-fabric-001"),
    ("10.0.0.102", device2, "lab-dc-evpn-fabric-001"),
    ("10.0.0.200", spine1, "lab-dc-evpn-fabric-001"),
    ("10.0.0.201", spine2, "lab-dc-evpn-fabric-001"),
]:
    alloc, created = ManagedLoopback.objects.get_or_create(
        ip_address=ip,
        device=dev,
        pool=lb_pool,
        defaults={"intent": intents[iid]},
    )
    print(f"  {'Created' if created else 'Exists '} Loopback: {ip} ({dev.name}) → {iid}")

# Wireless VLAN Pool
wlan_pool, created = WirelessVlanPool.objects.get_or_create(
    name="lab-dc1-wireless-vlans",
    defaults={"range_start": 500, "range_end": 599, "site": site},
)
print(f"  {'Created' if created else 'Exists '} Wireless VLAN Pool: lab-dc1-wireless-vlans (500-599)")

# ═════════════════════════════════════════════════════════════════════════════
# 13. Rendered Config Cache (for dry-run / preview testing)
# ═════════════════════════════════════════════════════════════════════════════
print("\n[13/14] Adding rendered config previews...")
RENDERED_CONFIGS = {
    "lab-dc-evpn-fabric-001": {
        "lab-arista-sw01": """! EVPN/VXLAN Fabric Configuration
! Generated by Intent Networking
!
router bgp 65001
   router-id 10.0.0.100
   no bgp default ipv4-unicast
   neighbor SPINE-UNDERLAY peer group
   neighbor SPINE-UNDERLAY remote-as 65000
   neighbor SPINE-UNDERLAY send-community extended
   neighbor 10.10.0.0 peer group SPINE-UNDERLAY
   neighbor 10.10.0.2 peer group SPINE-UNDERLAY
   !
   address-family ipv4
      neighbor SPINE-UNDERLAY activate
      network 10.0.0.100/32
      network 10.0.0.101/32
   !
   address-family evpn
      neighbor SPINE-OVERLAY peer group
      neighbor SPINE-OVERLAY remote-as 65000
      neighbor SPINE-OVERLAY update-source Loopback0
      neighbor SPINE-OVERLAY ebgp-multihop 3
      neighbor SPINE-OVERLAY send-community extended
!
interface Vxlan1
   vxlan source-interface Loopback1
   vxlan udp-port 4789
!
""",
    },
    "lab-acl-server-segment-001": {
        "lab-arista-sw01": """! Server Segmentation ACLs
! Generated by Intent Networking
!
ip access-list DENY-DEV-TO-PROD
   10 deny ip 10.20.1.0/24 10.20.0.0/24
   1000 permit ip any any
!
ip access-list DENY-DEV-TO-STORAGE
   10 deny ip 10.20.1.0/24 10.20.2.0/24
   1000 permit ip any any
!
interface Vlan101
   ip access-group DENY-DEV-TO-PROD out
   ip access-group DENY-DEV-TO-STORAGE out
!
""",
    },
    "lab-qos-classify-001": {
        "lab-arista-sw01": """! QoS Traffic Classification
! Generated by Intent Networking — DRY RUN PREVIEW
!
class-map type qos match-any PROD-CRITICAL
   match ip destination 10.20.0.0/24
!
class-map type qos match-any STORAGE
   match ip destination 10.20.2.0/24
!
class-map type qos match-any DEV-BEST-EFFORT
   match ip destination 10.20.1.0/24
!
policy-map type qos QOS-POLICY
   class PROD-CRITICAL
      set dscp ef
      bandwidth percent 40
   class STORAGE
      set dscp af31
      bandwidth percent 30
   class DEV-BEST-EFFORT
      set dscp default
      bandwidth percent 20
   class class-default
      bandwidth percent 10
!
""",
    },
}

for iid, configs in RENDERED_CONFIGS.items():
    intent = intents[iid]
    if not intent.rendered_configs:
        intent.rendered_configs = configs
        intent.save(update_fields=["rendered_configs"])
        print(f"  Cached config preview: {iid}")
    else:
        print(f"  Exists  config preview: {iid}")

# ═════════════════════════════════════════════════════════════════════════════
# 14. Summary
# ═════════════════════════════════════════════════════════════════════════════
print("\n[14/14] Summary...")
print("=" * 60)
print("  Arista Test Seed Complete!")
print(f"  Tenant:             {tenant.name}")
print(f"  Location:           {site.name}")
print(f"  Devices:")
for d in [device, device2, spine1, spine2]:
    intf_count = Interface.objects.filter(device=d).count()
    print(f"    - {d.name} ({d.device_type.model}) [{d.role.name}] — {intf_count} interfaces")
print(f"  Platform:           {platform.name}")
print(f"  Interfaces:         {Interface.objects.filter(device__tenant=tenant).count()}")
print(f"  Intents:            {Intent.objects.filter(tenant=tenant).count()}")
print(f"    - Deployed:       {Intent.objects.filter(tenant=tenant, status=status_map['Deployed']).count()}")
print(f"    - Validated:      {Intent.objects.filter(tenant=tenant, status=status_map['Validated']).count()}")
print(f"    - Deploying:      {Intent.objects.filter(tenant=tenant, status=status_map['Deploying']).count()}")
print(f"    - Draft:          {Intent.objects.filter(tenant=tenant, status=status_map['Draft']).count()}")
print(f"    - Failed:         {Intent.objects.filter(tenant=tenant, status=status_map['Failed']).count()}")
print(f"    - Rolled Back:    {Intent.objects.filter(tenant=tenant, status=status_map['Rolled Back']).count()}")
print(f"  Resolution Plans:   {ResolutionPlan.objects.filter(intent__tenant=tenant).count()}")
print(f"  Verifications:      {VerificationResult.objects.filter(intent__tenant=tenant).count()}")
print(f"  Audit Entries:      {IntentAuditEntry.objects.filter(intent__tenant=tenant).count()}")
print(f"  Deployment Stages:  {DeploymentStage.objects.filter(intent__tenant=tenant).count()}")
print(f"  VRFs:               {VRF.objects.filter(tenant=tenant).count()}")
print(f"  VNI Allocations:    {VniAllocation.objects.filter(intent__tenant=tenant).count()}")
print(f"  Loopback Allocs:    {ManagedLoopback.objects.filter(intent__tenant=tenant).count()}")
print("=" * 60)
print("\n  Device URL: /dcim/devices/?name=lab-arista-sw01")
print("  Intents URL: /plugins/intent-networking/intents/?tenant=Arista+Lab")
print("=" * 60)
