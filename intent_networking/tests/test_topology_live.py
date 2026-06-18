"""Tests for live device-data collection helpers in topology_api.

Covers the Arista-affecting fixes:
  - platform resolution via network_driver (not just the human-facing name)
  - routing-table raw-text fallback when TextFSM returns no structured data
  - vrf/bgp string-safety (no char-iteration of raw text)
"""

from types import SimpleNamespace

from django.test import SimpleTestCase

from intent_networking.topology_api import (
    _normalise_bgp,
    _normalise_routes,
    _normalise_vrfs,
    _platform_slug,
)


def _device(name=None, network_driver=None):
    plat = SimpleNamespace(name=name, network_driver=network_driver) if (name or network_driver) else None
    return SimpleNamespace(platform=plat)


class PlatformSlugTest(SimpleTestCase):
    """Platform slug resolution prefers network_driver over the display name."""

    def test_resolves_from_network_driver(self):
        # Human-named platform, but network_driver is canonical.
        self.assertEqual(_platform_slug(_device(name="Arista EOS", network_driver="arista_eos")), "arista-eos")

    def test_resolves_from_slug_name(self):
        self.assertEqual(_platform_slug(_device(name="arista-eos")), "arista-eos")

    def test_cisco_driver(self):
        self.assertEqual(_platform_slug(_device(name="Cisco IOS", network_driver="cisco_ios")), "cisco-ios-xe")

    def test_no_platform(self):
        self.assertEqual(_platform_slug(_device()), "")


class NormaliseRoutesTest(SimpleTestCase):
    """Routing-table normalisation: structured rows and raw-text fallback."""

    def test_parses_structured_eos_rows(self):
        rows = [
            {"network": "10.1.1.0", "prefix_length": "24", "protocol": "O",
             "next_hop": ["10.0.0.2"], "interface": ["Ethernet1"], "vrf": "default"},
        ]
        out = _normalise_routes(rows, "arista-eos")
        self.assertEqual(out[0]["network"], "10.1.1.0")
        self.assertEqual(out[0]["mask"], "24")
        self.assertEqual(out[0]["nexthop"], "10.0.0.2")
        self.assertEqual(out[0]["interface"], "Ethernet1")

    def test_raw_text_fallback_when_textfsm_misses(self):
        # Netmiko returns the raw string if no/failed TextFSM template.
        raw = (
            "VRF: default\n"
            "Codes: C - connected, O - OSPF, B - BGP\n"
            "\n"
            " C        10.0.0.0/24 is directly connected, Ethernet1\n"
            " O        10.1.1.0/24 [110/20] via 10.0.0.2, Ethernet1\n"
            " B E      192.168.1.0/24 [200/0] via 10.0.0.3, Ethernet2\n"
        )
        out = _normalise_routes(raw, "arista-eos")
        self.assertEqual(len(out), 3)  # would be 0 (char-iteration) before the fix
        nets = {r["network"]: r for r in out}
        self.assertEqual(nets["10.1.1.0"]["nexthop"], "10.0.0.2")
        self.assertEqual(nets["10.1.1.0"]["interface"], "Ethernet1")
        self.assertEqual(nets["10.0.0.0"]["nexthop"], "directly connected")


class NormaliseStringSafetyTest(SimpleTestCase):
    """VRF/BGP normalisation must not char-iterate raw TextFSM-miss strings."""

    def test_vrfs_string_safe(self):
        self.assertEqual(_normalise_vrfs("VRF: default\n", "arista-eos"), [])

    def test_bgp_string_safe(self):
        self.assertEqual(_normalise_bgp("% BGP inactive", "arista-eos"), [])
