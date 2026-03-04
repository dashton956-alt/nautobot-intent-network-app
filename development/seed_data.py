"""Seed Nautobot with realistic dummy data for testing the Intent Networking plugin."""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

# ─── Nautobot core models ────────────────────────────────────────────────────
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Location,
    LocationType,
    Manufacturer,
)
from nautobot.extras.models import Role, Status
from nautobot.tenancy.models import Tenant

# ─── Plugin models ───────────────────────────────────────────────────────────
from intent_networking.models import (
    Intent,
    IntentTypeChoices,
    ResolutionPlan,
    RouteDistinguisher,
    RouteDistinguisherPool,
    RouteTarget,
    RouteTargetPool,
    VerificationResult,
)

now = timezone.now()

print("=" * 60)
print("  Intent Networking — Seed Data Loader")
print("=" * 60)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Statuses
# ─────────────────────────────────────────────────────────────────────────────
print("\n[1/9] Creating statuses...")
intent_ct = ContentType.objects.get_for_model(Intent)

# Statuses for the Intent lifecycle
INTENT_STATUSES = ["Draft", "Validated", "Deploying", "Deployed", "Failed", "Rolled Back", "Deprecated"]
status_map = {}
for name in INTENT_STATUSES:
    s, created = Status.objects.get_or_create(name=name)
    s.content_types.add(intent_ct)
    status_map[name] = s
    print(f"  {'Created' if created else 'Exists '} status: {name}")

# Device / Location statuses
for model_class in [Device, Location]:
    ct = ContentType.objects.get_for_model(model_class)
    for name in ["Active", "Planned", "Staging", "Decommissioning"]:
        s, _ = Status.objects.get_or_create(name=name)
        s.content_types.add(ct)

active_status = Status.objects.get(name="Active")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Tenants
# ─────────────────────────────────────────────────────────────────────────────
print("\n[2/9] Creating tenants...")
TENANT_NAMES = [
    "FinServ Corp",
    "HealthNet Systems",
    "RetailEdge Inc",
    "GovCloud Agency",
]
tenants = {}
for name in TENANT_NAMES:
    t, created = Tenant.objects.get_or_create(name=name)
    tenants[name] = t
    print(f"  {'Created' if created else 'Exists '} tenant: {name}")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Locations (Sites / DCs)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3/9] Creating locations...")
region_type, _ = LocationType.objects.get_or_create(name="Region")
site_type, _ = LocationType.objects.get_or_create(name="Site", parent=region_type)
site_type.content_types.add(ContentType.objects.get_for_model(Device))

regions_sites = {
    "US-East": ["NYC-DC1", "NYC-DC2", "BOS-DC1"],
    "US-West": ["LAX-DC1", "SFO-DC1", "SEA-DC1"],
    "EU-West": ["LON-DC1", "AMS-DC1", "FRA-DC1"],
}
locations = {}
for region_name, site_names in regions_sites.items():
    region, _ = Location.objects.get_or_create(
        name=region_name, location_type=region_type, defaults={"status": active_status}
    )
    for site_name in site_names:
        loc, created = Location.objects.get_or_create(
            name=site_name,
            location_type=site_type,
            defaults={"status": active_status, "parent": region},
        )
        locations[site_name] = loc
        print(f"  {'Created' if created else 'Exists '} location: {region_name} / {site_name}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Manufacturers, Device Types, Roles, Devices
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4/9] Creating devices...")
cisco, _ = Manufacturer.objects.get_or_create(name="Cisco")
juniper, _ = Manufacturer.objects.get_or_create(name="Juniper")
arista, _ = Manufacturer.objects.get_or_create(name="Arista")

dt_asr9k, _ = DeviceType.objects.get_or_create(model="ASR-9001", defaults={"manufacturer": cisco})
dt_mx204, _ = DeviceType.objects.get_or_create(model="MX204", defaults={"manufacturer": juniper})
dt_7280, _ = DeviceType.objects.get_or_create(model="DCS-7280SR", defaults={"manufacturer": arista})

