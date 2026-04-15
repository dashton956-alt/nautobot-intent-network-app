"""Seed Nautobot with lab intents for the Arista cEOS Containerlab test environment.

Only covers intent types from Feature/improved-EOS that push REAL EOS CLI
and can be fully exercised against a running cEOS device.

Excluded (controller stubs — no EOS CLI rendered):
  - wireless_ssid / wireless_rf / wireless_guest  (Mist/CV stubs)
  - sdwan_overlay / sdwan_qos                     (SD-WAN controller stubs)

Included (16 intents — all push real EOS CLI via Nornir):

  Security / tunneling:
    lab-acl-security-001      acl
    lab-zbf-001               zbf
    lab-aaa-001               aaa
    lab-copp-001              copp
    lab-ra-guard-001          ra_guard

  Routing / WAN:
    lab-route-redist-001      route_redistribution
    lab-ospfv3-001            ospfv3
    lab-eigrp-001             eigrp
    lab-sr-mpls-001           sr_mpls

  L2:
    lab-pvlan-001             pvlan
    lab-stp-root-001          mgmt_stp_root

  QoS:
    lab-qos-police-001        qos_police
    lab-qos-queue-001         qos_queue
    lab-qos-shape-001         qos_shape
    lab-qos-trust-001         qos_trust

  Multicast:
    lab-msdp-001              msdp

All intents target tenant "Arista Lab", site "LAB-DC1".

Usage (inside nautobot shell / nbshell):
    exec(open("development/seed_lab_intents.py").read())
"""

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from nautobot.extras.models import Status
from nautobot.tenancy.models import Tenant

from intent_networking.models import Intent, IntentTypeChoices

now = timezone.now()

print("=" * 60)
print("  Intent Networking — Lab Intent Seeder (Feature/improved-EOS)")
print("=" * 60)

# ─── Ensure Retired status exists ────────────────────────────────────────────
intent_ct = ContentType.objects.get_for_model(Intent)
retired_status, created = Status.objects.get_or_create(name="Retired")
retired_status.content_types.add(intent_ct)
print(f"\n{'Created' if created else 'Exists '} status: Retired")

draft_status = Status.objects.get(name="Draft")

# ─── Tenant ───────────────────────────────────────────────────────────────────
tenant = Tenant.objects.get(name="Arista Lab")
print(f"Using tenant: {tenant.name}")

# ─── Intent definitions ───────────────────────────────────────────────────────
# Scope: LAB-DC1 contains all 4 cEOS lab devices.
# All intents use nornir controller and rolling strategy.

