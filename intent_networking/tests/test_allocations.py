"""Unit tests for intent_networking.allocations module.

Tests all six allocation functions (RD/VRF, RT, VNI, Tunnel ID, Loopback,
Wireless VLAN) plus the release_allocations function.  Covers:
  - Normal allocation (happy path)
  - Idempotency (duplicate call returns existing value)
  - Pool exhaustion (ValueError) — for pool-based allocations
  - Missing namespace / pool (ValueError)
  - release_allocations cleanup

RD and RT allocation now uses Nautobot's native ``ipam.VRF``,
``ipam.RouteTarget`` and ``ipam.Namespace`` models rather than custom pool
tables.
"""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import VRF, Namespace
from nautobot.ipam.models import RouteTarget as NautobotRouteTarget
from nautobot.tenancy.models import Tenant

from intent_networking import models
from intent_networking.allocations import (
    allocate_loopback_ip,
    allocate_route_distinguisher,
    allocate_route_target,
    allocate_tunnel_id,
    allocate_vxlan_vni,
    allocate_wireless_vlan,
    release_allocations,
)

PLUGIN_CFG = {
    "intent_networking": {
        "vrf_namespace": "Test Namespace",
        "default_bgp_asn": 65000,
        "vni_pool_name": "test-vni-pool",
        "tunnel_id_pool_name": "test-tunnel-pool",
        "loopback_pool_name": "test-loopback-pool",
    }
}