device_ct = ContentType.objects.get_for_model(Device)
pe_role, _ = Role.objects.get_or_create(name="PE Router")
pe_role.content_types.add(device_ct)
p_role, _ = Role.objects.get_or_create(name="P Router")
p_role.content_types.add(device_ct)
ce_role, _ = Role.objects.get_or_create(name="CE Switch")
ce_role.content_types.add(device_ct)

DEVICES = [
    # (name, site, device_type, role, tenant)
    ("nyc-pe01", "NYC-DC1", dt_asr9k, pe_role, "FinServ Corp"),
    ("nyc-pe02", "NYC-DC1", dt_mx204, pe_role, "FinServ Corp"),
    ("nyc-p01", "NYC-DC2", dt_asr9k, p_role, "FinServ Corp"),
    ("bos-pe01", "BOS-DC1", dt_asr9k, pe_role, "HealthNet Systems"),
    ("bos-ce01", "BOS-DC1", dt_7280, ce_role, "HealthNet Systems"),
    ("lax-pe01", "LAX-DC1", dt_mx204, pe_role, "RetailEdge Inc"),
    ("lax-pe02", "LAX-DC1", dt_asr9k, pe_role, "RetailEdge Inc"),
    ("sfo-pe01", "SFO-DC1", dt_mx204, pe_role, "GovCloud Agency"),
    ("sea-pe01", "SEA-DC1", dt_7280, pe_role, "GovCloud Agency"),
    ("lon-pe01", "LON-DC1", dt_asr9k, pe_role, "FinServ Corp"),
    ("ams-pe01", "AMS-DC1", dt_mx204, pe_role, "FinServ Corp"),
    ("fra-pe01", "FRA-DC1", dt_7280, pe_role, "HealthNet Systems"),
]

devices = {}
for dev_name, site_name, dt, role, tenant_name in DEVICES:
    dev, created = Device.objects.get_or_create(
        name=dev_name,
        defaults={
            "device_type": dt,
            "role": role,
            "location": locations[site_name],
            "status": active_status,
            "tenant": tenants[tenant_name],
        },
    )
    devices[dev_name] = dev
    print(f"  {'Created' if created else 'Exists '} device: {dev_name} ({dt.model}) @ {site_name}")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Intents