INTENTS = [
    # ════════════════════════════════════════════════════════════════════
    # SECURITY / TUNNELING — new security removal templates
    # ════════════════════════════════════════════════════════════════════
    {
        "intent_id": "lab-acl-security-001",
        "intent_type": IntentTypeChoices.ACL,
        "change_ticket": "CHG0020015",
        "description": "Management plane ACL — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "acl_name": "ACL-MGMT-PLANE",
            "acl_type": "extended",
            "address_family": "ipv4",
            "entries": [
                {"action": "permit", "protocol": "tcp", "source": "172.20.20.0/24", "destination": "any", "port": 22},
                {"action": "permit", "protocol": "udp", "source": "172.20.20.0/24", "destination": "any", "port": 161},
                {"action": "deny", "protocol": "ip", "source": "any", "destination": "any", "log": True},
            ],
            "apply_interfaces": [],
            "direction": "in",
        },
    },
    {
        "intent_id": "lab-zbf-001",
        "intent_type": IntentTypeChoices.ZBF,
        "change_ticket": "CHG0020016",
        "description": "Zone-based firewall — INSIDE to OUTSIDE — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "zones": [{"name": "INSIDE"}, {"name": "OUTSIDE"}],
            "zone_pairs": [{"source": "INSIDE", "destination": "OUTSIDE", "policy": "ZBF-INSIDE-OUT"}],
            "class_maps": [{"name": "MATCH-ANY", "type": "match-any", "match": [{"protocol": "ip"}]}],
            "policy_maps": [{"name": "ZBF-INSIDE-OUT", "classes": [{"name": "MATCH-ANY", "action": "inspect"}]}],
        },
    },
    {
        "intent_id": "lab-aaa-001",
        "intent_type": IntentTypeChoices.AAA,
        "change_ticket": "CHG0020017",
        "description": "TACACS+ AAA for device management — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "auth_methods": "group TACACS-LAB local",
            "enable_auth": "group TACACS-LAB enable",
            "authorization": "group TACACS-LAB local",
            "accounting": "group TACACS-LAB",
            "tacacs_servers": [{"ip": "172.20.20.200", "key": "tacacs-lab-key"}],
        },
    },
    {
        "intent_id": "lab-copp-001",
        "intent_type": IntentTypeChoices.COPP,
        "change_ticket": "CHG0020018",
        "description": "Control Plane Policing — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "policy_name": "COPP-LAB-POLICY",
            "classes": [
                {
                    "acl_name": "ACL-CPP-CRITICAL",
                    "rules": [
                        {"action": "permit", "protocol": "tcp", "source": "any", "destination": "any", "port": 179},
                        {"action": "permit", "protocol": "ospf", "source": "any", "destination": "any"},
                    ],
                    "police_rate": "64000",
                    "police_burst": "8000",
                },
                {
                    "acl_name": "ACL-CPP-IMPORTANT",
                    "rules": [
                        {"action": "permit", "protocol": "udp", "source": "any", "destination": "any", "port": 161},
                        {"action": "permit", "protocol": "tcp", "source": "any", "destination": "any", "port": 22},
                    ],
                    "police_rate": "32000",
                    "police_burst": "4000",
                },
                {
                    "acl_name": "ACL-CPP-DEFAULT",
                    "rules": [
                        {"action": "permit", "protocol": "ip", "source": "any", "destination": "any"},
                    ],
                    "police_rate": "8000",
                    "police_burst": "1000",
                },
            ],
        },
    },
    {
        "intent_id": "lab-ra-guard-001",
        "intent_type": IntentTypeChoices.RA_GUARD,
        "change_ticket": "CHG0020019",
        "description": "IPv6 RA Guard — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "policy_name": "RA-GUARD-LAB",
            "trusted_ports": ["Ethernet1", "Ethernet2"],
            "untrusted_ports": ["Ethernet3", "Ethernet4"],
        },
    },
    # ════════════════════════════════════════════════════════════════════
    # ROUTING / WAN — new routing/WAN removal templates
    # ════════════════════════════════════════════════════════════════════
    {
        "intent_id": "lab-route-redist-001",
        "intent_type": IntentTypeChoices.ROUTE_REDISTRIBUTION,
        "change_ticket": "CHG0020020",
        "description": "Redistribute connected into OSPF — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "protocol": "ospf",
            "process_id": 1,
            "sources": [
                {"protocol": "connected", "subnets": True, "route_map": "RM-CONNECTED-TO-OSPF"},
            ],
        },
    },
    {
        "intent_id": "lab-ospfv3-001",
        "intent_type": IntentTypeChoices.OSPFV3,
        "change_ticket": "CHG0020021",
        "description": "OSPFv3 IPv6 — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "process_id": 1,
            "area": "0.0.0.0",  # noqa: S104
            "address_family": "ipv6",
            "router_id": "10.0.0.1",
            "interfaces": [{"name": "Ethernet1", "area": "0.0.0.0"}],  # noqa: S104
        },
    },
    {
        "intent_id": "lab-eigrp-001",
        "intent_type": IntentTypeChoices.EIGRP,
        "change_ticket": "CHG0020022",
        "description": "EIGRP AS 100 — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "asn": 100,
            "networks": ["10.0.0.0/8", "172.20.20.0/24"],
            "router_id": "10.0.0.1",
            "passive_interfaces": ["Management0"],
        },
    },
    {
        "intent_id": "lab-sr-mpls-001",
        "intent_type": IntentTypeChoices.SR_MPLS,
        "change_ticket": "CHG0020023",
        "description": "Segment Routing MPLS — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "process_tag": "SR-LAB",
            "srgb_start": 16000,
            "srgb_end": 23999,
            "ti_lfa": True,
            "ti_lfa_mode": "node-protection",
        },
    },
    # ════════════════════════════════════════════════════════════════════
    # L2 — new L2/interface removal templates
    # ════════════════════════════════════════════════════════════════════
    {
        "intent_id": "lab-pvlan-001",
        "intent_type": IntentTypeChoices.PVLAN,
        "change_ticket": "CHG0020024",
        "description": "Private VLAN — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "primary_vlan": 400,
            "isolated_vlans": [401],
            "community_vlans": [402, 403],
            "promiscuous_ports": ["Ethernet1"],
            "isolated_ports": ["Ethernet3"],
        },
    },
    {
        "intent_id": "lab-stp-root-001",
        "intent_type": IntentTypeChoices.MGMT_STP_ROOT,
        "change_ticket": "CHG0020025",
        "description": "STP root bridge — spine devices — lab EOS",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "primary_vlans": [100, 101, 200, 300],
            "secondary_vlans": [],
            "priority": 4096,
        },
    },
    # ════════════════════════════════════════════════════════════════════
    # QoS — new QoS removal templates
    # ════════════════════════════════════════════════════════════════════
    {
        "intent_id": "lab-qos-police-001",
        "intent_type": IntentTypeChoices.QOS_POLICE,
        "change_ticket": "CHG0020026",
        "description": "QoS policing policy — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "policy_map": "LAB-POLICE-POL",
            "rate_bps": 100000000,
            "burst_bytes": 1500000,
            "conform_action": "transmit",
            "exceed_action": "drop",
            "violate_action": "drop",
            "apply_interfaces": ["Ethernet1"],
        },
    },
    {
        "intent_id": "lab-qos-queue-001",
        "intent_type": IntentTypeChoices.QOS_QUEUE,
        "change_ticket": "CHG0020027",
        "description": "QoS LLQ queuing policy — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "policy_map": "LAB-WAN-QOS",
            "queues": [
                {"class_name": "VOICE", "priority": True, "bandwidth_percent": 20},
                {"class_name": "VIDEO", "bandwidth_percent": 30},
                {"class_name": "DATA", "bandwidth_percent": 50},
            ],
            "apply_interfaces": ["Ethernet1"],
            "direction": "output",
        },
    },
    {
        "intent_id": "lab-qos-shape-001",
        "intent_type": IntentTypeChoices.QOS_SHAPE,
        "change_ticket": "CHG0020028",
        "description": "QoS traffic shaping — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "policy_map": "LAB-SHAPE-POL",
            "rate_bps": 50000000,
            "burst_bytes": 1000000,
            "apply_interfaces": ["Ethernet1"],
        },
    },
    {
        "intent_id": "lab-qos-trust-001",
        "intent_type": IntentTypeChoices.QOS_TRUST,
        "change_ticket": "CHG0020029",
        "description": "QoS DSCP trust boundary — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "trust_type": "dscp",
            "apply_interfaces": ["Ethernet1", "Ethernet2"],
        },
    },
    # ════════════════════════════════════════════════════════════════════
    # MULTICAST — new msdp removal template
    # ════════════════════════════════════════════════════════════════════
    {
        "intent_id": "lab-msdp-001",
        "intent_type": IntentTypeChoices.MSDP,
        "change_ticket": "CHG0020030",
        "description": "MSDP peering — lab EOS devices",
        "version": 1,
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "peers": [{"ip": "10.0.0.2", "remote_as": 65001, "connect_source": "Loopback0"}],
            "originator_id": "10.0.0.1",
        },
    },
]