class AllocationTestMixin:
    """Shared setUp for allocation tests — creates a device, an intent, and a Namespace."""

    @classmethod
    def setUpTestData(cls):
        """Create shared test data."""
        super().setUpTestData()
        # Statuses
        intent_ct = ContentType.objects.get_for_model(models.Intent)
        device_ct = ContentType.objects.get_for_model(Device)
        location_ct = ContentType.objects.get_for_model(Location)
        for sname in ("Draft", "Active"):
            st, _ = Status.objects.get_or_create(name=sname)
            st.content_types.add(intent_ct, device_ct, location_ct)

        cls.tenant, _ = Tenant.objects.get_or_create(name="Alloc Tenant")

        # Device hierarchy
        mfr, _ = Manufacturer.objects.get_or_create(name="Alloc Mfr")
        dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model="Test Model")
        role, _ = Role.objects.get_or_create(name="Alloc Role")
        role.content_types.add(device_ct)

        lt, _ = LocationType.objects.get_or_create(name="Alloc Site Type")
        lt.content_types.add(device_ct)
        site, _ = Location.objects.get_or_create(
            name="Alloc Site",
            location_type=lt,
            status=Status.objects.get(name="Active"),
        )
        cls.site = site
        cls.device, _ = Device.objects.get_or_create(
            name="alloc-rtr-01",
            defaults={
                "device_type": dt,
                "role": role,
                "location": site,
                "status": Status.objects.get(name="Active"),
                "tenant": cls.tenant,
            },
        )

        # Namespace for VRF/RD allocation (matches PLUGIN_CFG)
        cls.namespace, _ = Namespace.objects.get_or_create(name="Test Namespace")

        # Intent
        cls.intent, _ = models.Intent.objects.get_or_create(
            intent_id="alloc-test-001",
            defaults={
                "version": 1,
                "intent_type": models.IntentTypeChoices.CONNECTIVITY,
                "tenant": cls.tenant,
                "status": Status.objects.get(name="Draft"),
                "intent_data": {"type": "connectivity", "name": "alloc-test-001", "source": "Gi0/1"},
            },
        )

        # Second intent for release tests
        cls.intent2, _ = models.Intent.objects.get_or_create(
            intent_id="alloc-test-002",
            defaults={
                "version": 1,
                "intent_type": models.IntentTypeChoices.SECURITY,
                "tenant": cls.tenant,
                "status": Status.objects.get(name="Draft"),
                "intent_data": {"type": "security", "name": "alloc-test-002"},
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Route Distinguisher
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(PLUGINS_CONFIG=PLUGIN_CFG)
class AllocateRouteDistinguisherTest(AllocationTestMixin, TestCase):
    """Test allocate_route_distinguisher using Nautobot VRF + Namespace."""

    def test_allocate_rd_happy_path(self):
        """First allocation creates a VRF and returns 65000:1."""
        rd = allocate_route_distinguisher(self.device, "TEST-VRF", self.intent)
        self.assertEqual(rd, "65000:1")
        # Verify VRF was created in Nautobot
        self.assertTrue(VRF.objects.filter(name="TEST-VRF", namespace=self.namespace).exists())

    def test_allocate_rd_idempotent(self):
        """Second call for same VRF name + namespace returns the same RD."""
        rd1 = allocate_route_distinguisher(self.device, "IDEMPOTENT-VRF", self.intent)
        rd2 = allocate_route_distinguisher(self.device, "IDEMPOTENT-VRF", self.intent)
        self.assertEqual(rd1, rd2)
        # Only one VRF record
        self.assertEqual(
            VRF.objects.filter(name="IDEMPOTENT-VRF", namespace=self.namespace).count(),
            1,
        )

    def test_allocate_rd_increments_counter(self):
        """Successive VRFs get incrementing counters."""
        rd1 = allocate_route_distinguisher(self.device, "VRF-A", self.intent)
        rd2 = allocate_route_distinguisher(self.device, "VRF-B", self.intent)
        self.assertEqual(rd1, "65000:1")
        self.assertEqual(rd2, "65000:2")

    def test_allocate_rd_assigns_device(self):
        """VRF should have the device in its devices M2M."""
        allocate_route_distinguisher(self.device, "DEV-VRF", self.intent)
        vrf = VRF.objects.get(name="DEV-VRF", namespace=self.namespace)
        self.assertIn(self.device, vrf.devices.all())

    def test_allocate_rd_sets_description(self):
        """VRF description tracks the intent that created it."""
        allocate_route_distinguisher(self.device, "DESC-VRF", self.intent)
        vrf = VRF.objects.get(name="DESC-VRF", namespace=self.namespace)
        self.assertIn(self.intent.intent_id, vrf.description)

    def test_allocate_rd_missing_namespace(self):
        """ValueError when configured namespace doesn't exist."""
        with override_settings(
            PLUGINS_CONFIG={"intent_networking": {"vrf_namespace": "nonexistent", "default_bgp_asn": 65000}}
        ):
            with self.assertRaises(ValueError) as ctx:
                allocate_route_distinguisher(self.device, "FAIL-VRF", self.intent)
            self.assertIn("not found", str(ctx.exception))


# ─────────────────────────────────────────────────────────────────────────────
# Route Target
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(PLUGINS_CONFIG=PLUGIN_CFG)
class AllocateRouteTargetTest(AllocationTestMixin, TestCase):
    """Test allocate_route_target using Nautobot RouteTarget."""

    def test_allocate_rt_happy_path(self):
        """First allocation returns (65000:1, 65000:1)."""
        rt_export, rt_import = allocate_route_target(self.intent)
        self.assertEqual(rt_export, "65000:1")
        self.assertEqual(rt_import, "65000:1")
        # Verify RT was created in Nautobot
        self.assertTrue(NautobotRouteTarget.objects.filter(name="65000:1").exists())

    def test_allocate_rt_idempotent(self):
        """Second call for same intent returns the same RT."""
        rt1 = allocate_route_target(self.intent)
        rt2 = allocate_route_target(self.intent)
        self.assertEqual(rt1, rt2)
        # Only one RT record for this intent
        desc = f"Auto-allocated for intent {self.intent.intent_id}"
        self.assertEqual(NautobotRouteTarget.objects.filter(description=desc).count(), 1)

    def test_allocate_rt_increments_counter(self):
        """Successive RT allocations for different intents increment counter."""
        rt1_export, _ = allocate_route_target(self.intent)
        rt2_export, _ = allocate_route_target(self.intent2)
        self.assertEqual(rt1_export, "65000:1")
        self.assertEqual(rt2_export, "65000:2")

    def test_allocate_rt_sets_description(self):
        """RT description tracks the intent that created it."""
        allocate_route_target(self.intent)
        rt = NautobotRouteTarget.objects.get(name="65000:1")
        self.assertIn(self.intent.intent_id, rt.description)

    def test_allocate_rt_sets_tenant(self):
        """RT inherits tenant from the intent."""
        allocate_route_target(self.intent)
        rt = NautobotRouteTarget.objects.get(name="65000:1")
        self.assertEqual(rt.tenant, self.intent.tenant)


# ─────────────────────────────────────────────────────────────────────────────
# VXLAN VNI
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(PLUGINS_CONFIG=PLUGIN_CFG)
class AllocateVxlanVniTest(AllocationTestMixin, TestCase):
    """Test allocate_vxlan_vni."""

    @classmethod
    def setUpTestData(cls):
        """Create VNI pool."""
        super().setUpTestData()
        cls.vni_pool, _ = models.VxlanVniPool.objects.get_or_create(
            name="test-vni-pool",
            defaults={"range_start": 10000, "range_end": 10002},
        )

    def test_allocate_vni_happy_path(self):
        """First allocation returns 10000."""
        vni = allocate_vxlan_vni(self.intent, "l2")
        self.assertEqual(vni, 10000)

    def test_allocate_vni_idempotent(self):
        """Second call for same intent+type returns the same VNI."""
        vni1 = allocate_vxlan_vni(self.intent, "l3")
        vni2 = allocate_vxlan_vni(self.intent, "l3")
        self.assertEqual(vni1, vni2)

    def test_allocate_vni_different_types(self):
        """Different vni_type values get different VNIs."""
        vni_l2 = allocate_vxlan_vni(self.intent, "l2")
        vni_l3 = allocate_vxlan_vni(self.intent, "l3")
        self.assertNotEqual(vni_l2, vni_l3)

    def test_allocate_vni_pool_exhausted(self):
        """ValueError when the pool is full."""
        for i in range(10000, 10003):
            models.VniAllocation.objects.create(
                pool=self.vni_pool,
                value=i,
                intent=self.intent,
                vni_type="l2",
            )
        with self.assertRaises(ValueError) as ctx:
            allocate_vxlan_vni(self.intent2, "l2")
        self.assertIn("exhausted", str(ctx.exception))

    def test_allocate_vni_missing_pool(self):
        """ValueError when configured pool name doesn't exist."""
        with override_settings(PLUGINS_CONFIG={"intent_networking": {"vni_pool_name": "nonexistent"}}):
            with self.assertRaises(ValueError):
                allocate_vxlan_vni(self.intent, "l2")


# ─────────────────────────────────────────────────────────────────────────────
# Tunnel ID
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(PLUGINS_CONFIG=PLUGIN_CFG)
class AllocateTunnelIdTest(AllocationTestMixin, TestCase):
    """Test allocate_tunnel_id."""

    @classmethod
    def setUpTestData(cls):
        """Create Tunnel ID pool."""
        super().setUpTestData()
        cls.tunnel_pool, _ = models.TunnelIdPool.objects.get_or_create(
            name="test-tunnel-pool",
            defaults={"range_start": 100, "range_end": 102},
        )

    def test_allocate_tunnel_id_happy_path(self):
        """First allocation returns 100."""
        tid = allocate_tunnel_id(self.device, self.intent, "ipsec")
        self.assertEqual(tid, 100)

    def test_allocate_tunnel_id_idempotent(self):
        """Second call for same device+intent+type returns same ID."""
        tid1 = allocate_tunnel_id(self.device, self.intent, "gre")
        tid2 = allocate_tunnel_id(self.device, self.intent, "gre")
        self.assertEqual(tid1, tid2)

    def test_allocate_tunnel_id_pool_exhausted(self):
        """ValueError when the pool is full."""
        for i in range(100, 103):
            models.TunnelIdAllocation.objects.create(
                pool=self.tunnel_pool,
                value=i,
                device=self.device,
                intent=self.intent,
                tunnel_type="ipsec",
            )
        with self.assertRaises(ValueError) as ctx:
            allocate_tunnel_id(self.device, self.intent2, "ipsec")
        self.assertIn("exhausted", str(ctx.exception))

    def test_allocate_tunnel_id_missing_pool(self):
        """ValueError when configured pool name doesn't exist."""
        with override_settings(PLUGINS_CONFIG={"intent_networking": {"tunnel_id_pool_name": "nonexistent"}}):
            with self.assertRaises(ValueError):
                allocate_tunnel_id(self.device, self.intent, "ipsec")


# ─────────────────────────────────────────────────────────────────────────────
# Managed Loopback IP
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(PLUGINS_CONFIG=PLUGIN_CFG)
class AllocateLoopbackIpTest(AllocationTestMixin, TestCase):
    """Test allocate_loopback_ip."""

    @classmethod
    def setUpTestData(cls):
        """Create Loopback pool."""
        super().setUpTestData()
        cls.lb_pool, _ = models.ManagedLoopbackPool.objects.get_or_create(
            name="test-loopback-pool",
            defaults={"prefix": "192.0.2.0/30"},  # only 2 host IPs: .1 and .2
        )

    def test_allocate_loopback_happy_path(self):
        """First allocation returns 192.0.2.1."""
        ip = allocate_loopback_ip(self.device, self.intent)
        self.assertEqual(ip, "192.0.2.1")

    def test_allocate_loopback_idempotent(self):
        """Second call for same device+intent returns same IP."""
        ip1 = allocate_loopback_ip(self.device, self.intent)
        ip2 = allocate_loopback_ip(self.device, self.intent)
        self.assertEqual(ip1, ip2)

    def test_allocate_loopback_pool_exhausted(self):
        """ValueError when the pool is full (/30 = 2 hosts)."""
        models.ManagedLoopback.objects.create(
            pool=self.lb_pool, ip_address="192.0.2.1", device=self.device, intent=self.intent
        )
        # Need a second device for the second allocation
        dt = self.device.device_type
        role = self.device.role
        dev2, _ = Device.objects.get_or_create(
            name="alloc-rtr-02",
            defaults={
                "device_type": dt,
                "role": role,
                "location": self.site,
                "status": Status.objects.get(name="Active"),
                "tenant": self.tenant,
            },
        )
        models.ManagedLoopback.objects.create(
            pool=self.lb_pool, ip_address="192.0.2.2", device=dev2, intent=self.intent
        )
        dev3, _ = Device.objects.get_or_create(
            name="alloc-rtr-03",
            defaults={
                "device_type": dt,
                "role": role,
                "location": self.site,
                "status": Status.objects.get(name="Active"),
                "tenant": self.tenant,
            },
        )
        with self.assertRaises(ValueError) as ctx:
            allocate_loopback_ip(dev3, self.intent2)
        self.assertIn("exhausted", str(ctx.exception))

    def test_allocate_loopback_missing_pool(self):
        """ValueError when configured pool name doesn't exist."""
        with override_settings(PLUGINS_CONFIG={"intent_networking": {"loopback_pool_name": "nonexistent"}}):
            with self.assertRaises(ValueError):
                allocate_loopback_ip(self.device, self.intent)


# ─────────────────────────────────────────────────────────────────────────────
# Wireless VLAN
# ─────────────────────────────────────────────────────────────────────────────


class AllocateWirelessVlanTest(AllocationTestMixin, TestCase):
    """Test allocate_wireless_vlan."""

    @classmethod
    def setUpTestData(cls):
        """Create Wireless VLAN pool."""
        super().setUpTestData()
        cls.wlan_pool, _ = models.WirelessVlanPool.objects.get_or_create(
            name="test-wlan-pool",
            defaults={"range_start": 200, "range_end": 202, "site": cls.site},
        )
        cls.global_pool, _ = models.WirelessVlanPool.objects.get_or_create(
            name="test-global-wlan-pool",
            defaults={"range_start": 500, "range_end": 502, "site": None},
        )

    def test_allocate_wireless_vlan_site_pool(self):
        """Allocation uses site-specific pool first."""
        vid = allocate_wireless_vlan(self.site, "Corp-WiFi", self.intent)
        self.assertEqual(vid, 200)

    def test_allocate_wireless_vlan_global_fallback(self):
        """Falls back to global pool when no site pool exists."""
        # Use a location that has no pool
        lt = LocationType.objects.get(name="Alloc Site Type")
        other_site, _ = Location.objects.get_or_create(
            name="NoPool Site",
            location_type=lt,
            status=Status.objects.get(name="Active"),
        )
        vid = allocate_wireless_vlan(other_site, "Guest-WiFi", self.intent)
        self.assertEqual(vid, 500)

    def test_allocate_wireless_vlan_idempotent(self):
        """Second call for same SSID+intent returns same VLAN."""
        vid1 = allocate_wireless_vlan(self.site, "Reuse-SSID", self.intent)
        vid2 = allocate_wireless_vlan(self.site, "Reuse-SSID", self.intent)
        self.assertEqual(vid1, vid2)

    def test_allocate_wireless_vlan_pool_exhausted(self):
        """ValueError when the pool is full."""
        for i in range(200, 203):
            models.WirelessVlanAllocation.objects.create(
                pool=self.wlan_pool,
                vlan_id=i,
                ssid_name=f"exhaust-{i}",
                intent=self.intent,
            )
        with self.assertRaises(ValueError) as ctx:
            allocate_wireless_vlan(self.site, "overflow-ssid", self.intent2)
        self.assertIn("exhausted", str(ctx.exception))

    def test_allocate_wireless_vlan_no_pool(self):
        """ValueError when no pool at all (no site, no global)."""
        # Delete all pools
        models.WirelessVlanPool.objects.all().delete()
        with self.assertRaises(ValueError) as ctx:
            allocate_wireless_vlan(self.site, "fail-ssid", self.intent)
        self.assertIn("No wireless VLAN pool found", str(ctx.exception))


# ─────────────────────────────────────────────────────────────────────────────
# Release Allocations
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(PLUGINS_CONFIG=PLUGIN_CFG)
class ReleaseAllocationsTest(AllocationTestMixin, TestCase):
    """Test release_allocations cleans up all allocation types."""

    @classmethod
    def setUpTestData(cls):
        """Create pools for release tests (only pool-based types)."""
        super().setUpTestData()
        cls.vni_pool, _ = models.VxlanVniPool.objects.get_or_create(
            name="release-vni-pool",
            defaults={"range_start": 10000, "range_end": 20000},
        )
        cls.tunnel_pool, _ = models.TunnelIdPool.objects.get_or_create(
            name="release-tunnel-pool",
            defaults={"range_start": 100, "range_end": 999},
        )
        cls.lb_pool, _ = models.ManagedLoopbackPool.objects.get_or_create(
            name="release-lb-pool",
            defaults={"prefix": "10.0.0.0/24"},
        )
        cls.wlan_pool, _ = models.WirelessVlanPool.objects.get_or_create(
            name="release-wlan-pool",
            defaults={"range_start": 200, "range_end": 299, "site": cls.site},
        )

    def test_release_all_allocation_types(self):
        """release_allocations deletes VRFs, RTs, VNIs, tunnels, loopbacks, wireless VLANs."""
        intent = self.intent

        # Create Nautobot-native VRF (tracked via description)
        vrf = VRF.objects.create(
            name="REL-VRF",
            rd="65000:42",
            namespace=self.namespace,
            tenant=self.tenant,
            description=f"Auto-allocated by intent {intent.intent_id}",
        )
        vrf.devices.add(self.device)

        # Create Nautobot-native Route Target (tracked via description)
        NautobotRouteTarget.objects.create(
            name="65000:142",
            description=f"Auto-allocated for intent {intent.intent_id}",
            tenant=self.tenant,
        )

        # Pool-based allocations
        models.VniAllocation.objects.create(pool=self.vni_pool, value=10042, intent=intent, vni_type="l2")
        models.TunnelIdAllocation.objects.create(
            pool=self.tunnel_pool, value=142, device=self.device, intent=intent, tunnel_type="ipsec"
        )
        models.ManagedLoopback.objects.create(
            pool=self.lb_pool, ip_address="10.0.0.42", device=self.device, intent=intent
        )
        models.WirelessVlanAllocation.objects.create(
            pool=self.wlan_pool, vlan_id=242, ssid_name="release-ssid", intent=intent
        )

        result = release_allocations(intent)

        self.assertEqual(result["vrfs_released"], 1)
        self.assertEqual(result["rts_released"], 1)
        self.assertEqual(result["vnis_released"], 1)
        self.assertEqual(result["tunnels_released"], 1)
        self.assertEqual(result["loopbacks_released"], 1)
        self.assertEqual(result["wireless_vlans_released"], 1)

        # Verify nothing left
        self.assertEqual(VRF.objects.filter(description=f"Auto-allocated by intent {intent.intent_id}").count(), 0)
        self.assertEqual(
            NautobotRouteTarget.objects.filter(description=f"Auto-allocated for intent {intent.intent_id}").count(), 0
        )
        self.assertEqual(models.VniAllocation.objects.filter(intent=intent).count(), 0)
        self.assertEqual(models.TunnelIdAllocation.objects.filter(intent=intent).count(), 0)
        self.assertEqual(models.ManagedLoopback.objects.filter(intent=intent).count(), 0)
        self.assertEqual(models.WirelessVlanAllocation.objects.filter(intent=intent).count(), 0)

    def test_release_empty_returns_zeroes(self):
        """release_allocations on an intent with nothing allocated returns all zeroes."""
        result = release_allocations(self.intent2)
        for key, val in result.items():
            self.assertEqual(val, 0, f"{key} should be 0")
