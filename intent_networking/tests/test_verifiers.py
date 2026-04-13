"""Tests for BasicVerifier and NutsVerifier."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from nautobot.extras.models import Status

from intent_networking.models import Intent, ResolutionPlan, VerificationResult
from intent_networking.tests import fixtures


class TestBasicVerifier(TestCase):
    """Tests for BasicVerifier."""

    @classmethod
    def setUpTestData(cls):
        fixtures.create_intents()

    def _get_intent(self, intent_id="test-intent-001"):
        return Intent.objects.get(intent_id=intent_id)

    def _create_plan(self, intent, primitives=None, vrf_name="", affected_devices=None):
        plan, _ = ResolutionPlan.objects.update_or_create(
            intent=intent,
            intent_version=intent.version,
            defaults={
                "primitives": primitives or [],
                "vrf_name": vrf_name,
                "resolved_by": "test",
            },
        )
        if affected_devices:
            plan.affected_devices.set(affected_devices)
        return plan

    @patch("intent_networking.verifiers.basic.BasicVerifier._collect_device_state")
    @patch("intent_networking.verifiers.basic.BasicVerifier._check_controller_adapters")
    def test_basic_runs_existing_checks_for_connectivity_intent(self, mock_ctrl, mock_state):
        from intent_networking.verifiers.basic import BasicVerifier

        intent = self._get_intent()
        self._create_plan(intent, primitives=[])

        mock_ctrl.return_value = ([], True)
        result = BasicVerifier(intent).run()

        self.assertIn("passed", result)
        self.assertIn("has_warnings", result)
        self.assertIn("warning_reasons", result)
        self.assertIn("checks", result)

    @patch("intent_networking.verifiers.basic.BasicVerifier._collect_device_state")
    @patch("intent_networking.verifiers.basic.BasicVerifier._check_controller_adapters")
    @patch("intent_networking.verifiers.basic.BasicVerifier._measure_latency")
    def test_basic_returns_has_warnings_when_latency_near_threshold(self, mock_latency, mock_ctrl, mock_state):
        from intent_networking.verifiers.basic import BasicVerifier

        intent = self._get_intent()
        intent.intent_data["policy"] = {"max_latency_ms": 20}
        intent.save()
        self._create_plan(intent, primitives=[])

        mock_ctrl.return_value = ([], True)
        mock_latency.return_value = 17  # 85% of 20ms threshold

        result = BasicVerifier(intent).run()

        self.assertTrue(result["passed"])
        self.assertTrue(result["has_warnings"])
        self.assertIn("Latency 17ms is within 80% of SLA threshold 20ms", result["warning_reasons"][0])

    @patch("intent_networking.verifiers.basic.BasicVerifier._collect_device_state")
    @patch("intent_networking.verifiers.basic.BasicVerifier._check_controller_adapters")
    def test_basic_returns_passed_false_when_bgp_not_established(self, mock_ctrl, mock_state):
        from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
        from nautobot.extras.models import Role

        from intent_networking.verifiers.basic import BasicVerifier

        intent = self._get_intent()

        # Create a device to add to affected_devices
        mfg, _ = Manufacturer.objects.get_or_create(name="Cisco-Test")
        dt, _ = DeviceType.objects.get_or_create(model="CSR1000v-Test", manufacturer=mfg)
        status = Status.objects.filter(name="Active").first()
        if not status:
            status = Status.objects.first()
        loc_type, _ = LocationType.objects.get_or_create(name="Site-Test")
        loc_type.content_types.add(*list(loc_type.content_types.all()))
        from django.contrib.contenttypes.models import ContentType

        device_ct = ContentType.objects.get_for_model(Device)
        loc_type.content_types.add(device_ct)
        role, _ = Role.objects.get_or_create(name="Router-Test")
        role.content_types.add(device_ct)
        loc, _ = Location.objects.get_or_create(
            name="test-site-bgp", location_type=loc_type, defaults={"status": status}
        )
        device, _ = Device.objects.get_or_create(
            name="test-device-bgp",
            defaults={
                "device_type": dt,
                "location": loc,
                "status": status,
                "role": role,
            },
        )

        self._create_plan(
            intent,
            primitives=[{"device": "test-device-bgp", "primitive_type": "bgp_neighbor"}],
            vrf_name="FINANCE",
            affected_devices=[device],
        )

        mock_ctrl.return_value = ([], True)
        mock_state.return_value = {
            "vrfs": ["FINANCE"],
            "bgp_sessions": {"FINANCE": {"state": "Idle", "prefixes": 0}},
            "prefix_count": {"FINANCE": 0},
            "acls": [],
            "ospf_neighbor_count": 0,
            "vlans": [],
        }

        result = BasicVerifier(intent).run()

        self.assertFalse(result["passed"])
        bgp_checks = [c for c in result["checks"] if c.get("check") == "bgp_established"]
        self.assertTrue(len(bgp_checks) > 0)
        self.assertFalse(bgp_checks[0]["passed"])

    def test_basic_returns_no_plan_failure(self):
        from intent_networking.verifiers.basic import BasicVerifier

        intent = self._get_intent()
        # Ensure no plan exists
        ResolutionPlan.objects.filter(intent=intent).delete()

        result = BasicVerifier(intent).run()
        self.assertFalse(result["passed"])


class TestNutsVerifier(TestCase):
    """Tests for NutsVerifier."""

    @classmethod
    def setUpTestData(cls):
        fixtures.create_intents()

    def _get_intent(self, intent_id="test-intent-001"):
        return Intent.objects.get(intent_id=intent_id)

    def _create_plan(self, intent, affected_devices=None):
        plan, _ = ResolutionPlan.objects.update_or_create(
            intent=intent,
            intent_version=intent.version,
            defaults={
                "primitives": [],
                "vrf_name": "",
                "resolved_by": "test",
            },
        )
        if affected_devices:
            plan.affected_devices.set(affected_devices)
        return plan

    def test_allowed_test_classes_contains_expected_entries(self):
        from intent_networking.verifiers.extended import ALLOWED_TEST_CLASSES

        self.assertIn("TestNapalmBgpNeighbors", ALLOWED_TEST_CLASSES)
        self.assertIn("TestNapalmInterfaces", ALLOWED_TEST_CLASSES)
        self.assertIn("TestNapalmLldpNeighbors", ALLOWED_TEST_CLASSES)
        self.assertIn("TestNetmikoCdpNeighbors", ALLOWED_TEST_CLASSES)

    def test_disallowed_test_class_is_rejected(self):
        from intent_networking.verifiers.extended import ALLOWED_TEST_CLASSES

        self.assertNotIn("MaliciousTestClass", ALLOWED_TEST_CLASSES)

    def test_platform_mappings_exist(self):
        from intent_networking.verifiers.extended import PLATFORM_TO_NAPALM, PLATFORM_TO_NETMIKO

        self.assertEqual(PLATFORM_TO_NAPALM["arista-eos"], "eos")
        self.assertEqual(PLATFORM_TO_NETMIKO["arista-eos"], "arista_eos")
        self.assertIn("cisco-ios-xe", PLATFORM_TO_NAPALM)
        self.assertIn("cisco-ios-xe", PLATFORM_TO_NETMIKO)

    def test_nuts_import_error_when_not_installed(self):
        import sys

        # Temporarily remove nuts from modules to simulate not-installed
        original_nuts = sys.modules.get("nuts")
        sys.modules["nuts"] = None
        try:
            from importlib import reload

            import intent_networking.verifiers.extended as ext_mod

            reload(ext_mod)
            intent = self._get_intent()
            with self.assertRaises(ImportError) as ctx:
                ext_mod.NutsVerifier(intent)
            self.assertIn("pip install", str(ctx.exception))
        finally:
            if original_nuts is not None:
                sys.modules["nuts"] = original_nuts
            else:
                sys.modules.pop("nuts", None)

    @patch("intent_networking.verifiers.extended.NutsVerifier._ensure_nuts_installed")
    def test_nuts_verifier_initialises_with_intent(self, _mock_check):
        from intent_networking.verifiers.extended import NutsVerifier

        intent = self._get_intent()
        self._create_plan(intent)

        verifier = NutsVerifier(intent)
        self.assertEqual(verifier.intent, intent)

    @patch("intent_networking.verifiers.extended.NutsVerifier._ensure_nuts_installed")
    def test_nuts_verifier_has_cleanup_in_execute(self, _mock_check):
        from intent_networking.verifiers.extended import NutsVerifier

        intent = self._get_intent()
        self._create_plan(intent)

        verifier = NutsVerifier(intent)

        # Verify the _execute_nuts method has cleanup (shutil.rmtree in finally)
        import inspect

        source = inspect.getsource(verifier._execute_nuts)  # pylint: disable=protected-access
        self.assertIn("finally", source)
        self.assertIn("shutil.rmtree", source)

    def test_write_test_bundle_expands_expected_to_all_devices(self):
        """expected shorthand produces one test_data entry per device with correct host and payload."""
        import tempfile

        import yaml

        from intent_networking.verifiers.extended import NutsVerifier

        devices = [MagicMock(name="sw01"), MagicMock(name="sw02"), MagicMock(name="sw03")]
        for d in devices:
            d.name = d.name  # MagicMock sets .name on __init__ — explicitly set it

        devices[0].name = "sw01"
        devices[1].name = "sw02"
        devices[2].name = "sw03"

        bundles = [
            {
                "test_class": "TestNapalmConfig",
                "label": "Verify NTP",
                "expected": [{"config_snippet": "ntp server 10.0.0.1"}],
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            bundle_path = f.name

        NutsVerifier._write_test_bundle(bundle_path, bundles, devices)  # pylint: disable=protected-access

        with open(bundle_path, encoding="utf-8") as f:
            result = yaml.safe_load(f)

        self.assertEqual(len(result), 1)
        test_data = result[0]["test_data"]
        self.assertEqual(len(test_data), 3)
        hosts = [entry["host"] for entry in test_data]
        self.assertIn("sw01", hosts)
        self.assertIn("sw02", hosts)
        self.assertIn("sw03", hosts)
        for entry in test_data:
            self.assertEqual(entry["expected"], [{"config_snippet": "ntp server 10.0.0.1"}])

    def test_write_test_bundle_uses_explicit_test_data_unchanged(self):
        """When test_data is provided (no expected), it is written as-is."""
        import tempfile

        import yaml

        from intent_networking.verifiers.extended import NutsVerifier

        explicit_test_data = [
            {"host": "sw01", "expected": [{"local_port": "Ethernet1", "neighbor": "spine-01"}]},
            {"host": "sw02", "expected": [{"local_port": "Ethernet1", "neighbor": "spine-02"}]},
        ]
        bundles = [
            {
                "test_class": "TestNapalmLldpNeighbors",
                "test_data": explicit_test_data,
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            bundle_path = f.name

        NutsVerifier._write_test_bundle(bundle_path, bundles, devices=[])  # pylint: disable=protected-access

        with open(bundle_path, encoding="utf-8") as f:
            result = yaml.safe_load(f)

        self.assertEqual(result[0]["test_data"], explicit_test_data)

    def test_write_test_bundle_warns_when_both_expected_and_test_data_present(self):
        """When both expected and test_data are defined, test_data wins and a warning is logged."""
        import logging
        import tempfile

        from intent_networking.verifiers.extended import NutsVerifier

        explicit_test_data = [{"host": "sw01", "expected": [{"config_snippet": "ntp server 1.1.1.1"}]}]
        bundles = [
            {
                "test_class": "TestNapalmConfig",
                "label": "Ambiguous bundle",
                "expected": [{"config_snippet": "ntp server 10.0.0.1"}],
                "test_data": explicit_test_data,
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            bundle_path = f.name

        with self.assertLogs("intent_networking.verifiers.extended", level=logging.WARNING) as log:
            NutsVerifier._write_test_bundle(bundle_path, bundles, devices=[])  # pylint: disable=protected-access

        self.assertTrue(any("'test_data' takes precedence" in msg for msg in log.output))

        import yaml

        with open(bundle_path, encoding="utf-8") as f:
            result = yaml.safe_load(f)

        self.assertEqual(result[0]["test_data"], explicit_test_data)


class TestAutoEscalation(TestCase):
    """Tests for auto-escalation from basic to NUTS."""

    @classmethod
    def setUpTestData(cls):
        fixtures.create_intents()

    def _get_intent(self, intent_id="test-intent-001"):
        return Intent.objects.get(intent_id=intent_id)

    def _create_plan(self, intent):
        plan, _ = ResolutionPlan.objects.update_or_create(
            intent=intent,
            intent_version=intent.version,
            defaults={
                "primitives": [],
                "vrf_name": "",
                "resolved_by": "test",
            },
        )
        return plan

    @patch("intent_networking.jobs.IntentVerificationJob._run_nuts")
    @patch("intent_networking.verifiers.basic.BasicVerifier.run")
    @patch("intent_networking.jobs.notify_slack")
    def test_basic_with_warnings_triggers_nuts(self, mock_slack, mock_basic_run, mock_nuts):
        intent = self._get_intent()
        self._create_plan(intent)

        mock_basic_run.return_value = {
            "passed": True,
            "has_warnings": True,
            "warning_reasons": ["Latency near threshold"],
            "checks": [],
        }
        mock_nuts.return_value = {
            "passed": True,
            "has_warnings": False,
            "warning_reasons": [],
            "checks": [],
            "nuts_output": "",
        }

        from intent_networking.jobs import IntentVerificationJob

        job = IntentVerificationJob()
        job.logger = MagicMock()
        job.run(intent_id=intent.intent_id, triggered_by="test")

        mock_nuts.assert_called_once_with(intent)

    @patch("intent_networking.verifiers.basic.BasicVerifier.run")
    @patch("intent_networking.jobs.notify_slack")
    def test_basic_without_warnings_does_not_trigger_nuts(self, mock_slack, mock_basic_run):
        intent = self._get_intent()
        self._create_plan(intent)

        mock_basic_run.return_value = {
            "passed": True,
            "has_warnings": False,
            "warning_reasons": [],
            "checks": [],
        }

        from intent_networking.jobs import IntentVerificationJob

        job = IntentVerificationJob()
        job.logger = MagicMock()

        with patch("intent_networking.jobs.IntentVerificationJob._run_nuts") as mock_nuts:
            job.run(intent_id=intent.intent_id, triggered_by="test")
            mock_nuts.assert_not_called()

    @patch("intent_networking.jobs.IntentVerificationJob._run_nuts")
    @patch("intent_networking.verifiers.basic.BasicVerifier.run")
    @patch("intent_networking.jobs.notify_slack")
    def test_escalation_reason_stored_in_verification_result(self, mock_slack, mock_basic_run, mock_nuts):
        intent = self._get_intent()
        self._create_plan(intent)

        mock_basic_run.return_value = {
            "passed": True,
            "has_warnings": True,
            "warning_reasons": ["BGP prefix count above baseline"],
            "checks": [],
        }
        mock_nuts.return_value = {
            "passed": True,
            "has_warnings": False,
            "warning_reasons": [],
            "checks": [],
            "nuts_output": "",
        }

        from intent_networking.jobs import IntentVerificationJob

        job = IntentVerificationJob()
        job.logger = MagicMock()
        job.run(intent_id=intent.intent_id, triggered_by="test")

        vr = VerificationResult.objects.filter(intent=intent).order_by("-verified_at").first()
        self.assertIsNotNone(vr)
        self.assertEqual(vr.verification_engine, "escalated")
        self.assertIn("BGP prefix count above baseline", vr.escalation_reason)