# ─────────────────────────────────────────────────────────────────────────────
print("\n[5/9] Creating intents...")
INTENTS = [
    {
        "intent_id": "fin-pci-connectivity-001",
        "intent_type": IntentTypeChoices.CONNECTIVITY,
        "tenant": "FinServ Corp",
        "status": "Deployed",
        "version": 3,
        "change_ticket": "CHG0012345",
        "approved_by": "j.chen",
        "git_commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        "git_branch": "main",
        "git_pr_number": 142,
        "deployed_at": now - timedelta(days=5),
        "last_verified_at": now - timedelta(hours=1),
        "intent_data": {
            "type": "connectivity",
            "name": "PCI Zone Connectivity",
            "description": "L3VPN connectivity for PCI cardholder data environment",
            "sites": ["NYC-DC1", "LON-DC1"],
            "vrf": "VRF-PCI-FIN",
            "bandwidth_mbps": 1000,
            "qos_class": "ef",
            "sla": {"latency_ms": 50, "jitter_ms": 5, "availability_pct": 99.99},
            "acl_policy": "pci-strict",
        },
    },
    {
        "intent_id": "fin-office-connectivity-002",
        "intent_type": IntentTypeChoices.CONNECTIVITY,
        "tenant": "FinServ Corp",
        "status": "Deployed",
        "version": 2,
        "change_ticket": "CHG0012400",
        "approved_by": "m.rodriguez",
        "git_commit_sha": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
        "git_branch": "main",
        "git_pr_number": 156,
        "deployed_at": now - timedelta(days=3),
        "last_verified_at": now - timedelta(hours=2),
        "intent_data": {
            "type": "connectivity",
            "name": "Corporate Office WAN",
            "description": "MPLS L3VPN connecting NYC and AMS offices",
            "sites": ["NYC-DC1", "NYC-DC2", "AMS-DC1"],
            "vrf": "VRF-CORP-FIN",
            "bandwidth_mbps": 500,
            "qos_class": "af41",
        },
    },
    {
        "intent_id": "hnet-hipaa-security-001",
        "intent_type": IntentTypeChoices.SECURITY,
        "tenant": "HealthNet Systems",
        "status": "Deployed",
        "version": 1,
        "change_ticket": "CHG0012500",
        "approved_by": "s.patel",
        "git_commit_sha": "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        "git_branch": "main",
        "git_pr_number": 180,
        "deployed_at": now - timedelta(days=10),
        "last_verified_at": now - timedelta(minutes=30),
        "intent_data": {
            "type": "security",
            "name": "HIPAA Network Segmentation",
            "description": "Microsegmentation ACLs for HIPAA workloads",
            "sites": ["BOS-DC1", "FRA-DC1"],
            "acl_rules": [
                {"src": "10.200.0.0/16", "dst": "10.201.0.0/16", "action": "permit", "proto": "tcp", "port": 443},
                {"src": "any", "dst": "10.200.0.0/16", "action": "deny"},
            ],
        },
    },
    {
        "intent_id": "retail-edge-reachability-001",
        "intent_type": IntentTypeChoices.REACHABILITY,
        "tenant": "RetailEdge Inc",
        "status": "Validated",
        "version": 1,
        "change_ticket": "CHG0012600",
        "approved_by": "d.kim",
        "git_branch": "feature/retail-edge-bgp",
        "git_pr_number": 201,
        "intent_data": {
            "type": "reachability",
            "name": "Retail Store BGP Peering",
            "description": "eBGP peering with retail store routers via SD-WAN overlay",
            "sites": ["LAX-DC1"],
            "bgp": {"local_as": 65100, "peer_as": 65200, "peer_ip": "10.50.0.1", "prefixes_in": 50},
        },
    },
    {
        "intent_id": "gov-cloud-service-001",
        "intent_type": IntentTypeChoices.SERVICE,
        "tenant": "GovCloud Agency",
        "status": "Draft",
        "version": 1,
        "git_branch": "feature/govcloud-svc",
        "intent_data": {
            "type": "service",
            "name": "FedRAMP Service Chain",
            "description": "Service function chain: FW → IDS → LB for GovCloud workloads",
            "sites": ["SFO-DC1", "SEA-DC1"],
            "service_chain": ["firewall", "ids", "load_balancer"],
            "bandwidth_mbps": 2000,
        },
    },
    {
        "intent_id": "fin-dr-connectivity-003",
        "intent_type": IntentTypeChoices.CONNECTIVITY,
        "tenant": "FinServ Corp",
        "status": "Deploying",
        "version": 1,
        "change_ticket": "CHG0012700",
        "approved_by": "j.chen",
        "git_commit_sha": "d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
        "git_branch": "main",
        "git_pr_number": 210,
        "intent_data": {
            "type": "connectivity",
            "name": "Disaster Recovery Tunnel",
            "description": "Cross-region L3VPN for DR failover NYC ↔ LON",
            "sites": ["NYC-DC1", "LON-DC1"],
            "vrf": "VRF-DR-FIN",
            "bandwidth_mbps": 10000,
            "qos_class": "ef",
            "sla": {"latency_ms": 80, "availability_pct": 99.999},
        },
    },
    {
        "intent_id": "hnet-lab-connectivity-002",
        "intent_type": IntentTypeChoices.CONNECTIVITY,
        "tenant": "HealthNet Systems",
        "status": "Failed",
        "version": 2,
        "change_ticket": "CHG0012550",
        "approved_by": "s.patel",
        "git_commit_sha": "e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
        "git_branch": "main",
        "git_pr_number": 195,
        "intent_data": {
            "type": "connectivity",
            "name": "Lab Network Extension",
            "description": "Extend lab VRF from BOS to FRA for testing",
            "sites": ["BOS-DC1", "FRA-DC1"],
            "vrf": "VRF-LAB-HNET",
            "bandwidth_mbps": 100,
        },
    },
    {
        "intent_id": "retail-security-pci-001",
        "intent_type": IntentTypeChoices.SECURITY,
        "tenant": "RetailEdge Inc",
        "status": "Rolled Back",
        "version": 1,
        "change_ticket": "CHG0012650",
        "approved_by": "d.kim",
        "git_commit_sha": "f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1",
        "git_branch": "main",
        "git_pr_number": 205,
        "deployed_at": now - timedelta(days=1),
        "intent_data": {
            "type": "security",
            "name": "POS Terminal ACLs",
            "description": "Restrict POS terminal traffic to payment gateway only",
            "sites": ["LAX-DC1"],
            "acl_rules": [
                {"src": "10.100.0.0/24", "dst": "10.200.1.1/32", "action": "permit", "proto": "tcp", "port": 8443},
                {"src": "10.100.0.0/24", "dst": "any", "action": "deny"},
            ],
        },
    },
]

