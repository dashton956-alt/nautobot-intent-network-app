"""Basic verification engine — extracted from IntentVerificationJob.

Performs outcome-focused checks via Nornir/Netmiko:
  - VRF present on affected devices
  - BGP sessions established
  - Expected prefixes received
  - ACL presence
  - VLAN presence
  - OSPF neighbors
  - Latency SLA

No behaviour changes from the original IntentVerificationJob logic —
this is a clean extraction into a standalone class.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)


def _nautobot_url():
    """Return the Nautobot URL from environment."""
    return os.environ.get("NAUTOBOT_URL", "http://localhost:8080")


class BasicVerifier:
    """Outcome-focused verification using Nornir + Netmiko.

    Returns a result dict compatible with VerificationResult storage:
    {
        "passed": bool,
        "has_warnings": bool,
        "warning_reasons": list[str],
        "checks": [{"device": str, "check": str, "passed": bool, "detail": str}, ...]
    }
    """

    def __init__(self, intent):
        """Initialise with an Intent model instance."""
        self.intent = intent
        self.plan = intent.latest_plan

    def run(self):
        """Execute all basic verification checks.

        Returns:
            dict with keys: passed, has_warnings, warning_reasons, checks
        """
        if not self.plan:
            return {
                "passed": False,
                "has_warnings": False,
                "warning_reasons": [],
                "checks": [{"check": "plan_exists", "passed": False, "detail": "No resolution plan found"}],
            }

        checks = []
        all_passed = True
        warning_reasons = []
        measured_latency = None

        # Controller adapter verification
        checks, all_passed = self._check_controller_adapters(checks, all_passed)

        # Device-level verification
        for device in self.plan.affected_devices.all():
            device_state = self._collect_device_state(device)
            device_prims = [p for p in self.plan.primitives if p.get("device") == device.name]
            prim_types = {p.get("primitive_type") for p in device_prims}

            # VRF check
            if self.plan.vrf_name:
                vrf_present = self.plan.vrf_name in device_state.get("vrfs", [])
                checks.append(
                    {
                        "device": device.name,
                        "check": "vrf_present",
                        "passed": vrf_present,
                        "detail": f"VRF {self.plan.vrf_name} {'present' if vrf_present else 'MISSING'}",
                    }
                )
                if not vrf_present:
                    all_passed = False

            # BGP check
            if "bgp_neighbor" in prim_types or "bgp_evpn_af" in prim_types:
                bgp_vrf = self.plan.vrf_name or "global"
                bgp_state = device_state.get("bgp_sessions", {}).get(bgp_vrf, {}).get("state", "Unknown")
                bgp_up = bgp_state == "Established"
                checks.append(
                    {
                        "device": device.name,
                        "check": "bgp_established",
                        "passed": bgp_up,
                        "detail": f"BGP state ({bgp_vrf}): {bgp_state}",
                    }
                )
                if not bgp_up:
                    all_passed = False

                # Prefix count check
                prefixes_received = device_state.get("prefix_count", {}).get(bgp_vrf, 0)
                min_prefixes = self.intent.intent_data.get("policy", {}).get("min_prefixes", 1)
                prefix_ok = prefixes_received >= min_prefixes
                checks.append(
                    {
                        "device": device.name,
                        "check": "prefix_count",
                        "passed": prefix_ok,
                        "detail": f"{prefixes_received} prefixes received (min: {min_prefixes})",
                    }
                )
                if not prefix_ok:
                    all_passed = False

                # Warning: prefix count near baseline (above 80% of expected)
                max_prefixes = self.intent.intent_data.get("policy", {}).get("max_prefixes")
                if max_prefixes and prefixes_received > max_prefixes * 0.8:
                    warning_reasons.append(
                        f"BGP prefix count {prefixes_received} above 80% of max ({max_prefixes}) on {device.name}"
                    )

            # ACL check
            if "acl" in prim_types:
                expected_acls = [
                    p.get("acl_name") for p in device_prims if p.get("primitive_type") == "acl" and p.get("acl_name")
                ]
                device_acls = device_state.get("acls", [])
                for acl_name in expected_acls:
                    acl_present = acl_name in device_acls
                    checks.append(
                        {
                            "device": device.name,
                            "check": "acl_present",
                            "passed": acl_present,
                            "detail": f"ACL {acl_name} {'present' if acl_present else 'MISSING'}",
                        }
                    )
                    if not acl_present:
                        all_passed = False

            # VLAN check
            if "vlan" in prim_types:
                expected_vlans = sorted(
                    {p.get("vlan_id") for p in device_prims if p.get("primitive_type") == "vlan" and p.get("vlan_id")}
                )
                device_vlans = set(device_state.get("vlans", []))
                for vlan_id in expected_vlans:
                    vlan_present = vlan_id in device_vlans
                    checks.append(
                        {
                            "device": device.name,
                            "check": "vlan_present",
                            "passed": vlan_present,
                            "detail": f"VLAN {vlan_id} {'present' if vlan_present else 'MISSING'}",
                        }
                    )
                    if not vlan_present:
                        all_passed = False

            # OSPF check
            if "ospf" in prim_types or "ospfv3" in prim_types:
                ospf_neighbors = device_state.get("ospf_neighbor_count", 0)
                ospf_ok = ospf_neighbors > 0
                checks.append(
                    {
                        "device": device.name,
                        "check": "ospf_neighbors",
                        "passed": ospf_ok,
                        "detail": f"{ospf_neighbors} OSPF neighbor(s)",
                    }
                )
                if not ospf_ok:
                    all_passed = False

            # Primitive summary
            checks.append(
                {
                    "device": device.name,
                    "check": "primitives_rendered",
                    "passed": True,
                    "detail": f"Primitive types: {sorted(prim_types)}",
                }
            )

        # Latency SLA check
        max_latency = self.intent.intent_data.get("policy", {}).get("max_latency_ms")
        if max_latency:
            probe_device = self.plan.affected_devices.first()
            dest_prefixes = self.intent.intent_data.get("destination", {}).get("prefixes", [])
            probe_dest = dest_prefixes[0].split("/")[0] if dest_prefixes else ""
            measured_latency = self._measure_latency(device=probe_device, destination=probe_dest)
            latency_ok = measured_latency <= max_latency
            checks.append(
                {
                    "check": "latency_sla",
                    "passed": latency_ok,
                    "detail": f"{measured_latency}ms measured, {max_latency}ms SLA",
                }
            )
            if not latency_ok:
                all_passed = False

            # Warning: latency within 80% of SLA threshold
            if latency_ok and measured_latency > max_latency * 0.8:
                warning_reasons.append(f"Latency {measured_latency}ms is within 80% of SLA threshold {max_latency}ms")

        return {
            "passed": all_passed,
            "has_warnings": len(warning_reasons) > 0,
            "warning_reasons": warning_reasons,
            "checks": checks,
            "measured_latency_ms": measured_latency,
        }

    def _check_controller_adapters(self, checks, all_passed):
        """Verify controller-managed primitives (wireless, sdwan, cloud)."""
        from intent_networking.controller_adapters import classify_primitives, get_adapter  # noqa: PLC0415

        buckets = classify_primitives(self.plan.primitives)
        for adapter_type in ("wireless", "sdwan", "cloud"):
            adapter_prims = buckets.get(adapter_type)
            if not adapter_prims:
                continue
            try:
                adapter = get_adapter(adapter_type)
                result = adapter.verify(adapter_prims, self.intent.intent_id)
                adapter_passed = result.get("verified", False)
                checks.append(
                    {
                        "check": f"{adapter_type}_controller_verify",
                        "passed": adapter_passed,
                        "detail": result.get("details", ""),
                        "drift": result.get("drift", []),
                    }
                )
                if not adapter_passed:
                    all_passed = False
            except ValueError:
                logger.warning("Adapter '%s' not configured — skipping verification", adapter_type)
        return checks, all_passed

    def _collect_device_state(self, device):
        """Collect live state from device via Nornir."""
        from nautobot.dcim.models import Device  # noqa: PLC0415
        from nornir import InitNornir  # noqa: PLC0415
        from nornir_netmiko.tasks import netmiko_send_command  # noqa: PLC0415

        nr = InitNornir(
            inventory={
                "plugin": "NautobotORMInventory",
                "options": {
                    "queryset": Device.objects.filter(name=device.name),
                },
            },
            logging={"enabled": False},
        )

        state = {
            "vrfs": [],
            "bgp_sessions": {},
            "prefix_count": {},
            "acls": [],
            "ospf_neighbor_count": 0,
            "vlans": [],
        }
        platform = device.platform.name if device.platform else ""
        is_arista = platform == "arista-eos"

        # Collect VRF list
        vrf_result = nr.run(
            task=netmiko_send_command,
            command_string="show vrf" if is_arista else "show vrf brief",
            use_textfsm=True,
        )
        if not vrf_result[device.name].failed:
            for row in vrf_result[device.name].result:
                state["vrfs"].append(row.get("name", ""))

        # Collect BGP state
        if self.plan.vrf_name:
            bgp_result = nr.run(
                task=netmiko_send_command,
                command_string=(
                    f"show ip bgp vrf {self.plan.vrf_name} summary"
                    if is_arista
                    else f"show bgp vpnv4 unicast vrf {self.plan.vrf_name} summary"
                ),
                use_textfsm=True,
            )
            if not bgp_result[device.name].failed:
                for neighbor in bgp_result[device.name].result:
                    state["bgp_sessions"][self.plan.vrf_name] = {
                        "state": neighbor.get("state_pfxrcd", "Unknown"),
                        "prefixes": neighbor.get("state_pfxrcd", 0),
                    }
        else:
            bgp_result = nr.run(
                task=netmiko_send_command,
                command_string="show ip bgp summary" if is_arista else "show bgp summary",
                use_textfsm=True,
            )
            if not bgp_result[device.name].failed:
                for neighbor in bgp_result[device.name].result:
                    state["bgp_sessions"]["global"] = {
                        "state": neighbor.get("state_pfxrcd", "Unknown"),
                        "prefixes": neighbor.get("state_pfxrcd", 0),
                    }

        # Collect ACL names
        acl_result = nr.run(
            task=netmiko_send_command,
            command_string="show ip access-lists" if is_arista else "show access-lists",
            use_textfsm=True,
        )
        if not acl_result[device.name].failed:
            for acl in acl_result[device.name].result:
                state["acls"].append(acl.get("name", ""))

        # Collect VLANs
        vlan_result = nr.run(task=netmiko_send_command, command_string="show vlan", use_textfsm=False)
        if not vlan_result[device.name].failed:
            output = str(vlan_result[device.name].result)
            state["vlans"] = sorted({int(match.group(1)) for match in re.finditer(r"(?m)^\s*(\d+)\s+", output)})

        # Collect OSPF neighbor count
        ospf_result = nr.run(
            task=netmiko_send_command,
            command_string="show ip ospf neighbor" if is_arista else "show ip ospf neighbor brief",
            use_textfsm=True,
        )
        if not ospf_result[device.name].failed:
            state["ospf_neighbor_count"] = len(ospf_result[device.name].result)

        return state

    def _measure_latency(self, device=None, destination=""):
        """Measure latency from device to destination via ping."""
        if not device or not destination:
            return 0

        try:
            from nornir import InitNornir  # noqa: PLC0415
            from nornir_netmiko.tasks import netmiko_send_command  # noqa: PLC0415
        except ImportError:
            logger.warning("nornir/nornir_netmiko not installed — latency measurement skipped.")
            return 0

        try:
            from nautobot.dcim.models import Device as DeviceModel  # noqa: PLC0415

            nr = InitNornir(
                inventory={
                    "plugin": "NautobotORMInventory",
                    "options": {
                        "queryset": DeviceModel.objects.filter(name=device.name),
                    },
                },
                logging={"enabled": False},
            )
            result = nr.run(
                task=netmiko_send_command,
                command_string=f"ping {destination} repeat 5",
            )
            if result[device.name].failed:
                return 0

            output = str(result[device.name].result)
            match = re.search(r"[=/]\s*(\d+)/(\d+)/(\d+)", output)
            if match:
                return int(match.group(2))  # avg
            return 0
        except Exception as exc:
            logger.warning("Latency measurement failed: %s", exc)
            return 0
