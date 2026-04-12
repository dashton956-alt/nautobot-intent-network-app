# Arista EOS Template Gap Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the 24 missing provision templates and 47 missing removal templates for Arista EOS so every resolver primitive type renders valid CLI config and can be cleanly torn down.

**Architecture:** Pure Jinja2 templates in `intent_networking/jinja_templates/arista/eos/`. Tests use `jinja2.Environment` + `FileSystemLoader` directly — no Django needed. Cloud/SD-WAN/wireless intents that are controller-managed get informational stub templates (like the existing AOS-CX DMVPN stub). All other types get real EOS CLI.

**Tech Stack:** Jinja2, Python `django.test.SimpleTestCase`, pytest

---

## File Map

**New test file:**
- Create: `intent_networking/tests/test_eos_templates.py`

**New provision templates (24):**
- `intent_networking/jinja_templates/arista/eos/wireless_ssid.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_rf.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_vlan_map.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_dot1x.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_guest.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_mesh.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_qos.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_band_steer.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_roam.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_segment.j2`
- `intent_networking/jinja_templates/arista/eos/wireless_flexconnect.j2`
- `intent_networking/jinja_templates/arista/eos/cloud_vpc_peer.j2`
- `intent_networking/jinja_templates/arista/eos/cloud_transit_gw.j2`
- `intent_networking/jinja_templates/arista/eos/cloud_direct_connect.j2`
- `intent_networking/jinja_templates/arista/eos/cloud_vpn_gw.j2`
- `intent_networking/jinja_templates/arista/eos/cloud_security_group.j2`
- `intent_networking/jinja_templates/arista/eos/cloud_nat.j2`
- `intent_networking/jinja_templates/arista/eos/cloud_route_table.j2`
- `intent_networking/jinja_templates/arista/eos/cloud_sdwan.j2`
- `intent_networking/jinja_templates/arista/eos/hybrid_dns.j2`
- `intent_networking/jinja_templates/arista/eos/sdwan_overlay.j2`
- `intent_networking/jinja_templates/arista/eos/sdwan_app_policy.j2`
- `intent_networking/jinja_templates/arista/eos/sdwan_qos.j2`
- `intent_networking/jinja_templates/arista/eos/sdwan_dia.j2`

**New removal templates (47):**
- `intent_networking/jinja_templates/arista/eos/acl_removal.j2`
- `intent_networking/jinja_templates/arista/eos/zbf_removal.j2`
- `intent_networking/jinja_templates/arista/eos/gre_tunnel_removal.j2`
- `intent_networking/jinja_templates/arista/eos/ipsec_tunnel_removal.j2`
- `intent_networking/jinja_templates/arista/eos/ipsec_ikev2_removal.j2`
- `intent_networking/jinja_templates/arista/eos/ssl_inspection_removal.j2`
- `intent_networking/jinja_templates/arista/eos/ra_guard_removal.j2`
- `intent_networking/jinja_templates/arista/eos/wan_uplink_removal.j2`
- `intent_networking/jinja_templates/arista/eos/nat_removal.j2`
- `intent_networking/jinja_templates/arista/eos/nat64_removal.j2`
- `intent_networking/jinja_templates/arista/eos/route_redistribution_removal.j2`
- `intent_networking/jinja_templates/arista/eos/bgp_ipv6_af_removal.j2`
- `intent_networking/jinja_templates/arista/eos/ospfv3_removal.j2`
- `intent_networking/jinja_templates/arista/eos/ldp_removal.j2`
- `intent_networking/jinja_templates/arista/eos/sr_mpls_removal.j2`
- `intent_networking/jinja_templates/arista/eos/srv6_removal.j2`
- `intent_networking/jinja_templates/arista/eos/6pe_6vpe_removal.j2`
- `intent_networking/jinja_templates/arista/eos/evpn_mpls_removal.j2`
- `intent_networking/jinja_templates/arista/eos/evpn_multisite_removal.j2`
- `intent_networking/jinja_templates/arista/eos/l2vpn_vpls_removal.j2`
- `intent_networking/jinja_templates/arista/eos/pseudowire_removal.j2`
- `intent_networking/jinja_templates/arista/eos/rsvp_te_tunnel_removal.j2`
- `intent_networking/jinja_templates/arista/eos/mvpn_removal.j2`
- `intent_networking/jinja_templates/arista/eos/pvlan_removal.j2`
- `intent_networking/jinja_templates/arista/eos/qinq_removal.j2`
- `intent_networking/jinja_templates/arista/eos/ipv6_interface_removal.j2`
- `intent_networking/jinja_templates/arista/eos/mgmt_interface_removal.j2`
- `intent_networking/jinja_templates/arista/eos/lb_vib_removal.j2`
- `intent_networking/jinja_templates/arista/eos/service_insertion_removal.j2`
- `intent_networking/jinja_templates/arista/eos/dmvpn_removal.j2`
- `intent_networking/jinja_templates/arista/eos/stp_root_removal.j2`
- `intent_networking/jinja_templates/arista/eos/qos_cos_remark_removal.j2`
- `intent_networking/jinja_templates/arista/eos/qos_dscp_mark_removal.j2`
- `intent_networking/jinja_templates/arista/eos/qos_police_removal.j2`
- `intent_networking/jinja_templates/arista/eos/qos_queue_removal.j2`
- `intent_networking/jinja_templates/arista/eos/qos_shape_removal.j2`
- `intent_networking/jinja_templates/arista/eos/qos_trust_removal.j2`
- `intent_networking/jinja_templates/arista/eos/aaa_removal.j2`
- `intent_networking/jinja_templates/arista/eos/copp_removal.j2`
- `intent_networking/jinja_templates/arista/eos/urpf_removal.j2`
- `intent_networking/jinja_templates/arista/eos/eigrp_removal.j2`
- `intent_networking/jinja_templates/arista/eos/msdp_removal.j2`
- `intent_networking/jinja_templates/arista/eos/multicast_vrf_removal.j2`
- `intent_networking/jinja_templates/arista/eos/ip_source_guard_removal.j2`
- `intent_networking/jinja_templates/arista/eos/dns_record_removal.j2`
- `intent_networking/jinja_templates/arista/eos/dhcp_pool_removal.j2`
- `intent_networking/jinja_templates/arista/eos/dhcp_relay_removal.j2`

---

## Task 1: Write the test file (all tests fail initially)

