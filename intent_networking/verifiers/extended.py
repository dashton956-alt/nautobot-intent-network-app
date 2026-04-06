"""Extended verification engine powered by NUTS (Network Unit Testing System).

Runs user-defined NUTS test bundles declared in the intent YAML's
``verification.tests`` section.  Each test entry maps to an allowed
NUTS test class (NAPALM or Netmiko-based); arbitrary ``test_module``
paths are rejected to prevent code-injection.

NUTS is an optional dependency.  If not installed, ``NutsVerifier``
raises a clear ``ImportError`` with install instructions.
"""

import json
import logging
import os
import shutil
import tempfile

import yaml

from intent_networking.secrets import get_device_credentials

logger = logging.getLogger(__name__)

# ── Allowed test classes (whitelist) ────────────────────────────────────────
# Only built-in NUTS test classes are allowed.  ``test_module`` is never
# accepted from user YAML to prevent arbitrary code execution.

ALLOWED_TEST_CLASSES = frozenset(
    {
        # NAPALM-based
        "TestNapalmBgpNeighbors",
        "TestNapalmBgpNeighborsCount",
        "TestNapalmArp",
        "TestNapalmArpRange",
        "TestNapalmInterfaces",
        "TestNapalmLldpNeighbors",
        "TestNapalmLldpNeighborsCount",
        "TestNapalmPing",
        "TestNapalmConfig",
        "TestNapalmUsers",
        "TestNapalmOnlyDefinedUsersExist",
        "TestNapalmVlans",
        "TestNapalmInterfaceInVlan",
        "TestNapalmOnlyDefinedVlansExist",
        "TestNapalmNetworkInstances",
        # Netmiko-based (require ntc-templates)
        "TestNetmikoCdpNeighbors",
        "TestNetmikoCdpNeighborsCount",
        "TestNetmikoOspfNeighbors",
        "TestNetmikoOspfNeighborsCount",
        "TestNetmikoIperf",
    }
)

# Map Nautobot platform slugs → NAPALM driver names used in Nornir inventory.
PLATFORM_TO_NAPALM = {
    "arista-eos": "eos",
    "cisco-ios-xe": "ios",
    "cisco-ios-xr": "iosxr",
    "cisco-nxos": "nxos",
    "juniper-junos": "junos",
    "nokia-sros": "sros",
    "aruba-aos-cx": "aoscx",
}

# Map Nautobot platform slugs → Netmiko device types.
PLATFORM_TO_NETMIKO = {
    "arista-eos": "arista_eos",
    "cisco-ios-xe": "cisco_ios",
    "cisco-ios-xr": "cisco_xr",
    "cisco-nxos": "cisco_nxos",
    "juniper-junos": "juniper_junos",
    "nokia-sros": "nokia_sros",
    "aruba-aos-cx": "aruba_osswitch",
}