intents = {}
for data in INTENTS:
    intent, created = Intent.objects.get_or_create(
        intent_id=data["intent_id"],
        defaults={
            "intent_type": data["intent_type"],
            "tenant": tenants[data["tenant"]],
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
        },
    )
    intents[data["intent_id"]] = intent
    print(f"  {'Created' if created else 'Exists '} intent: {data['intent_id']} [{data['status']}]")

# ─────────────────────────────────────────────────────────────────────────────
# 6. Resolution Plans
# ─────────────────────────────────────────────────────────────────────────────
print("\n[6/9] Creating resolution plans...")
PLANS = [
    {
        "intent_id": "fin-pci-connectivity-001",
        "intent_version": 3,
        "vrf_name": "VRF-PCI-FIN",
        "requires_new_vrf": False,
        "requires_mpls": True,
        "allocated_rds": {"nyc-pe01": "65000:1001", "lon-pe01": "65000:1002"},
        "allocated_rts": {"export": "65000:5001", "import": "65000:5001"},
        "resolved_by": "IntentResolverJob",
        "devices": ["nyc-pe01", "nyc-pe02", "lon-pe01"],
        "primitives": [
            {"type": "VrfPrimitive", "name": "VRF-PCI-FIN", "rd": "65000:1001", "device": "nyc-pe01"},
            {"type": "VrfPrimitive", "name": "VRF-PCI-FIN", "rd": "65000:1002", "device": "lon-pe01"},
            {
                "type": "BgpNeighborPrimitive",
                "local_device": "nyc-pe01",
                "peer_device": "lon-pe01",
                "address_family": "vpnv4",
            },
            {"type": "AclPrimitive", "name": "pci-strict-in", "direction": "inbound", "device": "nyc-pe01"},
            {"type": "AclPrimitive", "name": "pci-strict-in", "direction": "inbound", "device": "lon-pe01"},
        ],
    },
    {
        "intent_id": "fin-office-connectivity-002",
        "intent_version": 2,
        "vrf_name": "VRF-CORP-FIN",
        "requires_new_vrf": False,
        "requires_mpls": True,
        "allocated_rds": {"nyc-pe01": "65000:1010", "ams-pe01": "65000:1011"},
        "allocated_rts": {"export": "65000:5010", "import": "65000:5010"},
        "resolved_by": "IntentResolverJob",
        "devices": ["nyc-pe01", "nyc-pe02", "nyc-p01", "ams-pe01"],
        "primitives": [
            {"type": "VrfPrimitive", "name": "VRF-CORP-FIN", "rd": "65000:1010", "device": "nyc-pe01"},
            {"type": "VrfPrimitive", "name": "VRF-CORP-FIN", "rd": "65000:1011", "device": "ams-pe01"},
            {
                "type": "BgpNeighborPrimitive",
                "local_device": "nyc-pe01",
                "peer_device": "ams-pe01",
                "address_family": "vpnv4",
            },
        ],
    },
    {
        "intent_id": "hnet-hipaa-security-001",
        "intent_version": 1,
        "vrf_name": "",
        "requires_new_vrf": False,
        "requires_mpls": False,
        "allocated_rds": {},
        "allocated_rts": {},
        "resolved_by": "IntentResolverJob",
        "devices": ["bos-pe01", "bos-ce01", "fra-pe01"],
        "primitives": [
            {"type": "AclPrimitive", "name": "hipaa-segment-in", "direction": "inbound", "device": "bos-pe01"},
            {"type": "AclPrimitive", "name": "hipaa-segment-out", "direction": "outbound", "device": "bos-pe01"},
            {"type": "AclPrimitive", "name": "hipaa-segment-in", "direction": "inbound", "device": "fra-pe01"},
        ],
    },
    {
        "intent_id": "fin-dr-connectivity-003",
        "intent_version": 1,
        "vrf_name": "VRF-DR-FIN",
        "requires_new_vrf": True,
        "requires_mpls": True,
        "allocated_rds": {"nyc-pe01": "65000:1020", "lon-pe01": "65000:1021"},
        "allocated_rts": {"export": "65000:5020", "import": "65000:5020"},
        "resolved_by": "IntentResolverJob",
        "devices": ["nyc-pe01", "nyc-pe02", "lon-pe01"],
        "primitives": [
            {"type": "VrfPrimitive", "name": "VRF-DR-FIN", "rd": "65000:1020", "device": "nyc-pe01"},
            {"type": "VrfPrimitive", "name": "VRF-DR-FIN", "rd": "65000:1021", "device": "lon-pe01"},
            {
                "type": "BgpNeighborPrimitive",
                "local_device": "nyc-pe01",
                "peer_device": "lon-pe01",
                "address_family": "vpnv4",
            },
            {"type": "QosPrimitive", "class": "ef", "bandwidth_mbps": 10000, "device": "nyc-pe01"},
            {"type": "QosPrimitive", "class": "ef", "bandwidth_mbps": 10000, "device": "lon-pe01"},
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
        for dev_name in plan_data["devices"]:
            if dev_name in devices:
                plan.affected_devices.add(devices[dev_name])
    print(
        f"  {'Created' if created else 'Exists '} plan: {plan_data['intent_id']} v{plan_data['intent_version']} ({len(plan_data['primitives'])} primitives)"
    )

# ─────────────────────────────────────────────────────────────────────────────
# 7. Verification Results
# ─────────────────────────────────────────────────────────────────────────────
print("\n[7/9] Creating verification results...")
VERIFICATIONS = [
    # fin-pci — last 3 checks all passed
    ("fin-pci-connectivity-001", True, "deployment", 12, 4, 4, 8, 8, {}),
    ("fin-pci-connectivity-001", True, "reconciliation", 14, 4, 4, 8, 8, {}),
    ("fin-pci-connectivity-001", True, "reconciliation", 11, 4, 4, 8, 8, {}),
    # fin-office — passed
    ("fin-office-connectivity-002", True, "deployment", 22, 6, 6, 12, 12, {}),
    ("fin-office-connectivity-002", True, "reconciliation", 20, 6, 6, 12, 12, {}),
    # hnet-hipaa — passed
    ("hnet-hipaa-security-001", True, "deployment", None, 0, 0, 0, 0, {}),
    ("hnet-hipaa-security-001", True, "reconciliation", None, 0, 0, 0, 0, {}),
    # hnet-lab — FAILED with drift
    (
        "hnet-lab-connectivity-002",
        False,
        "deployment",
        None,
        2,
        0,
        4,
        0,
        {
            "bos-pe01": "BGP session to fra-pe01 not established",
            "fra-pe01": "VRF VRF-LAB-HNET not found in running config",
        },
    ),
    # retail-security — FAILED then rolled back
    (
        "retail-security-pci-001",
        False,
        "deployment",
        None,
        0,
        0,
        0,
        0,
        {"lax-pe01": "ACL pci-pos-in rejected by device — syntax error in rule 2"},
    ),
]

for i, (iid, passed, trigger, latency, bgp_exp, bgp_est, pfx_exp, pfx_rcv, drift) in enumerate(VERIFICATIONS):
    intent = intents[iid]
    # Check if a verification already exists for this intent with this trigger at roughly this time
    existing = VerificationResult.objects.filter(intent=intent, triggered_by=trigger, passed=passed).count()
    if existing > 0 and i < existing:
        print(f"  Exists  verification: {iid} — {'PASS' if passed else 'FAIL'} ({trigger})")
        continue
    checks = []
    if bgp_exp > 0:
        checks.append(
            {
                "device": "pe01",
                "check_name": "bgp_sessions",
                "passed": bgp_est == bgp_exp,
                "detail": f"{bgp_est}/{bgp_exp} established",
            }
        )
        checks.append(
            {
                "device": "pe01",
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
        remediation_triggered=bool(drift),
        github_issue_url=f"https://github.com/acme-net/intents/issues/{200 + i}" if drift else "",
    )
    print(f"  Created verification: {iid} — {'PASS' if passed else 'FAIL'} ({trigger})")

# ─────────────────────────────────────────────────────────────────────────────
# 8. Route Distinguisher & Target Pools
# ─────────────────────────────────────────────────────────────────────────────
print("\n[8/9] Creating RD/RT pools...")
rd_pool, created = RouteDistinguisherPool.objects.get_or_create(
    name="provider-rd-pool",
    defaults={"asn": 65000, "range_start": 1000, "range_end": 9999, "tenant": tenants["FinServ Corp"]},
)
print(f"  {'Created' if created else 'Exists '} RD pool: provider-rd-pool (65000:1000-9999)")

rt_pool, created = RouteTargetPool.objects.get_or_create(
    name="provider-rt-pool",
    defaults={"asn": 65000, "range_start": 5000, "range_end": 5999},
)
print(f"  {'Created' if created else 'Exists '} RT pool: provider-rt-pool (65000:5000-5999)")

# ─────────────────────────────────────────────────────────────────────────────
# 9. RD/RT Allocations
# ─────────────────────────────────────────────────────────────────────────────
print("\n[9/9] Creating RD/RT allocations...")
RD_ALLOCS = [
    ("65000:1001", "nyc-pe01", "VRF-PCI-FIN", "fin-pci-connectivity-001"),
    ("65000:1002", "lon-pe01", "VRF-PCI-FIN", "fin-pci-connectivity-001"),
    ("65000:1010", "nyc-pe01", "VRF-CORP-FIN", "fin-office-connectivity-002"),
    ("65000:1011", "ams-pe01", "VRF-CORP-FIN", "fin-office-connectivity-002"),
    ("65000:1020", "nyc-pe01", "VRF-DR-FIN", "fin-dr-connectivity-003"),
    ("65000:1021", "lon-pe01", "VRF-DR-FIN", "fin-dr-connectivity-003"),
]
for value, dev_name, vrf, iid in RD_ALLOCS:
    # unique_together on (device, vrf_name), so check that
    rd, created = RouteDistinguisher.objects.get_or_create(
        device=devices[dev_name],
        vrf_name=vrf,
        defaults={"pool": rd_pool, "value": value, "intent": intents[iid]},
    )
    print(f"  {'Created' if created else 'Exists '} RD: {value} → {dev_name}/{vrf}")

RT_ALLOCS = [
    ("65000:5001", "fin-pci-connectivity-001"),
    ("65000:5010", "fin-office-connectivity-002"),
    ("65000:5020", "fin-dr-connectivity-003"),
]
for value, iid in RT_ALLOCS:
    rt, created = RouteTarget.objects.get_or_create(
        intent=intents[iid],
        defaults={"pool": rt_pool, "value": value},
    )
    print(f"  {'Created' if created else 'Exists '} RT: {value} → {iid}")

# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Seed complete!")
print(f"  Tenants:       {Tenant.objects.count()}")
print(f"  Locations:     {Location.objects.count()}")
print(f"  Devices:       {Device.objects.count()}")
print(f"  Intents:       {Intent.objects.count()}")
print(f"  Plans:         {ResolutionPlan.objects.count()}")
print(f"  Verifications: {VerificationResult.objects.count()}")
print(f"  RD Pools:      {RouteDistinguisherPool.objects.count()}")
print(f"  RD Allocs:     {RouteDistinguisher.objects.count()}")
print(f"  RT Pools:      {RouteTargetPool.objects.count()}")
print(f"  RT Allocs:     {RouteTarget.objects.count()}")
print("=" * 60)