**Files:**
- Create: `intent_networking/tests/test_eos_templates.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for Arista EOS Jinja2 templates — provision and removal.

Each test renders a template with minimal valid context and asserts
key EOS CLI strings are present. Uses jinja2 directly — no Django DB needed.
"""
from pathlib import Path

from django.test import SimpleTestCase
from jinja2 import Environment, FileSystemLoader, Undefined

EOS_DIR = Path(__file__).resolve().parent.parent / "jinja_templates" / "arista" / "eos"


def _render(template_name: str, ctx: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(EOS_DIR)),
        undefined=Undefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template(template_name).render(**ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — Wireless
# ─────────────────────────────────────────────────────────────────────────────


class EOSWirelessProvisionTest(SimpleTestCase):
    def test_wireless_ssid_renders(self):
        out = _render("wireless_ssid.j2", {
            "intent_id": "t-001", "ssid_name": "CorpWifi",
            "security_mode": "wpa3-enterprise", "vlan_id": 100,
        })
        self.assertIn("CorpWifi", out)

    def test_wireless_rf_renders(self):
        out = _render("wireless_rf.j2", {
            "intent_id": "t-001", "channels_2g": [1, 6, 11],
            "channels_5g": [36, 40], "tx_power_min": 5, "tx_power_max": 20,
        })
        self.assertIn("wireless", out.lower())

    def test_wireless_vlan_map_renders(self):
        out = _render("wireless_vlan_map.j2", {
            "intent_id": "t-001", "ssid_name": "CorpWifi", "vlan_id": 100,
        })
        self.assertIn("CorpWifi", out)

    def test_wireless_dot1x_renders(self):
        out = _render("wireless_dot1x.j2", {
            "intent_id": "t-001", "ssid_name": "CorpWifi",
            "radius_servers": ["10.0.0.1"], "eap_method": "PEAP",
        })
        self.assertIn("CorpWifi", out)

    def test_wireless_guest_renders(self):
        out = _render("wireless_guest.j2", {
            "intent_id": "t-001", "ssid_name": "Guest",
            "captive_portal_url": "https://portal.example.com", "vlan_id": 200,
        })
        self.assertIn("Guest", out)

    def test_wireless_mesh_renders(self):
        out = _render("wireless_mesh.j2", {
            "intent_id": "t-001", "backhaul_ssid": "MESH-BH",
            "mesh_role": "map", "bridge_group": 1,
        })
        self.assertIn("MESH-BH", out)

    def test_wireless_qos_renders(self):
        out = _render("wireless_qos.j2", {
            "intent_id": "t-001", "ssid_name": "CorpWifi",
        })
        self.assertIn("CorpWifi", out)

    def test_wireless_band_steer_renders(self):
        out = _render("wireless_band_steer.j2", {
            "intent_id": "t-001", "preferred_band": "5ghz",
        })
        self.assertIn("5ghz", out)

    def test_wireless_roam_renders(self):
        out = _render("wireless_roam.j2", {
            "intent_id": "t-001", "ft_enabled": True, "ft_over_ds": True,
        })
        self.assertIn("roam", out.lower())

    def test_wireless_segment_renders(self):
        out = _render("wireless_segment.j2", {
            "intent_id": "t-001", "ssid_name": "CorpWifi", "client_isolation": True,
        })
        self.assertIn("CorpWifi", out)

    def test_wireless_flexconnect_renders(self):
        out = _render("wireless_flexconnect.j2", {
            "intent_id": "t-001", "local_switching": True, "ap_group": "AP-GRP-1",
        })
        self.assertIn("AP-GRP-1", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — Cloud (stubs)
# ─────────────────────────────────────────────────────────────────────────────


class EOSCloudProvisionTest(SimpleTestCase):
    def test_cloud_vpc_peer_renders(self):
        out = _render("cloud_vpc_peer.j2", {
            "intent_id": "t-001", "requester_vpc": "vpc-aaa", "accepter_vpc": "vpc-bbb",
        })
        self.assertIn("vpc-aaa", out)

    def test_cloud_transit_gw_renders(self):
        out = _render("cloud_transit_gw.j2", {
            "intent_id": "t-001", "transit_gateway_id": "tgw-123",
        })
        self.assertIn("tgw-123", out)

    def test_cloud_direct_connect_renders(self):
        out = _render("cloud_direct_connect.j2", {
            "intent_id": "t-001", "connection_id": "dxcon-abc", "vlan": 100,
            "bgp_asn": 65000, "provider": "aws",
        })
        self.assertIn("dxcon-abc", out)

    def test_cloud_vpn_gw_renders(self):
        out = _render("cloud_vpn_gw.j2", {
            "intent_id": "t-001", "provider": "aws",
        })
        self.assertIn("aws", out)

    def test_cloud_security_group_renders(self):
        out = _render("cloud_security_group.j2", {
            "intent_id": "t-001", "group_name": "sg-web", "provider": "aws",
        })
        self.assertIn("sg-web", out)

    def test_cloud_nat_renders(self):
        out = _render("cloud_nat.j2", {
            "intent_id": "t-001", "provider": "aws",
        })
        self.assertIn("aws", out)

    def test_cloud_route_table_renders(self):
        out = _render("cloud_route_table.j2", {
            "intent_id": "t-001", "provider": "aws",
        })
        self.assertIn("aws", out)

    def test_cloud_sdwan_renders(self):
        out = _render("cloud_sdwan.j2", {
            "intent_id": "t-001", "provider": "aws",
        })
        self.assertIn("aws", out)

    def test_hybrid_dns_renders(self):
        out = _render("hybrid_dns.j2", {
            "intent_id": "t-001", "domain": "corp.example.com",
            "forwarders": ["10.0.0.1"],
        })
        self.assertIn("corp.example.com", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — SD-WAN (stubs)
# ─────────────────────────────────────────────────────────────────────────────


class EOSSdwanProvisionTest(SimpleTestCase):
    def test_sdwan_overlay_renders(self):
        out = _render("sdwan_overlay.j2", {
            "intent_id": "t-001", "fabric_name": "SDWAN-FABRIC",
            "system_ip": "10.0.0.1",
        })
        self.assertIn("SDWAN-FABRIC", out)

    def test_sdwan_app_policy_renders(self):
        out = _render("sdwan_app_policy.j2", {
            "intent_id": "t-001", "policy_name": "APP-POL-1",
        })
        self.assertIn("APP-POL-1", out)

    def test_sdwan_qos_renders(self):
        out = _render("sdwan_qos.j2", {
            "intent_id": "t-001", "policy_name": "QOS-POL-1",
        })
        self.assertIn("QOS-POL-1", out)

    def test_sdwan_dia_renders(self):
        out = _render("sdwan_dia.j2", {
            "intent_id": "t-001", "interface": "Ethernet1",
        })
        self.assertIn("Ethernet1", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — Security / Tunneling
# ─────────────────────────────────────────────────────────────────────────────


class EOSSecurityRemovalTest(SimpleTestCase):
    def test_acl_removal_renders(self):
        out = _render("acl_removal.j2", {
            "intent_id": "t-001", "acl_name": "ACL-WEB",
            "address_family": "ipv4", "apply_interfaces": ["Ethernet1"],
            "direction": "in",
        })
        self.assertIn("no ip access-list", out)
        self.assertIn("ACL-WEB", out)

    def test_zbf_removal_renders(self):
        out = _render("zbf_removal.j2", {
            "intent_id": "t-001",
            "zones": [{"name": "INSIDE"}, {"name": "OUTSIDE"}],
            "zone_pairs": [{"source": "INSIDE", "destination": "OUTSIDE", "policy": "ZBF-POL"}],
        })
        self.assertIn("no zone", out)

    def test_gre_tunnel_removal_renders(self):
        out = _render("gre_tunnel_removal.j2", {
            "intent_id": "t-001", "tunnel_interface": "Tunnel1",
        })
        self.assertIn("no interface Tunnel1", out)

    def test_ipsec_tunnel_removal_renders(self):
        out = _render("ipsec_tunnel_removal.j2", {
            "intent_id": "t-001", "tunnel_id": 10, "remote_peer": "203.0.113.1",
        })
        self.assertIn("no interface Tunnel10", out)

    def test_ipsec_ikev2_removal_renders(self):
        out = _render("ipsec_ikev2_removal.j2", {
            "intent_id": "t-001",
            "proposal_name": "IKE-PROP-1",
            "policy_name": "IKE-POL-1",
            "profile_name": "IKE-PROF-1",
            "keyring_name": "IKE-KEYRING-1",
        })
        self.assertIn("no crypto ikev2", out)

    def test_ssl_inspection_removal_renders(self):
        out = _render("ssl_inspection_removal.j2", {
            "intent_id": "t-001", "policy_name": "SSL-INSPECT-1",
        })
        self.assertIn("SSL-INSPECT-1", out)

    def test_ra_guard_removal_renders(self):
        out = _render("ra_guard_removal.j2", {
            "intent_id": "t-001", "policy_name": "RA-GUARD-1",
            "trusted_ports": ["Ethernet1"], "untrusted_ports": ["Ethernet2"],
        })
        self.assertIn("no ipv6 nd raguard", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — Routing / WAN
# ─────────────────────────────────────────────────────────────────────────────


class EOSRoutingRemovalTest(SimpleTestCase):
    def test_wan_uplink_removal_renders(self):
        out = _render("wan_uplink_removal.j2", {
            "intent_id": "t-001", "interface": "Ethernet1",
            "ip_address": "203.0.113.1/30", "default_route": True,
        })
        self.assertIn("no ip address", out)

    def test_nat_removal_renders(self):
        out = _render("nat_removal.j2", {
            "intent_id": "t-001",
            "inside_interfaces": ["Ethernet1"],
            "outside_interfaces": ["Ethernet2"],
        })
        self.assertIn("no ip nat", out)

    def test_nat64_removal_renders(self):
        out = _render("nat64_removal.j2", {
            "intent_id": "t-001", "interfaces": ["Ethernet1"],
        })
        self.assertIn("no nat64", out)

    def test_route_redistribution_removal_renders(self):
        out = _render("route_redistribution_removal.j2", {
            "intent_id": "t-001",
            "dest_protocol": "ospf",
            "dest_process": 1,
            "source_protocol": "connected",
        })
        self.assertIn("no redistribute", out)

    def test_bgp_ipv6_af_removal_renders(self):
        out = _render("bgp_ipv6_af_removal.j2", {
            "intent_id": "t-001", "local_asn": 65001,
            "neighbors": [{"ip": "2001:db8::1"}],
        })
        self.assertIn("no address-family ipv6", out)

    def test_ospfv3_removal_renders(self):
        out = _render("ospfv3_removal.j2", {
            "intent_id": "t-001", "process_id": 1,
            "interfaces": [{"name": "Ethernet1"}],
        })
        self.assertIn("no ipv6 router ospf", out)

    def test_ldp_removal_renders(self):
        out = _render("ldp_removal.j2", {
            "intent_id": "t-001", "interfaces": ["Ethernet1"],
        })
        self.assertIn("no mpls ldp", out)

    def test_sr_mpls_removal_renders(self):
        out = _render("sr_mpls_removal.j2", {
            "intent_id": "t-001", "srgb_start": 16000, "srgb_end": 23999,
        })
        self.assertIn("no segment-routing", out)

    def test_srv6_removal_renders(self):
        out = _render("srv6_removal.j2", {
            "intent_id": "t-001", "locator_name": "MAIN",
        })
        self.assertIn("no segment-routing", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — MPLS / Overlay
# ─────────────────────────────────────────────────────────────────────────────


class EOSMplsRemovalTest(SimpleTestCase):
    def test_6pe_6vpe_removal_renders(self):
        out = _render("6pe_6vpe_removal.j2", {
            "intent_id": "t-001", "mode": "6pe", "vrf": "",
            "neighbor_ip": "10.0.0.1",
        })
        self.assertIn("no", out)

    def test_evpn_mpls_removal_renders(self):
        out = _render("evpn_mpls_removal.j2", {
            "intent_id": "t-001",
        })
        self.assertIn("no", out)

    def test_evpn_multisite_removal_renders(self):
        out = _render("evpn_multisite_removal.j2", {
            "intent_id": "t-001",
        })
        self.assertIn("no", out)

    def test_l2vpn_vpls_removal_renders(self):
        out = _render("l2vpn_vpls_removal.j2", {
            "intent_id": "t-001", "vpls_name": "VPLS-TEST",
        })
        self.assertIn("no", out)

    def test_pseudowire_removal_renders(self):
        out = _render("pseudowire_removal.j2", {
            "intent_id": "t-001", "pw_id": 100, "remote_pe": "10.0.0.1",
        })
        self.assertIn("no interface", out)

    def test_rsvp_te_tunnel_removal_renders(self):
        out = _render("rsvp_te_tunnel_removal.j2", {
            "intent_id": "t-001", "tunnel_id": 10,
        })
        self.assertIn("no interface Tunnel10", out)

    def test_mvpn_removal_renders(self):
        out = _render("mvpn_removal.j2", {
            "intent_id": "t-001", "vrf": "CUST-A",
        })
        self.assertIn("no mdt", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — L2 / Interface / Misc
# ─────────────────────────────────────────────────────────────────────────────


class EOSL2RemovalTest(SimpleTestCase):
    def test_pvlan_removal_renders(self):
        out = _render("pvlan_removal.j2", {
            "intent_id": "t-001", "primary_vlan": 100,
            "secondary_vlans": [101, 102],
        })
        self.assertIn("no private-vlan", out)

    def test_qinq_removal_renders(self):
        out = _render("qinq_removal.j2", {
            "intent_id": "t-001", "interface": "Ethernet1",
            "outer_vlan": 100, "inner_vlan": 200,
        })
        self.assertIn("no switchport", out)

    def test_ipv6_interface_removal_renders(self):
        out = _render("ipv6_interface_removal.j2", {
            "intent_id": "t-001", "interface": "Ethernet1",
        })
        self.assertIn("no ipv6", out)

    def test_mgmt_interface_removal_renders(self):
        out = _render("mgmt_interface_removal.j2", {
            "intent_id": "t-001",
            "interface": "Management1", "ip_address": "192.168.1.1/24",
        })
        self.assertIn("no ip address", out)

    def test_lb_vip_removal_renders(self):
        out = _render("lb_vib_removal.j2", {
            "intent_id": "t-001", "vip_address": "10.0.0.100",
            "vip_port": 80,
        })
        self.assertIn("10.0.0.100", out)

    def test_service_insertion_removal_renders(self):
        out = _render("service_insertion_removal.j2", {
            "intent_id": "t-001",
            "service_name": "FW-SERVICE",
        })
        self.assertIn("FW-SERVICE", out)

    def test_dmvpn_removal_renders(self):
        out = _render("dmvpn_removal.j2", {
            "intent_id": "t-001", "tunnel_interface": "Tunnel100",
        })
        self.assertIn("no interface Tunnel100", out)

    def test_stp_root_removal_renders(self):
        out = _render("stp_root_removal.j2", {
            "intent_id": "t-001", "vlans": [1, 10, 20],
        })
        self.assertIn("no spanning-tree", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — QoS
# ─────────────────────────────────────────────────────────────────────────────


class EOSQoSRemovalTest(SimpleTestCase):
    def test_qos_cos_remark_removal_renders(self):
        out = _render("qos_cos_remark_removal.j2", {
            "intent_id": "t-001", "policy_name": "COS-POL",
            "interfaces": ["Ethernet1"],
        })
        self.assertIn("no service-policy", out)

    def test_qos_dscp_mark_removal_renders(self):
        out = _render("qos_dscp_mark_removal.j2", {
            "intent_id": "t-001", "policy_name": "DSCP-POL",
            "interfaces": ["Ethernet1"],
        })
        self.assertIn("no service-policy", out)

    def test_qos_police_removal_renders(self):
        out = _render("qos_police_removal.j2", {
            "intent_id": "t-001", "policy_name": "POLICE-POL",
            "interfaces": ["Ethernet1"],
        })
        self.assertIn("no service-policy", out)

    def test_qos_queue_removal_renders(self):
        out = _render("qos_queue_removal.j2", {
            "intent_id": "t-001", "policy_name": "QUEUE-POL",
            "interfaces": ["Ethernet1"],
        })
        self.assertIn("no service-policy", out)

    def test_qos_shape_removal_renders(self):
        out = _render("qos_shape_removal.j2", {
            "intent_id": "t-001", "policy_name": "SHAPE-POL",
            "interfaces": ["Ethernet1"],
        })
        self.assertIn("no service-policy", out)

    def test_qos_trust_removal_renders(self):
        out = _render("qos_trust_removal.j2", {
            "intent_id": "t-001", "interfaces": ["Ethernet1"],
        })
        self.assertIn("no qos trust", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — Misc
# ─────────────────────────────────────────────────────────────────────────────


class EOSMiscRemovalTest(SimpleTestCase):
    def test_aaa_removal_renders(self):
        out = _render("aaa_removal.j2", {
            "intent_id": "t-001",
            "radius_servers": [{"host": "10.0.0.1"}],
            "tacacs_servers": [],
        })
        self.assertIn("no aaa", out)

    def test_copp_removal_renders(self):
        out = _render("copp_removal.j2", {
            "intent_id": "t-001", "policy_name": "COPP-POLICY",
        })
        self.assertIn("COPP-POLICY", out)

    def test_urpf_removal_renders(self):
        out = _render("urpf_removal.j2", {
            "intent_id": "t-001", "interface": "Ethernet1", "mode": "strict",
        })
        self.assertIn("no ip verify unicast", out)

    def test_eigrp_removal_renders(self):
        out = _render("eigrp_removal.j2", {
            "intent_id": "t-001", "as_number": 100,
        })
        self.assertIn("no router eigrp 100", out)

    def test_msdp_removal_renders(self):
        out = _render("msdp_removal.j2", {
            "intent_id": "t-001", "peers": [{"peer_ip": "10.0.0.1"}],
        })
        self.assertIn("no ip msdp", out)

    def test_multicast_vrf_removal_renders(self):
        out = _render("multicast_vrf_removal.j2", {
            "intent_id": "t-001", "vrf": "CUST-A",
        })
        self.assertIn("no ip multicast-routing", out)

    def test_ip_source_guard_removal_renders(self):
        out = _render("ip_source_guard_removal.j2", {
            "intent_id": "t-001", "interfaces": ["Ethernet1"],
        })
        self.assertIn("no ip verify source", out)

    def test_dns_record_removal_renders(self):
        out = _render("dns_record_removal.j2", {
            "intent_id": "t-001", "hostname": "server1",
            "record_type": "A", "value": "10.0.0.1",
        })
        self.assertIn("server1", out)

    def test_dhcp_pool_removal_renders(self):
        out = _render("dhcp_pool_removal.j2", {
            "intent_id": "t-001", "pool_name": "POOL-1",
        })
        self.assertIn("no ip dhcp pool POOL-1", out)

    def test_dhcp_relay_removal_renders(self):
        out = _render("dhcp_relay_removal.j2", {
            "intent_id": "t-001", "interface": "Vlan10",
            "relay_servers": ["10.0.0.1"],
        })
        self.assertIn("no ip helper-address", out)
```

