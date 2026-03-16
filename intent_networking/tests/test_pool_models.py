"""Unit tests for resource pool models and their allocation models.

Tests __str__ representations, utilisation_pct properties, Meta constraints,
and the detect_conflicts / validate_tenant_isolation model functions.

Note: RouteDistinguisherPool / RouteDistinguisher and RouteTargetPool /
RouteTarget have been removed — RD and RT allocation now uses Nautobot's
native ipam.VRF, ipam.RouteTarget and ipam.Namespace models.
"""

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import Role, Status
from nautobot.tenancy.models import Tenant

from intent_networking.models import (
    DeploymentStage,
    Intent,
    IntentAuditEntry,
    IntentTypeChoices,
    ManagedLoopback,
    ManagedLoopbackPool,
    ResolutionPlan,
    TunnelIdAllocation,
    TunnelIdPool,
    VerificationResult,
    VniAllocation,
    VxlanVniPool,
    WirelessVlanAllocation,
    WirelessVlanPool,
    detect_conflicts,
    validate_tenant_isolation,
)


class PoolModelTestMixin:
    """Shared setUp creating device, tenant and status objects."""

    @classmethod
    def setUpTestData(cls):
        """Create shared test data."""
        super().setUpTestData()
        intent_ct = ContentType.objects.get_for_model(Intent)
        device_ct = ContentType.objects.get_for_model(Device)
        location_ct = ContentType.objects.get_for_model(Location)
        for sname in (
            "Draft",
            "Active",
            "Validated",
            "Deploying",
            "Deployed",
            "Failed",
            "Rolled Back",
            "Deprecated",
            "Retired",
        ):
            st, _ = Status.objects.get_or_create(name=sname)
            st.content_types.add(intent_ct, device_ct, location_ct)

        cls.tenant, _ = Tenant.objects.get_or_create(name="Pool Test Tenant")
        mfr, _ = Manufacturer.objects.get_or_create(name="Pool Mfr")
        dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model="Pool Model")
        role, _ = Role.objects.get_or_create(name="Pool Role")
        role.content_types.add(device_ct)
        lt, _ = LocationType.objects.get_or_create(name="Pool Site Type")
        lt.content_types.add(device_ct)
        site, _ = Location.objects.get_or_create(
            name="Pool Site",
            location_type=lt,
            status=Status.objects.get(name="Active"),
        )
        cls.site = site
        cls.device, _ = Device.objects.get_or_create(
            name="pool-rtr-01",
            defaults={
                "device_type": dt,
                "role": role,
                "location": site,
                "status": Status.objects.get(name="Active"),
                "tenant": cls.tenant,
            },
        )
        cls.intent, _ = Intent.objects.get_or_create(
            intent_id="pool-test-001",
            defaults={
                "version": 1,
                "intent_type": IntentTypeChoices.CONNECTIVITY,
                "tenant": cls.tenant,
                "status": Status.objects.get(name="Draft"),
                "intent_data": {"type": "connectivity", "name": "pool-test-001", "source": "Gi0/1"},
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# VxlanVniPool / VniAllocation
# ─────────────────────────────────────────────────────────────────────────────


class VxlanVniPoolModelTest(PoolModelTestMixin, TestCase):
    """Test VxlanVniPool and VniAllocation models."""

    @classmethod
    def setUpTestData(cls):
        """Create VNI pool."""
        super().setUpTestData()
        cls.vni_pool = VxlanVniPool.objects.create(name="model-vni-pool", range_start=10000, range_end=10009)

    def test_pool_str(self):
        """__str__ includes name and range."""
        s = str(self.vni_pool)
        self.assertIn("model-vni-pool", s)
        self.assertIn("10000", s)

    def test_utilisation_pct_empty(self):
        """Utilisation is 0% when empty."""
        self.assertEqual(self.vni_pool.utilisation_pct, 0)

    def test_vni_allocation_str(self):
        """VniAllocation __str__ includes VNI value and type."""
        alloc = VniAllocation.objects.create(pool=self.vni_pool, value=10042, intent=self.intent, vni_type="l2")
        s = str(alloc)
        self.assertIn("10042", s)
        self.assertIn("l2", s)


# ─────────────────────────────────────────────────────────────────────────────
# TunnelIdPool / TunnelIdAllocation
# ─────────────────────────────────────────────────────────────────────────────


class TunnelIdPoolModelTest(PoolModelTestMixin, TestCase):
    """Test TunnelIdPool and TunnelIdAllocation models."""

    @classmethod
    def setUpTestData(cls):
        """Create Tunnel pool."""
        super().setUpTestData()
        cls.tunnel_pool = TunnelIdPool.objects.create(name="model-tunnel-pool", range_start=100, range_end=199)

    def test_pool_str(self):
        """__str__ includes name and range."""
        s = str(self.tunnel_pool)
        self.assertIn("model-tunnel-pool", s)
        self.assertIn("100", s)

    def test_utilisation_pct_empty(self):
        """0% when empty."""
        self.assertEqual(self.tunnel_pool.utilisation_pct, 0)

    def test_allocation_str(self):
        """TunnelIdAllocation __str__ includes tunnel ID and device."""
        alloc = TunnelIdAllocation.objects.create(
            pool=self.tunnel_pool, value=100, device=self.device, intent=self.intent, tunnel_type="ipsec"
        )
        s = str(alloc)
        self.assertIn("100", s)
        self.assertIn("ipsec", s)
        self.assertIn("pool-rtr-01", s)


# ─────────────────────────────────────────────────────────────────────────────
# ManagedLoopbackPool / ManagedLoopback
# ─────────────────────────────────────────────────────────────────────────────


class ManagedLoopbackPoolModelTest(PoolModelTestMixin, TestCase):
    """Test ManagedLoopbackPool and ManagedLoopback models."""

    @classmethod
    def setUpTestData(cls):
        """Create Loopback pool."""
        super().setUpTestData()
        cls.lb_pool = ManagedLoopbackPool.objects.create(name="model-lb-pool", prefix="10.0.0.0/24")

    def test_pool_str(self):
        """__str__ includes name and prefix."""
        s = str(self.lb_pool)
        self.assertIn("model-lb-pool", s)
        self.assertIn("10.0.0.0/24", s)

    def test_utilisation_pct_empty(self):
        """0% when empty."""
        self.assertEqual(self.lb_pool.utilisation_pct, 0)

    def test_utilisation_pct_with_allocation(self):
        """Utilisation reflects allocation count (/24 has 254 hosts)."""
        ManagedLoopback.objects.create(pool=self.lb_pool, ip_address="10.0.0.1", device=self.device, intent=self.intent)
        # 1 / 254 ≈ 0% (rounds down)
        self.assertLessEqual(self.lb_pool.utilisation_pct, 1)

    def test_allocation_str(self):
        """ManagedLoopback __str__ includes IP and device."""
        alloc = ManagedLoopback.objects.create(
            pool=self.lb_pool, ip_address="10.0.0.42", device=self.device, intent=self.intent
        )
        s = str(alloc)
        self.assertIn("10.0.0.42", s)
        self.assertIn("pool-rtr-01", s)


# ─────────────────────────────────────────────────────────────────────────────
# WirelessVlanPool / WirelessVlanAllocation
# ─────────────────────────────────────────────────────────────────────────────


class WirelessVlanPoolModelTest(PoolModelTestMixin, TestCase):
    """Test WirelessVlanPool and WirelessVlanAllocation models."""

    @classmethod
    def setUpTestData(cls):
        """Create Wireless VLAN pool."""
        super().setUpTestData()
        cls.wlan_pool = WirelessVlanPool.objects.create(
            name="model-wlan-pool", range_start=200, range_end=209, site=cls.site
        )

    def test_pool_str(self):
        """__str__ includes name and VLAN range."""
        s = str(self.wlan_pool)
        self.assertIn("model-wlan-pool", s)
        self.assertIn("200", s)

    def test_utilisation_pct_empty(self):
        """0% when empty."""
        self.assertEqual(self.wlan_pool.utilisation_pct, 0)

    def test_allocation_str(self):
        """WirelessVlanAllocation __str__ includes VLAN ID and SSID."""
        alloc = WirelessVlanAllocation.objects.create(
            pool=self.wlan_pool, vlan_id=201, ssid_name="Corp-WiFi", intent=self.intent
        )
        s = str(alloc)
        self.assertIn("201", s)
        self.assertIn("Corp-WiFi", s)


# ─────────────────────────────────────────────────────────────────────────────
# Intent model — status transitions & properties
# ─────────────────────────────────────────────────────────────────────────────


class IntentStatusTransitionTest(PoolModelTestMixin, TestCase):
    """Test Intent.clean() status transition validation."""

    def _create_intent(self, status_name):
        """Helper to create a fresh intent with given status."""
        return Intent.objects.create(
            intent_id=f"transition-{status_name}-{id(self)}",
            version=1,
            intent_type=IntentTypeChoices.SECURITY,
            tenant=self.tenant,
            status=Status.objects.get(name=status_name),
            intent_data={"type": "security", "name": f"transition-{status_name}"},
        )

    def test_draft_to_validated_allowed(self):
        """Draft → Validated is a valid transition."""
        intent = self._create_intent("Draft")
        intent.status = Status.objects.get(name="Validated")
        intent.full_clean()  # Should not raise

    def test_draft_to_deployed_not_allowed(self):
        """Draft → Deployed should raise ValidationError."""
        intent = self._create_intent("Draft")
        intent.status = Status.objects.get(name="Deployed")
        with self.assertRaises(ValidationError):
            intent.full_clean()

    def test_deployed_to_deprecated_allowed(self):
        """Deployed → Deprecated is allowed."""
        intent = self._create_intent("Deployed")
        intent.status = Status.objects.get(name="Deprecated")
        intent.full_clean()

    def test_deprecated_is_terminal(self):
        """Deprecated → anything else should raise ValidationError."""
        intent = self._create_intent("Deprecated")
        intent.status = Status.objects.get(name="Draft")
        with self.assertRaises(ValidationError):
            intent.full_clean()

    def test_deployed_to_retired_allowed(self):
        """Deployed → Retired is allowed."""
        intent = self._create_intent("Deployed")
        intent.status = Status.objects.get(name="Retired")
        intent.full_clean()

    def test_retired_to_draft_allowed(self):
        """Retired → Draft is the only allowed transition out of Retired."""
        intent = self._create_intent("Retired")
        intent.status = Status.objects.get(name="Draft")
        intent.full_clean()

    def test_retired_to_deployed_not_allowed(self):
        """Retired → Deployed should raise ValidationError."""
        intent = self._create_intent("Retired")
        intent.status = Status.objects.get(name="Deployed")
        with self.assertRaises(ValidationError):
            intent.full_clean()

    def test_retired_to_validated_not_allowed(self):
        """Retired → Validated should raise ValidationError."""
        intent = self._create_intent("Retired")
        intent.status = Status.objects.get(name="Validated")
        with self.assertRaises(ValidationError):
            intent.full_clean()


class IntentPropertiesTest(PoolModelTestMixin, TestCase):
    """Test Intent model computed properties."""

    def test_is_deployed_true(self):
        """is_deployed returns True when status is 'Deployed'."""
        intent = Intent.objects.create(
            intent_id="prop-deployed",
            version=1,
            intent_type=IntentTypeChoices.CONNECTIVITY,
            tenant=self.tenant,
            status=Status.objects.get(name="Deployed"),
            intent_data={"type": "connectivity", "source": "Gi0/1"},
        )
        self.assertTrue(intent.is_deployed)

    def test_is_deployed_false(self):
        """is_deployed returns False when status is not 'Deployed'."""
        self.assertFalse(self.intent.is_deployed)

    def test_is_retired_true(self):
        """is_retired returns True when status is 'Retired'."""
        intent = Intent.objects.create(
            intent_id="prop-retired",
            version=1,
            intent_type=IntentTypeChoices.CONNECTIVITY,
            tenant=self.tenant,
            status=Status.objects.get(name="Retired"),
            intent_data={"type": "connectivity", "source": "Gi0/1"},
        )
        self.assertTrue(intent.is_retired)

    def test_is_retired_false(self):
        """is_retired returns False when status is not 'Retired'."""
        self.assertFalse(self.intent.is_retired)

    def test_str_representation(self):
        """Intent __str__ includes intent_id and version."""
        s = str(self.intent)
        self.assertIn("pool-test-001", s)
        self.assertIn("v1", s)


# ─────────────────────────────────────────────────────────────────────────────
# VerificationResult model
# ─────────────────────────────────────────────────────────────────────────────


class VerificationResultModelTest(PoolModelTestMixin, TestCase):
    """Test VerificationResult model."""

    def test_bgp_health_pct_all_established(self):
        """100% when all BGP sessions are established."""
        vr = VerificationResult.objects.create(
            intent=self.intent,
            passed=True,
            bgp_sessions_expected=4,
            bgp_sessions_established=4,
        )
        self.assertEqual(vr.bgp_health_pct, 100)

    def test_bgp_health_pct_partial(self):
        """50% when half are established."""
        vr = VerificationResult.objects.create(
            intent=self.intent,
            passed=False,
            bgp_sessions_expected=4,
            bgp_sessions_established=2,
        )
        self.assertEqual(vr.bgp_health_pct, 50)

    def test_bgp_health_pct_zero_expected(self):
        """100% when no BGP sessions expected."""
        vr = VerificationResult.objects.create(
            intent=self.intent,
            passed=True,
            bgp_sessions_expected=0,
            bgp_sessions_established=0,
        )
        self.assertEqual(vr.bgp_health_pct, 100)

    def test_str_pass(self):
        """__str__ shows PASS for passed=True."""
        vr = VerificationResult.objects.create(intent=self.intent, passed=True)
        self.assertIn("PASS", str(vr))

    def test_str_fail(self):
        """__str__ shows FAIL for passed=False."""
        vr = VerificationResult.objects.create(intent=self.intent, passed=False)
        self.assertIn("FAIL", str(vr))


# ─────────────────────────────────────────────────────────────────────────────
# detect_conflicts
# ─────────────────────────────────────────────────────────────────────────────


class DetectConflictsTest(PoolModelTestMixin, TestCase):
    """Test detect_conflicts() function."""

    def test_no_conflicts_when_no_prefixes(self):
        """No prefixes → empty conflict list."""
        # Ensure intent_data has dict-type source/destination (not a plain string)
        intent = Intent.objects.create(
            intent_id="no-prefix-intent",
            version=1,
            intent_type=IntentTypeChoices.SECURITY,
            tenant=self.tenant,
            status=Status.objects.get(name="Draft"),
            intent_data={"type": "security"},
        )
        conflicts = detect_conflicts(intent)
        self.assertEqual(conflicts, [])

    def test_prefix_overlap_detected(self):
        """Overlapping prefixes between two intents are detected."""
        intent1 = Intent.objects.create(
            intent_id="conflict-a",
            version=1,
            intent_type=IntentTypeChoices.CONNECTIVITY,
            tenant=self.tenant,
            status=Status.objects.get(name="Validated"),
            intent_data={
                "type": "connectivity",
                "source": {"prefixes": ["10.0.0.0/24", "172.16.0.0/16"]},
            },
        )
        Intent.objects.create(
            intent_id="conflict-b",
            version=1,
            intent_type=IntentTypeChoices.CONNECTIVITY,
            tenant=self.tenant,
            status=Status.objects.get(name="Validated"),
            intent_data={
                "type": "connectivity",
                "source": {"prefixes": ["10.0.0.0/24"]},
            },
        )
        conflicts = detect_conflicts(intent1)
        self.assertGreater(len(conflicts), 0)
        self.assertEqual(conflicts[0]["type"], "prefix_overlap")


# ─────────────────────────────────────────────────────────────────────────────
# validate_tenant_isolation
# ─────────────────────────────────────────────────────────────────────────────


class ValidateTenantIsolationTest(PoolModelTestMixin, TestCase):
    """Test validate_tenant_isolation() function."""

    def test_no_warnings_when_no_plan(self):
        """No plan → empty warning list."""
        warnings = validate_tenant_isolation(self.intent)
        self.assertEqual(warnings, [])

    def test_no_warnings_when_same_tenant(self):
        """Devices belonging to same tenant produce no warnings."""
        plan = ResolutionPlan.objects.create(
            intent=self.intent,
            intent_version=self.intent.version,
            primitives=[],
        )
        plan.affected_devices.add(self.device)
        warnings = validate_tenant_isolation(self.intent)
        self.assertEqual(warnings, [])

    def test_warning_for_different_tenant(self):
        """Device from different tenant produces a warning."""
        other_tenant, _ = Tenant.objects.get_or_create(name="Other Tenant")
        dt = self.device.device_type
        role = self.device.role
        other_device = Device.objects.create(
            name="other-tenant-rtr",
            device_type=dt,
            role=role,
            location=self.site,
            status=Status.objects.get(name="Active"),
            tenant=other_tenant,
        )
        plan = ResolutionPlan.objects.create(
            intent=self.intent,
            intent_version=self.intent.version,
            primitives=[],
        )
        plan.affected_devices.add(other_device)
        warnings = validate_tenant_isolation(self.intent)
        self.assertGreater(len(warnings), 0)
        self.assertIn("Other Tenant", warnings[0])


# ─────────────────────────────────────────────────────────────────────────────
# ResolutionPlan model
# ─────────────────────────────────────────────────────────────────────────────


class ResolutionPlanModelTest(PoolModelTestMixin, TestCase):
    """Test ResolutionPlan model properties."""

    def test_str(self):
        """__str__ includes intent_id and version."""
        plan = ResolutionPlan.objects.create(intent=self.intent, intent_version=1, primitives=[{"p": 1}, {"p": 2}])
        s = str(plan)
        self.assertIn("pool-test-001", s)
        self.assertIn("v1", s)

    def test_primitive_count(self):
        """primitive_count returns length of primitives list."""
        plan = ResolutionPlan.objects.create(
            intent=self.intent, intent_version=1, primitives=[{"a": 1}, {"b": 2}, {"c": 3}]
        )
        self.assertEqual(plan.primitive_count, 3)

    def test_affected_device_names(self):
        """affected_device_names returns sorted list of device names."""
        plan = ResolutionPlan.objects.create(intent=self.intent, intent_version=1, primitives=[])
        plan.affected_devices.add(self.device)
        self.assertEqual(plan.affected_device_names, ["pool-rtr-01"])


# ─────────────────────────────────────────────────────────────────────────────
# IntentAuditEntry model
# ─────────────────────────────────────────────────────────────────────────────


class IntentAuditEntryModelTest(PoolModelTestMixin, TestCase):
    """Test IntentAuditEntry model."""

    def test_str(self):
        """__str__ includes intent_id and action."""
        entry = IntentAuditEntry.objects.create(intent=self.intent, action="created", actor="test-user")
        s = str(entry)
        self.assertIn("pool-test-001", s)
        self.assertIn("created", s)
        self.assertIn("test-user", s)


# ─────────────────────────────────────────────────────────────────────────────
# DeploymentStage model
# ─────────────────────────────────────────────────────────────────────────────


class DeploymentStageModelTest(PoolModelTestMixin, TestCase):
    """Test DeploymentStage model."""

    def test_str_with_location(self):
        """__str__ includes intent_id, stage order and location."""
        stage = DeploymentStage.objects.create(intent=self.intent, stage_order=0, location=self.site, status="pending")
        s = str(stage)
        self.assertIn("pool-test-001", s)
        self.assertIn("stage 0", s)
        self.assertIn("Pool Site", s)

    def test_str_without_location(self):
        """__str__ shows 'unassigned' when location is None."""
        stage = DeploymentStage.objects.create(intent=self.intent, stage_order=1, status="pending")
        s = str(stage)
        self.assertIn("unassigned", s)