class NutsVerifier:
    """Run NUTS test bundles defined in the intent YAML.

    Returns a result dict with the same shape as BasicVerifier.run()
    for consistent storage in VerificationResult::

        {
            "passed": bool,
            "has_warnings": bool,
            "warning_reasons": list[str],
            "checks": list[dict],
            "nuts_output": str,
        }
    """

    def __init__(self, intent):
        """Initialise with an Intent model instance."""
        self._ensure_nuts_installed()
        self.intent = intent
        self.plan = intent.latest_plan

    @staticmethod
    def _ensure_nuts_installed():
        """Raise ImportError with install hint if NUTS is not available."""
        try:
            __import__("nuts")
        except ImportError as exc:
            raise ImportError("NUTS is required for extended verification. Install with: pip install nuts") from exc

    def run(self):
        """Execute NUTS test bundles from the intent's verification.tests.

        Returns:
            dict with keys: passed, has_warnings, warning_reasons, checks, nuts_output
        """
        if not self.plan:
            return {
                "passed": False,
                "has_warnings": False,
                "warning_reasons": [],
                "checks": [{"check": "plan_exists", "passed": False, "detail": "No resolution plan found"}],
                "nuts_output": "",
            }

        intent_data = self.intent.intent_data or {}
        verification_block = intent_data.get("verification", {})
        test_bundles = verification_block.get("tests", [])

        if not test_bundles:
            return {
                "passed": True,
                "has_warnings": True,
                "warning_reasons": [
                    (
                        "No NUTS test bundles defined in verification.tests —"
                        " add test definitions to your intent YAML"
                    )
                ],
                "checks": [
                    {
                        "check": "nuts_tests_defined",
                        "passed": True,
                        "detail": "No test bundles defined — skipped",
                    }
                ],
                "nuts_output": "",
            }

        # Validate all test classes against allowlist
        warning_reasons = []
        validated_bundles = []
        for bundle in test_bundles:
            test_class = bundle.get("test_class", "")

            # Reject test_module — only built-in classes allowed
            if "test_module" in bundle:
                warning_reasons.append(
                    f"Rejected test_module in bundle for '{test_class}' — "
                    "only built-in NUTS test classes are allowed"
                )
                logger.warning(
                    "Rejected test_module in NUTS bundle for intent %s: %s",
                    self.intent.intent_id,
                    bundle.get("test_module"),
                )
                continue

            if test_class not in ALLOWED_TEST_CLASSES:
                warning_reasons.append(
                    f"Unknown test class '{test_class}' — skipped. "
                    f"Allowed: {', '.join(sorted(ALLOWED_TEST_CLASSES))}"
                )
                logger.warning(
                    "Rejected unknown NUTS test class '%s' for intent %s",
                    test_class,
                    self.intent.intent_id,
                )
                continue

            validated_bundles.append(bundle)

        if not validated_bundles:
            return {
                "passed": False,
                "has_warnings": True,
                "warning_reasons": warning_reasons,
                "checks": [
                    {
                        "check": "nuts_validation",
                        "passed": False,
                        "detail": "All test bundles were rejected during validation",
                    }
                ],
                "nuts_output": "",
            }

        # Build nornir inventory from the intent's affected devices
        devices = list(self.plan.affected_devices.select_related("platform").all())
        if not devices:
            return {
                "passed": True,
                "has_warnings": True,
                "warning_reasons": ["No affected devices in resolution plan"],
                "checks": [
                    {
                        "check": "devices_found",
                        "passed": True,
                        "detail": "No devices to test — skipped",
                    }
                ],
                "nuts_output": "",
            }

        # Run pytest with NUTS
        try:
            result = self._execute_nuts(validated_bundles, devices)
        except Exception as exc:
            logger.error("NUTS verification failed for %s: %s", self.intent.intent_id, exc)
            return {
                "passed": False,
                "has_warnings": bool(warning_reasons),
                "warning_reasons": warning_reasons,
                "checks": [
                    {
                        "check": "nuts_execution",
                        "passed": False,
                        "detail": f"NUTS execution error: {exc}",
                    }
                ],
                "nuts_output": "",
            }

        result["warning_reasons"] = warning_reasons + result.get("warning_reasons", [])
        result["has_warnings"] = len(result["warning_reasons"]) > 0
        return result

    def _execute_nuts(self, test_bundles, devices):
        """Write temp files, invoke pytest, parse results."""
        import pytest  # noqa: PLC0415

        tmpdir = tempfile.mkdtemp(prefix="nuts-verify-")

        try:
            # Write Nornir inventory
            inventory_dir = os.path.join(tmpdir, "inventory")
            os.makedirs(inventory_dir)
            self._write_nornir_inventory(inventory_dir, devices)

            # Write nornir config
            nr_config_path = os.path.join(tmpdir, "nr-config.yaml")
            self._write_nornir_config(nr_config_path, inventory_dir)

            # Write test bundle YAML
            bundle_path = os.path.join(tmpdir, "test_bundle.yaml")
            self._write_test_bundle(bundle_path, test_bundles)

            # Write conftest.py pointing to our nornir config
            conftest_path = os.path.join(tmpdir, "conftest.py")
            self._write_conftest(conftest_path, nr_config_path)

            # Run pytest programmatically with JSON report
            json_report_path = os.path.join(tmpdir, "results.json")
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                exit_code = pytest.main(
                    [
                        bundle_path,
                        f"--json-report-file={json_report_path}",
                        "--json-report",
                        "--no-header",
                        "-q",
                        "--tb=short",
                        "--override-ini=addopts=",
                    ],
                    plugins=[],
                )
            finally:
                os.chdir(original_cwd)

            # Parse results
            return self._parse_results(json_report_path, exit_code)

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _write_nornir_inventory(self, inventory_dir, devices):
        """Write hosts.yaml and defaults.yaml for the Nornir inventory."""
        username, password = get_device_credentials()
        hosts = {}

        for device in devices:
            platform_slug = device.platform.name if device.platform else ""
            primary_ip = ""
            if device.primary_ip:
                primary_ip = str(device.primary_ip.host)

            napalm_driver = PLATFORM_TO_NAPALM.get(platform_slug, "eos")
            netmiko_type = PLATFORM_TO_NETMIKO.get(platform_slug, "linux")

            hosts[device.name] = {
                "hostname": primary_ip,
                "platform": napalm_driver,
                "data": {
                    "netmiko_device_type": netmiko_type,
                },
            }

        hosts_path = os.path.join(inventory_dir, "hosts.yaml")
        with open(hosts_path, "w", encoding="utf-8") as f:
            yaml.dump(hosts, f, default_flow_style=False)

        defaults = {
            "username": username,
            "password": password,
            "connection_options": {
                "napalm": {
                    "extras": {
                        "optional_args": {
                            "transport": "ssh",
                        },
                    },
                },
                "netmiko": {
                    "extras": {},
                },
            },
        }

        defaults_path = os.path.join(inventory_dir, "defaults.yaml")
        with open(defaults_path, "w", encoding="utf-8") as f:
            yaml.dump(defaults, f, default_flow_style=False)

        # Empty groups file
        groups_path = os.path.join(inventory_dir, "groups.yaml")
        with open(groups_path, "w", encoding="utf-8") as f:
            yaml.dump({}, f)

    @staticmethod
    def _write_nornir_config(config_path, inventory_dir):
        """Write nr-config.yaml for NUTS to pick up."""
        config = {
            "inventory": {
                "plugin": "SimpleInventory",
                "options": {
                    "host_file": os.path.join(inventory_dir, "hosts.yaml"),
                    "group_file": os.path.join(inventory_dir, "groups.yaml"),
                    "defaults_file": os.path.join(inventory_dir, "defaults.yaml"),
                },
            },
            "runner": {
                "plugin": "threaded",
                "options": {
                    "num_workers": 5,
                },
            },
        }

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False)

    @staticmethod
    def _write_test_bundle(bundle_path, test_bundles):
        """Write the NUTS test bundle YAML file."""
        bundles = []
        for bundle in test_bundles:
            entry = {"test_class": bundle["test_class"]}
            if bundle.get("label"):
                entry["label"] = bundle["label"]
            if bundle.get("test_execution"):
                entry["test_execution"] = bundle["test_execution"]
            entry["test_data"] = bundle.get("test_data", [])
            bundles.append(entry)

        with open(bundle_path, "w", encoding="utf-8") as f:
            yaml.dump(bundles, f, default_flow_style=False)

    @staticmethod
    def _write_conftest(conftest_path, nr_config_path):
        """Write a conftest.py that configures NUTS with the nornir config."""
        content = (
            "import pytest\n"
            "\n"
            "\n"
            "def pytest_configure(config):\n"
            f'    config.option.nuts_config = "{nr_config_path}"\n'
        )
        with open(conftest_path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _parse_results(json_report_path, exit_code):
        """Parse pytest-json-report output into our standard result dict."""
        checks = []
        passed = True
        nuts_output_lines = []

        try:
            with open(json_report_path, encoding="utf-8") as f:
                report = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "passed": exit_code == 0,
                "has_warnings": True,
                "warning_reasons": ["Could not parse NUTS JSON report"],
                "checks": [
                    {
                        "check": "nuts_report",
                        "passed": exit_code == 0,
                        "detail": f"pytest exit code: {exit_code}",
                    }
                ],
                "nuts_output": f"pytest exit code: {exit_code}",
            }

        tests = report.get("tests", [])
        skipped_count = 0
        for test in tests:
            test_id = test.get("nodeid", "unknown")
            outcome = test.get("outcome", "unknown")
            test_passed = outcome == "passed"
            duration = test.get("duration", 0)

            # Skip tests that NUTS skipped because the field wasn't in
            # test_data (e.g. mac_address, mtu, speed).  These are not
            # user-requested checks and only add noise to the results.
            if outcome == "skipped":
                skipped_count += 1
                continue

            detail_parts = [f"outcome={outcome}"]
            if duration:
                detail_parts.append(f"duration={duration:.2f}s")

            # Extract failure message if present
            call_info = test.get("call", {})
            if call_info.get("longrepr"):
                longrepr = call_info["longrepr"]
                if isinstance(longrepr, str):
                    detail_parts.append(longrepr[:200])
                elif isinstance(longrepr, dict):
                    crash = longrepr.get("crash", {})
                    if crash.get("message"):
                        detail_parts.append(crash["message"][:200])

            if not test_passed:
                passed = False

            checks.append(
                {
                    "check": test_id,
                    "passed": test_passed,
                    "detail": "; ".join(detail_parts),
                }
            )

            nuts_output_lines.append(f"{'PASS' if test_passed else 'FAILED'} {test_id}")

        # Summary line
        summary = report.get("summary", {})
        summary_parts = []
        for key in ("passed", "failed", "error"):
            count = summary.get(key, 0)
            if count:
                summary_parts.append(f"{count} {key}")
        if skipped_count:
            summary_parts.append(f"{skipped_count} skipped (not in test_data)")
        if summary_parts:
            nuts_output_lines.append(f"\nSummary: {', '.join(summary_parts)}")

        return {
            "passed": passed,
            "has_warnings": False,
            "warning_reasons": [],
            "checks": checks,
            "nuts_output": "\n".join(nuts_output_lines),
        }
