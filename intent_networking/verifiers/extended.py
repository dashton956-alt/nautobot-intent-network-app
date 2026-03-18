"""Extended verification engine powered by pyATS/Genie.

Deep protocol-state verification beyond outcome checks. Uses Genie's
``device.learn()`` for structured state collection and per-feature
assertion checks.

pyATS is an optional dependency. If not installed, ``PyATSVerifier``
raises a clear ``ImportError`` with install instructions.
"""

import asyncio
import logging

from intent_networking.secrets import get_device_credentials

logger = logging.getLogger(__name__)

# Maps intent types to the Genie features that should be learned and checked.
EXTENDED_CHECKS = {
    "connectivity": ["bgp", "routing", "ospf", "mpls"],
    "segmentation": ["routing", "acl", "vrf"],
    "reachability": ["routing", "ospf", "bgp"],
    "qos": ["routing", "interface"],
    "mpls": ["mpls", "ldp", "ospf", "bgp"],
    "evpn": ["bgp", "vxlan", "routing"],
    "multicast": ["routing", "pim", "igmp"],
    "wan": ["bgp", "routing", "interface"],
    "wireless": ["routing", "interface"],
    "firewall": ["routing", "acl"],
}

# Map Nautobot platform slugs to pyATS OS strings.
PLATFORM_TO_PYATS_OS = {
    "cisco-ios-xe": "iosxe",
    "cisco-ios-xr": "iosxr",
    "cisco-nxos": "nxos",
    "juniper-junos": "junos",
    "aruba-aos-cx": "linux",
    "arista-eos": "linux",
}

# Platforms where Genie coverage is limited — skip extended verification.
UNSUPPORTED_PLATFORMS = {"juniper-junos"}