- [ ] **Step 2: Run tests — verify all fail with TemplateNotFound**

```bash
cd /home/dan/Desktop/github/nautobot-intent-network-app
python -m pytest intent_networking/tests/test_eos_templates.py -v 2>&1 | head -60
```

Expected: All tests fail with `TemplateNotFound` or similar.

- [ ] **Step 3: Commit test file**

```bash
git add intent_networking/tests/test_eos_templates.py
git commit -m "test: add EOS template gap tests (all failing)"
```

---

## Task 2: Provision templates — Wireless (11 templates)

**Files:** All in `intent_networking/jinja_templates/arista/eos/`

- [ ] **Step 1: Create wireless_ssid.j2**

```jinja2
{# wireless_ssid.j2 — arista-eos #}
! Wireless SSID (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! Note: Arista EOS wireless SSIDs are managed via Mist cloud API or CloudVision.
! SSID: {{ ssid_name }}
! Security: {{ security_mode | default("wpa3-enterprise") }}
! VLAN: {{ vlan_id | default("unset") }}
! Band: {{ band | default("dual") }}
```

- [ ] **Step 2: Create wireless_rf.j2**

```jinja2
{# wireless_rf.j2 — arista-eos #}
! RF Policy (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! Note: RF policies on Arista are managed via Mist or CloudVision AP profiles.
! 2.4 GHz channels: {{ channels_2g | default([1, 6, 11]) | join(", ") }}
! 5 GHz channels: {{ channels_5g | default([]) | join(", ") }}
! TX Power min/max: {{ tx_power_min | default("auto") }} / {{ tx_power_max | default("auto") }} dBm
```

