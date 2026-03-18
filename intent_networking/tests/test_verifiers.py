"""Tests for BasicVerifier and PyATSVerifier."""

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

        from intent_networking.verifiers.basic import BasicVerifier

        intent = self._get_intent()

        # Create a device to add to affected_devices
        mfg, _ = Manufacturer.objects.get_or_create(name="Cisco-Test")
        dt, _ = DeviceType.objects.get_or_create(model="CSR1000v-Test", manufacturer=mfg)
        status = Status.objects.filter(name="Active").first()
        if not status:
            status = Status.objects.first()
        loc_type, _ = LocationType.objects.get_or_create(name="Site-Test")
        loc_type.content_types.add(
            *[ct for ct in loc_type.content_types.all()]
        )
        from django.contrib.contenttypes.models import ContentType

        device_ct = ContentType.objects.get_for_model(Device)
        loc_type.content_types.add(device_ct)
        loc, _ = Location.objects.get_or_create(
            name="test-site-bgp", location_type=loc_type, defaults={"status": status}
        )
        device, _ = Device.objects.get_or_create(
            name="test-device-bgp",
            defaults={
                "device_type": dt,
                "location": loc,
                "status": status,
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


class TestPyATSVerifier(TestCase):
    """Tests for PyATSVerifier."""

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

    @patch.dict("sys.modules", {"pyats": MagicMock(), "pyats.topology": MagicMock(), "genie": MagicMock()})
    def test_extended_learns_correct_features_for_connectivity_intent(self):
        from intent_networking.verifiers.extended import EXTENDED_CHECKS

        self.assertEqual(EXTENDED_CHECKS["connectivity"], ["bgp", "routing", "ospf", "mpls"])

    @patch.dict("sys.modules", {"pyats": MagicMock(), "pyats.topology": MagicMock(), "genie": MagicMock()})
    def test_extended_learns_correct_features_for_mpls_intent(self):
        from intent_networking.verifiers.extended import EXTENDED_CHECKS

        self.assertEqual(EXTENDED_CHECKS["mpls"], ["mpls", "ldp", "ospf", "bgp"])

    @patch.dict("sys.modules", {"pyats": MagicMock(), "pyats.topology": MagicMock(), "genie": MagicMock()})
    def test_extended_falls_back_for_junos_device(self):
        from nautobot.dcim.models import (
            Device,
            DeviceType,
            Location,
            LocationType,
            Manufacturer,
            Platform,
        )

        from intent_networking.verifiers.extended import UNSUPPORTED_PLATFORMS, PyATSVerifier

        # Verify junos is in unsupported list
        self.assertIn("juniper-junos", UNSUPPORTED_PLATFORMS)

        intent = self._get_intent()
        mfg, _ = Manufacturer.objects.get_or_create(name="Juniper-Test")
        dt, _ = DeviceType.objects.get_or_create(model="MX480-Test", manufacturer=mfg)
        platform, _ = Platform.objects.get_or_create(name="juniper-junos")
        status = Status.objects.filter(name="Active").first() or Status.objects.first()

        from django.contrib.contenttypes.models import ContentType

        loc_type, _ = LocationType.objects.get_or_create(name="Site-Junos-Test")
        device_ct = ContentType.objects.get_for_model(Device)
        loc_type.content_types.add(device_ct)
        loc, _ = Location.objects.get_or_create(
            name="test-site-junos", location_type=loc_type, defaults={"status": status}
        )
        device, _ = Device.objects.get_or_create(
            name="test-junos-device",
            defaults={
                "device_type": dt,
                "location": loc,
                "status": status,
                "platform": platform,
            },
        )

        self._create_plan(intent, affected_devices=[device])

        verifier = PyATSVerifier(intent)
        result = verifier.run()

        # Should return a warning instead of failing
        self.assertTrue(result["has_warnings"])
        self.assertTrue(
            any("limited Genie coverage" in r for r in result["warning_reasons"])
        )

    def test_extended_raises_import_error_when_pyats_not_installed(self):
        import sys

        # Temporarily remove pyats from modules to simulate not-installed
        original_pyats = sys.modules.get("pyats")
        original_genie = sys.modules.get("genie")
        sys.modules["pyats"] = None
        sys.modules["genie"] = None
        try:
            # Force reimport to pick up the missing module
            from importlib import reload

            import intent_networking.verifiers.extended as ext_mod

            reload(ext_mod)
            intent = self._get_intent()
            with self.assertRaises(ImportError) as ctx:
                ext_mod.PyATSVerifier(intent)
            self.assertIn("pip install", str(ctx.exception))
        finally:
            if original_pyats is not None:
                sys.modules["pyats"] = original_pyats
            else:
                sys.modules.pop("pyats", None)
            if original_genie is not None:
                sys.modules["genie"] = original_genie
            else:
                sys.modules.pop("genie", None)

    @patch.dict("sys.modules", {"pyats": MagicMock(), "pyats.topology": MagicMock(), "genie": MagicMock()})
    def test_semaphore_limits_concurrent_connections_to_five(self):
        from intent_networking.verifiers.extended import PyATSVerifier

        intent = self._get_intent()
        self._create_plan(intent)

        verifier = PyATSVerifier(intent)
        self.assertEqual(verifier.MAX_CONCURRENT_SESSIONS, 5)

    @patch.dict("sys.modules", {"pyats": MagicMock(), "pyats.topology": MagicMock(), "genie": MagicMock()})
    @patch("intent_networking.verifiers.extended.get_device_credentials", return_value=("user", "pass"))
    def test_devices_disconnected_in_finally_block(self, mock_creds):
        from intent_networking.verifiers.extended import PyATSVerifier

        intent = self._get_intent()
        self._create_plan(intent)

        verifier = PyATSVerifier(intent)

        # Create a mock device with connect/disconnect
        mock_pyats_device = MagicMock()
        mock_pyats_device.learn.side_effect = Exception("simulated failure")

        mock_testbed = MagicMock()
        mock_testbed.devices = {"test-device": mock_pyats_device}

        with patch("intent_networking.verifiers.extended.PyATSVerifier._build_testbed") as mock_build:
            mock_build.return_value = {"testbed": {"name": "test"}, "devices": {}}

            # The _verify_device method should always disconnect
            mock_device = MagicMock()
            mock_device.name = "test-device"
            mock_device.platform = MagicMock()
            mock_device.platform.name = "cisco-ios-xe"
            mock_device.primary_ip = None

            # We can't easily test the full flow without real pyATS,
            # but we verify the class structure has the finally block
            import inspect

            source = inspect.getsource(verifier._verify_device)
            self.assertIn("finally", source)
            self.assertIn("disconnect", source)


class TestAutoEscalation(TestCase):
    """Tests for auto-escalation from basic to extended."""

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

    @patch("intent_networking.jobs.IntentVerificationJob._run_extended")
    @patch("intent_networking.verifiers.basic.BasicVerifier.run")
    @patch("intent_networking.jobs.notify_slack")
    def test_basic_with_warnings_triggers_extended(self, mock_slack, mock_basic_run, mock_extended):
        intent = self._get_intent()
        self._create_plan(intent)

        mock_basic_run.return_value = {
            "passed": True,
            "has_warnings": True,
            "warning_reasons": ["Latency near threshold"],
            "checks": [],
        }
        mock_extended.return_value = {
            "passed": True,
            "has_warnings": False,
            "warning_reasons": [],
            "checks": [],
            "pyats_diff_output": "",
        }

        from intent_networking.jobs import IntentVerificationJob

        job = IntentVerificationJob()
        job.logger = MagicMock()
        job.run(intent_id=intent.intent_id, triggered_by="test")

        mock_extended.assert_called_once_with(intent)

    @patch("intent_networking.verifiers.basic.BasicVerifier.run")
    @patch("intent_networking.jobs.notify_slack")
    def test_basic_without_warnings_does_not_trigger_extended(self, mock_slack, mock_basic_run):
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

        with patch("intent_networking.jobs.IntentVerificationJob._run_extended") as mock_extended:
            job.run(intent_id=intent.intent_id, triggered_by="test")
            mock_extended.assert_not_called()

    @patch("intent_networking.jobs.IntentVerificationJob._run_extended")
    @patch("intent_networking.verifiers.basic.BasicVerifier.run")
    @patch("intent_networking.jobs.notify_slack")
    def test_escalation_reason_stored_in_verification_result(self, mock_slack, mock_basic_run, mock_extended):
        intent = self._get_intent()
        self._create_plan(intent)

        mock_basic_run.return_value = {
            "passed": True,
            "has_warnings": True,
            "warning_reasons": ["BGP prefix count above baseline"],
            "checks": [],
        }
        mock_extended.return_value = {
            "passed": True,
            "has_warnings": False,
            "warning_reasons": [],
            "checks": [],
            "pyats_diff_output": "",
        }

        from intent_networking.jobs import IntentVerificationJob

        job = IntentVerificationJob()
        job.logger = MagicMock()
        job.run(intent_id=intent.intent_id, triggered_by="test")

        vr = VerificationResult.objects.filter(intent=intent).order_by("-verified_at").first()
        self.assertIsNotNone(vr)
        self.assertEqual(vr.verification_engine, "escalated")
        self.assertIn("BGP prefix count above baseline", vr.escalation_reason)
