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

from intent_networking.secrets import get_credentials_for_device

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
        "TestNapalmRunningConfigContains",
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
                    "No NUTS test bundles defined in verification.tests — add test definitions to your intent YAML"
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

            # Write conftest.py to register first-party custom NUTS test classes
            conftest_path = os.path.join(tmpdir, "conftest.py")
            with open(conftest_path, "w", encoding="utf-8") as f:
                f.write(
                    "import nuts.index\n"
                    'nuts.index.default_index["TestNapalmRunningConfigContains"] = '
                    '"intent_networking.nuts_tests.running_config"\n'
                )

            # Write test bundle YAML
            bundle_path = os.path.join(tmpdir, "test_bundle.yaml")
            self._write_test_bundle(bundle_path, test_bundles, devices)

            # Run pytest programmatically with JSON report
            json_report_path = os.path.join(tmpdir, "results.json")
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                exit_code = pytest.main(
                    [
                        bundle_path,
                        f"--nornir-config={nr_config_path}",
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
        """Write hosts.yaml and defaults.yaml for the Nornir inventory.

        Credentials are resolved per device from the SecretsGroup assigned
        directly to each device in Nautobot. If a device has no SecretsGroup
        assigned, the global fallback credentials are used.
        """
        hosts = {}

        for device in devices:
            # Use platform slug for driver lookup — platform.name is the human-readable
            # label (e.g. "Arista EOS"), platform.slug is the normalised key (e.g. "arista-eos")
            # that matches the PLATFORM_TO_NAPALM/NETMIKO dicts.
            platform_slug = ""
            if device.platform:
                platform_slug = getattr(device.platform, "slug", None) or device.platform.name
            primary_ip = ""
            if device.primary_ip:
                primary_ip = str(device.primary_ip.host)

            napalm_driver = PLATFORM_TO_NAPALM.get(platform_slug, "eos")
            netmiko_type = PLATFORM_TO_NETMIKO.get(platform_slug, "linux")

            username, password = get_credentials_for_device(device)

            hosts[device.name] = {
                "hostname": primary_ip,
                "platform": napalm_driver,
                "username": username,
                "password": password,
                "connection_options": {
                    "netmiko": {
                        "platform": netmiko_type,
                        "extras": {},
                    },
                },
            }

        hosts_path = os.path.join(inventory_dir, "hosts.yaml")
        with open(hosts_path, "w", encoding="utf-8") as f:
            yaml.dump(hosts, f, default_flow_style=False)

        defaults = {
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
    def _write_test_bundle(bundle_path, test_bundles, devices=None):
        """Write the NUTS test bundle YAML file.

        If a bundle defines top-level ``expected`` instead of per-host
        ``test_data``, the expected checks are automatically expanded to
        every device in scope — so intent authors don't have to repeat
        identical checks for each host.
        """
        device_names = sorted(d.name for d in devices) if devices else []
        bundles = []
        for bundle in test_bundles:
            entry = {"test_class": bundle["test_class"]}
            if bundle.get("label"):
                entry["label"] = bundle["label"]
            if bundle.get("test_execution"):
                entry["test_execution"] = bundle["test_execution"]

            if "expected" in bundle and "test_data" in bundle:
                # Both keys present — test_data takes precedence; warn so the author
                # knows their expected shorthand is being ignored.
                logger.warning(
                    "Test bundle '%s' defines both 'expected' and 'test_data' — "
                    "'test_data' takes precedence and 'expected' is ignored. "
                    "Remove one to avoid ambiguity.",
                    bundle.get("label", bundle["test_class"]),
                )
                entry["test_data"] = bundle["test_data"]
            elif "expected" in bundle:
                # Shorthand: expand expected checks to all scoped devices.
                # For TestNapalmRunningConfigContains, each expected item is a
                # {config_snippet: ...} dict that must become a flat test_data row
                # per (device, snippet) — the NUTS parametrisation key is
                # config_snippet, not a nested expected list.
                if bundle["test_class"] == "TestNapalmRunningConfigContains":
                    snippets = [e["config_snippet"] for e in bundle["expected"] if "config_snippet" in e]
                    entry["test_data"] = [
                        {"host": name, "config_snippet": snip} for name in device_names for snip in snippets
                    ]
                else:
                    entry["test_data"] = [{"host": name, "expected": bundle["expected"]} for name in device_names]
            else:
                entry["test_data"] = bundle.get("test_data", [])

            bundles.append(entry)

        with open(bundle_path, "w", encoding="utf-8") as f:
            yaml.dump(bundles, f, default_flow_style=False)

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
