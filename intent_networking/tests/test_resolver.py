"""Unit tests for intent_networking.resolver module.

Tests the resolve_intent dispatcher, RESOLVERS completeness, helper functions,
and selected resolver functions with mocked Nautobot data.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from intent_networking.models import IntentTypeChoices
from intent_networking.resolver import (
    RESOLVERS,
    _empty_plan,
    _get_scope_devices,
    generate_vrf_name,
    resolve_intent,
)

# ─────────────────────────────────────────────────────────────────────────────
# RESOLVERS dict completeness
# ─────────────────────────────────────────────────────────────────────────────


class ResolverRegistryTest(SimpleTestCase):
    """Verify RESOLVERS dict has an entry for every IntentTypeChoices value."""

    def test_all_intent_types_have_resolvers(self):
        """Every IntentTypeChoices value must have a resolver function."""
        missing = []
        for choice_value, _label in IntentTypeChoices.choices:
            if choice_value not in RESOLVERS:
                missing.append(choice_value)
        self.assertEqual(
            missing,
            [],
            f"Missing resolver(s) for intent types: {missing}",
        )

    def test_no_extra_resolvers(self):
        """RESOLVERS should not contain keys outside IntentTypeChoices."""
        valid_types = {v for v, _l in IntentTypeChoices.choices}
        extra = set(RESOLVERS.keys()) - valid_types
        self.assertEqual(
            extra,
            set(),
            f"RESOLVERS has entries not in IntentTypeChoices: {extra}",
        )

    def test_all_resolver_values_are_callable(self):
        """Every resolver value must be a callable."""
        for key, fn in RESOLVERS.items():
            self.assertTrue(callable(fn), f"RESOLVERS['{key}'] is not callable: {fn}")

    def test_resolver_count_matches_choices(self):
        """Number of resolvers matches number of intent type choices."""
        self.assertEqual(len(RESOLVERS), len(IntentTypeChoices.choices))


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────


class EmptyPlanTest(SimpleTestCase):
    """Test the _empty_plan helper."""

    def test_returns_expected_keys(self):
        """_empty_plan returns dict with all required plan keys."""
        plan = _empty_plan(["dev1"], [{"primitive_type": "acl"}])
        self.assertIn("affected_devices", plan)
        self.assertIn("vrf_name", plan)
        self.assertIn("requires_new_vrf", plan)
        self.assertIn("requires_mpls", plan)
        self.assertIn("primitives", plan)
        self.assertIn("allocated_rds", plan)
        self.assertIn("allocated_rts", plan)

    def test_default_values(self):
        """_empty_plan defaults: no VRF, no MPLS, empty allocations."""
        plan = _empty_plan([], [])
        self.assertEqual(plan["vrf_name"], "")
        self.assertFalse(plan["requires_new_vrf"])
        self.assertFalse(plan["requires_mpls"])
        self.assertEqual(plan["allocated_rds"], {})
        self.assertEqual(plan["allocated_rts"], {})


class GenerateVrfNameTest(SimpleTestCase):
    """Test generate_vrf_name helper."""

    def test_with_pci_compliance(self):
        """PCI-DSS compliance maps to -PCI suffix."""
        intent = MagicMock()
        intent.tenant.name = "ACME Corp"
        intent.intent_data = {"policy": {"compliance": "PCI-DSS"}}
        intent.intent_id = "test-intent-001"
        self.assertEqual(generate_vrf_name(intent), "ACMECORP-PCI")

    def test_with_hipaa_compliance(self):
        """HIPAA compliance maps to -HIPAA suffix."""
        intent = MagicMock()
        intent.tenant.name = "HealthCo"
        intent.intent_data = {"policy": {"compliance": "HIPAA"}}
        intent.intent_id = "test-intent-002"
        self.assertEqual(generate_vrf_name(intent), "HEALTHCO-HIPAA")

    def test_with_soc2_compliance(self):
        """SOC2 compliance maps to -SOC2 suffix."""
        intent = MagicMock()
        intent.tenant.name = "CloudCo"
        intent.intent_data = {"policy": {"compliance": "SOC2"}}
        intent.intent_id = "test-intent-003"
        self.assertEqual(generate_vrf_name(intent), "CLOUDCO-SOC2")

    def test_with_iso27001_compliance(self):
        """ISO27001 compliance maps to -ISO27K suffix."""
        intent = MagicMock()
        intent.tenant.name = "SecureCo"
        intent.intent_data = {"policy": {"compliance": "ISO27001"}}
        intent.intent_id = "test-intent-004"
        self.assertEqual(generate_vrf_name(intent), "SECURECO-ISO27K")

    def test_without_compliance(self):
        """Without compliance, falls back to intent_id suffix."""
        intent = MagicMock()
        intent.tenant.name = "WidgetCo"
        intent.intent_data = {"policy": {"compliance": "none"}}
        intent.intent_id = "fin-pci-connectivity-001"
        self.assertEqual(generate_vrf_name(intent), "WIDGETCO-001")

    def test_no_policy_at_all(self):
        """When no 'policy' key in intent_data, falls back to intent_id suffix."""
        intent = MagicMock()
        intent.tenant.name = "NoPol"
        intent.intent_data = {}
        intent.intent_id = "abc-def-ghi"
        result = generate_vrf_name(intent)
        self.assertTrue(result.startswith("NOPOL-"))

    def test_tenant_name_truncated(self):
        """Tenant name is truncated to 8 chars."""
        intent = MagicMock()
        intent.tenant.name = "A Very Long Tenant Name"
        intent.intent_data = {"policy": {"compliance": "PCI-DSS"}}
        intent.intent_id = "test-001"
        result = generate_vrf_name(intent)
        # "A Very Long Tenant Name" → "AVERYLO" (after stripping spaces, up to 8 chars)
        self.assertTrue(result.startswith("AVERYLON"))


# ─────────────────────────────────────────────────────────────────────────────
# resolve_intent dispatcher
# ─────────────────────────────────────────────────────────────────────────────


class ResolveIntentDispatchTest(SimpleTestCase):
    """Test the resolve_intent() dispatch function."""

    def test_unknown_type_raises_value_error(self):
        """Calling resolve_intent with an unknown type raises ValueError."""
        intent = MagicMock()
        intent.intent_type = "completely_unknown_type"
        intent.intent_id = "bad-001"
        with self.assertRaises(ValueError) as ctx:
            resolve_intent(intent)
        self.assertIn("No resolver implemented", str(ctx.exception))
        self.assertIn("completely_unknown_type", str(ctx.exception))

    @patch(
        "intent_networking.resolver.RESOLVERS",
        {"connectivity": MagicMock(return_value={"affected_devices": ["d1"], "primitives": [{"p": 1}]})},
    )
    def test_dispatches_to_correct_resolver(self):
        """resolve_intent calls the correct resolver function."""
        intent = MagicMock()
        intent.intent_type = "connectivity"
        intent.intent_id = "test-001"
        intent.tenant.name = "TestTenant"
        result = resolve_intent(intent)
        self.assertEqual(result["affected_devices"], ["d1"])


# ─────────────────────────────────────────────────────────────────────────────
# _get_scope_devices (requires DB)
# ─────────────────────────────────────────────────────────────────────────────


class GetScopeDevicesTest(TestCase):
    """Test _get_scope_devices helper with database objects."""

    @classmethod
    def setUpTestData(cls):
        """Create test devices."""
        from django.contrib.contenttypes.models import ContentType
        from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
        from nautobot.extras.models import Role, Status, Tag
        from nautobot.tenancy.models import Tenant

        from intent_networking.models import Intent

        # Statuses
        device_ct = ContentType.objects.get_for_model(Device)
        location_ct = ContentType.objects.get_for_model(Location)
        intent_ct = ContentType.objects.get_for_model(Intent)
        for sname in ("Active", "Draft", "Maintenance"):
            st, _ = Status.objects.get_or_create(name=sname)
            st.content_types.add(device_ct, location_ct, intent_ct)

        cls.tenant, _ = Tenant.objects.get_or_create(name="Scope Tenant")
        mfr, _ = Manufacturer.objects.get_or_create(name="ScopeTest Mfr")
        dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model="Scope Model")
        role, _ = Role.objects.get_or_create(name="Scope Role")
        role.content_types.add(device_ct)
        lt, _ = LocationType.objects.get_or_create(name="Scope Site Type")
        lt.content_types.add(device_ct)
        site, _ = Location.objects.get_or_create(
            name="Scope-Site-HQ",
            location_type=lt,
            status=Status.objects.get(name="Active"),
        )
        cls.site = site
        tag, _ = Tag.objects.get_or_create(name="service-group-web")
        tag.content_types.add(device_ct)

        cls.device = Device.objects.create(
            name="scope-rtr-01",
            device_type=dt,
            role=role,
            location=site,
            status=Status.objects.get(name="Active"),
            tenant=cls.tenant,
        )
        cls.device.tags.add(tag)

        # Maintenance device — should be excluded
        maint_dev = Device.objects.create(
            name="scope-rtr-maint",
            device_type=dt,
            role=role,
            location=site,
            status=Status.objects.get(name="Maintenance"),
            tenant=cls.tenant,
        )
        maint_dev.tags.add(tag)

        cls.intent = Intent.objects.create(
            intent_id="scope-test-001",
            version=1,
            intent_type="connectivity",
            tenant=cls.tenant,
            status=Status.objects.get(name="Draft"),
            intent_data={
                "type": "connectivity",
                "source": "Gi0/1",
                "scope": {
                    "sites": ["Scope-Site-HQ"],
                    "group": "web",
                },
            },
        )

    def test_get_scope_devices_returns_active_only(self):
        """_get_scope_devices returns active devices, excludes maintenance."""
        devices = _get_scope_devices(self.intent, scope_key="scope")
        device_names = [d.name for d in devices]
        self.assertIn("scope-rtr-01", device_names)
        self.assertNotIn("scope-rtr-maint", device_names)

    def test_get_scope_devices_no_match_raises(self):
        """ValueError when no devices match the scope."""
        intent = MagicMock()
        intent.intent_id = "fail-scope"
        intent.tenant = self.tenant
        intent.intent_data = {
            "scope": {"sites": ["Nonexistent-Site"], "group": "nonexistent"},
        }
        with self.assertRaises(ValueError) as ctx:
            _get_scope_devices(intent, scope_key="scope")
        self.assertIn("No active devices found", str(ctx.exception))