- [ ] **Step 3: Create wireless_vlan_map.j2**

```jinja2
{# wireless_vlan_map.j2 — arista-eos #}
! Wireless VLAN Mapping (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! SSID: {{ ssid_name }}
! VLAN: {{ vlan_id | default("unset") }}
! Note: VLAN-to-SSID mapping is configured via Mist or CloudVision.
```

- [ ] **Step 4: Create wireless_dot1x.j2**

```jinja2
{# wireless_dot1x.j2 — arista-eos #}
! 802.1X Wireless (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! SSID: {{ ssid_name }}
! EAP Method: {{ eap_method | default("PEAP") }}
{% for srv in radius_servers | default([]) %}
! RADIUS Server: {{ srv }}
{% endfor %}
! Note: Wireless 802.1X is managed via Mist or CloudVision.
```

- [ ] **Step 5: Create wireless_guest.j2**

```jinja2
{# wireless_guest.j2 — arista-eos #}
! Guest Wireless / Captive Portal (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! SSID: {{ ssid_name }}
! Portal URL: {{ captive_portal_url | default("") }}
! VLAN: {{ vlan_id | default("unset") }}
! Note: Guest wireless is managed via Mist or CloudVision.
```

- [ ] **Step 6: Create wireless_mesh.j2**

```jinja2
{# wireless_mesh.j2 — arista-eos #}
! Mesh Wireless (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! Backhaul SSID: {{ backhaul_ssid }}
! Mesh Role: {{ mesh_role | default("map") }}
! Bridge Group: {{ bridge_group | default(1) }}
! Note: Mesh is configured via Mist or CloudVision.
```

- [ ] **Step 7: Create wireless_qos.j2**

```jinja2
{# wireless_qos.j2 — arista-eos #}
! Wireless QoS / WMM (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! SSID: {{ ssid_name }}
! Note: Wireless QoS is managed via Mist or CloudVision AP profiles.
```

- [ ] **Step 8: Create wireless_band_steer.j2**

```jinja2
{# wireless_band_steer.j2 — arista-eos #}
! Band Steering (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! Preferred Band: {{ preferred_band | default("5ghz") }}
! Note: Band steering is configured via Mist or CloudVision AP profiles.
```

- [ ] **Step 9: Create wireless_roam.j2**

```jinja2
{# wireless_roam.j2 — arista-eos #}
! Fast Roaming / 802.11r (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! 802.11r FT: {{ "enabled" if ft_enabled | default(true) else "disabled" }}
! FT over DS: {{ "enabled" if ft_over_ds | default(true) else "disabled" }}
! Note: Fast roam configuration is managed via Mist or CloudVision.
```

- [ ] **Step 10: Create wireless_segment.j2**

```jinja2
{# wireless_segment.j2 — arista-eos #}
! Wireless Segmentation (Mist / CloudVision managed)
! Intent: {{ intent_id }}
! SSID: {{ ssid_name }}
! Client Isolation: {{ client_isolation | default(true) }}
! Note: Wireless segmentation is managed via Mist or CloudVision.
```

- [ ] **Step 11: Create wireless_flexconnect.j2**

```jinja2
{# wireless_flexconnect.j2 — arista-eos #}
! FlexConnect / Local Switching (Cisco-specific — not applicable to Arista EOS)
! Intent: {{ intent_id }}
! AP Group: {{ ap_group | default("") }}
! Note: FlexConnect is a Cisco WLC feature. Arista uses Mist or CloudVision for local switching.
```

- [ ] **Step 12: Run wireless provision tests**

```bash
python -m pytest intent_networking/tests/test_eos_templates.py::EOSWirelessProvisionTest -v
```

Expected: All 11 PASS.

- [ ] **Step 13: Commit**

```bash
git add intent_networking/jinja_templates/arista/eos/wireless_*.j2
git commit -m "feat: add EOS wireless provision templates (Mist/CV stubs)"
```

---

## Task 3: Provision templates — Cloud + SD-WAN (13 templates)

**Files:** All in `intent_networking/jinja_templates/arista/eos/`

- [ ] **Step 1: Create cloud_vpc_peer.j2**

```jinja2
{# cloud_vpc_peer.j2 — arista-eos #}
! VPC / VNet Peering (cloud API managed)
! Intent: {{ intent_id }}
! Requester VPC: {{ requester_vpc }}
! Accepter VPC: {{ accepter_vpc }}
! Provider: {{ provider | default("aws") }}
! Note: VPC peering is managed via cloud provider API, not device CLI.
```

