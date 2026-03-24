"""Update lab-arista-sw01 management IP to the Containerlab cEOS address."""

from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix

active = Status.objects.get(name="Active")
ns = Namespace.objects.get(name="Global")
device = Device.objects.get(name="lab-arista-sw01")

# Create the 172.20.20.0/24 prefix if it doesn't exist
Prefix.objects.get_or_create(
    network="172.20.20.0",
    prefix_length=24,
    namespace=ns,
    defaults={"status": active, "type": "network"},
)

# Create the new management IP
new_ip, created = IPAddress.objects.get_or_create(
    address="172.20.20.2/24",
    namespace=ns,
    defaults={"status": active},
)
tag = "Created" if created else "Exists"
print(f"  {tag} IP: {new_ip}")

# Assign to Management0 interface (or first available)
mgmt_intf = device.interfaces.filter(name="Management0").first()
if not mgmt_intf:
    mgmt_intf = device.interfaces.first()
if mgmt_intf:
    assoc, c = IPAddressToInterface.objects.get_or_create(
        ip_address=new_ip,
        interface=mgmt_intf,
    )
    print(f"  Assigned {new_ip} to {mgmt_intf.name} (created={c})")
else:
    print("  WARNING: No interface found on device!")

# Set as primary IP
device.primary_ip4 = new_ip
device.validated_save()
print(f"  Updated primary_ip4 for {device.name} to {new_ip}")
print("  Done!")