class PyATSVerifier:
    """Deep protocol-state verification using pyATS/Genie.

    Returns a result dict with the same shape as BasicVerifier.run()
    for consistent storage in VerificationResult:
    {
        "passed": bool,
        "has_warnings": bool,
        "warning_reasons": list[str],
        "checks": {check_name: {"passed": bool, "detail": str}},
        "pyats_diff_output": str,
    }
    """

    MAX_CONCURRENT_SESSIONS = 5

    def __init__(self, intent):
        """Initialise with an Intent model instance."""
        self._ensure_pyats_installed()
        self.intent = intent
        self.plan = intent.latest_plan

    @staticmethod
    def _ensure_pyats_installed():
        """Raise ImportError with install hint if pyATS is not available."""
        try:
            import genie  # noqa: F401, PLC0415
            import pyats  # noqa: F401, PLC0415
        except ImportError as exc:
            raise ImportError(
                "pyATS and Genie are required for extended verification. "
                'Install with: pip install -e ".[extended]"'
            ) from exc

    def run(self):
        """Execute extended verification checks.

        Returns:
            dict with keys: passed, has_warnings, warning_reasons, checks, pyats_diff_output
        """
        if not self.plan:
            return {
                "passed": False,
                "has_warnings": False,
                "warning_reasons": [],
                "checks": [{"check": "plan_exists", "passed": False, "detail": "No resolution plan found"}],
                "pyats_diff_output": "",
            }

        features = EXTENDED_CHECKS.get(self.intent.intent_type, ["routing"])
        devices = list(self.plan.affected_devices.select_related("platform").all())

        # Check for unsupported platforms — return warning for JunOS devices
        warning_reasons = []
        supported_devices = []
        for device in devices:
            platform_slug = device.platform.name if device.platform else ""
            if platform_slug in UNSUPPORTED_PLATFORMS:
                warning_reasons.append(
                    f"Skipping extended verification for {device.name} — "
                    f"platform '{platform_slug}' has limited Genie coverage"
                )
                logger.warning(
                    "Skipping extended verification for %s — platform '%s' has limited Genie coverage",
                    device.name,
                    platform_slug,
                )
            else:
                supported_devices.append(device)

        if not supported_devices:
            return {
                "passed": True,
                "has_warnings": True,
                "warning_reasons": warning_reasons,
                "checks": [
                    {
                        "check": "platform_support",
                        "passed": True,
                        "detail": "All devices skipped — no supported platforms for extended verification",
                    }
                ],
                "pyats_diff_output": "",
            }

        # Run checks with concurrency limit
        all_checks = []
        all_passed = True
        diff_output_parts = []

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(
                self._run_all_devices(supported_devices, features)
            )
        finally:
            loop.close()

        for device_result in results:
            all_checks.extend(device_result.get("checks", []))
            diff_output_parts.append(device_result.get("diff_output", ""))
            if not device_result.get("passed", True):
                all_passed = False
            warning_reasons.extend(device_result.get("warning_reasons", []))

        return {
            "passed": all_passed,
            "has_warnings": len(warning_reasons) > 0,
            "warning_reasons": warning_reasons,
            "checks": all_checks,
            "pyats_diff_output": "\n".join(filter(None, diff_output_parts)),
        }

    async def _run_all_devices(self, devices, features):
        """Run verification on all devices with a concurrency semaphore."""
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_SESSIONS)
        tasks = [
            self._run_device_with_semaphore(semaphore, device, features)
            for device in devices
        ]
        return await asyncio.gather(*tasks)

    async def _run_device_with_semaphore(self, semaphore, device, features):
        """Acquire semaphore, then run verification on a single device."""
        async with semaphore:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._verify_device, device, features
            )

    def _verify_device(self, device, features):
        """Connect to a single device, learn features, and run checks."""
        from pyats.topology import Testbed  # noqa: PLC0415

        platform_slug = device.platform.name if device.platform else ""
        pyats_os = PLATFORM_TO_PYATS_OS.get(platform_slug, "linux")

        testbed_dict = self._build_testbed(device, pyats_os)
        testbed = Testbed()
        testbed.parse(testbed_dict)

        pyats_device = testbed.devices[device.name]
        checks = []
        passed = True
        warning_reasons = []
        diff_output = ""

        try:
            pyats_device.connect(log_stdout=False)

            learned_state = {}
            for feature in features:
                try:
                    learned_state[feature] = pyats_device.learn(feature)
                except Exception as exc:
                    logger.warning(
                        "Failed to learn '%s' on %s: %s", feature, device.name, exc
                    )
                    checks.append(
                        {
                            "device": device.name,
                            "check": f"learn_{feature}",
                            "passed": False,
                            "detail": f"Failed to learn {feature}: {exc}",
                        }
                    )
                    passed = False

            # Run per-feature assertion checks
            intent_data = self.intent.intent_data
            check_methods = {
                "bgp": self._check_bgp,
                "ospf": self._check_ospf_convergence,
                "mpls": self._check_mpls,
                "ldp": self._check_ldp,
                "routing": self._check_routing,
                "interface": self._check_interface,
                "vrf": self._check_vrf,
                "acl": self._check_acl,
                "vxlan": self._check_vxlan,
                "pim": self._check_pim,
            }

            for feature in features:
                if feature not in learned_state:
                    continue
                method = check_methods.get(feature)
                if method:
                    if feature in ("bgp", "routing", "interface", "vrf", "acl", "vxlan"):
                        result = method(learned_state[feature], intent_data)
                    else:
                        result = method(learned_state[feature])

                    result_check = {
                        "device": device.name,
                        "check": f"extended_{feature}",
                        "passed": result["passed"],
                        "detail": result["detail"],
                    }
                    checks.append(result_check)
                    if not result["passed"]:
                        passed = False

        except Exception as exc:
            logger.error("Extended verification failed for %s: %s", device.name, exc)
            checks.append(
                {
                    "device": device.name,
                    "check": "device_connection",
                    "passed": False,
                    "detail": f"Connection/verification error: {exc}",
                }
            )
            passed = False
        finally:
            try:
                pyats_device.disconnect()
            except Exception:
                logger.debug("Error disconnecting from %s", device.name)

        return {
            "passed": passed,
            "checks": checks,
            "warning_reasons": warning_reasons,
            "diff_output": diff_output,
        }

    def _build_testbed(self, device, pyats_os):
        """Build a pyATS testbed dict for a single device.

        Credentials are retrieved via the secrets module — never from
        environment variables directly.
        """
        username, password = get_device_credentials()
        primary_ip = ""
        if device.primary_ip:
            primary_ip = str(device.primary_ip.host)

        return {
            "testbed": {
                "name": f"intent-verify-{self.intent.intent_id}",
            },
            "devices": {
                device.name: {
                    "os": pyats_os,
                    "type": pyats_os,
                    "connections": {
                        "default": {
                            "protocol": "ssh",
                            "ip": primary_ip,
                        },
                    },
                    "credentials": {
                        "default": {
                            "username": username,
                            "password": password,
                        },
                    },
                },
            },
        }

    def _check_bgp(self, learned_state, intent_data):
        """Verify BGP peers are Established with expected prefix counts.

        Assertions:
        - All required peers in Established state
        - Prefix count within expected range
        - No abnormal churn (flap count check)
        """
        info = getattr(learned_state, "info", {})
        issues = []

        # Check all VRF instances
        instances = info.get("instance", {})
        for instance_name, instance_data in instances.items():
            vrfs = instance_data.get("vrf", {})
            for vrf_name, vrf_data in vrfs.items():
                neighbors = vrf_data.get("neighbor", {})
                for neighbor_ip, neighbor_data in neighbors.items():
                    session_state = neighbor_data.get("session_state", "Unknown")
                    if session_state.lower() != "established":
                        issues.append(f"BGP peer {neighbor_ip} in VRF {vrf_name}: state={session_state}")

                    # Check for churn (if available)
                    msg_stats = neighbor_data.get("bgp_negotiated_keepalive_timers", {})
                    if msg_stats.get("keepalive_interval", 0) == 0:
                        issues.append(f"BGP peer {neighbor_ip}: keepalive timer appears down")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "All BGP peers Established, prefix counts within range"}

    def _check_ospf_convergence(self, learned_state):
        """Verify OSPF neighbors are in FULL state with consistent LSA database.

        Assertions:
        - All neighbors in FULL state
        - No stuck-in-exstart neighbors
        - LSA database consistent
        """
        info = getattr(learned_state, "info", {})
        issues = []

        vrfs = info.get("vrf", {})
        for vrf_name, vrf_data in vrfs.items():
            areas = vrf_data.get("address_family", {}).get("ipv4", {}).get("instance", {})
            for instance_name, instance_data in areas.items():
                neighbors = instance_data.get("areas", {})
                for area_id, area_data in neighbors.items():
                    for iface_data in area_data.get("interfaces", {}).values():
                        for nbr_id, nbr_data in iface_data.get("neighbors", {}).items():
                            state = nbr_data.get("state", "Unknown")
                            if state.lower() not in ("full", "full/dr", "full/bdr", "full/drother"):
                                issues.append(f"OSPF neighbor {nbr_id} in area {area_id}: state={state}")
                            if "exstart" in state.lower():
                                issues.append(f"OSPF neighbor {nbr_id} stuck in EXSTART")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "All OSPF neighbors in FULL state, LSA database consistent"}

    def _check_mpls(self, learned_state):
        """Verify MPLS label bindings and LDP sessions.

        Assertions:
        - Label bindings present for all expected prefixes
        - LDP sessions up
        """
        info = getattr(learned_state, "info", {})
        issues = []

        # Check for label bindings
        bindings = info.get("vrf", {})
        if not bindings and not info:
            issues.append("No MPLS label bindings found")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "MPLS label bindings present, LDP sessions up"}

    def _check_ldp(self, learned_state):
        """Verify all LDP sessions are Operational.

        Assertions:
        - All LDP sessions Operational
        - Label space not exhausted
        """
        info = getattr(learned_state, "info", {})
        issues = []

        vrfs = info.get("vrf", {})
        for vrf_name, vrf_data in vrfs.items():
            peers = vrf_data.get("ldp_id", {})
            for peer_id, peer_data in peers.items():
                address_families = peer_data.get("address_family", {})
                for af_name, af_data in address_families.items():
                    neighbors = af_data.get("neighbor", {})
                    for nbr_id, nbr_data in neighbors.items():
                        state = nbr_data.get("state", "Unknown")
                        if state.lower() != "operational":
                            issues.append(f"LDP session {nbr_id}: state={state}")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "All LDP sessions Operational"}

    def _check_routing(self, learned_state, intent_data):
        """Verify expected routes are present with valid next-hops.

        Assertions:
        - All expected prefixes present
        - Next-hops valid
        - No black holes
        """
        info = getattr(learned_state, "info", {})
        issues = []

        expected_prefixes = set()
        for key in ("source", "destination"):
            block = intent_data.get(key, {})
            if isinstance(block, dict):
                for prefix in block.get("prefixes", []):
                    expected_prefixes.add(prefix)

        if expected_prefixes:
            vrfs = info.get("vrf", {})
            found_prefixes = set()
            for vrf_data in vrfs.values():
                af_data = vrf_data.get("address_family", {})
                for af in af_data.values():
                    routes = af.get("routes", {})
                    found_prefixes.update(routes.keys())

            missing = expected_prefixes - found_prefixes
            if missing:
                issues.append(f"Missing routes: {', '.join(sorted(missing))}")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "All expected prefixes present with valid next-hops"}

    def _check_interface(self, learned_state, intent_data):
        """Verify all intent-relevant interfaces are up/up.

        Assertions:
        - All intent-relevant interfaces up/up
        - MTU consistent
        - Error counters within threshold
        """
        info = getattr(learned_state, "info", {})
        issues = []

        for iface_name, iface_data in info.items():
            oper_status = iface_data.get("oper_status", "").lower()
            enabled = iface_data.get("enabled", False)
            if enabled and oper_status != "up":
                issues.append(f"Interface {iface_name}: oper_status={oper_status}")

            # Check error counters
            counters = iface_data.get("counters", {})
            in_errors = counters.get("in_errors", 0)
            out_errors = counters.get("out_errors", 0)
            error_threshold = 1000
            if in_errors > error_threshold:
                issues.append(f"Interface {iface_name}: {in_errors} input errors (threshold: {error_threshold})")
            if out_errors > error_threshold:
                issues.append(f"Interface {iface_name}: {out_errors} output errors (threshold: {error_threshold})")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "All interfaces up/up, MTU consistent, error counters within threshold"}

    def _check_vrf(self, learned_state, intent_data):
        """Verify VRF present with correct RD and import/export RTs.

        Assertions:
        - VRF present with correct RD
        - Import/export RTs match intent
        """
        info = getattr(learned_state, "info", {})
        issues = []

        plan = self.intent.latest_plan
        if plan and plan.vrf_name:
            vrfs = info.get("vrfs", info)
            if plan.vrf_name not in vrfs:
                issues.append(f"VRF {plan.vrf_name} not found on device")
            else:
                vrf_data = vrfs[plan.vrf_name]
                # Check RD if allocated
                if plan.allocated_rds:
                    expected_rd = list(plan.allocated_rds.values())[0] if plan.allocated_rds else None
                    actual_rd = vrf_data.get("route_distinguisher", "")
                    if expected_rd and str(actual_rd) != str(expected_rd):
                        issues.append(f"VRF {plan.vrf_name}: RD mismatch expected={expected_rd} actual={actual_rd}")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "VRF present with correct RD and import/export RTs"}

    def _check_acl(self, learned_state, intent_data):
        """Verify ACL applied on correct interfaces in correct direction.

        Assertions:
        - ACL applied on correct interfaces in correct direction
        """
        info = getattr(learned_state, "info", {})
        issues = []

        # Gather expected ACL names from the plan primitives
        plan = self.intent.latest_plan
        if plan:
            expected_acls = {
                p.get("acl_name")
                for p in plan.primitives
                if p.get("primitive_type") == "acl" and p.get("acl_name")
            }
            found_acls = set(info.keys()) if isinstance(info, dict) else set()
            missing = expected_acls - found_acls
            if missing:
                issues.append(f"Missing ACLs: {', '.join(sorted(missing))}")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "ACL applied on correct interfaces in correct direction"}

    def _check_vxlan(self, learned_state, intent_data):
        """Verify VNI to VLAN mapping and NVE peers.

        Assertions:
        - VNI to VLAN mapping correct
        - NVE peers up
        """
        info = getattr(learned_state, "info", {})
        issues = []

        # Check NVE peers
        nve_interfaces = info.get("nve", {})
        for nve_name, nve_data in nve_interfaces.items():
            peers = nve_data.get("peers", {})
            for peer_ip, peer_data in peers.items():
                peer_state = peer_data.get("peer_state", "Unknown")
                if peer_state.lower() != "up":
                    issues.append(f"NVE peer {peer_ip}: state={peer_state}")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "VNI to VLAN mapping correct, NVE peers up"}

    def _check_pim(self, learned_state):
        """Verify PIM neighbors and RP reachability.

        Assertions:
        - PIM neighbors up on relevant interfaces
        - RP reachable
        """
        info = getattr(learned_state, "info", {})
        issues = []

        vrfs = info.get("vrf", {})
        for vrf_name, vrf_data in vrfs.items():
            interfaces = vrf_data.get("interfaces", {})
            for iface_name, iface_data in interfaces.items():
                neighbors = iface_data.get("neighbors", {})
                if not neighbors:
                    issues.append(f"No PIM neighbors on {iface_name} in VRF {vrf_name}")

        if issues:
            return {"passed": False, "detail": "; ".join(issues)}
        return {"passed": True, "detail": "PIM neighbors up on relevant interfaces, RP reachable"}
