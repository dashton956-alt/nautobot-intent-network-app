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

    def _mock_intent(self, scope):
        """Build a lightweight intent stub with the given scope block."""
        intent = MagicMock()
        intent.intent_id = "scope-contract"
        intent.tenant = self.tenant
        intent.intent_data = {"scope": scope}
        return intent

    def test_scope_by_roles(self):
        """Scope by 'roles' resolves devices with that Nautobot role."""
        devices = _get_scope_devices(self._mock_intent({"roles": ["Scope Role"]}))
        self.assertIn("scope-rtr-01", [d.name for d in devices])

    def test_scope_by_singular_role(self):
        """Singular 'role' string is accepted."""
        devices = _get_scope_devices(self._mock_intent({"role": "Scope Role"}))
        self.assertIn("scope-rtr-01", [d.name for d in devices])

    def test_scope_by_roles_wrong_role_raises(self):
        """A role with no matching active devices raises."""
        with self.assertRaises(ValueError):
            _get_scope_devices(self._mock_intent({"roles": ["No Such Role"]}))

    def test_scope_all_tenant_devices(self):
        """all_tenant_devices targets every active tenant device."""
        devices = _get_scope_devices(self._mock_intent({"all_tenant_devices": True}))
        names = [d.name for d in devices]
        self.assertIn("scope-rtr-01", names)
        self.assertNotIn("scope-rtr-maint", names)  # maintenance still excluded

    def test_scope_singular_site_and_device(self):
        """Singular 'site' and 'device' forms are accepted."""
        by_site = _get_scope_devices(self._mock_intent({"site": "Scope-Site-HQ"}))
        self.assertIn("scope-rtr-01", [d.name for d in by_site])
        by_device = _get_scope_devices(self._mock_intent({"device": "scope-rtr-01"}))
        self.assertEqual(["scope-rtr-01"], [d.name for d in by_device])

    def test_scope_empty_raises(self):
        """An empty/unrecognised scope fails loudly instead of selecting all."""
        with self.assertRaises(ValueError) as ctx:
            _get_scope_devices(self._mock_intent({}))
        self.assertIn("empty or", str(ctx.exception))

    def test_scope_sites_and_roles_intersection(self):
        """sites + roles resolves the intersection."""
        devices = _get_scope_devices(self._mock_intent({"sites": ["Scope-Site-HQ"], "roles": ["Scope Role"]}))
        self.assertIn("scope-rtr-01", [d.name for d in devices])

    def test_fabric_spines_leaves_fallback(self):
        """Fabric intents with no scope resolve devices from fabric.spines/leaves."""
        intent = MagicMock()
        intent.intent_id = "fabric-scope"
        intent.tenant = self.tenant
        intent.intent_data = {"fabric": {"spines": [], "leaves": ["scope-rtr-01"]}}
        devices = _get_scope_devices(intent)
        self.assertEqual(["scope-rtr-01"], [d.name for d in devices])


# ─────────────────────────────────────────────────────────────────────────────
# Nested-block field mapping (schema in network_as_code_example)
# ─────────────────────────────────────────────────────────────────────────────


