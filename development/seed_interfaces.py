"""Add interfaces, management IPs and platforms to seed devices."""

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device, Interface
from nautobot.extras.models import Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix

active = Status.objects.get(name="Active")

# Ensure active status is allowed on IPAddress, Prefix, Interface
for model in (IPAddress, Prefix, Interface):
    ct = ContentType.objects.get_for_model(model)
    active.content_types.add(ct)

ns, _ = Namespace.objects.get_or_create(name="Global")

# Create parent prefix hierarchy so Nautobot IPAddress creation succeeds.
# Nautobot 3.x is strict: each IP must have a direct parent prefix.
PREFIXES = [
    "10.0.0.0/8",
    "10.0.0.0/24",       # Loopback IPs
    "10.255.0.0/24",     # Management IPs
]
for pfx_str in PREFIXES:
    Prefix.objects.get_or_create(
        prefix=pfx_str, defaults={"namespace": ns, "status": active}
    )


def _get_parent_prefix(ip_str):
    """Return the correct parent prefix for an IP."""
    if ip_str.startswith("10.0."):
        return Prefix.objects.get(prefix="10.0.0.0/24")
    return Prefix.objects.get(prefix="10.255.0.0/24")


def _get_or_create_ip(ip_str):
    """Create an IPAddress in Nautobot 3.x (needs parent prefix)."""
    parent = _get_parent_prefix(ip_str)
    # IPAddress stores host and mask_length separately
    # but get_or_create on 'address' works if we provide the parent
    try:
        # Try to find existing
        host_part = ip_str.split("/")[0]
        mask_part = int(ip_str.split("/")[1])
        ip_obj = IPAddress.objects.get(host=host_part, mask_length=mask_part, parent=parent)
        return ip_obj, False
    except IPAddress.DoesNotExist:
        ip_obj = IPAddress(
            address=ip_str,
            parent=parent,
            status=active,
        )
        ip_obj.validated_save()
        return ip_obj, True


print("Adding interfaces + mgmt IPs to devices...")