- [ ] **Step 2: Create cloud_transit_gw.j2**

```jinja2
{# cloud_transit_gw.j2 — arista-eos #}
! Transit Gateway (cloud API managed)
! Intent: {{ intent_id }}
! Transit Gateway: {{ transit_gateway_id }}
! Provider: {{ provider | default("aws") }}
! Note: Transit gateway attachment is managed via cloud provider API.
```

- [ ] **Step 3: Create cloud_direct_connect.j2**

```jinja2
{# cloud_direct_connect.j2 — arista-eos #}
! Cloud Direct Connect — BGP peering on physical handoff
! Intent: {{ intent_id }}
!
{% if vlan | default("") %}
interface {{ interface | default("Ethernet1") }}.{{ vlan }}
   encapsulation dot1q vlan {{ vlan }}
   ip address {{ local_ip | default("") }}
!
{% else %}
interface {{ interface | default("Ethernet1") }}
   ip address {{ local_ip | default("") }}
!
{% endif %}
router bgp {{ bgp_asn | default("") }}
   neighbor {{ peer_ip | default("") }} remote-as {{ peer_asn | default("") }}
   neighbor {{ peer_ip | default("") }} description {{ provider | default("aws") }}-direct-connect-{{ connection_id }}
{% if bgp_auth_key | default("") %}
   neighbor {{ peer_ip | default("") }} password {{ bgp_auth_key }}
{% endif %}
   neighbor {{ peer_ip | default("") }} activate
!
```

- [ ] **Step 4: Create cloud_vpn_gw.j2**

```jinja2
{# cloud_vpn_gw.j2 — arista-eos #}
! Cloud VPN Gateway (cloud API managed)
! Intent: {{ intent_id }}
! Provider: {{ provider | default("aws") }}
! Note: Cloud VPN gateway configuration is managed via cloud provider API.
```

- [ ] **Step 5: Create cloud_security_group.j2**

```jinja2
{# cloud_security_group.j2 — arista-eos #}
! Cloud Security Group (cloud API managed)
! Intent: {{ intent_id }}
! Group: {{ group_name | default("") }}
! Provider: {{ provider | default("aws") }}
! Note: Cloud security groups are managed via cloud provider API, not device CLI.
```

- [ ] **Step 6: Create cloud_nat.j2**

```jinja2
{# cloud_nat.j2 — arista-eos #}
! Cloud NAT (cloud API managed)
! Intent: {{ intent_id }}
! Provider: {{ provider | default("aws") }}
! Note: Cloud NAT is managed via cloud provider API, not device CLI.
```

- [ ] **Step 7: Create cloud_route_table.j2**

```jinja2
{# cloud_route_table.j2 — arista-eos #}
! Cloud Route Table (cloud API managed)
! Intent: {{ intent_id }}
! Provider: {{ provider | default("aws") }}
! Note: Cloud route tables are managed via cloud provider API, not device CLI.
```

- [ ] **Step 8: Create cloud_sdwan.j2**

```jinja2
{# cloud_sdwan.j2 — arista-eos #}
! Cloud SD-WAN Integration (cloud API managed)
! Intent: {{ intent_id }}
! Provider: {{ provider | default("aws") }}
! Note: Cloud SD-WAN integration is managed via SD-WAN controller API.
```

- [ ] **Step 9: Create hybrid_dns.j2**

```jinja2
{# hybrid_dns.j2 — arista-eos #}
! Hybrid DNS Configuration
! Intent: {{ intent_id }}
!
ip domain-name {{ domain | default("") }}
{% for fwd in forwarders | default([]) %}
ip name-server {{ fwd }}
{% endfor %}
!
```

- [ ] **Step 10: Create sdwan_overlay.j2**

```jinja2
{# sdwan_overlay.j2 — arista-eos #}
! SD-WAN Overlay (controller managed)
! Intent: {{ intent_id }}
! Fabric: {{ fabric_name | default("") }}
! System IP: {{ system_ip | default("") }}
! Note: SD-WAN overlay configuration is managed via SD-WAN controller (e.g. Viptela, Meraki).
```

- [ ] **Step 11: Create sdwan_app_policy.j2**

```jinja2
{# sdwan_app_policy.j2 — arista-eos #}
! SD-WAN Application Policy (controller managed)
! Intent: {{ intent_id }}
! Policy: {{ policy_name | default("") }}
! Note: SD-WAN application policies are managed via SD-WAN controller.
```

- [ ] **Step 12: Create sdwan_qos.j2**

```jinja2
{# sdwan_qos.j2 — arista-eos #}
! SD-WAN QoS Policy (controller managed)
! Intent: {{ intent_id }}
! Policy: {{ policy_name | default("") }}
! Note: SD-WAN QoS policies are managed via SD-WAN controller.
```

- [ ] **Step 13: Create sdwan_dia.j2**

```jinja2
{# sdwan_dia.j2 — arista-eos #}
! SD-WAN Direct Internet Access
! Intent: {{ intent_id }}
!
interface {{ interface | default("Ethernet1") }}
   description SD-WAN-DIA-{{ intent_id }}
   no switchport
{% if ip_address | default("") %}
   ip address {{ ip_address }}
{% else %}
   ip address dhcp
{% endif %}
   no shutdown
!
```

- [ ] **Step 14: Run cloud + SD-WAN tests**

```bash
python -m pytest intent_networking/tests/test_eos_templates.py::EOSCloudProvisionTest intent_networking/tests/test_eos_templates.py::EOSSdwanProvisionTest -v
```

Expected: All 13 PASS.

- [ ] **Step 15: Commit**

```bash
git add intent_networking/jinja_templates/arista/eos/cloud_*.j2 intent_networking/jinja_templates/arista/eos/hybrid_dns.j2 intent_networking/jinja_templates/arista/eos/sdwan_*.j2
git commit -m "feat: add EOS cloud and SD-WAN provision templates"
```

---

## Task 4: Removal templates — Security / Tunneling (7 templates)

**Files:** All in `intent_networking/jinja_templates/arista/eos/`

- [ ] **Step 1: Create acl_removal.j2**

```jinja2
{# acl_removal.j2 — arista-eos #}
! Remove ACL Configuration — {{ acl_name }}
! Intent: {{ intent_id }}
!
{% for iface in apply_interfaces | default([]) %}
interface {{ iface }}
   no ip{{ "v6" if address_family | default("ipv4") == "ipv6" else "" }} access-group {{ acl_name }} {{ direction | default("in") }}
!
{% endfor %}
{% if address_family | default("ipv4") == "ipv6" %}
no ipv6 access-list {{ acl_name }}
{% else %}
no ip access-list {{ acl_name }}
{% endif %}
!
```

- [ ] **Step 2: Create zbf_removal.j2**

```jinja2
{# zbf_removal.j2 — arista-eos #}
! Remove Zone-Based Firewall Configuration
! Intent: {{ intent_id }}
!
{% for pair in zone_pairs | default([]) %}
no zone-pair security {{ pair.source }}-{{ pair.destination }}
!
{% endfor %}
{% for zone in zones | default([]) %}
no zone security {{ zone.name }}
!
{% endfor %}
```

- [ ] **Step 3: Create gre_tunnel_removal.j2**

```jinja2
{# gre_tunnel_removal.j2 — arista-eos #}
! Remove GRE Tunnel Configuration
! Intent: {{ intent_id }}
!
no interface {{ tunnel_interface | default("Tunnel1") }}
!
```

- [ ] **Step 4: Create ipsec_tunnel_removal.j2**

```jinja2
{# ipsec_tunnel_removal.j2 — arista-eos #}
! Remove IPSec Tunnel Configuration
! Intent: {{ intent_id }}
!
no interface Tunnel{{ tunnel_id }}
no crypto map CM-{{ remote_peer | replace(".", "-") }}
no crypto isakmp policy 10
!
```

- [ ] **Step 5: Create ipsec_ikev2_removal.j2**