# ─── Create / update intents ──────────────────────────────────────────────────
print(f"\nCreating {len(INTENTS)} intents for tenant '{tenant.name}'...\n")
created_count = 0
updated_count = 0

for data in INTENTS:
    intent_data = data.pop("intent_data")
    iid = data["intent_id"]

    intent, created = Intent.objects.update_or_create(
        intent_id=iid,
        defaults={
            "intent_type": data["intent_type"],
            "tenant": tenant,
            "status": draft_status,
            "version": data["version"],
            "change_ticket": data["change_ticket"],
            "controller_type": data.get("controller_type", "nornir"),
            "deployment_strategy": data.get("deployment_strategy", "rolling"),
            "verification_level": data.get("verification_level", "basic"),
            "verification_trigger": data.get("verification_trigger", "on_deploy"),
            "verification_fail_action": data.get("verification_fail_action", "alert"),
            "intent_data": intent_data,
        },
    )

    flag = "Created" if created else "Updated"
    print(f"  {flag}: {iid} (type={data['intent_type']})")
    if created:
        created_count += 1
    else:
        updated_count += 1

print(f"\n{'=' * 60}")
print(f"  Done: {created_count} created, {updated_count} updated")
print(f"  Total lab intents in DB: {Intent.objects.filter(tenant=tenant).count()}")
print("  All in status: Draft — ready for pipeline")
print("  Intent types cover Feature/improved-EOS new EOS templates:")
print("    security x5 | routing x4 | l2 x2 | qos x4 | multicast x1 = 16 total")
print(f"{'=' * 60}")
print("\nNext: exec(open('development/run_pipeline_retire.py').read())")