# ── Per-device interface templates ────────────────────────────────────────────
# Each device gets: Loopback0, Management0, and 4-6 fabric interfaces
# Interface naming follows vendor convention
# Tuple: (name, type, enabled, ip, description, mtu, mac, speed_kbps)
DEVICE_INTERFACES = {
    # Cisco ASR-9001
    "nyc-pe01": {
        "mgmt_ip": "10.255.0.1/32",
        "interfaces": [
            ("Loopback0", "virtual", True, "10.0.0.1/32", "Router-ID / IGP source", None, None, None),
            ("MgmtEth0/RSP0/CPU0/0", "1000base-t", True, "10.255.0.1/24", "OOB Management", 1500, "00:1A:2B:01:00:00", 1000000),
            ("GigabitEthernet0/0/0/0", "10gbase-x-sfpp", True, None, "TO nyc-pe02 et-0/0/0", 9214, "00:1A:2B:01:00:01", 10000000),
            ("GigabitEthernet0/0/0/1", "10gbase-x-sfpp", True, None, "TO nyc-p01 Gi0/0/0/0", 9214, "00:1A:2B:01:00:02", 10000000),
            ("GigabitEthernet0/0/0/2", "10gbase-x-sfpp", True, None, "TO bos-pe01 Gi0/0/0/0", 9214, "00:1A:2B:01:00:03", 10000000),
            ("GigabitEthernet0/0/0/3", "10gbase-x-sfpp", False, None, "SPARE — not provisioned", 9214, "00:1A:2B:01:00:04", 10000000),
        ],
    },
    # Juniper MX204
    "nyc-pe02": {
        "mgmt_ip": "10.255.0.2/32",
        "interfaces": [
            ("lo0.0", "virtual", True, "10.0.0.2/32", "Router-ID / IGP source", None, None, None),
            ("fxp0", "1000base-t", True, "10.255.0.2/24", "OOB Management", 1500, "00:1A:2B:02:00:00", 1000000),
            ("et-0/0/0", "100gbase-x-qsfp28", True, None, "TO nyc-pe01 Gi0/0/0/0", 9214, "00:1A:2B:02:00:01", 100000000),
            ("et-0/0/1", "100gbase-x-qsfp28", True, None, "TO nyc-p01 Gi0/0/0/1", 9214, "00:1A:2B:02:00:02", 100000000),
            ("et-0/0/2", "100gbase-x-qsfp28", False, None, "SPARE", 9214, "00:1A:2B:02:00:03", 100000000),
        ],
    },
    "nyc-p01": {
        "mgmt_ip": "10.255.0.3/32",
        "interfaces": [
            ("Loopback0", "virtual", True, "10.0.0.3/32", "Router-ID / IGP source", None, None, None),
            ("MgmtEth0/RSP0/CPU0/0", "1000base-t", True, "10.255.0.3/24", "OOB Management", 1500, "00:1A:2B:03:00:00", 1000000),
            ("GigabitEthernet0/0/0/0", "10gbase-x-sfpp", True, None, "TO nyc-pe01 Gi0/0/0/1", 9214, "00:1A:2B:03:00:01", 10000000),
            ("GigabitEthernet0/0/0/1", "10gbase-x-sfpp", True, None, "TO nyc-pe02 et-0/0/1", 9214, "00:1A:2B:03:00:02", 10000000),
        ],
    },
    "bos-pe01": {
        "mgmt_ip": "10.255.0.10/32",
        "interfaces": [
            ("Loopback0", "virtual", True, "10.0.0.10/32", "Router-ID / IGP source", None, None, None),
            ("MgmtEth0/RSP0/CPU0/0", "1000base-t", True, "10.255.0.10/24", "OOB Management", 1500, "00:1A:2B:10:00:00", 1000000),
            ("GigabitEthernet0/0/0/0", "10gbase-x-sfpp", True, None, "TO nyc-pe01 Gi0/0/0/2", 9214, "00:1A:2B:10:00:01", 10000000),
            ("GigabitEthernet0/0/0/1", "10gbase-x-sfpp", True, None, "TO bos-ce01 Ethernet1", 9214, "00:1A:2B:10:00:02", 10000000),
            ("GigabitEthernet0/0/0/2", "10gbase-x-sfpp", False, None, "SPARE — reserved for DC expansion", 9214, "00:1A:2B:10:00:03", 10000000),
        ],
    },
    # Arista DCS-7280SR
    "bos-ce01": {
        "mgmt_ip": "10.255.0.11/32",
        "interfaces": [
            ("Loopback0", "virtual", True, "10.0.0.11/32", "Router-ID / IGP source", None, None, None),
            ("Management1", "1000base-t", True, "10.255.0.11/24", "OOB Management", 1500, "00:1A:2B:11:00:00", 1000000),
            ("Ethernet1", "10gbase-x-sfpp", True, None, "TO bos-pe01 Gi0/0/0/1", 9214, "00:1A:2B:11:00:01", 10000000),
            ("Ethernet2", "10gbase-x-sfpp", True, None, "Downstream — Customer ACME Corp", 9214, "00:1A:2B:11:00:02", 10000000),
            ("Ethernet3", "10gbase-x-sfpp", False, None, "SPARE", 9214, "00:1A:2B:11:00:03", 10000000),
            ("Ethernet4", "10gbase-x-sfpp", False, None, "SPARE", 9214, "00:1A:2B:11:00:04", 10000000),
        ],
    },
    "lax-pe01": {
        "mgmt_ip": "10.255.0.20/32",
        "interfaces": [
            ("lo0.0", "virtual", True, "10.0.0.20/32", "Router-ID / IGP source", None, None, None),
            ("fxp0", "1000base-t", True, "10.255.0.20/24", "OOB Management", 1500, "00:1A:2B:20:00:00", 1000000),
            ("et-0/0/0", "100gbase-x-qsfp28", True, None, "TO lax-pe02 Gi0/0/0/0", 9214, "00:1A:2B:20:00:01", 100000000),
            ("et-0/0/1", "100gbase-x-qsfp28", True, None, "TO sfo-pe01 et-0/0/0", 9214, "00:1A:2B:20:00:02", 100000000),
            ("et-0/0/2", "100gbase-x-qsfp28", False, None, "SPARE", 9214, "00:1A:2B:20:00:03", 100000000),
        ],
    },
    "lax-pe02": {
        "mgmt_ip": "10.255.0.21/32",
        "interfaces": [
            ("Loopback0", "virtual", True, "10.0.0.21/32", "Router-ID / IGP source", None, None, None),
            ("MgmtEth0/RSP0/CPU0/0", "1000base-t", True, "10.255.0.21/24", "OOB Management", 1500, "00:1A:2B:21:00:00", 1000000),
            ("GigabitEthernet0/0/0/0", "10gbase-x-sfpp", True, None, "TO lax-pe01 et-0/0/0", 9214, "00:1A:2B:21:00:01", 10000000),
            ("GigabitEthernet0/0/0/1", "10gbase-x-sfpp", False, None, "SPARE", 9214, "00:1A:2B:21:00:02", 10000000),
        ],
    },
    "sfo-pe01": {
        "mgmt_ip": "10.255.0.30/32",
        "interfaces": [
            ("lo0.0", "virtual", True, "10.0.0.30/32", "Router-ID / IGP source", None, None, None),
            ("fxp0", "1000base-t", True, "10.255.0.30/24", "OOB Management", 1500, "00:1A:2B:30:00:00", 1000000),
            ("et-0/0/0", "100gbase-x-qsfp28", True, None, "TO lax-pe01 et-0/0/1", 9214, "00:1A:2B:30:00:01", 100000000),
            ("et-0/0/1", "100gbase-x-qsfp28", True, None, "TO sea-pe01 Ethernet1", 9214, "00:1A:2B:30:00:02", 100000000),
        ],
    },
    "sea-pe01": {
        "mgmt_ip": "10.255.0.31/32",
        "interfaces": [
            ("Loopback0", "virtual", True, "10.0.0.31/32", "Router-ID / IGP source", None, None, None),
            ("Management1", "1000base-t", True, "10.255.0.31/24", "OOB Management", 1500, "00:1A:2B:31:00:00", 1000000),
            ("Ethernet1", "10gbase-x-sfpp", True, None, "TO sfo-pe01 et-0/0/1", 9214, "00:1A:2B:31:00:01", 10000000),
            ("Ethernet2", "10gbase-x-sfpp", True, None, "TO lon-pe01 Gi0/0/0/0 (transatlantic)", 9214, "00:1A:2B:31:00:02", 10000000),
            ("Ethernet3", "10gbase-x-sfpp", False, None, "SPARE", 9214, "00:1A:2B:31:00:03", 10000000),
        ],
    },
    "lon-pe01": {
        "mgmt_ip": "10.255.0.40/32",
        "interfaces": [
            ("Loopback0", "virtual", True, "10.0.0.40/32", "Router-ID / IGP source", None, None, None),
            ("MgmtEth0/RSP0/CPU0/0", "1000base-t", True, "10.255.0.40/24", "OOB Management", 1500, "00:1A:2B:40:00:00", 1000000),
            ("GigabitEthernet0/0/0/0", "10gbase-x-sfpp", True, None, "TO sea-pe01 Ethernet2 (transatlantic)", 9214, "00:1A:2B:40:00:01", 10000000),
            ("GigabitEthernet0/0/0/1", "10gbase-x-sfpp", True, None, "TO ams-pe01 et-0/0/0", 9214, "00:1A:2B:40:00:02", 10000000),
            ("GigabitEthernet0/0/0/2", "10gbase-x-sfpp", True, None, "TO fra-pe01 Ethernet1", 9214, "00:1A:2B:40:00:03", 10000000),
            ("GigabitEthernet0/0/0/3", "10gbase-x-sfpp", False, None, "SPARE", 9214, "00:1A:2B:40:00:04", 10000000),
        ],
    },
    "ams-pe01": {
        "mgmt_ip": "10.255.0.41/32",
        "interfaces": [
            ("lo0.0", "virtual", True, "10.0.0.41/32", "Router-ID / IGP source", None, None, None),
            ("fxp0", "1000base-t", True, "10.255.0.41/24", "OOB Management", 1500, "00:1A:2B:41:00:00", 1000000),
            ("et-0/0/0", "100gbase-x-qsfp28", True, None, "TO lon-pe01 Gi0/0/0/1", 9214, "00:1A:2B:41:00:01", 100000000),
            ("et-0/0/1", "100gbase-x-qsfp28", True, None, "TO fra-pe01 Ethernet2", 9214, "00:1A:2B:41:00:02", 100000000),
            ("et-0/0/2", "100gbase-x-qsfp28", False, None, "SPARE", 9214, "00:1A:2B:41:00:03", 100000000),
        ],
    },
    "fra-pe01": {
        "mgmt_ip": "10.255.0.42/32",
        "interfaces": [
            ("Loopback0", "virtual", True, "10.0.0.42/32", "Router-ID / IGP source", None, None, None),
            ("Management1", "1000base-t", True, "10.255.0.42/24", "OOB Management", 1500, "00:1A:2B:42:00:00", 1000000),
            ("Ethernet1", "10gbase-x-sfpp", True, None, "TO lon-pe01 Gi0/0/0/2", 9214, "00:1A:2B:42:00:01", 10000000),
            ("Ethernet2", "10gbase-x-sfpp", True, None, "TO ams-pe01 et-0/0/1", 9214, "00:1A:2B:42:00:02", 10000000),
            ("Ethernet3", "10gbase-x-sfpp", False, None, "SPARE", 9214, "00:1A:2B:42:00:03", 10000000),
        ],
    },
}