```jinja2
{# ipsec_ikev2_removal.j2 — arista-eos #}
! Remove IKEv2 Configuration
! Intent: {{ intent_id }}
!
{% if profile_name | default("") %}
no crypto ikev2 profile {{ profile_name }}
{% endif %}
{% if policy_name | default("") %}
no crypto ikev2 policy {{ policy_name }}
{% endif %}
{% if proposal_name | default("") %}
no crypto ikev2 proposal {{ proposal_name }}
{% endif %}
{% if keyring_name | default("") %}
no crypto ikev2 keyring {{ keyring_name }}
{% endif %}
!
```

- [ ] **Step 6: Create ssl_inspection_removal.j2**

```jinja2
{# ssl_inspection_removal.j2 — arista-eos #}
! Remove SSL/TLS Inspection Policy
! Intent: {{ intent_id }}
! Policy: {{ policy_name }}
! Note: SSL inspection removal requires manual policy detach before deletion.
no ssl profile {{ policy_name }}
!
```

- [ ] **Step 7: Create ra_guard_removal.j2**

```jinja2
{# ra_guard_removal.j2 — arista-eos #}
! Remove IPv6 RA Guard Policy
! Intent: {{ intent_id }}
!
{% for port in trusted_ports | default([]) %}
interface {{ port }}
   no ipv6 nd raguard attach-policy {{ policy_name }}
!
{% endfor %}
{% for port in untrusted_ports | default([]) %}
interface {{ port }}
   no ipv6 nd raguard attach-policy {{ policy_name }}
!
{% endfor %}
no ipv6 nd raguard policy {{ policy_name }}
!
```

- [ ] **Step 8: Run security removal tests**

```bash
python -m pytest intent_networking/tests/test_eos_templates.py::EOSSecurityRemovalTest -v
```

Expected: All 7 PASS.

- [ ] **Step 9: Commit**

```bash
git add intent_networking/jinja_templates/arista/eos/acl_removal.j2 intent_networking/jinja_templates/arista/eos/zbf_removal.j2 intent_networking/jinja_templates/arista/eos/gre_tunnel_removal.j2 intent_networking/jinja_templates/arista/eos/ipsec_tunnel_removal.j2 intent_networking/jinja_templates/arista/eos/ipsec_ikev2_removal.j2 intent_networking/jinja_templates/arista/eos/ssl_inspection_removal.j2 intent_networking/jinja_templates/arista/eos/ra_guard_removal.j2
git commit -m "feat: add EOS security/tunneling removal templates"
```

---

## Task 5: Removal templates — Routing / WAN (9 templates)

**Files:** All in `intent_networking/jinja_templates/arista/eos/`

- [ ] **Step 1: Create wan_uplink_removal.j2**

```jinja2
{# wan_uplink_removal.j2 — arista-eos #}
! Remove WAN Uplink Configuration
! Intent: {{ intent_id }}
!
interface {{ interface }}
   no ip address
   no description
   shutdown
!
{% if default_route | default(false) %}
no ip route 0.0.0.0/0
{% endif %}
!
```

- [ ] **Step 2: Create nat_removal.j2**

```jinja2
{# nat_removal.j2 — arista-eos #}
! Remove NAT Configuration
! Intent: {{ intent_id }}
!
no ip nat translation max-entries
{% for iface in inside_interfaces | default([]) %}
interface {{ iface }}
   no ip nat inside
!
{% endfor %}
{% for iface in outside_interfaces | default([]) %}
interface {{ iface }}
   no ip nat outside
!
{% endfor %}
no ip nat pool {{ pool_name | default("NAT-POOL") }}
!
```

- [ ] **Step 3: Create nat64_removal.j2**

```jinja2
{# nat64_removal.j2 — arista-eos #}
! Remove NAT64 Configuration
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface }}
   no nat64 enable
!
{% endfor %}
no nat64 prefix stateful {{ prefix | default("64:ff9b::/96") }}
!
```

- [ ] **Step 4: Create route_redistribution_removal.j2**

```jinja2
{# route_redistribution_removal.j2 — arista-eos #}
! Remove Route Redistribution
! Intent: {{ intent_id }}
!
{% if dest_protocol == "ospf" %}
router ospf {{ dest_process | default(1) }}
   no redistribute {{ source_protocol }}{% if route_map | default("") %} route-map {{ route_map }}{% endif %}

{% elif dest_protocol == "bgp" %}
router bgp {{ dest_process }}
   no redistribute {{ source_protocol }}{% if route_map | default("") %} route-map {{ route_map }}{% endif %}

{% elif dest_protocol == "isis" %}
router isis
   no redistribute {{ source_protocol }}{% if route_map | default("") %} route-map {{ route_map }}{% endif %}

{% endif %}
!
```

- [ ] **Step 5: Create bgp_ipv6_af_removal.j2**

```jinja2
{# bgp_ipv6_af_removal.j2 — arista-eos #}
! Remove BGP IPv6 Address Family
! Intent: {{ intent_id }}
!
router bgp {{ local_asn }}
   address-family ipv6
{% for nbr in neighbors | default([]) %}
      no neighbor {{ nbr.ip }} activate
{% endfor %}
   no address-family ipv6
!
```

- [ ] **Step 6: Create ospfv3_removal.j2**

```jinja2
{# ospfv3_removal.j2 — arista-eos #}
! Remove OSPFv3 Configuration
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface.name }}
   no ipv6 ospf {{ process_id | default(1) }} area {{ area | default("0.0.0.0") }}
!
{% endfor %}
no ipv6 router ospf {{ process_id | default(1) }}
!
```

- [ ] **Step 7: Create ldp_removal.j2**

```jinja2
{# ldp_removal.j2 — arista-eos #}
! Remove LDP Configuration
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface }}
   no mpls ldp interface
!
{% endfor %}
no mpls ldp router-id
no mpls ldp
!
```

- [ ] **Step 8: Create sr_mpls_removal.j2**

```jinja2
{# sr_mpls_removal.j2 — arista-eos #}
! Remove Segment Routing MPLS Configuration
! Intent: {{ intent_id }}
!
router isis
   no segment-routing mpls
!
no segment-routing global-block {{ srgb_start | default(16000) }} {{ srgb_end | default(23999) }}
!
```

- [ ] **Step 9: Create srv6_removal.j2**

```jinja2
{# srv6_removal.j2 — arista-eos #}
! Remove SRv6 Configuration
! Intent: {{ intent_id }}
!
segment-routing
   no srv6
   locator {{ locator_name | default("MAIN") }}
      no prefix
!
no segment-routing srv6
!
```

- [ ] **Step 10: Run routing/WAN removal tests**

```bash
python -m pytest intent_networking/tests/test_eos_templates.py::EOSRoutingRemovalTest -v
```

Expected: All 9 PASS.

- [ ] **Step 11: Commit**

```bash
git add intent_networking/jinja_templates/arista/eos/wan_uplink_removal.j2 intent_networking/jinja_templates/arista/eos/nat_removal.j2 intent_networking/jinja_templates/arista/eos/nat64_removal.j2 intent_networking/jinja_templates/arista/eos/route_redistribution_removal.j2 intent_networking/jinja_templates/arista/eos/bgp_ipv6_af_removal.j2 intent_networking/jinja_templates/arista/eos/ospfv3_removal.j2 intent_networking/jinja_templates/arista/eos/ldp_removal.j2 intent_networking/jinja_templates/arista/eos/sr_mpls_removal.j2 intent_networking/jinja_templates/arista/eos/srv6_removal.j2
git commit -m "feat: add EOS routing/WAN removal templates"
```

---

## Task 6: Removal templates — MPLS / Overlay (7 templates)

**Files:** All in `intent_networking/jinja_templates/arista/eos/`

- [ ] **Step 1: Create 6pe_6vpe_removal.j2**

