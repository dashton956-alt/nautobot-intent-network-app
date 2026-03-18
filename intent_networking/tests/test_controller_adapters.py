"""Unit tests for intent_networking.controller_adapters module.

Tests the adapter hierarchy, factory, classify_primitives, and all three
concrete adapters (Wireless, SD-WAN, Cloud).
"""

from django.test import SimpleTestCase, override_settings

from intent_networking.controller_adapters import (
    ADAPTER_REGISTRY,
    CloudAdapter,
    ControllerAdapter,
    FirewallControllerAdapter,
    SdWanControllerAdapter,
    WirelessControllerAdapter,
    classify_primitives,
    get_adapter,
)

ADAPTER_PLUGIN_CFG = {
    "intent_networking": {
        "wireless_controller_url": "https://wlc.example.com",
        "wireless_controller_creds": {"username": "admin", "password": "secret"},
        "sdwan_controller_url": "https://vmanage.example.com",
        "sdwan_controller_creds": {"username": "admin", "password": "secret"},
        "cloud_controller_url": "https://cloud-api.example.com",
        "cloud_controller_creds": {"token": "tok123"},
        "firewall_controller_url": "https://panorama.example.com",
        "firewall_controller_creds": {"username": "admin", "api_key": "key123"},
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# Abstract Base / Concrete instantiation
# ─────────────────────────────────────────────────────────────────────────────


class ControllerAdapterBaseTest(SimpleTestCase):
    """Test the ControllerAdapter abstract base class."""

    def test_cannot_instantiate_abc(self):
        """ControllerAdapter cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            ControllerAdapter("https://example.com")  # pylint: disable=abstract-class-instantiated

    def test_url_trailing_slash_stripped(self):
        """controller_url should have trailing slash stripped."""
        adapter = WirelessControllerAdapter("https://wlc.example.com/")
        self.assertEqual(adapter.controller_url, "https://wlc.example.com")

    def test_credentials_default_to_empty_dict(self):
        """credentials defaults to {} when not supplied."""
        adapter = WirelessControllerAdapter("https://wlc.example.com")
        self.assertEqual(adapter.credentials, {})

    def test_credentials_stored(self):
        """Supplied credentials are stored."""
        creds = {"user": "admin", "pass": "secret"}
        adapter = WirelessControllerAdapter("https://wlc.example.com", credentials=creds)
        self.assertEqual(adapter.credentials, creds)

    def test_context_manager(self):
        """Adapter works as a context manager (connect / disconnect)."""
        adapter = WirelessControllerAdapter("https://wlc.example.com")
        with adapter as a:
            self.assertIs(a, adapter)


# ─────────────────────────────────────────────────────────────────────────────
# Wireless Controller Adapter
# ─────────────────────────────────────────────────────────────────────────────


class WirelessControllerAdapterTest(SimpleTestCase):
    """Test WirelessControllerAdapter push/verify/rollback."""

    def setUp(self):
        """Create adapter instance."""
        self.adapter = WirelessControllerAdapter("https://wlc.example.com")

    def test_push_filters_non_wireless(self):
        """Non-wireless primitives are skipped."""
        primitives = [
            {"primitive_type": "static_route", "data": {}},
            {"primitive_type": "wireless_ssid", "data": {"ssid_name": "Corp"}},
        ]
        result = self.adapter.push(primitives, "test-001")
        # Only 1 primitive processed (wireless_ssid)
        self.assertEqual(len(result["details"]), 1)

    def test_push_returns_failure_without_vendor_override(self):
        """Base _dispatch_push returns ok=False (no vendor impl)."""
        primitives = [{"primitive_type": "wireless_ssid"}]
        result = self.adapter.push(primitives, "test-001")
        self.assertFalse(result["success"])

    def test_verify_reports_drift_without_override(self):
        """Base _check_present returns False, so verify finds drift."""
        primitives = [{"primitive_type": "wireless_ssid"}]
        result = self.adapter.verify(primitives, "test-001")
        self.assertFalse(result["verified"])
        self.assertEqual(len(result["drift"]), 1)

    def test_verify_ignores_non_wireless(self):
        """Non-wireless primitives don't produce drift."""
        primitives = [{"primitive_type": "static_route"}]
        result = self.adapter.verify(primitives, "test-001")
        self.assertTrue(result["verified"])
        self.assertEqual(len(result["drift"]), 0)

    def test_rollback_returns_failure_without_override(self):
        """Base _dispatch_rollback returns ok=False."""
        primitives = [{"primitive_type": "wireless_vlan_map"}]
        result = self.adapter.rollback(primitives, "test-001")
        self.assertFalse(result["success"])

    def test_primitive_types_frozenset(self):
        """PRIMITIVE_TYPES is a frozenset with expected wireless types."""
        self.assertIsInstance(WirelessControllerAdapter.PRIMITIVE_TYPES, frozenset)
        self.assertIn("wireless_ssid", WirelessControllerAdapter.PRIMITIVE_TYPES)
        self.assertIn("wireless_dot1x", WirelessControllerAdapter.PRIMITIVE_TYPES)
        self.assertIn("wireless_mesh", WirelessControllerAdapter.PRIMITIVE_TYPES)


# ─────────────────────────────────────────────────────────────────────────────
# SD-WAN Controller Adapter
# ─────────────────────────────────────────────────────────────────────────────


class SdWanControllerAdapterTest(SimpleTestCase):
    """Test SdWanControllerAdapter push/verify/rollback."""

    def setUp(self):
        """Create adapter instance."""
        self.adapter = SdWanControllerAdapter("https://vmanage.example.com")

    def test_push_filters_non_sdwan(self):
        """Non-SDWAN primitives are skipped."""
        primitives = [
            {"primitive_type": "wireless_ssid"},
            {"primitive_type": "sdwan_overlay"},
        ]
        result = self.adapter.push(primitives, "test-001")
        self.assertEqual(len(result["details"]), 1)

    def test_push_returns_failure_without_vendor_override(self):
        """Base returns ok=False."""
        primitives = [{"primitive_type": "sdwan_app_policy"}]
        result = self.adapter.push(primitives, "test-001")
        self.assertFalse(result["success"])

    def test_verify_reports_drift(self):
        """Drift reported for each sdwan primitive."""
        primitives = [{"primitive_type": "sdwan_overlay"}, {"primitive_type": "sdwan_qos"}]
        result = self.adapter.verify(primitives, "test-001")
        self.assertFalse(result["verified"])
        self.assertEqual(len(result["drift"]), 2)

    def test_rollback_returns_failure(self):
        """Base returns ok=False."""
        primitives = [{"primitive_type": "sdwan_dia"}]
        result = self.adapter.rollback(primitives, "test-001")
        self.assertFalse(result["success"])

    def test_primitive_types(self):
        """SDWAN adapter recognises correct primitive types."""
        self.assertIn("sdwan_overlay", SdWanControllerAdapter.PRIMITIVE_TYPES)
        self.assertIn("sdwan_app_policy", SdWanControllerAdapter.PRIMITIVE_TYPES)
        self.assertIn("cloud_sdwan", SdWanControllerAdapter.PRIMITIVE_TYPES)


# ─────────────────────────────────────────────────────────────────────────────
# Cloud Adapter
# ─────────────────────────────────────────────────────────────────────────────


class CloudAdapterTest(SimpleTestCase):
    """Test CloudAdapter push/verify/rollback."""

    def setUp(self):
        """Create adapter instance."""
        self.adapter = CloudAdapter("https://cloud-api.example.com")

    def test_push_uses_provider_from_primitive(self):
        """Provider is read from the primitive dict."""
        primitives = [{"primitive_type": "cloud_vpc_peer", "provider": "azure"}]
        result = self.adapter.push(primitives, "test-001")
        self.assertFalse(result["success"])  # no vendor impl
        self.assertEqual(len(result["details"]), 1)

    def test_push_defaults_provider_to_aws(self):
        """Provider defaults to 'aws' if not specified."""
        primitives = [{"primitive_type": "cloud_transit_gw"}]
        result = self.adapter.push(primitives, "test-001")
        self.assertEqual(len(result["details"]), 1)

    def test_push_filters_non_cloud(self):
        """Non-cloud primitives are skipped."""
        primitives = [{"primitive_type": "ospf"}, {"primitive_type": "cloud_nat"}]
        result = self.adapter.push(primitives, "test-001")
        self.assertEqual(len(result["details"]), 1)

    def test_verify_reports_drift(self):
        """Drift detected for unimplemented check."""
        primitives = [{"primitive_type": "cloud_security_group", "provider": "gcp"}]
        result = self.adapter.verify(primitives, "test-001")
        self.assertFalse(result["verified"])
        self.assertIn("gcp", result["drift"][0])

    def test_rollback_returns_failure(self):
        """Base returns ok=False."""
        primitives = [{"primitive_type": "cloud_route_table", "provider": "aws"}]
        result = self.adapter.rollback(primitives, "test-001")
        self.assertFalse(result["success"])

    def test_primitive_types(self):
        """Cloud adapter recognises correct primitive types."""
        self.assertIn("cloud_vpc_peer", CloudAdapter.PRIMITIVE_TYPES)
        self.assertIn("cloud_direct_connect", CloudAdapter.PRIMITIVE_TYPES)
        self.assertIn("hybrid_dns", CloudAdapter.PRIMITIVE_TYPES)


# ─────────────────────────────────────────────────────────────────────────────
# Firewall Controller Adapter
# ─────────────────────────────────────────────────────────────────────────────


class FirewallControllerAdapterTest(SimpleTestCase):
    """Test FirewallControllerAdapter push/verify/rollback."""

    def setUp(self):
        """Create adapter instance."""
        self.adapter = FirewallControllerAdapter("https://panorama.example.com")

    def test_push_filters_non_firewall(self):
        """Non-firewall primitives are skipped."""
        primitives = [
            {"primitive_type": "static_route", "data": {}},
            {"primitive_type": "fw_rule", "policy_name": "DENY-ALL"},
        ]
        result = self.adapter.push(primitives, "test-001")
        self.assertEqual(len(result["details"]), 1)

    def test_push_returns_failure_without_vendor_override(self):
        """Base _dispatch_push returns ok=False (no vendor impl)."""
        primitives = [{"primitive_type": "fw_rule"}]
        result = self.adapter.push(primitives, "test-001")
        self.assertFalse(result["success"])

    def test_verify_reports_drift_without_override(self):
        """Base _check_present returns False, so verify finds drift."""
        primitives = [{"primitive_type": "fw_rule", "policy_name": "TEST"}]
        result = self.adapter.verify(primitives, "test-001")
        self.assertFalse(result["verified"])
        self.assertEqual(len(result["drift"]), 1)

    def test_verify_ignores_non_firewall(self):
        """Non-firewall primitives don't produce drift."""
        primitives = [{"primitive_type": "static_route"}]
        result = self.adapter.verify(primitives, "test-001")
        self.assertTrue(result["verified"])
        self.assertEqual(len(result["drift"]), 0)

    def test_rollback_returns_failure_without_override(self):
        """Base _dispatch_rollback returns ok=False."""
        primitives = [{"primitive_type": "fw_rule"}]
        result = self.adapter.rollback(primitives, "test-001")
        self.assertFalse(result["success"])

    def test_primitive_types_frozenset(self):
        """PRIMITIVE_TYPES is a frozenset with expected firewall types."""
        self.assertIsInstance(FirewallControllerAdapter.PRIMITIVE_TYPES, frozenset)
        self.assertIn("fw_rule", FirewallControllerAdapter.PRIMITIVE_TYPES)


# ─────────────────────────────────────────────────────────────────────────────
# Adapter Factory — get_adapter()
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(PLUGINS_CONFIG=ADAPTER_PLUGIN_CFG)
class GetAdapterFactoryTest(SimpleTestCase):
    """Test get_adapter() factory function."""

    def test_get_wireless_adapter(self):
        """Factory returns WirelessControllerAdapter for 'wireless'."""
        adapter = get_adapter("wireless")
        self.assertIsInstance(adapter, WirelessControllerAdapter)
        self.assertEqual(adapter.controller_url, "https://wlc.example.com")

    def test_get_sdwan_adapter(self):
        """Factory returns SdWanControllerAdapter for 'sdwan'."""
        adapter = get_adapter("sdwan")
        self.assertIsInstance(adapter, SdWanControllerAdapter)

    def test_get_cloud_adapter(self):
        """Factory returns CloudAdapter for 'cloud'."""
        adapter = get_adapter("cloud")
        self.assertIsInstance(adapter, CloudAdapter)

    def test_get_firewall_adapter(self):
        """Factory returns FirewallControllerAdapter for 'firewall'."""
        adapter = get_adapter("firewall")
        self.assertIsInstance(adapter, FirewallControllerAdapter)
        self.assertEqual(adapter.controller_url, "https://panorama.example.com")

    def test_unknown_adapter_type_raises(self):
        """ValueError for an unregistered adapter type."""
        with self.assertRaises(ValueError) as ctx:
            get_adapter("unknown-type")
        self.assertIn("Unknown adapter type", str(ctx.exception))

    def test_missing_url_raises(self):
        """ValueError when no URL configured and no override."""
        with override_settings(PLUGINS_CONFIG={"intent_networking": {}}):
            with self.assertRaises(ValueError) as ctx:
                get_adapter("wireless")
            self.assertIn("not set", str(ctx.exception))

    def test_url_override(self):
        """controller_url kwarg overrides plugin config."""
        adapter = get_adapter("wireless", controller_url="https://override.example.com")
        self.assertEqual(adapter.controller_url, "https://override.example.com")

    def test_credentials_override(self):
        """credentials kwarg overrides plugin config."""
        creds = {"token": "override-tok"}
        adapter = get_adapter("wireless", credentials=creds)
        self.assertEqual(adapter.credentials, creds)


# ─────────────────────────────────────────────────────────────────────────────
# ADAPTER_REGISTRY
# ─────────────────────────────────────────────────────────────────────────────


class AdapterRegistryTest(SimpleTestCase):
    """Test ADAPTER_REGISTRY mapping."""

    def test_registry_has_all_types(self):
        """Registry contains wireless, sdwan, cloud and firewall."""
        self.assertIn("wireless", ADAPTER_REGISTRY)
        self.assertIn("sdwan", ADAPTER_REGISTRY)
        self.assertIn("cloud", ADAPTER_REGISTRY)
        self.assertIn("firewall", ADAPTER_REGISTRY)

    def test_registry_values_are_classes(self):
        """All registry values are ControllerAdapter subclasses."""
        for key, cls in ADAPTER_REGISTRY.items():
            self.assertTrue(
                issubclass(cls, ControllerAdapter),
                f"{key} -> {cls} is not a ControllerAdapter subclass",
            )


# ─────────────────────────────────────────────────────────────────────────────
# classify_primitives
# ─────────────────────────────────────────────────────────────────────────────


class ClassifyPrimitivesTest(SimpleTestCase):
    """Test classify_primitives() bucketing logic."""

    def test_empty_list(self):
        """Empty primitive list returns empty dict."""
        self.assertEqual(classify_primitives([]), {})

    def test_nornir_bucket(self):
        """Primitives not in any controller set go to 'nornir'."""
        primitives = [
            {"primitive_type": "static_route"},
            {"primitive_type": "ospf"},
            {"primitive_type": "acl"},
        ]
        result = classify_primitives(primitives)
        self.assertIn("nornir", result)
        self.assertEqual(len(result["nornir"]), 3)
        self.assertNotIn("wireless", result)
        self.assertNotIn("sdwan", result)
        self.assertNotIn("cloud", result)
        self.assertNotIn("firewall", result)

    def test_wireless_bucket(self):
        """Wireless primitives go to 'wireless' bucket."""
        primitives = [
            {"primitive_type": "wireless_ssid"},
            {"primitive_type": "wireless_dot1x"},
        ]
        result = classify_primitives(primitives)
        self.assertIn("wireless", result)
        self.assertEqual(len(result["wireless"]), 2)

    def test_sdwan_bucket(self):
        """SD-WAN primitives go to 'sdwan' bucket."""
        primitives = [{"primitive_type": "sdwan_overlay"}]
        result = classify_primitives(primitives)
        self.assertIn("sdwan", result)
        self.assertEqual(len(result["sdwan"]), 1)

    def test_cloud_bucket(self):
        """Cloud primitives go to 'cloud' bucket."""
        primitives = [{"primitive_type": "cloud_vpc_peer"}, {"primitive_type": "hybrid_dns"}]
        result = classify_primitives(primitives)
        self.assertIn("cloud", result)
        self.assertEqual(len(result["cloud"]), 2)

    def test_firewall_bucket(self):
        """Firewall primitives go to 'firewall' bucket."""
        primitives = [{"primitive_type": "fw_rule"}]
        result = classify_primitives(primitives)
        self.assertIn("firewall", result)
        self.assertEqual(len(result["firewall"]), 1)

    def test_mixed_primitives(self):
        """Mixed primitives are sorted into correct buckets."""
        primitives = [
            {"primitive_type": "ospf"},
            {"primitive_type": "wireless_ssid"},
            {"primitive_type": "sdwan_overlay"},
            {"primitive_type": "cloud_vpc_peer"},
            {"primitive_type": "acl"},
            {"primitive_type": "fw_rule"},
        ]
        result = classify_primitives(primitives)
        self.assertEqual(len(result["nornir"]), 2)
        self.assertEqual(len(result["wireless"]), 1)
        self.assertEqual(len(result["sdwan"]), 1)
        self.assertEqual(len(result["cloud"]), 1)
        self.assertEqual(len(result["firewall"]), 1)

    def test_empty_buckets_removed(self):
        """Buckets with zero items are not in the result."""
        primitives = [{"primitive_type": "wireless_ssid"}]
        result = classify_primitives(primitives)
        self.assertNotIn("nornir", result)
        self.assertNotIn("sdwan", result)
        self.assertNotIn("cloud", result)
        self.assertNotIn("firewall", result)
        self.assertIn("wireless", result)

    def test_cloud_sdwan_overlap(self):
        """cloud_sdwan goes to sdwan bucket (it's in SdWanControllerAdapter.PRIMITIVE_TYPES)."""
        primitives = [{"primitive_type": "cloud_sdwan"}]
        result = classify_primitives(primitives)
        # cloud_sdwan is in BOTH SdWanControllerAdapter and CloudAdapter,
        # but the classify function checks wireless → sdwan → cloud order.
        # So it should land in sdwan.
        self.assertIn("sdwan", result)


# ─────────────────────────────────────────────────────────────────────────────
# Catalyst Center Adapter
# ─────────────────────────────────────────────────────────────────────────────


class FakeIntent:
    """Minimal intent-like object for adapter tests."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        intent_id="test-001",
        intent_type="connectivity",
        controller_site="London-HQ",
        controller_org="acme-corp",
        intent_data=None,
    ):
        """Create a fake intent for testing."""
        self.intent_id = intent_id
        self.intent_type = intent_type
        self.controller_site = controller_site
        self.controller_org = controller_org
        self.intent_data = intent_data or {"source": "10.0.0.0/8"}


class FakeTaskResponse:
    """Fake task result from Catalyst Center task API."""

    def __init__(self, task_id="task-123", end_time="2026-01-01T00:00:00", is_error=False, failure_reason=""):
        """Create a fake task response."""
        self.response = type(
            "TaskData",
            (),
            {
                "taskId": task_id,
                "endTime": end_time,
                "isError": is_error,
                "failureReason": failure_reason,
                "progress": "completed",
            },
        )()


class FakeAPIResponse:
    """Fake response from Catalyst Center SDA API calls."""

    def __init__(self, task_id="task-123"):
        """Create a fake API response with a task ID."""
        self.response = type("ResponseData", (), {"taskId": task_id})()


class CatalystCenterAdapterImportTest(SimpleTestCase):
    """Test that the base package works without dnacentersdk installed."""

    def test_base_package_imports_without_dnacentersdk(self):
        """Importing intent_networking.controller_adapters succeeds without dnacentersdk."""
        import intent_networking.controller_adapters as mod  # noqa: PLC0415

        # The module should load fine — CatalystCenterAdapter is defined but
        # the import only fires on instantiation.
        # Note: do NOT reload the module here — it invalidates class references
        # held by other tests in the same process.
        self.assertTrue(hasattr(mod, "CatalystCenterAdapter"))
        self.assertTrue(hasattr(mod, "VALID_CONTROLLER_TYPES"))

    def test_import_error_with_helpful_message(self):
        """ImportError raised with install hint when dnacentersdk missing."""
        import sys  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415

        from intent_networking.controller_adapters import CatalystCenterAdapter  # noqa: PLC0415

        # Simulate dnacentersdk not being installed
        with mock.patch.dict(sys.modules, {"dnacentersdk": None}):
            with self.assertRaises(ImportError) as ctx:
                CatalystCenterAdapter(FakeIntent())
            self.assertIn("catalyst", str(ctx.exception))
            self.assertIn("poetry add", str(ctx.exception))


class CatalystCenterAdapterTest(SimpleTestCase):
    """Test CatalystCenterAdapter deploy, verify, rollback, and task polling."""

    def _make_adapter(self, intent=None):
        """Create a CatalystCenterAdapter with a mocked SDK."""
        from unittest import mock  # noqa: PLC0415

        adapter_intent = intent or FakeIntent()

        # Create a mock DNACenterAPI class
        mock_api = mock.MagicMock()

        # Patch the import and credentials
        from intent_networking.controller_adapters import CatalystCenterAdapter  # noqa: PLC0415

        with mock.patch.object(
            CatalystCenterAdapter,
            "_resolve_credentials",
            return_value=("https://dnac.example.com", "admin", "password"),
        ):
            # Patch dnacentersdk import inside __init__
            fake_sdk_module = mock.MagicMock()
            fake_sdk_module.DNACenterAPI = mock.MagicMock(return_value=mock_api)

            import sys  # noqa: PLC0415

            with mock.patch.dict(sys.modules, {"dnacentersdk": fake_sdk_module}):
                adapter = CatalystCenterAdapter(adapter_intent)

        adapter.api = mock_api
        return adapter, mock_api

    def test_deploy_connectivity(self):
        """Deploy connectivity intent calls SDA virtual network API."""
        intent = FakeIntent(intent_type="connectivity", intent_data={"source": "10.0.0.0/8", "vn_name": "CORP-VN"})
        adapter, mock_api = self._make_adapter(intent)

        mock_api.sda.add_virtual_network_with_scalable_groups.return_value = FakeAPIResponse("task-001")
        mock_api.task.get_task_by_id.return_value = FakeTaskResponse("task-001")

        result = adapter.deploy(None)

        self.assertTrue(result["success"])
        mock_api.sda.add_virtual_network_with_scalable_groups.assert_called_once()

    def test_deploy_segmentation(self):
        """Deploy segmentation intent calls SDA authentication profile API."""
        intent = FakeIntent(intent_type="segmentation", intent_data={"policy_name": "SEG-POLICY"})
        adapter, mock_api = self._make_adapter(intent)

        mock_api.sda.add_default_authentication_profile.return_value = FakeAPIResponse("task-002")
        mock_api.task.get_task_by_id.return_value = FakeTaskResponse("task-002")

        result = adapter.deploy(None)

        self.assertTrue(result["success"])
        mock_api.sda.add_default_authentication_profile.assert_called_once()

    def test_deploy_reachability(self):
        """Deploy reachability intent calls SDA site API."""
        intent = FakeIntent(intent_type="reachability", intent_data={"fabric_name": "Default"})
        adapter, mock_api = self._make_adapter(intent)

        mock_api.sda.add_site.return_value = FakeAPIResponse("task-003")
        mock_api.task.get_task_by_id.return_value = FakeTaskResponse("task-003")

        result = adapter.deploy(None)

        self.assertTrue(result["success"])
        mock_api.sda.add_site.assert_called_once()

    def test_deploy_unsupported_type_raises(self):
        """UnsupportedIntentTypeError raised for non-supported intent type."""
        from intent_networking.controller_adapters import UnsupportedIntentTypeError  # noqa: PLC0415

        intent = FakeIntent(intent_type="mpls_l3vpn")
        adapter, _ = self._make_adapter(intent)

        with self.assertRaises(UnsupportedIntentTypeError) as ctx:
            adapter.deploy(None)
        self.assertIn("mpls_l3vpn", str(ctx.exception))
        self.assertIn("connectivity", str(ctx.exception))

    def test_verify_no_drift(self):
        """Verify returns verified=True when no non-compliant devices."""
        adapter, mock_api = self._make_adapter()

        compliance_response = type("ComplianceResp", (), {"response": []})()
        mock_api.compliance.get_compliance_detail.return_value = compliance_response

        result = adapter.verify()

        self.assertTrue(result["verified"])
        self.assertEqual(len(result["drift"]), 0)

    def test_verify_with_drift(self):
        """Verify returns drift when non-compliant devices found."""
        adapter, mock_api = self._make_adapter()

        device = type("Device", (), {"deviceName": "switch-01", "complianceType": "RUNNING_CONFIG"})()
        compliance_response = type("ComplianceResp", (), {"response": [device]})()
        mock_api.compliance.get_compliance_detail.return_value = compliance_response

        result = adapter.verify()

        self.assertFalse(result["verified"])
        self.assertEqual(len(result["drift"]), 1)
        self.assertEqual(result["drift"][0]["device"], "switch-01")

    def test_rollback_connectivity(self):
        """Rollback connectivity intent calls delete virtual network."""
        intent = FakeIntent(intent_type="connectivity", intent_data={"vn_name": "CORP-VN"})
        adapter, mock_api = self._make_adapter(intent)

        mock_api.sda.delete_virtual_network_with_scalable_groups.return_value = FakeAPIResponse("task-010")
        mock_api.task.get_task_by_id.return_value = FakeTaskResponse("task-010")

        result = adapter.rollback(None)

        self.assertTrue(result["success"])
        mock_api.sda.delete_virtual_network_with_scalable_groups.assert_called_once()

    def test_task_poll_timeout(self):
        """Task polling returns failure on timeout."""
        from unittest import mock  # noqa: PLC0415

        adapter, mock_api = self._make_adapter()

        # Task never completes (endTime stays None)
        never_done = type(
            "TaskResp",
            (),
            {
                "response": type(
                    "TaskData",
                    (),
                    {
                        "endTime": None,
                        "isError": False,
                        "progress": "in progress",
                    },
                )()
            },
        )()
        mock_api.task.get_task_by_id.return_value = never_done

        # Override timeout to avoid waiting 5 minutes
        adapter.TASK_POLL_TIMEOUT = 0.1
        adapter.TASK_POLL_INTERVAL = 0.05

        with mock.patch("time.sleep"):
            result = adapter._poll_task("task-999")  # pylint: disable=protected-access

        self.assertFalse(result["completed"])
        self.assertIn("timed out", result["error"])

    def test_get_live_state(self):
        """get_live_state returns device list from Catalyst Center."""
        adapter, mock_api = self._make_adapter()

        dev = type(
            "Dev",
            (),
            {
                "hostname": "pe-01",
                "managementIpAddress": "10.0.0.1",
                "reachabilityStatus": "Reachable",
                "role": "ACCESS",
            },
        )()
        mock_api.devices.get_device_list.return_value = type("DevResp", (), {"response": [dev]})()  # pylint: disable=no-member

        result = adapter.get_live_state()

        self.assertEqual(len(result["devices"]), 1)
        self.assertEqual(result["devices"][0]["hostname"], "pe-01")


class ValidControllerTypesTest(SimpleTestCase):
    """Test VALID_CONTROLLER_TYPES constant."""

    def test_contains_expected_types(self):
        """VALID_CONTROLLER_TYPES contains all expected controller types."""
        from intent_networking.controller_adapters import VALID_CONTROLLER_TYPES  # noqa: PLC0415

        self.assertIn("nornir", VALID_CONTROLLER_TYPES)
        self.assertIn("catalyst_center", VALID_CONTROLLER_TYPES)
        self.assertIn("meraki", VALID_CONTROLLER_TYPES)
        self.assertIn("mist", VALID_CONTROLLER_TYPES)