created_count = 0
updated_count = 0
for dev_name, spec in DEVICE_INTERFACES.items():
    try:
        device = Device.objects.get(name=dev_name)
    except Device.DoesNotExist:
        print(f"  SKIP {dev_name} — not found")
        continue

    mgmt_ip_obj = None
    for iface_name, iface_type, enabled, ip_str, desc, mtu, mac, speed in spec["interfaces"]:
        iface, ic = Interface.objects.get_or_create(
            device=device,
            name=iface_name,
            defaults={
                "type": iface_type,
                "enabled": enabled,
                "status": active,
                "description": desc or "",
                "mtu": mtu,
                "mac_address": mac,
                "speed": speed,
            },
        )
        if not ic:
            # Update existing interfaces with the new fields
            changed = False
            if desc and not iface.description:
                iface.description = desc
                changed = True
            if mtu and not iface.mtu:
                iface.mtu = mtu
                changed = True
            if mac and not iface.mac_address:
                iface.mac_address = mac
                changed = True
            if speed and not iface.speed:
                iface.speed = speed
                changed = True
            if changed:
                iface.validated_save()
                updated_count += 1
        else:
            created_count += 1

        if ip_str:
            ip_obj, _ = _get_or_create_ip(ip_str)
            IPAddressToInterface.objects.get_or_create(
                ip_address=ip_obj,
                interface=iface,
            )
            # Use the management IP for the device primary_ip
            if "mgmt" in iface_name.lower() or "fxp0" in iface_name.lower() or "management" in iface_name.lower():
                mgmt_ip_obj = ip_obj

    if mgmt_ip_obj and not device.primary_ip4:
        device.primary_ip4 = mgmt_ip_obj
        device.save()
        print(f"  {dev_name}: interfaces + primary_ip4={mgmt_ip_obj}")
    else:
        print(f"  {dev_name}: interfaces added")

print(f"\nTotal interfaces created: {created_count}")
print(f"Total interfaces updated: {updated_count}")
print(f"Total interfaces now:     {Interface.objects.count()}")