```jinja2
{# 6pe_6vpe_removal.j2 — arista-eos #}
! Remove 6PE / 6VPE Configuration
! Intent: {{ intent_id }}
!
router bgp {{ local_asn | default("") }}
{% if mode | default("6pe") == "6vpe" and vrf | default("") %}
   vrf {{ vrf }}
{% endif %}
   no neighbor {{ neighbor_ip }} activate
   address-family ipv6
      no neighbor {{ neighbor_ip }} activate
!
```

- [ ] **Step 2: Create evpn_mpls_removal.j2**

```jinja2
{# evpn_mpls_removal.j2 — arista-eos #}
! Remove EVPN over MPLS Configuration
! Intent: {{ intent_id }}
!
router bgp {{ local_asn | default("") }}
   no address-family evpn
!
```

- [ ] **Step 3: Create evpn_multisite_removal.j2**

```jinja2
{# evpn_multisite_removal.j2 — arista-eos #}
! Remove EVPN Multi-Site Configuration
! Intent: {{ intent_id }}
!
router bgp {{ local_asn | default("") }}
   no address-family evpn
!
evpn
   no multisite border-gateway interface {{ dci_interface | default("") }}
!
```

- [ ] **Step 4: Create l2vpn_vpls_removal.j2**

```jinja2
{# l2vpn_vpls_removal.j2 — arista-eos #}
! Remove L2VPN VPLS Configuration
! Intent: {{ intent_id }}
!
no l2vpn vpls {{ vpls_name | default("") }}
!
```

- [ ] **Step 5: Create pseudowire_removal.j2**

```jinja2
{# pseudowire_removal.j2 — arista-eos #}
! Remove Pseudowire / EoMPLS Configuration
! Intent: {{ intent_id }}
!
no interface pseudowire {{ pw_id }}
!
```

- [ ] **Step 6: Create rsvp_te_tunnel_removal.j2**

```jinja2
{# rsvp_te_tunnel_removal.j2 — arista-eos #}
! Remove RSVP-TE Tunnel
! Intent: {{ intent_id }}
!
no interface Tunnel{{ tunnel_id }}
!
```

- [ ] **Step 7: Create mvpn_removal.j2**

```jinja2
{# mvpn_removal.j2 — arista-eos #}
! Remove Multicast VPN (mVPN) Configuration
! Intent: {{ intent_id }}
!
vrf instance {{ vrf }}
   no mdt default {{ mdt_default_group | default("") }}
!
```

- [ ] **Step 8: Run MPLS/overlay removal tests**

```bash
python -m pytest intent_networking/tests/test_eos_templates.py::EOSMplsRemovalTest -v
```

Expected: All 7 PASS.

- [ ] **Step 9: Commit**

```bash
git add intent_networking/jinja_templates/arista/eos/6pe_6vpe_removal.j2 intent_networking/jinja_templates/arista/eos/evpn_mpls_removal.j2 intent_networking/jinja_templates/arista/eos/evpn_multisite_removal.j2 intent_networking/jinja_templates/arista/eos/l2vpn_vpls_removal.j2 intent_networking/jinja_templates/arista/eos/pseudowire_removal.j2 intent_networking/jinja_templates/arista/eos/rsvp_te_tunnel_removal.j2 intent_networking/jinja_templates/arista/eos/mvpn_removal.j2
git commit -m "feat: add EOS MPLS/overlay removal templates"
```

---

## Task 7: Removal templates — L2 / Interface / Misc (8 templates)

**Files:** All in `intent_networking/jinja_templates/arista/eos/`

- [ ] **Step 1: Create pvlan_removal.j2**

```jinja2
{# pvlan_removal.j2 — arista-eos #}
! Remove Private VLAN Configuration
! Intent: {{ intent_id }}
!
{% for sec_vlan in secondary_vlans | default([]) %}
vlan {{ sec_vlan }}
   no private-vlan community
!
{% endfor %}
vlan {{ primary_vlan }}
   no private-vlan primary
!
```

- [ ] **Step 2: Create qinq_removal.j2**

```jinja2
{# qinq_removal.j2 — arista-eos #}
! Remove QinQ / Double-Tag Configuration
! Intent: {{ intent_id }}
!
interface {{ interface }}
   no switchport dot1q ethertype
   no switchport trunk allowed vlan {{ outer_vlan | default("") }}
   no switchport mode trunk
!
```

- [ ] **Step 3: Create ipv6_interface_removal.j2**

```jinja2
{# ipv6_interface_removal.j2 — arista-eos #}
! Remove IPv6 Interface Configuration
! Intent: {{ intent_id }}
!
interface {{ interface }}
   no ipv6 address
   no ipv6 enable
!
```

- [ ] **Step 4: Create mgmt_interface_removal.j2**

```jinja2
{# mgmt_interface_removal.j2 — arista-eos #}
! Remove Management Interface Configuration
! Intent: {{ intent_id }}
!
interface {{ interface | default("Management1") }}
   no ip address
   no description
   shutdown
!
```

- [ ] **Step 5: Create lb_vib_removal.j2** (note: filename is lb_vib_removal.j2 matching the file map)

```jinja2
{# lb_vib_removal.j2 — arista-eos #}
! Remove Load Balancer VIP
! Intent: {{ intent_id }}
! VIP: {{ vip_address | default("") }}:{{ vip_port | default("") }}
! Note: LB VIP removal requires coordination with the load balancer platform.
no ip virtual-router address {{ vip_address | default("") }}
!
```

- [ ] **Step 6: Create service_insertion_removal.j2**

```jinja2
{# service_insertion_removal.j2 — arista-eos #}
! Remove Service Insertion / Chaining
! Intent: {{ intent_id }}
! Service: {{ service_name | default("") }}
! Note: Service insertion removal requires policy map detach before deletion.
no policy-map type service-insertion {{ service_name | default("") }}
!
```

- [ ] **Step 7: Create dmvpn_removal.j2**

```jinja2
{# dmvpn_removal.j2 — arista-eos #}
! Remove DMVPN Configuration
! Intent: {{ intent_id }}
!
no interface {{ tunnel_interface | default("Tunnel100") }}
!
```

- [ ] **Step 8: Create stp_root_removal.j2**

```jinja2
{# stp_root_removal.j2 — arista-eos #}
! Remove Spanning Tree Root Configuration
! Intent: {{ intent_id }}
!
{% if vlans | default([]) %}
{% for vlan in vlans %}
no spanning-tree vlan {{ vlan }} priority
{% endfor %}
{% else %}
no spanning-tree priority
{% endif %}
!
```

- [ ] **Step 9: Run L2/interface removal tests**

```bash
python -m pytest intent_networking/tests/test_eos_templates.py::EOSL2RemovalTest -v
```

Expected: All 8 PASS.

- [ ] **Step 10: Commit**

```bash
git add intent_networking/jinja_templates/arista/eos/pvlan_removal.j2 intent_networking/jinja_templates/arista/eos/qinq_removal.j2 intent_networking/jinja_templates/arista/eos/ipv6_interface_removal.j2 intent_networking/jinja_templates/arista/eos/mgmt_interface_removal.j2 intent_networking/jinja_templates/arista/eos/lb_vib_removal.j2 intent_networking/jinja_templates/arista/eos/service_insertion_removal.j2 intent_networking/jinja_templates/arista/eos/dmvpn_removal.j2 intent_networking/jinja_templates/arista/eos/stp_root_removal.j2
git commit -m "feat: add EOS L2/interface removal templates"
```

---

## Task 8: Removal templates — QoS (6 templates)

**Files:** All in `intent_networking/jinja_templates/arista/eos/`

- [ ] **Step 1: Create qos_cos_remark_removal.j2**

```jinja2
{# qos_cos_remark_removal.j2 — arista-eos #}
! Remove CoS Remarking Policy
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface }}
   no service-policy output {{ policy_name | default("") }}
!
{% endfor %}
no policy-map {{ policy_name | default("") }}
!
```

- [ ] **Step 2: Create qos_dscp_mark_removal.j2**

```jinja2
{# qos_dscp_mark_removal.j2 — arista-eos #}
! Remove DSCP Marking Policy
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface }}
   no service-policy input {{ policy_name | default("") }}
!
{% endfor %}
no policy-map {{ policy_name | default("") }}
!
```

