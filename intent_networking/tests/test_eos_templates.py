"""Tests for Arista EOS Jinja2 templates — provision and removal.

Each test renders a template with minimal valid context and asserts
key EOS CLI strings are present. Uses jinja2 directly — no Django DB needed.
"""

from pathlib import Path

from django.test import SimpleTestCase
from jinja2 import Environment, FileSystemLoader, StrictUndefined

EOS_DIR = Path(__file__).resolve().parent.parent / "jinja_templates" / "arista" / "eos"


def _render(template_name: str, ctx: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(EOS_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template(template_name).render(**ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — Wireless
# ─────────────────────────────────────────────────────────────────────────────


class EOSWirelessProvisionTest(SimpleTestCase):
    """Render tests for Arista EOS wireless provision templates."""

    def test_wireless_ssid_renders(self):
        out = _render(
            "wireless_ssid.j2",
            {
                "intent_id": "t-001",
                "ssid_name": "CorpWifi",
                "security_mode": "wpa3-enterprise",
                "vlan_id": 100,
            },
        )
        self.assertIn("CorpWifi", out)

    def test_wireless_rf_renders(self):
        out = _render(
            "wireless_rf.j2",
            {
                "intent_id": "t-001",
                "channels_2g": [1, 6, 11],
                "channels_5g": [36, 40],
                "tx_power_min": 5,
                "tx_power_max": 20,
            },
        )
        self.assertIn("1, 6, 11", out)

    def test_wireless_vlan_map_renders(self):
        out = _render(
            "wireless_vlan_map.j2",
            {
                "intent_id": "t-001",
                "ssid_name": "CorpWifi",
                "vlan_id": 100,
            },
        )
        self.assertIn("CorpWifi", out)

    def test_wireless_dot1x_renders(self):
        out = _render(
            "wireless_dot1x.j2",
            {
                "intent_id": "t-001",
                "ssid_name": "CorpWifi",
                "radius_servers": ["10.0.0.1"],
                "eap_method": "PEAP",
            },
        )
        self.assertIn("CorpWifi", out)

    def test_wireless_guest_renders(self):
        out = _render(
            "wireless_guest.j2",
            {
                "intent_id": "t-001",
                "ssid_name": "Guest",
                "captive_portal_url": "https://portal.example.com",
                "vlan_id": 200,
            },
        )
        self.assertIn("Guest", out)

    def test_wireless_mesh_renders(self):
        out = _render(
            "wireless_mesh.j2",
            {
                "intent_id": "t-001",
                "backhaul_ssid": "MESH-BH",
                "mesh_role": "map",
                "bridge_group": 1,
            },
        )
        self.assertIn("MESH-BH", out)

    def test_wireless_qos_renders(self):
        out = _render(
            "wireless_qos.j2",
            {
                "intent_id": "t-001",
                "ssid_name": "CorpWifi",
            },
        )
        self.assertIn("CorpWifi", out)

    def test_wireless_band_steer_renders(self):
        out = _render(
            "wireless_band_steer.j2",
            {
                "intent_id": "t-001",
                "preferred_band": "5ghz",
            },
        )
        self.assertIn("5ghz", out)

    def test_wireless_roam_renders(self):
        out = _render(
            "wireless_roam.j2",
            {
                "intent_id": "t-001",
                "ft_enabled": True,
                "ft_over_ds": True,
            },
        )
        self.assertIn("roam", out.lower())

    def test_wireless_segment_renders(self):
        out = _render(
            "wireless_segment.j2",
            {
                "intent_id": "t-001",
                "ssid_name": "CorpWifi",
                "client_isolation": True,
            },
        )
        self.assertIn("CorpWifi", out)

    def test_wireless_flexconnect_renders(self):
        out = _render(
            "wireless_flexconnect.j2",
            {
                "intent_id": "t-001",
                "local_switching": True,
                "ap_group": "AP-GRP-1",
            },
        )
        self.assertIn("AP-GRP-1", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — Cloud (stubs)
# ─────────────────────────────────────────────────────────────────────────────


class EOSCloudProvisionTest(SimpleTestCase):
    """Render tests for Arista EOS cloud provision templates."""

    def test_cloud_vpc_peer_renders(self):
        out = _render(
            "cloud_vpc_peer.j2",
            {
                "intent_id": "t-001",
                "requester_vpc": "vpc-aaa",
                "accepter_vpc": "vpc-bbb",
            },
        )
        self.assertIn("vpc-aaa", out)

    def test_cloud_transit_gw_renders(self):
        out = _render(
            "cloud_transit_gw.j2",
            {
                "intent_id": "t-001",
                "transit_gateway_id": "tgw-123",
            },
        )
        self.assertIn("tgw-123", out)

    def test_cloud_direct_connect_renders(self):
        out = _render(
            "cloud_direct_connect.j2",
            {
                "intent_id": "t-001",
                "connection_id": "dxcon-abc",
                "vlan": 100,
                "bgp_asn": 65000,
                "provider": "aws",
            },
        )
        self.assertIn("dxcon-abc", out)

    def test_cloud_vpn_gw_renders(self):
        out = _render(
            "cloud_vpn_gw.j2",
            {
                "intent_id": "t-001",
                "provider": "aws",
            },
        )
        self.assertIn("aws", out)

    def test_cloud_security_group_renders(self):
        out = _render(
            "cloud_security_group.j2",
            {
                "intent_id": "t-001",
                "group_name": "sg-web",
                "provider": "aws",
            },
        )
        self.assertIn("sg-web", out)

    def test_cloud_nat_renders(self):
        out = _render(
            "cloud_nat.j2",
            {
                "intent_id": "t-001",
                "provider": "aws",
            },
        )
        self.assertIn("aws", out)

    def test_cloud_route_table_renders(self):
        out = _render(
            "cloud_route_table.j2",
            {
                "intent_id": "t-001",
                "provider": "aws",
            },
        )
        self.assertIn("aws", out)

    def test_cloud_sdwan_renders(self):
        out = _render(
            "cloud_sdwan.j2",
            {
                "intent_id": "t-001",
                "provider": "aws",
            },
        )
        self.assertIn("aws", out)

    def test_hybrid_dns_renders(self):
        out = _render(
            "hybrid_dns.j2",
            {
                "intent_id": "t-001",
                "domain": "corp.example.com",
                "forwarders": ["10.0.0.1"],
            },
        )
        self.assertIn("corp.example.com", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — SD-WAN (stubs)
# ─────────────────────────────────────────────────────────────────────────────


class EOSSdwanProvisionTest(SimpleTestCase):
    """Render tests for Arista EOS SD-WAN provision templates."""

    def test_sdwan_overlay_renders(self):
        out = _render(
            "sdwan_overlay.j2",
            {
                "intent_id": "t-001",
                "fabric_name": "SDWAN-FABRIC",
                "system_ip": "10.0.0.1",
            },
        )
        self.assertIn("SDWAN-FABRIC", out)

    def test_sdwan_app_policy_renders(self):
        out = _render(
            "sdwan_app_policy.j2",
            {
                "intent_id": "t-001",
                "policy_name": "APP-POL-1",
            },
        )
        self.assertIn("APP-POL-1", out)

    def test_sdwan_qos_renders(self):
        out = _render(
            "sdwan_qos.j2",
            {
                "intent_id": "t-001",
                "policy_name": "QOS-POL-1",
            },
        )
        self.assertIn("QOS-POL-1", out)

    def test_sdwan_dia_renders(self):
        out = _render(
            "sdwan_dia.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
            },
        )
        self.assertIn("Ethernet1", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — Security / Tunneling
# ─────────────────────────────────────────────────────────────────────────────


class EOSSecurityRemovalTest(SimpleTestCase):
    """Render tests for Arista EOS security and tunnelling removal templates."""

    def test_acl_removal_renders(self):
        out = _render(
            "acl_removal.j2",
            {
                "intent_id": "t-001",
                "acl_name": "ACL-WEB",
                "address_family": "ipv4",
                "apply_interfaces": ["Ethernet1"],
                "direction": "in",
            },
        )
        self.assertIn("no ip access-list", out)
        self.assertIn("ACL-WEB", out)

    def test_zbf_removal_renders(self):
        out = _render(
            "zbf_removal.j2",
            {
                "intent_id": "t-001",
                "zones": [{"name": "INSIDE"}, {"name": "OUTSIDE"}],
                "zone_pairs": [{"source": "INSIDE", "destination": "OUTSIDE", "policy": "ZBF-POL"}],
            },
        )
        self.assertIn("no zone", out)

    def test_gre_tunnel_removal_renders(self):
        out = _render(
            "gre_tunnel_removal.j2",
            {
                "intent_id": "t-001",
                "tunnel_interface": "Tunnel1",
            },
        )
        self.assertIn("no interface Tunnel1", out)

    def test_ipsec_tunnel_removal_renders(self):
        out = _render(
            "ipsec_tunnel_removal.j2",
            {
                "intent_id": "t-001",
                "tunnel_id": 10,
                "remote_peer": "203.0.113.1",
            },
        )
        self.assertIn("no interface Tunnel10", out)

    def test_ipsec_ikev2_removal_renders(self):
        out = _render(
            "ipsec_ikev2_removal.j2",
            {
                "intent_id": "t-001",
                "proposal_name": "IKE-PROP-1",
                "policy_name": "IKE-POL-1",
                "profile_name": "IKE-PROF-1",
                "keyring_name": "IKE-KEYRING-1",
            },
        )
        self.assertIn("no crypto ikev2", out)

    def test_ssl_inspection_removal_renders(self):
        out = _render(
            "ssl_inspection_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "SSL-INSPECT-1",
            },
        )
        self.assertIn("SSL-INSPECT-1", out)

    def test_ra_guard_removal_renders(self):
        out = _render(
            "ra_guard_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "RA-GUARD-1",
                "trusted_ports": ["Ethernet1"],
                "untrusted_ports": ["Ethernet2"],
            },
        )
        self.assertIn("no ipv6 nd raguard", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — Routing / WAN
# ─────────────────────────────────────────────────────────────────────────────


class EOSRoutingRemovalTest(SimpleTestCase):
    """Render tests for Arista EOS routing and WAN removal templates."""

    def test_wan_uplink_removal_renders(self):
        out = _render(
            "wan_uplink_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "ip_address": "203.0.113.1/30",
                "default_route": True,
            },
        )
        self.assertIn("no ip address", out)

    def test_nat_removal_renders(self):
        out = _render(
            "nat_removal.j2",
            {
                "intent_id": "t-001",
                "inside_interfaces": ["Ethernet1"],
                "outside_interfaces": ["Ethernet2"],
            },
        )
        self.assertIn("no ip nat", out)

    def test_nat64_removal_renders(self):
        out = _render(
            "nat64_removal.j2",
            {
                "intent_id": "t-001",
                "interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no nat64", out)

    def test_route_redistribution_removal_renders(self):
        out = _render(
            "route_redistribution_removal.j2",
            {
                "intent_id": "t-001",
                "dest_protocol": "ospf",
                "dest_process": 1,
                "source_protocol": "connected",
            },
        )
        self.assertIn("no redistribute", out)

    def test_bgp_ipv6_af_removal_renders(self):
        out = _render(
            "bgp_ipv6_af_removal.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "neighbors": [{"ip": "2001:db8::1"}],
            },
        )
        self.assertIn("no address-family ipv6", out)

    def test_ospfv3_removal_renders(self):
        out = _render(
            "ospfv3_removal.j2",
            {
                "intent_id": "t-001",
                "process_id": 1,
                "interfaces": [{"name": "Ethernet1"}],
            },
        )
        self.assertIn("no ipv6 router ospf", out)

    def test_ldp_removal_renders(self):
        out = _render(
            "ldp_removal.j2",
            {
                "intent_id": "t-001",
                "interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no mpls ldp", out)

    def test_sr_mpls_removal_renders(self):
        out = _render(
            "sr_mpls_removal.j2",
            {
                "intent_id": "t-001",
                "srgb_start": 16000,
                "srgb_end": 23999,
            },
        )
        self.assertIn("no segment-routing", out)

    def test_srv6_removal_renders(self):
        out = _render(
            "srv6_removal.j2",
            {
                "intent_id": "t-001",
                "locator_name": "MAIN",
            },
        )
        self.assertIn("no segment-routing", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — MPLS / Overlay
# ─────────────────────────────────────────────────────────────────────────────


class EOSMplsRemovalTest(SimpleTestCase):
    """Render tests for Arista EOS MPLS and overlay removal templates."""

    def test_6pe_6vpe_removal_renders(self):
        out = _render(
            "6pe_6vpe_removal.j2",
            {
                "intent_id": "t-001",
                "mode": "6pe",
                "vrf": "",
                "neighbor_ip": "10.0.0.1",
            },
        )
        self.assertIn("no neighbor", out)

    def test_evpn_mpls_removal_renders(self):
        out = _render(
            "evpn_mpls_removal.j2",
            {
                "intent_id": "t-001",
            },
        )
        self.assertIn("no address-family evpn", out)

    def test_evpn_multisite_removal_renders(self):
        out = _render(
            "evpn_multisite_removal.j2",
            {
                "intent_id": "t-001",
            },
        )
        self.assertIn("no address-family evpn", out)

    def test_l2vpn_vpls_removal_renders(self):
        out = _render(
            "l2vpn_vpls_removal.j2",
            {
                "intent_id": "t-001",
                "vpls_name": "VPLS-TEST",
            },
        )
        self.assertIn("no l2vpn vpls", out)

    def test_pseudowire_removal_renders(self):
        out = _render(
            "pseudowire_removal.j2",
            {
                "intent_id": "t-001",
                "pw_id": 100,
                "remote_pe": "10.0.0.1",
            },
        )
        self.assertIn("no interface", out)

    def test_rsvp_te_tunnel_removal_renders(self):
        out = _render(
            "rsvp_te_tunnel_removal.j2",
            {
                "intent_id": "t-001",
                "tunnel_id": 10,
            },
        )
        self.assertIn("no interface Tunnel10", out)

    def test_mvpn_removal_renders(self):
        out = _render(
            "mvpn_removal.j2",
            {
                "intent_id": "t-001",
                "vrf": "CUST-A",
            },
        )
        self.assertIn("no mdt", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — L2 / Interface / Misc
# ─────────────────────────────────────────────────────────────────────────────


class EOSL2RemovalTest(SimpleTestCase):
    """Render tests for Arista EOS L2, interface, and miscellaneous removal templates."""

    def test_pvlan_removal_renders(self):
        out = _render(
            "pvlan_removal.j2",
            {
                "intent_id": "t-001",
                "primary_vlan": 100,
                "secondary_vlans": [101, 102],
            },
        )
        self.assertIn("no private-vlan", out)

    def test_qinq_removal_renders(self):
        out = _render(
            "qinq_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "outer_vlan": 100,
                "inner_vlan": 200,
            },
        )
        self.assertIn("no switchport", out)

    def test_ipv6_interface_removal_renders(self):
        out = _render(
            "ipv6_interface_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
            },
        )
        self.assertIn("no ipv6", out)

    def test_mgmt_interface_removal_renders(self):
        out = _render(
            "mgmt_interface_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Management1",
                "ip_address": "192.168.1.1/24",
            },
        )
        self.assertIn("no ip address", out)

    def test_lb_vip_removal_renders(self):
        out = _render(
            "lb_vip_removal.j2",
            {
                "intent_id": "t-001",
                "vip_address": "10.0.0.100",
                "vip_port": 80,
            },
        )
        self.assertIn("10.0.0.100", out)

    def test_service_insertion_removal_renders(self):
        out = _render(
            "service_insertion_removal.j2",
            {
                "intent_id": "t-001",
                "service_name": "FW-SERVICE",
            },
        )
        self.assertIn("FW-SERVICE", out)

    def test_dmvpn_removal_renders(self):
        out = _render(
            "dmvpn_removal.j2",
            {
                "intent_id": "t-001",
                "tunnel_interface": "Tunnel100",
            },
        )
        self.assertIn("no interface Tunnel100", out)

    def test_stp_root_removal_renders(self):
        out = _render(
            "stp_root_removal.j2",
            {
                "intent_id": "t-001",
                "vlans": [1, 10, 20],
            },
        )
        self.assertIn("no spanning-tree", out)
        self.assertIn("1", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — QoS
# ─────────────────────────────────────────────────────────────────────────────


class EOSQoSRemovalTest(SimpleTestCase):
    """Render tests for Arista EOS QoS removal templates."""

    def test_qos_cos_remark_removal_renders(self):
        out = _render(
            "qos_cos_remark_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "COS-POL",
                "interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no service-policy", out)

    def test_qos_dscp_mark_removal_renders(self):
        out = _render(
            "qos_dscp_mark_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "DSCP-POL",
                "interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no service-policy", out)

    def test_qos_police_removal_renders(self):
        out = _render(
            "qos_police_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "POLICE-POL",
                "interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no service-policy", out)

    def test_qos_queue_removal_renders(self):
        out = _render(
            "qos_queue_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "QUEUE-POL",
                "interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no service-policy", out)

    def test_qos_shape_removal_renders(self):
        out = _render(
            "qos_shape_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "SHAPE-POL",
                "interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no service-policy", out)

    def test_qos_trust_removal_renders(self):
        out = _render(
            "qos_trust_removal.j2",
            {
                "intent_id": "t-001",
                "interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no qos trust", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — Misc
# ─────────────────────────────────────────────────────────────────────────────


class EOSMiscRemovalTest(SimpleTestCase):
    """Render tests for Arista EOS miscellaneous removal templates."""

    def test_aaa_removal_renders(self):
        out = _render(
            "aaa_removal.j2",
            {
                "intent_id": "t-001",
                "radius_servers": [{"host": "10.0.0.1"}],
                "tacacs_servers": [],
            },
        )
        self.assertIn("no aaa", out)

    def test_copp_removal_renders(self):
        out = _render(
            "copp_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "COPP-POLICY",
            },
        )
        self.assertIn("COPP-POLICY", out)

    def test_urpf_removal_renders(self):
        out = _render(
            "urpf_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "mode": "strict",
            },
        )
        self.assertIn("no ip verify unicast", out)

    def test_eigrp_removal_renders(self):
        out = _render(
            "eigrp_removal.j2",
            {
                "intent_id": "t-001",
                "as_number": 100,
            },
        )
        self.assertIn("no router eigrp 100", out)

    def test_msdp_removal_renders(self):
        out = _render(
            "msdp_removal.j2",
            {
                "intent_id": "t-001",
                "peers": [{"peer_ip": "10.0.0.1"}],
            },
        )
        self.assertIn("no ip msdp", out)

    def test_multicast_vrf_removal_renders(self):
        out = _render(
            "multicast_vrf_removal.j2",
            {
                "intent_id": "t-001",
                "vrf": "CUST-A",
            },
        )
        self.assertIn("no ip multicast-routing", out)

    def test_ip_source_guard_removal_renders(self):
        out = _render(
            "ip_source_guard_removal.j2",
            {
                "intent_id": "t-001",
                "interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no ip verify source", out)

    def test_dns_record_removal_renders(self):
        out = _render(
            "dns_record_removal.j2",
            {
                "intent_id": "t-001",
                "hostname": "server1",
                "record_type": "A",
                "value": "10.0.0.1",
            },
        )
        self.assertIn("server1", out)

    def test_dhcp_pool_removal_renders(self):
        out = _render(
            "dhcp_pool_removal.j2",
            {
                "intent_id": "t-001",
                "pool_name": "POOL-1",
            },
        )
        self.assertIn("no ip dhcp pool POOL-1", out)

    def test_dhcp_relay_removal_renders(self):
        out = _render(
            "dhcp_relay_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Vlan10",
                "relay_servers": ["10.0.0.1"],
            },
        )
        self.assertIn("no ip helper-address", out)