class NestedBlockResolverTest(TestCase):
    """Resolvers must read the typed blocks (dc.*, routing.*, …) used by the
    network_as_code_example intents, not only the legacy flat fields."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.contenttypes.models import ContentType
        from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
        from nautobot.extras.models import Role, Status
        from nautobot.tenancy.models import Tenant

        from intent_networking.models import Intent

        device_ct = ContentType.objects.get_for_model(Device)
        location_ct = ContentType.objects.get_for_model(Location)
        intent_ct = ContentType.objects.get_for_model(Intent)
        for sname in ("Active", "Draft", "Maintenance"):
            st, _ = Status.objects.get_or_create(name=sname)
            st.content_types.add(device_ct, location_ct, intent_ct)

        cls.tenant, _ = Tenant.objects.get_or_create(name="Nested Tenant")
        mfr, _ = Manufacturer.objects.get_or_create(name="Nested Mfr")
        dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model="Nested Model")
        role, _ = Role.objects.get_or_create(name="leaf-switch")
        role.content_types.add(device_ct)
        lt, _ = LocationType.objects.get_or_create(name="Nested Site Type")
        lt.content_types.add(device_ct)
        site, _ = Location.objects.get_or_create(
            name="dc-east",
            location_type=lt,
            status=Status.objects.get(name="Active"),
        )
        cls.device = Device.objects.create(
            name="dc-east-leaf-01",
            device_type=dt,
            role=role,
            location=site,
            status=Status.objects.get(name="Active"),
            tenant=cls.tenant,
        )

    def _intent(self, intent_data):
        intent = MagicMock()
        intent.intent_id = "nested-test"
        intent.tenant = self.tenant
        intent.intent_data = {"scope": {"devices": ["dc-east-leaf-01"]}, **intent_data}
        return intent

    def test_bgp_evpn_af_reads_routing_block(self):
        from intent_networking.resolver import resolve_bgp_evpn_af

        intent = self._intent(
            {
                "routing": {
                    "as_number": 65001,
                    "router_id": "10.255.0.1",
                    "address_families": {"l2vpn_evpn": {"neighbors": [{"ip": "10.255.0.100", "remote_as": 65001}]}},
                }
            }
        )
        prim = resolve_bgp_evpn_af(intent)["primitives"][0]
        self.assertEqual(prim["local_asn"], 65001)
        self.assertEqual(prim["router_id"], "10.255.0.1")
        self.assertEqual(prim["neighbors"][0]["ip"], "10.255.0.100")

    def test_anycast_gateway_reads_dc_block_and_loops_svls(self):
        from intent_networking.resolver import resolve_anycast_gateway

        intent = self._intent(
            {
                "dc": {
                    "anycast_gateway": {
                        "mac": "00:00:00:00:00:01",
                        "svls": [
                            {"vlan": 100, "ip": "10.100.0.1/24", "vni": 10100},
                            {"vlan": 200, "ip": "10.200.0.1/24", "vni": 10200},
                        ],
                    }
                }
            }
        )
        prims = resolve_anycast_gateway(intent)["primitives"]
        self.assertEqual(len(prims), 2)  # one per SVI
        self.assertEqual(prims[0]["vlan_id"], 100)
        self.assertEqual(prims[0]["virtual_ip"], "10.100.0.1/24")
        self.assertEqual(prims[0]["anycast_mac"], "00:00:00:00:00:01")
        self.assertEqual(prims[1]["vni"], 10200)

    def test_vtep_reads_dc_block(self):
        from intent_networking.resolver import resolve_vtep

        intent = self._intent(
            {
                "dc": {
                    "vtep": {
                        "source_interface": "Loopback1",
                        "vni_map": [{"vlan": 100, "vni": 10100}],
                        "ingress_replication": {"enabled": True},
                    }
                }
            }
        )
        prim = resolve_vtep(intent)["primitives"][0]
        self.assertEqual(prim["source_interface"], "Loopback1")
        self.assertEqual(prim["vni_map"], [{"vlan": 100, "vni": 10100}])
        self.assertEqual(prim["replication_mode"], "ingress-replication")

    def test_mgmt_netflow_reads_structured_fields(self):
        from intent_networking.resolver import resolve_mgmt_netflow

        intent = self._intent(
            {
                "collectors": [{"ip": "10.1.2.10", "port": 2055}],
                "sampling": {"mode": "deterministic", "rate": 1000},
                "flow_cache": {"max_entries": 16000},
                "interfaces": [{"name": "GigabitEthernet0/0", "direction": "input"}],
            }
        )
        prim = resolve_mgmt_netflow(intent)["primitives"][0]
        self.assertEqual(prim["collector_ip"], "10.1.2.10")
        self.assertEqual(prim["collector_port"], 2055)
        self.assertEqual(prim["sampler_rate"], 1000)
        self.assertEqual(prim["flow_cache"], {"max_entries": 16000})
        self.assertEqual(len(prim["apply_interfaces"]), 1)

    def test_eigrp_reads_routing_block(self):
        from intent_networking.resolver import resolve_eigrp

        intent = self._intent({"routing": {"as_number": 100, "networks": ["10.0.0.0/8"], "router_id": "10.255.0.1"}})
        prim = resolve_eigrp(intent)["primitives"][0]
        self.assertEqual(prim["as_number"], 100)
        self.assertEqual(prim["networks"], ["10.0.0.0/8"])
        self.assertEqual(prim["router_id"], "10.255.0.1")

    def test_ospfv3_reads_routing_block_areas(self):
        from intent_networking.resolver import resolve_ospfv3

        intent = self._intent(
            {
                "routing": {
                    "process_id": 1,
                    "router_id": "10.255.0.1",
                    "areas": [{"area_id": "0.0.0.0", "type": "backbone"}],
                    "interfaces": [{"name": "GigabitEthernet0/0", "area": "0.0.0.0"}],
                }
            }
        )
        prim = resolve_ospfv3(intent)["primitives"][0]
        self.assertEqual(prim["router_id"], "10.255.0.1")
        self.assertEqual(prim["area"], "0.0.0.0")
        self.assertEqual(len(prim["interfaces"]), 1)

    def test_bgp_ipv6_af_reads_routing_block(self):
        from intent_networking.resolver import resolve_bgp_ipv6_af

        intent = self._intent(
            {
                "routing": {
                    "as_number": 65001,
                    "address_families": {
                        "ipv6_unicast": {
                            "neighbors": [{"ip": "2001:db8:1::1", "remote_as": 1299}],
                            "networks": ["2001:db8:acme::/48"],
                            "redistribute": ["connected"],
                        }
                    },
                }
            }
        )
        prim = resolve_bgp_ipv6_af(intent)["primitives"][0]
        self.assertEqual(prim["local_asn"], 65001)
        self.assertEqual(prim["neighbors"][0]["ip"], "2001:db8:1::1")
        self.assertEqual(prim["networks"], ["2001:db8:acme::/48"])
        self.assertEqual(prim["redistribute"], ["connected"])

    def test_isis_reads_routing_block_and_normalises_level(self):
        from intent_networking.resolver import resolve_isis

        intent = self._intent(
            {
                "routing": {
                    "net_address": "49.0001.0100.2550.0001.00",
                    "process_id": 1,
                    "level": 2,
                    "metric_style": "wide",
                    "interfaces": [{"name": "Ethernet1"}],
                }
            }
        )
        prim = resolve_isis(intent)["primitives"][0]
        self.assertEqual(prim["net"], "49.0001.0100.2550.0001.00")
        self.assertEqual(prim["level"], "level-2")  # int 2 normalised
        self.assertEqual(len(prim["interfaces"]), 1)

    def test_route_redistribution_loops_routing_list(self):
        from intent_networking.resolver import resolve_route_redistribution

        intent = self._intent(
            {
                "routing": {
                    "redistribution": [
                        {"from": "connected", "into": "ospf", "process_id": 1, "route_map": "RM1"},
                        {"from": "ospf", "into": "bgp", "as_number": 65001, "route_map": "RM2"},
                    ]
                }
            }
        )
        prims = resolve_route_redistribution(intent)["primitives"]
        self.assertEqual(len(prims), 2)
        self.assertEqual(prims[0]["source_protocol"], "connected")
        self.assertEqual(prims[0]["dest_protocol"], "ospf")
        self.assertEqual(prims[1]["as_number"], 65001)

    def test_vrf_basic_loops_routing_vrfs(self):
        from intent_networking.resolver import resolve_vrf_basic

        intent = self._intent(
            {
                "routing": {
                    "vrfs": [
                        {"name": "PROD", "rd": "65001:100", "interfaces": ["Gi0/1.100"]},
                        {"name": "DEV", "rd": "65001:200", "interfaces": ["Gi0/1.200"]},
                    ]
                }
            }
        )
        result = resolve_vrf_basic(intent)
        prims = result["primitives"]
        self.assertEqual(len(prims), 2)
        self.assertEqual({p["vrf_name"] for p in prims}, {"PROD", "DEV"})
        self.assertEqual(result["vrf_name"], "PROD")
        # vrf.j2 references these under StrictUndefined — must always be present.
        self.assertIn("redistribute_connected", prims[0])
        self.assertIn("redistribute_static", prims[0])

    def test_mpls_l3vpn_emits_renderable_vrf_primitive(self):
        from intent_networking.resolver import resolve_mpls_l3vpn

        intent = self._intent(
            {
                "vrf_name": "CUSTOMER-A",
                "local_asn": 65001,
                "rd": "65001:100",
                "rt_export": "65001:100",
                "rt_import": "65001:100",
                "redistribute_connected": True,
            }
        )
        result = resolve_mpls_l3vpn(intent)
        self.assertTrue(result["requires_mpls"])
        prim = result["primitives"][0]
        self.assertEqual(prim["primitive_type"], "vrf")  # renderable via vrf.j2
        self.assertEqual(prim["device"], "dc-east-leaf-01")
        self.assertEqual(prim["vrf_name"], "CUSTOMER-A")
        self.assertEqual(prim["route_distinguisher"], "65001:100")
        self.assertTrue(prim["redistribute_connected"])

    def test_service_lb_vip_resolves_devices_and_members(self):
        from intent_networking.resolver import resolve_service_lb_vip

        intent = self._intent(
            {
                "vip_name": "VS-WEB",
                "vip_address": "10.100.0.100",
                "vip_port": 443,
                "pool_name": "POOL-WEB",
                "load_balancing_method": "round_robin",
                "members": [{"address": "10.100.1.10", "port": 8443}],
                "health_monitor": {"type": "https", "path": "/health"},
            }
        )
        result = resolve_service_lb_vip(intent)
        self.assertEqual(result["affected_devices"], ["dc-east-leaf-01"])  # device now resolved
        prim = result["primitives"][0]
        self.assertEqual(prim["device"], "dc-east-leaf-01")  # primitive renders per-device
        self.assertEqual(prim["pool_members"][0]["address"], "10.100.1.10")
        self.assertEqual(prim["algorithm"], "round_robin")
        self.assertEqual(prim["health_check"]["type"], "https")

    def test_mgmt_ssh_maps_flat_fields(self):
        from intent_networking.resolver import resolve_mgmt_ssh

        intent = self._intent(
            {
                "acl": "ACL-SSH-SOURCES",
                "timeout_secs": 60,
                "authentication_retries": 3,
                "key_bits": 4096,
                "vty_lines": [{"range": "0 4"}],
            }
        )
        prim = resolve_mgmt_ssh(intent)["primitives"][0]
        self.assertEqual(prim["acl_name"], "ACL-SSH-SOURCES")
        self.assertEqual(prim["timeout"], 60)
        self.assertEqual(prim["retries"], 3)
        self.assertEqual(prim["key_size"], 4096)
        self.assertEqual(prim["vty_lines"], [{"range": "0 4"}])

    def test_mgmt_stp_root_maps_root_vlans_and_secondary(self):
        from intent_networking.resolver import resolve_mgmt_stp_root

        intent = self._intent(
            {
                "mode": "rapid-pvst",
                "root_vlans": ["1-999"],
                "priority": 4096,
                "secondary": {"priority": 8192},
                "hello_time": 2,
            }
        )
        prim = resolve_mgmt_stp_root(intent)["primitives"][0]
        self.assertEqual(prim["primary_vlans"], ["1-999"])  # mapped from root_vlans
        self.assertEqual(prim["priority"], 4096)
        self.assertEqual(prim["secondary_priority"], 8192)
        self.assertEqual(prim["mode"], "rapid-pvst")

    # ── 1C: wrapped management.<subtype> canonical form ──────────────────────

    def test_mgmt_ssh_wrapped_management_subtype(self):
        from intent_networking.resolver import resolve_mgmt_ssh

        intent = self._intent(
            {"management": {"ssh": {"acl": "ACL-SSH", "timeout_secs": 45, "key_bits": 2048, "version": 2}}}
        )
        prim = resolve_mgmt_ssh(intent)["primitives"][0]
        self.assertEqual(prim["acl_name"], "ACL-SSH")
        self.assertEqual(prim["timeout"], 45)
        self.assertEqual(prim["key_size"], 2048)

    def test_mgmt_snmp_wrapped_flat_under_management(self):
        from intent_networking.resolver import resolve_mgmt_snmp

        intent = self._intent({"management": {"snmp_version": "v3", "snmp_trap_targets": ["10.0.1.100"]}})
        prim = resolve_mgmt_snmp(intent)["primitives"][0]
        self.assertEqual(prim["version"], "v3")
        self.assertEqual(prim["trap_targets"], ["10.0.1.100"])

    def test_mgmt_ntp_wrapped(self):
        from intent_networking.resolver import resolve_mgmt_ntp

        intent = self._intent({"management": {"ntp_servers": ["10.0.0.1", "10.0.0.2"]}})
        prim = resolve_mgmt_ntp(intent)["primitives"][0]
        self.assertEqual(prim["servers"], ["10.0.0.1", "10.0.0.2"])

    def test_mgmt_interface_wrapped_interfaces_block(self):
        from intent_networking.resolver import resolve_mgmt_interface

        intent = self._intent(
            {
                "management": {
                    "interfaces": {
                        "loopback": {"name": "Loopback0", "ip_range": "10.255.0.0/24"},
                        "oob_management": {"name": "Management0", "vrf": "MGMT"},
                    }
                }
            }
        )
        prims = resolve_mgmt_interface(intent)["primitives"]
        kinds = {p["primitive_type"]: p for p in prims}
        self.assertEqual(kinds["loopback"]["interface"], "Loopback0")
        self.assertEqual(kinds["mgmt_interface"]["interface"], "Management0")
        self.assertEqual(kinds["mgmt_interface"]["vrf"], "MGMT")

    def test_mgmt_dns_dhcp_wrapped_dns_block(self):
        from intent_networking.resolver import resolve_mgmt_dns_dhcp

        intent = self._intent({"management": {"dns": {"servers": ["10.1.1.10"], "domain_name": "acme.internal"}}})
        prims = resolve_mgmt_dns_dhcp(intent)["primitives"]
        dns = [p for p in prims if p["primitive_type"] == "dns"][0]
        self.assertEqual(dns["servers"], ["10.1.1.10"])
        self.assertEqual(dns["domain_name"], "acme.internal")

    # ── 2A: mgmt_aaa_device structured primitive ─────────────────────────────

    def test_mgmt_aaa_device_structured_primitive(self):
        from intent_networking.resolver import resolve_mgmt_aaa_device

        intent = self._intent(
            {
                "management": {
                    "aaa_device": {
                        "tacacs_servers": [{"host": "10.1.1.20", "port": 49, "key_ref": "vault:x"}],
                        "server_group": "TACACS-CORP",
                        "authentication": {"login": "group TACACS-CORP local"},
                        "authorization": {"commands_15": "group TACACS-CORP none"},
                        "local_fallback": {"username": "emergency-admin", "privilege": 15},
                    }
                }
            }
        )
        prim = resolve_mgmt_aaa_device(intent)["primitives"][0]
        self.assertEqual(prim["primitive_type"], "aaa_device")
        self.assertEqual(prim["server_group"], "TACACS-CORP")
        self.assertEqual(prim["tacacs_servers"][0]["host"], "10.1.1.20")
        self.assertEqual(prim["authentication"]["login"], "group TACACS-CORP local")
        self.assertEqual(prim["local_fallback"]["username"], "emergency-admin")

    # ── 3A: behaviour-affecting fields ───────────────────────────────────────

    def test_ospf_derives_networks_from_areas(self):
        from intent_networking.resolver import resolve_ospf

        intent = self._intent(
            {
                "routing": {
                    "process_id": 1,
                    "router_id": "10.255.0.1",
                    "areas": [
                        {"area_id": "0.0.0.0", "type": "backbone", "networks": ["10.255.0.0/24"]},
                        {"area_id": "0.0.0.1", "type": "stub", "networks": ["10.10.1.0/24"]},
                    ],
                }
            }
        )
        prim = resolve_ospf(intent)["primitives"][0]
        nets = {n["network"]: n for n in prim["networks"]}
        self.assertEqual(nets["10.255.0.0"]["wildcard"], "0.0.0.255")
        self.assertEqual(nets["10.255.0.0"]["area"], "0.0.0.0")
        self.assertEqual(prim["stub_areas"], ["0.0.0.1"])

    def test_fhrp_groups_active_standby(self):
        from intent_networking.resolver import resolve_fhrp

        intent = self._intent(
            {
                "fhrp": {
                    "protocol": "hsrp",
                    "groups": [
                        {
                            "vlan": 100,
                            "group_id": 100,
                            "virtual_ip": "10.100.0.1",
                            "active_priority": 110,
                            "standby_priority": 90,
                            "preempt": True,
                            "track": [{"interface": "Gi0/0", "decrement": 20}],
                        }
                    ],
                }
            }
        )
        # Single in-scope device -> treated as active.
        prim = resolve_fhrp(intent)["primitives"][0]
        grp = prim["groups"][0]
        self.assertEqual(grp["interface"], "Vlan100")
        self.assertEqual(grp["priority"], 110)  # active
        self.assertEqual(grp["track"], "Gi0/0")
        self.assertEqual(grp["decrement"], 20)

    def test_wireless_ssid_passes_psk(self):
        from intent_networking.resolver import resolve_wireless_ssid

        intent = self._intent({"ssid_name": "CORP-WIFI", "security_mode": "wpa2-psk", "psk": "s3cret-pass"})
        prim = resolve_wireless_ssid(intent)["primitives"][0]
        self.assertEqual(prim["psk"], "s3cret-pass")


class GapResolutionTest(TestCase):
    """Fabric-name registry and endpoint-IP device resolution (gap #1)."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.contenttypes.models import ContentType
        from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer
        from nautobot.extras.models import Role, Status
        from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix
        from nautobot.tenancy.models import Tenant

        from intent_networking.models import Intent

        device_ct = ContentType.objects.get_for_model(Device)
        intf_ct = ContentType.objects.get_for_model(Interface)
        loc_ct = ContentType.objects.get_for_model(Location)
        ip_ct = ContentType.objects.get_for_model(IPAddress)
        prefix_ct = ContentType.objects.get_for_model(Prefix)
        intent_ct = ContentType.objects.get_for_model(Intent)
        active, _ = Status.objects.get_or_create(name="Active")
        active.content_types.add(device_ct, intf_ct, loc_ct, ip_ct, prefix_ct, intent_ct)
        draft, _ = Status.objects.get_or_create(name="Draft")
        draft.content_types.add(intent_ct)

        cls.tenant, _ = Tenant.objects.get_or_create(name="Gap Tenant")
        mfr, _ = Manufacturer.objects.get_or_create(name="Gap Mfr")
        dt, _ = DeviceType.objects.get_or_create(manufacturer=mfr, model="Gap Model")
        role, _ = Role.objects.get_or_create(name="leaf-switch")
        role.content_types.add(device_ct)
        lt, _ = LocationType.objects.get_or_create(name="Gap Site Type")
        lt.content_types.add(device_ct)
        site, _ = Location.objects.get_or_create(name="gap-dc", location_type=lt, status=active)
        cls.device = Device.objects.create(
            name="gap-leaf-01", device_type=dt, role=role, location=site, status=active, tenant=cls.tenant
        )

        # Fabric registry: an evpn_vxlan_fabric intent that names this leaf.
        Intent.objects.create(
            intent_id="gap-fabric-001",
            version=1,
            intent_type="evpn_vxlan_fabric",
            tenant=cls.tenant,
            status=draft,
            intent_data={
                "type": "evpn_vxlan_fabric",
                "fabric": {"name": "gap-fabric", "spines": [], "leaves": ["gap-leaf-01"]},
            },
        )

        # IPAM: assign 203.0.113.10/24 to an interface on the device.
        ns, _ = Namespace.objects.get_or_create(name="Global")
        prefix, _ = Prefix.objects.get_or_create(prefix="203.0.113.0/24", defaults={"namespace": ns, "status": active})
        ip = IPAddress(address="203.0.113.10/24", parent=prefix, status=active)
        ip.validated_save()
        intf = Interface.objects.create(device=cls.device, name="Ethernet1", type="10gbase-x-sfpp", status=active)
        IPAddressToInterface.objects.get_or_create(ip_address=ip, interface=intf)

    def _intent(self, intent_data):
        intent = MagicMock()
        intent.intent_id = "gap-test"
        intent.tenant = self.tenant
        intent.intent_data = intent_data
        return intent

    def test_l2vni_fabric_name_resolves_to_fabric_leaves(self):
        devices = _get_scope_devices(self._intent({"fabric": {"name": "gap-fabric"}}))
        self.assertEqual(["gap-leaf-01"], [d.name for d in devices])

    def test_unknown_fabric_name_raises(self):
        with self.assertRaises(ValueError):
            _get_scope_devices(self._intent({"fabric": {"name": "no-such-fabric"}}))

    def test_devices_by_ip(self):
        from intent_networking.resolver import _devices_by_ip

        intent = self._intent({})
        self.assertEqual(["gap-leaf-01"], [d.name for d in _devices_by_ip(intent, "203.0.113.10")])
        # accepts CIDR form and unknown IP returns empty
        self.assertEqual(["gap-leaf-01"], [d.name for d in _devices_by_ip(intent, "203.0.113.10/24")])
        self.assertEqual([], _devices_by_ip(intent, "9.9.9.9"))