- [ ] **Step 3: Create qos_police_removal.j2**

```jinja2
{# qos_police_removal.j2 — arista-eos #}
! Remove Policing Policy
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface }}
   no service-policy input {{ policy_name | default("") }}
!
{% endfor %}
no policy-map {{ policy_name | default("") }}
!
```

- [ ] **Step 4: Create qos_queue_removal.j2**

```jinja2
{# qos_queue_removal.j2 — arista-eos #}
! Remove Queuing Policy
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface }}
   no service-policy output {{ policy_name | default("") }}
!
{% endfor %}
no policy-map {{ policy_name | default("") }}
!
```

- [ ] **Step 5: Create qos_shape_removal.j2**

```jinja2
{# qos_shape_removal.j2 — arista-eos #}
! Remove Traffic Shaping Policy
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface }}
   no service-policy output {{ policy_name | default("") }}
!
{% endfor %}
no policy-map {{ policy_name | default("") }}
!
```

- [ ] **Step 6: Create qos_trust_removal.j2**

```jinja2
{# qos_trust_removal.j2 — arista-eos #}
! Remove QoS Trust Boundary
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface }}
   no qos trust
!
{% endfor %}
!
```

- [ ] **Step 7: Run QoS removal tests**

```bash
python -m pytest intent_networking/tests/test_eos_templates.py::EOSQoSRemovalTest -v
```

Expected: All 6 PASS.

- [ ] **Step 8: Commit**

```bash
git add intent_networking/jinja_templates/arista/eos/qos_cos_remark_removal.j2 intent_networking/jinja_templates/arista/eos/qos_dscp_mark_removal.j2 intent_networking/jinja_templates/arista/eos/qos_police_removal.j2 intent_networking/jinja_templates/arista/eos/qos_queue_removal.j2 intent_networking/jinja_templates/arista/eos/qos_shape_removal.j2 intent_networking/jinja_templates/arista/eos/qos_trust_removal.j2
git commit -m "feat: add EOS QoS removal templates"
```

---

## Task 9: Removal templates — Misc (10 templates)

**Files:** All in `intent_networking/jinja_templates/arista/eos/`

- [ ] **Step 1: Create aaa_removal.j2**

```jinja2
{# aaa_removal.j2 — arista-eos #}
! Remove AAA Configuration
! Intent: {{ intent_id }}
!
no aaa authentication login default
no aaa authorization exec default
no aaa accounting exec default start-stop
{% for srv in radius_servers | default([]) %}
no radius-server host {{ srv.host | default(srv) }}
{% endfor %}
{% for srv in tacacs_servers | default([]) %}
no tacacs-server host {{ srv.host | default(srv) }}
{% endfor %}
!
```

- [ ] **Step 2: Create copp_removal.j2**

```jinja2
{# copp_removal.j2 — arista-eos #}
! Remove CoPP Policy
! Intent: {{ intent_id }}
! Policy: {{ policy_name | default("COPP-POLICY") }}
! Note: Restores default control-plane policy.
no policy-map {{ policy_name | default("COPP-POLICY") }}
!
control-plane
   no service-policy input {{ policy_name | default("COPP-POLICY") }}
!
```

- [ ] **Step 3: Create urpf_removal.j2**

```jinja2
{# urpf_removal.j2 — arista-eos #}
! Remove uRPF Configuration
! Intent: {{ intent_id }}
!
interface {{ interface }}
   no ip verify unicast source reachable-via {{ mode | default("strict") }}
!
```

- [ ] **Step 4: Create eigrp_removal.j2**

```jinja2
{# eigrp_removal.j2 — arista-eos #}
! Remove EIGRP Configuration
! Intent: {{ intent_id }}
!
no router eigrp {{ as_number }}
!
```

- [ ] **Step 5: Create msdp_removal.j2**

```jinja2
{# msdp_removal.j2 — arista-eos #}
! Remove MSDP Configuration
! Intent: {{ intent_id }}
!
{% for peer in peers | default([]) %}
no ip msdp peer {{ peer.peer_ip | default(peer) }}
{% endfor %}
!
```

- [ ] **Step 6: Create multicast_vrf_removal.j2**

```jinja2
{# multicast_vrf_removal.j2 — arista-eos #}
! Remove Multicast VRF Configuration
! Intent: {{ intent_id }}
!
vrf instance {{ vrf }}
   no ip multicast-routing
!
```

- [ ] **Step 7: Create ip_source_guard_removal.j2**

```jinja2
{# ip_source_guard_removal.j2 — arista-eos #}
! Remove IP Source Guard
! Intent: {{ intent_id }}
!
{% for iface in interfaces | default([]) %}
interface {{ iface }}
   no ip verify source
!
{% endfor %}
!
```

- [ ] **Step 8: Create dns_record_removal.j2**

```jinja2
{# dns_record_removal.j2 — arista-eos #}
! Remove DNS Record
! Intent: {{ intent_id }}
! Host: {{ hostname }}  Type: {{ record_type | default("A") }}  Value: {{ value }}
! Note: EOS local DNS entries are removed via the host command.
no ip host {{ hostname }}
!
```

- [ ] **Step 9: Create dhcp_pool_removal.j2**

```jinja2
{# dhcp_pool_removal.j2 — arista-eos #}
! Remove DHCP Pool
! Intent: {{ intent_id }}
!
no ip dhcp pool {{ pool_name }}
!
```

- [ ] **Step 10: Create dhcp_relay_removal.j2**

```jinja2
{# dhcp_relay_removal.j2 — arista-eos #}
! Remove DHCP Relay
! Intent: {{ intent_id }}
!
interface {{ interface }}
{% for srv in relay_servers | default([]) %}
   no ip helper-address {{ srv }}
{% endfor %}
!
```

- [ ] **Step 11: Run misc removal tests**

```bash
python -m pytest intent_networking/tests/test_eos_templates.py::EOSMiscRemovalTest -v
```

Expected: All 10 PASS.

- [ ] **Step 12: Commit**

```bash
git add intent_networking/jinja_templates/arista/eos/aaa_removal.j2 intent_networking/jinja_templates/arista/eos/copp_removal.j2 intent_networking/jinja_templates/arista/eos/urpf_removal.j2 intent_networking/jinja_templates/arista/eos/eigrp_removal.j2 intent_networking/jinja_templates/arista/eos/msdp_removal.j2 intent_networking/jinja_templates/arista/eos/multicast_vrf_removal.j2 intent_networking/jinja_templates/arista/eos/ip_source_guard_removal.j2 intent_networking/jinja_templates/arista/eos/dns_record_removal.j2 intent_networking/jinja_templates/arista/eos/dhcp_pool_removal.j2 intent_networking/jinja_templates/arista/eos/dhcp_relay_removal.j2
git commit -m "feat: add EOS misc removal templates (aaa, copp, urpf, eigrp, msdp, multicast, dhcp, dns)"
```

---

## Task 10: Full test suite verification

- [ ] **Step 1: Run entire EOS template test file**

```bash
python -m pytest intent_networking/tests/test_eos_templates.py -v
```

Expected: All 71 tests PASS.

- [ ] **Step 2: Run full test suite to check for regressions**

```bash
python -m pytest intent_networking/tests/ -v --tb=short 2>&1 | tail -30
```

Expected: No regressions. Pre-existing failures (if any) unchanged.

- [ ] **Step 3: Verify template count is correct**

```bash
python3 -c "
import os
EOS = 'intent_networking/jinja_templates/arista/eos'
provision = [f for f in os.listdir(EOS) if f.endswith('.j2') and not f.endswith('_removal.j2')]
removal = [f for f in os.listdir(EOS) if f.endswith('_removal.j2')]
print(f'Provision templates: {len(provision)}')
print(f'Removal templates: {len(removal)}')
"
```

Expected: Provision: 116, Removal: 92.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete EOS template gap fix — 24 provision + 47 removal templates added"
```
