"""Tests for Arista EOS Jinja2 templates — provision and removal.

Each test renders a template with minimal valid context and asserts
key EOS CLI strings are present. Uses jinja2 directly — no Django DB needed.
"""

from pathlib import Path

from django.test import SimpleTestCase
from jinja2 import Environment, FileSystemLoader, StrictUndefined

EOS_DIR = Path(__file__).resolve().parent.parent / "jinja_templates" / "arista" / "eos"

_ENV = Environment(
    loader=FileSystemLoader(str(EOS_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

# Loose env: Undefined (not Strict) for templates that use {% if var %} without is-defined guards.
_ENV_LOOSE = Environment(
    loader=FileSystemLoader(str(EOS_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _render(template_name: str, ctx: dict) -> str:
    return _ENV.get_template(template_name).render(**ctx)


def _render_loose(template_name: str, ctx: dict) -> str:
    return _ENV_LOOSE.get_template(template_name).render(**ctx)


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
                "local_ip": "10.0.0.1/30",
                "bgp_asn": 65000,
                "peer_ip": "10.0.0.2",
                "peer_asn": 64512,
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
        self.assertIn("no security zone", out)

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
                "tunnel_interface": "Tunnel10",
                "crypto_map_name": "CRYPTO-MAP",
                "crypto_map_seq": 10,
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
        self.assertIn("no mpls ip", out)

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
                "local_asn": 65001,
                "mode": "6pe",
                "neighbor_ip": "10.0.0.1",
            },
        )
        self.assertIn("no neighbor", out)

    def test_evpn_mpls_removal_renders(self):
        out = _render(
            "evpn_mpls_removal.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
            },
        )
        self.assertIn("no address-family evpn", out)
        self.assertIn("router bgp 65001", out)

    def test_evpn_multisite_removal_renders(self):
        out = _render(
            "evpn_multisite_removal.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
            },
        )
        self.assertIn("no address-family evpn", out)
        self.assertIn("router bgp 65001", out)

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
                "pseudowires": [{"interface": "Pseudowire100"}],
            },
        )
        self.assertIn("no interface Pseudowire100", out)

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
                "local_asn": 65001,
                "vrf": "CUST-A",
            },
        )
        self.assertIn("no address-family ipv4 multicast", out)


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
                "classes": [{"acl_name": "COPP-ACL-MGMT"}, {"acl_name": "COPP-ACL-ROUTING"}],
            },
        )
        self.assertIn("COPP-ACL-MGMT", out)

    def test_urpf_removal_renders(self):
        out = _render(
            "urpf_removal.j2",
            {
                "intent_id": "t-001",
                "interfaces": [{"name": "Ethernet1", "mode": "strict"}],
            },
        )
        self.assertIn("no ip verify unicast", out)
        self.assertIn("reachable-via rx", out)

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


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — Core Routing (BGP, OSPF, IS-IS, VRF, etc.)
# ─────────────────────────────────────────────────────────────────────────────


class EOSCoreRoutingProvisionTest(SimpleTestCase):  # pylint: disable=too-many-public-methods
    """Render tests for Arista EOS core routing provision templates."""

    def test_bgp_neighbor_renders(self):
        out = _render_loose(
            "bgp_neighbor.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "neighbor_ip": "10.0.0.2",
                "neighbor_asn": 65002,
                "vrf_name": None,
            },
        )
        self.assertIn("router bgp 65001", out)
        self.assertIn("neighbor 10.0.0.2 remote-as 65002", out)

    def test_bgp_network_renders(self):
        out = _render_loose(
            "bgp_network.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "networks": ["10.0.0.0/8", "192.168.0.0/16"],
                "vrf": None,
                "route_map": None,
            },
        )
        self.assertIn("router bgp 65001", out)
        self.assertIn("network 10.0.0.0/8", out)

    def test_bgp_evpn_af_renders(self):
        out = _render_loose(
            "bgp_evpn_af.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "neighbors": [{"ip": "10.0.0.2", "remote_asn": 65002, "update_source": "Loopback0"}],
                "advertise_all_vni": True,
                "route_target_auto": True,
            },
        )
        self.assertIn("address-family evpn", out)
        self.assertIn("10.0.0.2", out)

    def test_bgp_ipv6_af_renders(self):
        out = _render_loose(
            "bgp_ipv6_af.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "neighbors": [{"ip": "2001:db8::2"}],
                "networks": ["2001:db8::/32"],
            },
        )
        self.assertIn("address-family ipv6", out)
        self.assertIn("2001:db8::2", out)

    def test_ospf_renders(self):
        out = _render_loose(
            "ospf.j2",
            {
                "intent_id": "t-001",
                "process_id": 1,
                "router_id": "1.1.1.1",
                "interfaces": [{"name": "Ethernet1", "area": "0.0.0.0"}],
                "passive_interfaces": [],
                "redistribute": [],
            },
        )
        self.assertIn("router ospf 1", out)
        self.assertIn("router-id 1.1.1.1", out)

    def test_ospfv3_renders(self):
        out = _render_loose(
            "ospfv3.j2",
            {
                "intent_id": "t-001",
                "process_id": 1,
                "router_id": "1.1.1.1",
                "interfaces": [{"name": "Ethernet1", "area": "0.0.0.0"}],
                "redistribute": [],
            },
        )
        self.assertIn("ipv6 router ospf 1", out)
        self.assertIn("Ethernet1", out)

    def test_isis_renders(self):
        out = _render_loose(
            "isis.j2",
            {
                "intent_id": "t-001",
                "process_tag": "CORE",
                "net": "49.0001.0000.0000.0001.00",
                "level": "level-2",
                "metric_style": "wide",
                "interfaces": [{"name": "Ethernet1"}],
            },
        )
        self.assertIn("router isis CORE", out)
        self.assertIn("49.0001.0000.0000.0001.00", out)

    def test_vrf_renders(self):
        out = _render_loose(
            "vrf.j2",
            {
                "intent_id": "t-001",
                "vrf_name": "CUST-A",
                "route_distinguisher": "65001:100",
                "rt_import": None,
                "rt_export": None,
                "interfaces": [],
            },
        )
        self.assertIn("vrf instance CUST-A", out)
        self.assertIn("rd 65001:100", out)

    def test_vlan_renders(self):
        out = _render_loose(
            "vlan.j2",
            {
                "vlan_id": 100,
                "vlan_name": "PROD-SERVERS",
                "description": None,
            },
        )
        self.assertIn("vlan 100", out)
        self.assertIn("name PROD-SERVERS", out)

    def test_static_route_renders(self):
        out = _render_loose(
            "static_route.j2",
            {
                "intent_id": "t-001",
                "prefix": "10.0.0.0/8",
                "next_hop": "192.168.1.1",
                "vrf": None,
                "exit_interface": None,
                "admin_distance": None,
                "tag": None,
                "track": None,
                "name": None,
            },
        )
        self.assertIn("ip route 10.0.0.0/8 192.168.1.1", out)

    def test_eigrp_renders(self):
        out = _render_loose(
            "eigrp.j2",
            {
                "intent_id": "t-001",
                "asn": 100,
                "networks": ["10.0.0.0/8"],
                "passive_interfaces": [],
                "redistribute": [],
            },
        )
        self.assertIn("router eigrp 100", out)

    def test_route_redistribution_renders(self):
        out = _render_loose(
            "route_redistribution.j2",
            {
                "intent_id": "t-001",
                "protocol": "bgp",
                "asn": 65001,
                "vrf": None,
                "sources": [{"protocol": "connected", "route_map": None}],
            },
        )
        self.assertIn("router bgp 65001", out)
        self.assertIn("redistribute connected", out)

    def test_route_policy_renders(self):
        out = _render_loose(
            "route_policy.j2",
            {
                "intent_id": "t-001",
                "policy_name": "RM-OUT",
                "entries": [{"action": "permit", "seq": 10, "set_local_preference": 200}],
            },
        )
        self.assertIn("route-map RM-OUT permit 10", out)
        self.assertIn("set local-preference 200", out)

    def test_prefix_list_renders(self):
        out = _render_loose(
            "prefix_list.j2",
            {
                "intent_id": "t-001",
                "list_name": "PFX-IN",
                "entries": [{"seq": 10, "action": "permit", "prefix": "10.0.0.0/8"}],
            },
        )
        self.assertIn("ip prefix-list PFX-IN", out)
        self.assertIn("10.0.0.0/8", out)

    def test_ldp_renders(self):
        out = _render_loose(
            "ldp.j2",
            {
                "intent_id": "t-001",
                "interfaces": ["Ethernet1", "Ethernet2"],
                "router_id": None,
                "password": None,
                "neighbor": None,
            },
        )
        self.assertIn("mpls ip", out)
        self.assertIn("Ethernet1", out)

    def test_sr_mpls_renders(self):
        out = _render_loose(
            "sr_mpls.j2",
            {
                "intent_id": "t-001",
                "process_tag": "CORE",
                "srgb_start": 16000,
                "srgb_end": 23999,
                "interfaces": [],
                "ti_lfa": False,
                "srlb_start": None,
            },
        )
        self.assertIn("segment-routing mpls", out)
        self.assertIn("router isis CORE", out)

    def test_srv6_renders(self):
        out = _render_loose(
            "srv6.j2",
            {
                "intent_id": "t-001",
                "locator_name": "SRv6-LOC",
                "prefix": "2001:db8::/32",
                "sids": [],
                "interfaces": [],
            },
        )
        self.assertIn("segment-routing", out)
        self.assertIn("SRv6-LOC", out)

    def test_6pe_6vpe_renders(self):
        out = _render_loose(
            "6pe_6vpe.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "neighbors": [{"ip": "10.0.0.2"}],
                "networks": [],
                "vrf": None,
            },
        )
        self.assertIn("router bgp 65001", out)
        self.assertIn("address-family ipv6", out)

    def test_evpn_mpls_renders(self):
        out = _render_loose(
            "evpn_mpls.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "neighbors": [{"ip": "10.0.0.2"}],
                "evpn_instances": [],
            },
        )
        self.assertIn("address-family evpn", out)
        self.assertIn("encapsulation mpls", out)

    def test_evpn_multisite_renders(self):
        out = _render_loose(
            "evpn_multisite.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "dci_neighbors": [{"ip": "10.0.0.2", "remote_asn": 65002, "update_source": "Loopback0"}],
                "site_id": 1,
            },
        )
        self.assertIn("address-family evpn", out)
        self.assertIn("10.0.0.2", out)

    def test_l2vpn_vpls_renders(self):
        out = _render_loose(
            "l2vpn_vpls.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "vlan_id": 100,
                "vpls_id": "100:100",
                "route_distinguisher": "65001:100",
                "route_target": "65001:100",
                "pseudowires": [],
            },
        )
        self.assertIn("router bgp 65001", out)

    def test_rsvp_te_tunnel_renders(self):
        out = _render_loose(
            "rsvp_te_tunnel.j2",
            {
                "intent_id": "t-001",
                "tunnel_destination": "10.0.0.2",
                "tunnel_interface": "Tunnel1",
                "tunnel_source": "Loopback0",
                "unnumbered_interface": "Loopback0",
                "interfaces": [],
                "setup_priority": None,
                "bandwidth": None,
                "affinity": None,
                "explicit_path": None,
                "rsvp_bandwidth": 1000000,
            },
        )
        self.assertIn("tunnel mpls traffic-eng", out)
        self.assertIn("10.0.0.2", out)

    def test_pbr_renders(self):
        out = _render_loose(
            "pbr.j2",
            {
                "intent_id": "t-001",
                "policy_name": "PBR-OUT",
                "entries": [{"action": "permit", "seq": 10, "set_next_hop": "10.0.0.1", "match_acl": "ACL-PBR"}],
                "apply_interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("route-map PBR-OUT permit 10", out)
        self.assertIn("set ip next-hop 10.0.0.1", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — L2 / DC / Overlay
# ─────────────────────────────────────────────────────────────────────────────


class EOSL2DCProvisionTest(SimpleTestCase):
    """Render tests for Arista EOS L2/DC/overlay provision templates."""

    def test_l2_port_access_renders(self):
        out = _render_loose(
            "l2_port.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "mode": "access",
                "access_vlan": 100,
                "description": "server-01",
                "voice_vlan": None,
                "portfast": True,
                "bpdu_guard": True,
            },
        )
        self.assertIn("interface Ethernet1", out)
        self.assertIn("switchport mode access", out)
        self.assertIn("switchport access vlan 100", out)

    def test_l2_port_trunk_renders(self):
        out = _render_loose(
            "l2_port.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet2",
                "mode": "trunk",
                "allowed_vlans": [100, 200, 300],
                "native_vlan": 1,
                "description": None,
                "voice_vlan": None,
                "portfast": False,
                "bpdu_guard": False,
            },
        )
        self.assertIn("switchport mode trunk", out)
        self.assertIn("100,200,300", out)

    def test_l2vni_renders(self):
        out = _render_loose(
            "l2vni.j2",
            {
                "intent_id": "t-001",
                "vlan_id": 100,
                "vni": 10100,
                "vlan_name": "PROD",
                "bgp_asn": 65001,
                "replication_mode": "ingress",
                "mcast_group": None,
            },
        )
        self.assertIn("vxlan vlan 100 vni 10100", out)

    def test_l3vni_renders(self):
        out = _render_loose(
            "l3vni.j2",
            {
                "intent_id": "t-001",
                "vrf_name": "CUST-A",
                "vni": 50001,
                "vlan_id": 3001,
                "bgp_asn": 65001,
                "redistribute_connected": True,
                "anycast_gateway_mac": None,
            },
        )
        self.assertIn("vxlan vrf CUST-A vni 50001", out)

    def test_mlag_renders(self):
        out = _render_loose(
            "mlag.j2",
            {
                "intent_id": "t-001",
                "domain_id": "MLAG-DOMAIN",
                "peer_address": "10.0.0.2",
                "peer_link_interfaces": ["Ethernet47", "Ethernet48"],
                "keepalive_vlan": 4093,
                "peer_link_vlan": 4094,
                "peer_link_channel": 2000,
                "description": None,
                "reload_delay": None,
                "reload_delay_non_mlag": None,
            },
        )
        self.assertIn("mlag configuration", out)
        self.assertIn("domain-id MLAG-DOMAIN", out)
        self.assertIn("peer-address 10.0.0.2", out)

    def test_lag_renders(self):
        out = _render_loose(
            "lag.j2",
            {
                "intent_id": "t-001",
                "channel_id": 10,
                "member_interfaces": ["Ethernet1", "Ethernet2"],
                "mode": "trunk",
                "allowed_vlans": [100, 200],
                "description": "uplink",
                "mtu": 9214,
                "lacp_mode": "active",
            },
        )
        self.assertIn("interface Port-Channel10", out)
        self.assertIn("channel-group 10 mode active", out)

    def test_vtep_renders(self):
        out = _render_loose(
            "vtep.j2",
            {
                "intent_id": "t-001",
                "source_interface": "Loopback1",
                "replication_mode": "ingress",
                "l2_vni": [{"vlan_id": 100, "vni": 10100}],
                "l3_vni": [{"vrf_name": "CUST-A", "vni": 50001}],
                "vni_map": [],
                "nve_interface": "Vxlan1",
            },
        )
        self.assertIn("vxlan source-interface Loopback1", out)
        self.assertIn("vxlan vlan 100 vni 10100", out)

    def test_anycast_gateway_renders(self):
        out = _render_loose(
            "anycast_gateway.j2",
            {
                "intent_id": "t-001",
                "vlan_id": 100,
                "virtual_ip": "10.0.0.1",
                "subnet_mask": 24,
                "vrf": "CUST-A",
                "anycast_mac": "00:1c:73:00:00:01",
            },
        )
        self.assertIn("ip address virtual 10.0.0.1/24", out)
        self.assertIn("Vlan100", out)

    def test_pvlan_renders(self):
        out = _render_loose(
            "pvlan.j2",
            {
                "intent_id": "t-001",
                "primary_vlan": 100,
                "secondary_vlans": [101, 102],
                "secondary_type": "isolated",
                "promiscuous_interfaces": ["Ethernet1"],
                "host_interfaces": [],
            },
        )
        self.assertIn("private-vlan type primary", out)
        self.assertIn("vlan 101", out)

    def test_qinq_renders(self):
        out = _render_loose(
            "qinq.j2",
            {
                "intent_id": "t-001",
                "interfaces": [{"name": "Ethernet1", "outer_vlan": 100, "description": "QinQ"}],
            },
        )
        self.assertIn("switchport mode dot1q-tunnel", out)
        self.assertIn("Ethernet1", out)

    def test_fhrp_renders(self):
        out = _render_loose(
            "fhrp.j2",
            {
                "intent_id": "t-001",
                "groups": [
                    {
                        "interface": "Vlan100",
                        "group_id": 10,
                        "virtual_ip": "10.0.0.254",
                        "priority": 110,
                        "preempt": True,
                        "track_interface": None,
                        "authentication": None,
                    }
                ],
            },
        )
        self.assertIn("vrrp 10 priority 110", out)
        self.assertIn("vrrp 10 ipv4 10.0.0.254", out)

    def test_pseudowire_renders(self):
        out = _render_loose(
            "pseudowire.j2",
            {
                "intent_id": "t-001",
                "pseudowires": [{"interface": "Pseudowire100", "neighbor": "10.0.0.2", "vc_id": 100}],
            },
        )
        self.assertIn("Pseudowire100", out)
        self.assertIn("neighbor 10.0.0.2 100", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — Management
# ─────────────────────────────────────────────────────────────────────────────


class EOSManagementProvisionTest(SimpleTestCase):
    """Render tests for Arista EOS management provision templates."""

    def test_aaa_renders(self):
        out = _render_loose(
            "aaa.j2",
            {
                "intent_id": "t-001",
                "auth_methods": "group tacacs+ local",
                "enable_auth": None,
                "authorization": None,
                "accounting": None,
                "radius_servers": [],
                "tacacs_servers": [{"ip": "10.0.0.1", "key": "secret"}],
            },
        )
        self.assertIn("aaa authentication login default", out)
        self.assertIn("tacacs-server host 10.0.0.1", out)

    def test_ntp_renders(self):
        out = _render_loose(
            "ntp.j2",
            {
                "intent_id": "t-001",
                "servers": ["10.0.0.1", "10.0.0.2"],
                "prefer": "10.0.0.1",
                "source_interface": "Management1",
                "authentication": False,
            },
        )
        self.assertIn("ntp server 10.0.0.1 prefer", out)
        self.assertIn("ntp local-interface Management1", out)

    def test_snmp_v2c_renders(self):
        out = _render_loose(
            "snmp.j2",
            {
                "intent_id": "t-001",
                "version": "v2c",
                "community": "public",
                "location": "DC-EAST",
                "contact": "noc@example.com",
                "views": [],
                "groups": [],
                "users": [],
                "trap_targets": ["10.0.0.5"],
            },
        )
        self.assertIn("snmp-server community public ro", out)
        self.assertIn("snmp-server location DC-EAST", out)
        self.assertIn("snmp-server host 10.0.0.5", out)

    def test_snmp_v3_renders(self):
        out = _render_loose(
            "snmp.j2",
            {
                "intent_id": "t-001",
                "version": "v3",
                "community": None,
                "location": "DC-EAST",
                "contact": None,
                "views": [{"name": "ALL-VIEW", "oid": "1.3.6.1"}],
                "groups": [{"name": "NOC-GROUP", "security_level": "priv", "read_view": "ALL-VIEW"}],
                "users": [
                    {
                        "name": "noc-user",
                        "group": "NOC-GROUP",
                        "auth_protocol": "sha",
                        "auth_password": "authpass",
                        "priv_protocol": "aes128",
                        "priv_password": "privpass",
                    }
                ],
                "trap_targets": [],
            },
        )
        self.assertIn("snmp-server user noc-user NOC-GROUP v3", out)
        self.assertIn("snmp-server group NOC-GROUP v3", out)

    def test_syslog_renders(self):
        out = _render_loose(
            "syslog.j2",
            {
                "intent_id": "t-001",
                "servers": ["10.0.0.10"],
                "facility": "local7",
                "severity": "informational",
                "source_interface": "Management1",
            },
        )
        self.assertIn("logging host 10.0.0.10", out)
        self.assertIn("logging facility local7", out)

    def test_ssh_renders(self):
        out = _render_loose(
            "ssh.j2",
            {
                "intent_id": "t-001",
                "timeout": 60,
                "version": 2,
                "key_type": None,
                "key_size": None,
                "allowed_networks": None,
                "acl_name": None,
            },
        )
        self.assertIn("management ssh", out)
        self.assertIn("idle-timeout 60", out)

    def test_motd_renders(self):
        out = _render_loose(
            "motd.j2",
            {
                "intent_id": "t-001",
                "motd_banner": "Authorized access only",
                "login_banner": None,
                "exec_banner": None,
            },
        )
        self.assertIn("banner motd", out)
        self.assertIn("Authorized access only", out)

    def test_netconf_renders(self):
        out = _render_loose(
            "netconf.j2",
            {
                "intent_id": "t-001",
                "netconf_enabled": True,
                "vrf": "MGMT",
                "port": 830,
                "enable_restconf": False,
                "restconf_port": None,
                "restconf_vrf": None,
                "gnmi_enabled": False,
                "gnmi_port": None,
            },
        )
        self.assertIn("management api netconf", out)
        self.assertIn("transport ssh default", out)

    def test_netflow_renders(self):
        out = _render_loose(
            "netflow.j2",
            {
                "intent_id": "t-001",
                "apply_interfaces": ["Ethernet1"],
                "collector_ip": "10.0.0.10",
                "collector_port": 2055,
                "source_interface": "Management1",
                "sampler_rate": 1024,
                "exporter_name": None,
            },
        )
        self.assertIn("sflow destination 10.0.0.10", out)
        self.assertIn("sflow run", out)

    def test_telemetry_renders(self):
        out = _render_loose(
            "telemetry.j2",
            {
                "intent_id": "t-001",
                "destination_ip": "10.0.0.10",
                "destination_port": 6030,
                "protocol": "grpc",
                "encoding": "json",
                "source_interface": None,
                "subscriptions": [],
            },
        )
        self.assertIn("management api gnmi", out)

    def test_mgmt_interface_renders(self):
        out = _render_loose(
            "mgmt_interface.j2",
            {
                "intent_id": "t-001",
                "interface": "Management1",
                "ip_address": "192.168.1.1/24",
                "gateway": "192.168.1.254",
                "vrf": "MGMT",
            },
        )
        self.assertIn("interface Management1", out)
        self.assertIn("ip address 192.168.1.1/24", out)

    def test_lldp_cdp_renders(self):
        out = _render_loose(
            "lldp_cdp.j2",
            {
                "intent_id": "t-001",
                "lldp_global": True,
                "disable_on": [],
            },
        )
        self.assertIn("lldp run", out)

    def test_global_config_renders(self):
        out = _render_loose(
            "global_config.j2",
            {
                "intent_id": "t-001",
                "hostname": "leaf-01",
                "domain_name": "corp.example.com",
                "dns_domain_list": [],
                "dns_servers": ["8.8.8.8"],
                "timezone": "UTC",
                "timezone_offset": None,
                "ntp_servers": ["10.0.0.1"],
                "ntp_prefer": "10.0.0.1",
                "ntp_source_interface": "Management1",
                "syslog_servers": ["10.0.0.10"],
                "syslog_source_interface": None,
                "syslog_facility": "local7",
                "syslog_trap_level": "informational",
                "snmp_version": "v2c",
                "snmp_community": "public",
                "snmp_location": "DC-EAST",
                "snmp_contact": None,
                "snmp_views": [],
                "snmp_groups": [],
                "snmp_users": [],
                "snmp_trap_targets": [],
                "login_banner": None,
                "motd_banner": None,
                "enable_ssh": True,
                "ssh_timeout": 60,
                "enable_netconf": False,
                "enable_restconf": False,
                "enable_lldp": True,
                "dhcp_pools": [],
            },
        )
        self.assertIn("hostname leaf-01", out)
        self.assertIn("ntp server 10.0.0.1 prefer", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — Security / Tunneling
# ─────────────────────────────────────────────────────────────────────────────


class EOSSecurityTunnelingProvisionTest(SimpleTestCase):
    """Render tests for Arista EOS security and tunneling provision templates."""

    def test_acl_extended_renders(self):
        out = _render_loose(
            "acl.j2",
            {
                "intent_id": "t-001",
                "acl_name": "ACL-WEB",
                "acl_type": "extended",
                "address_family": "ipv4",
                "entries": [
                    {
                        "seq": 10,
                        "action": "permit",
                        "protocol": "tcp",
                        "source": "10.0.0.0/8",
                        "destination": "any",
                        "port": 80,
                    }
                ],
                "apply_interfaces": ["Ethernet1"],
                "direction": "in",
            },
        )
        self.assertIn("ip access-list ACL-WEB", out)
        self.assertIn("permit tcp", out)

    def test_fw_rule_renders(self):
        out = _render_loose(
            "fw_rule.j2",
            {
                "intent_id": "t-001",
                "intent_version": 1,
                "policy_name": "FW-POLICY",
                "firewall_type": "stateless",
                "default_action": "deny",
                "rules": [
                    {
                        "action": "permit",
                        "protocol": "tcp",
                        "source": "10.0.0.0/8",
                        "destination": "any",
                        "port": 443,
                    }
                ],
                "apply_interfaces": ["Ethernet1"],
                "direction": "in",
            },
        )
        self.assertIn("ip access-list FW-POLICY", out)
        self.assertIn("permit tcp", out)

    def test_gre_tunnel_renders(self):
        out = _render_loose(
            "gre_tunnel.j2",
            {
                "intent_id": "t-001",
                "tunnel_interface": "Tunnel1",
                "tunnel_ip": "172.16.0.1/30",
                "tunnel_source": "Loopback0",
                "tunnel_destination": "203.0.113.1",
                "description": None,
                "tunnel_key": None,
                "keepalive": None,
                "mtu": None,
            },
        )
        self.assertIn("interface Tunnel1", out)
        self.assertIn("tunnel source Loopback0", out)
        self.assertIn("tunnel destination 203.0.113.1", out)

    def test_ipsec_ikev2_renders(self):
        out = _render_loose(
            "ipsec_ikev2.j2",
            {
                "intent_id": "t-001",
                "peer_ip": "203.0.113.1",
                "pre_shared_key": "supersecret",
                "proposal": {"name": "IKEv2-PROP", "encryption": "aes256", "integrity": "sha256", "dh_group": 14},
                "policy": {"name": "IKEv2-POL"},
                "profile": {"name": "IKEv2-PROF"},
            },
        )
        self.assertIn("crypto ikev2 proposal IKEv2-PROP", out)
        self.assertIn("encryption aes256", out)

    def test_ipsec_tunnel_renders(self):
        out = _render_loose(
            "ipsec_tunnel.j2",
            {
                "intent_id": "t-001",
                "peer_ip": "203.0.113.1",
                "pre_shared_key": "supersecret",
                "acl_name": "CRYPTO-ACL",
                "crypto_map_name": "CRYPTO-MAP",
                "crypto_map_seq": 10,
                "isakmp_policy": {"priority": 10, "encryption": "aes256", "hash": "sha256"},
                "transform_set": {"name": "TS-AES", "encryption": "esp-aes 256", "integrity": "esp-sha256-hmac"},
                "tunnel_interface": None,
            },
        )
        self.assertIn("crypto isakmp key supersecret address 203.0.113.1", out)
        self.assertIn("set peer 203.0.113.1", out)

    def test_dmvpn_renders(self):
        out = _render_loose(
            "dmvpn.j2",
            {
                "intent_id": "t-001",
                "tunnel_interface": "Tunnel100",
                "tunnel_ip": "10.0.0.1/24",
                "tunnel_source": "Ethernet1",
                "nhrp_network_id": 1,
                "nhrp_nhs": "10.0.0.254",
                "nhrp_map": None,
                "tunnel_key": None,
                "ipsec_profile": None,
                "description": None,
            },
        )
        self.assertIn("interface Tunnel100", out)
        self.assertIn("tunnel mode gre multipoint", out)
        self.assertIn("ip nhrp network-id 1", out)

    def test_zbf_renders(self):
        out = _render_loose(
            "zbf.j2",
            {
                "intent_id": "t-001",
                "zones": [
                    {"name": "INSIDE", "interfaces": ["Ethernet1"]},
                    {"name": "OUTSIDE", "interfaces": ["Ethernet2"]},
                ],
                "class_maps": [{"name": "PERMIT-INSIDE", "match": []}],
                "zone_pairs": [{"source": "INSIDE", "destination": "OUTSIDE", "policy": "ZBF-POL"}],
            },
        )
        self.assertIn("security zone INSIDE", out)
        self.assertIn("security zone-pair INSIDE-to-OUTSIDE", out)

    def test_ssl_inspection_renders(self):
        out = _render_loose(
            "ssl_inspection.j2",
            {
                "intent_id": "t-001",
                "policy_name": "SSL-INSPECT",
                "ca_cert": None,
                "bypass_categories": [],
                "decrypt_categories": [],
            },
        )
        self.assertIn("SSL-INSPECT", out)

    def test_ra_guard_renders(self):
        out = _render_loose(
            "ra_guard.j2",
            {
                "intent_id": "t-001",
                "trusted_ports": ["Ethernet1"],
                "untrusted_ports": ["Ethernet2"],
                "policy_name": None,
            },
        )
        self.assertIn("ipv6 nd ra-guard trusted", out)

    def test_macsec_renders(self):
        out = _render_loose(
            "macsec.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "policy_name": "MACSEC-POL",
                "cipher_suite": "gcm-aes-128",
                "key_chain": "MACSEC-KEYS",
                "key_id": "01",
                "replay_protection": True,
                "replay_window": 32,
            },
        )
        self.assertIn("mac security profile MACSEC-POL", out)
        self.assertIn("interface Ethernet1", out)

    def test_port_security_renders(self):
        out = _render_loose(
            "port_security.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "max_mac": 2,
                "violation_action": "restrict",
                "sticky": True,
                "aging_time": 60,
            },
        )
        self.assertIn("switchport port-security", out)
        self.assertIn("switchport port-security maximum 2", out)

    def test_storm_control_renders(self):
        out = _render_loose(
            "storm_control.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "broadcast_level": 10,
                "multicast_level": 10,
                "unicast_level": None,
                "action": "shutdown",
            },
        )
        self.assertIn("storm-control broadcast level 10", out)

    def test_ip_source_guard_renders(self):
        out = _render_loose(
            "ip_source_guard.j2",
            {
                "intent_id": "t-001",
                "interfaces": ["Ethernet1", "Ethernet2"],
            },
        )
        self.assertIn("ip verify source", out)

    def test_urpf_renders(self):
        out = _render_loose(
            "urpf.j2",
            {
                "intent_id": "t-001",
                "interfaces": [{"name": "Ethernet1", "mode": "strict"}],
            },
        )
        self.assertIn("ip verify unicast source reachable-via rx", out)

    def test_service_insertion_renders(self):
        out = _render_loose(
            "service_insertion.j2",
            {
                "intent_id": "t-001",
                "service_node": "FW-01",
                "redirect_interface": "Ethernet3",
                "service_chain": [],
            },
        )
        self.assertIn("FW-01", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — DHCP / DNS / IPAM
# ─────────────────────────────────────────────────────────────────────────────


class EOSDhcpDnsProvisionTest(SimpleTestCase):
    """Render tests for Arista EOS DHCP, DNS, and IPAM provision templates."""

    def test_dhcp_pool_renders(self):
        out = _render_loose(
            "dhcp_pool.j2",
            {
                "intent_id": "t-001",
                "network": "10.0.0.0/24",
                "default_router": "10.0.0.1",
                "dns_server": "8.8.8.8",
                "lease_time": "1",
                "ranges": [{"start": "10.0.0.100", "end": "10.0.0.200"}],
                "excluded_addresses": [],
            },
        )
        self.assertIn("subnet 10.0.0.0/24", out)
        self.assertIn("default-gateway 10.0.0.1", out)

    def test_dhcp_relay_renders(self):
        out = _render_loose(
            "dhcp_relay.j2",
            {
                "intent_id": "t-001",
                "interface": "Vlan100",
                "helper_address": "10.0.0.1",
            },
        )
        self.assertIn("ip helper-address 10.0.0.1", out)

    def test_dhcp_server_renders(self):
        out = _render_loose(
            "dhcp_server.j2",
            {
                "intent_id": "t-001",
                "pools": [
                    {
                        "network": "10.0.0.0/24",
                        "default_router": "10.0.0.1",
                        "dns_server": "8.8.8.8",
                        "lease_time": "1",
                        "domain_name": "corp.example.com",
                        "ranges": [],
                        "excluded_addresses": [],
                    }
                ],
            },
        )
        self.assertIn("subnet 10.0.0.0/24", out)

    def test_dhcp_snooping_renders(self):
        out = _render_loose(
            "dhcp_snooping.j2",
            {
                "intent_id": "t-001",
                "vlans": [100, 200],
                "trusted_interfaces": ["Ethernet1"],
                "rate_limit": 100,
                "verify_mac": True,
            },
        )
        self.assertIn("ip dhcp snooping", out)
        self.assertIn("ip dhcp snooping vlan 100", out)

    def test_dns_renders(self):
        out = _render_loose(
            "dns.j2",
            {
                "intent_id": "t-001",
                "domain_name": "corp.example.com",
                "domain_list": [],
                "servers": ["8.8.8.8", "8.8.4.4"],
            },
        )
        self.assertIn("dns domain corp.example.com", out)
        self.assertIn("name-server 8.8.8.8", out)

    def test_dns_record_renders(self):
        out = _render_loose(
            "dns_record.j2",
            {
                "intent_id": "t-001",
                "record_name": "server1",
                "record_type": "A",
                "record_value": "10.0.0.1",
                "ttl": 300,
            },
        )
        self.assertIn("server1", out)

    def test_dot1x_renders(self):
        out = _render_loose(
            "dot1x.j2",
            {
                "intent_id": "t-001",
                "radius_group": "radius",
                "interfaces": [
                    {
                        "name": "Ethernet1",
                        "port_control": "auto",
                        "host_mode": "single-host",
                        "reauth_period": None,
                        "mab": False,
                    }
                ],
            },
        )
        self.assertIn("dot1x system-auth-control", out)
        self.assertIn("dot1x port-control auto", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — QoS (apply)
# ─────────────────────────────────────────────────────────────────────────────


class EOSQoSProvisionTest(SimpleTestCase):
    """Render tests for Arista EOS QoS provision templates."""

    def test_qos_classify_renders(self):
        out = _render_loose(
            "qos_classify.j2",
            {
                "intent_id": "t-001",
                "policy_map": "QOS-IN",
                "class_maps": [
                    {
                        "name": "VOICE",
                        "dscp": "ef",
                        "acl": None,
                        "rules": [],
                        "set_dscp": None,
                        "set_cos": None,
                        "police_rate": None,
                        "cos": None,
                        "protocol": None,
                    }
                ],
                "apply_interfaces": ["Ethernet1"],
                "direction": "input",
            },
        )
        self.assertIn("policy-map QOS-IN", out)
        self.assertIn("class-map match-any VOICE", out)

    def test_qos_cos_remark_renders(self):
        out = _render_loose(
            "qos_cos_remark.j2",
            {
                "intent_id": "t-001",
                "trust_cos": True,
                "apply_interfaces": ["Ethernet1"],
                "cos_map": [{"cos": 5, "dscp": "ef"}],
            },
        )
        self.assertIn("qos trust cos", out)

    def test_qos_dscp_mark_renders(self):
        out = _render_loose(
            "qos_dscp_mark.j2",
            {
                "intent_id": "t-001",
                "policy_map": "DSCP-POL",
                "markings": [{"class_name": "VOICE", "dscp": "ef"}],
                "apply_interfaces": ["Ethernet1"],
                "trust_boundary": None,
            },
        )
        self.assertIn("policy-map DSCP-POL", out)
        self.assertIn("set dscp ef", out)

    def test_qos_police_renders(self):
        out = _render_loose(
            "qos_police.j2",
            {
                "intent_id": "t-001",
                "policy_map": "POLICE-POL",
                "rate_bps": 1000000,
                "burst_bytes": 8000,
                "conform_action": "transmit",
                "exceed_action": "drop",
                "violate_action": None,
                "apply_interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("policy-map POLICE-POL", out)
        self.assertIn("police rate 1000000", out)

    def test_qos_queue_renders(self):
        out = _render_loose(
            "qos_queue.j2",
            {
                "intent_id": "t-001",
                "policy_map": "QUEUE-POL",
                "queues": [
                    {
                        "class_name": "VOICE",
                        "bandwidth_percent": 30,
                        "priority": True,
                        "shape_rate": None,
                        "queue_limit": None,
                    }
                ],
                "apply_interfaces": ["Ethernet1"],
                "direction": "output",
            },
        )
        self.assertIn("policy-map QUEUE-POL", out)
        self.assertIn("class VOICE", out)

    def test_qos_shape_renders(self):
        out = _render_loose(
            "qos_shape.j2",
            {
                "intent_id": "t-001",
                "policy_map": "SHAPE-POL",
                "rate_bps": 100000000,
                "child_policy": None,
                "apply_interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("policy-map SHAPE-POL", out)
        self.assertIn("shape rate 100000000", out)

    def test_qos_trust_renders(self):
        out = _render_loose(
            "qos_trust.j2",
            {
                "intent_id": "t-001",
                "trust_type": "dscp",
                "apply_interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("qos trust dscp", out)


# ─────────────────────────────────────────────────────────────────────────────
# Provision templates — WAN / Multicast / Misc
# ─────────────────────────────────────────────────────────────────────────────


class EOSWanMulticastMiscProvisionTest(SimpleTestCase):
    """Render tests for Arista EOS WAN, multicast, and misc provision templates."""

    def test_wan_uplink_renders(self):
        out = _render_loose(
            "wan_uplink.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "ip_address": "203.0.113.1/30",
                "bandwidth": None,
                "description": "ISP-A",
                "default_route": "203.0.113.2",
                "admin_distance": None,
                "isp_name": None,
            },
        )
        self.assertIn("interface Ethernet1", out)
        self.assertIn("ip address 203.0.113.1/30", out)
        self.assertIn("ip route 0.0.0.0/0 203.0.113.2", out)

    def test_nat_pat_renders(self):
        out = _render_loose(
            "nat.j2",
            {
                "intent_id": "t-001",
                "nat_type": "pat",
                "acl": "NAT-ACL",
                "outside_interface": "Ethernet1",
                "inside_interface": "Ethernet2",
                "static_mappings": [],
                "pool_name": None,
                "pool_start": None,
                "pool_end": None,
                "prefix_length": None,
                "overload": True,
            },
        )
        self.assertIn("ip nat source list NAT-ACL interface Ethernet1 overload", out)

    def test_nat64_renders(self):
        out = _render_loose(
            "nat64.j2",
            {
                "intent_id": "t-001",
                "prefix": "64:ff9b::/96",
                "mode": "stateless",
                "interfaces": ["Ethernet1"],
                "v4_pool": None,
            },
        )
        self.assertIn("ipv6 nat prefix 64:ff9b::/96", out)

    def test_bfd_renders(self):
        out = _render_loose(
            "bfd.j2",
            {
                "intent_id": "t-001",
                "interfaces": [{"name": "Ethernet1", "interval": 300, "min_rx": 300, "multiplier": 3}],
                "echo_mode": True,
            },
        )
        self.assertIn("bfd interval 300 min-rx 300 multiplier 3", out)

    def test_dai_renders(self):
        out = _render_loose(
            "dai.j2",
            {
                "intent_id": "t-001",
                "vlans": [100, 200],
                "trusted_interfaces": ["Ethernet1"],
                "rate_limit": 100,
            },
        )
        self.assertIn("ip arp inspection vlan 100", out)
        self.assertIn("ip arp inspection trust", out)

    def test_copp_renders(self):
        out = _render_loose(
            "copp.j2",
            {
                "intent_id": "t-001",
                "classes": [
                    {
                        "acl_name": "COPP-MGMT",
                        "rules": [
                            {
                                "seq": 10,
                                "action": "permit",
                                "protocol": "tcp",
                                "source": "any",
                                "destination": "any",
                                "port": "22",
                            }
                        ],
                    }
                ],
            },
        )
        self.assertIn("ip access-list COPP-MGMT", out)
        self.assertIn("system control-plane", out)

    def test_pim_sm_renders(self):
        out = _render_loose(
            "pim.j2",
            {
                "intent_id": "t-001",
                "mode": "sparse-mode",
                "rp_address": "10.0.0.10",
                "rp_type": "static",
                "interfaces": [{"name": "Ethernet1"}],
                "bsr_candidate": None,
                "anycast_rp_set": [],
                "ssm_range": None,
            },
        )
        self.assertIn("ip pim rp-address 10.0.0.10", out)
        self.assertIn("ip pim sparse-mode", out)

    def test_igmp_snooping_renders(self):
        out = _render_loose(
            "igmp_snooping.j2",
            {
                "intent_id": "t-001",
                "vlans": [100, 200],
                "querier_enabled": True,
                "querier_address": "10.0.0.1",
                "fast_leave": True,
            },
        )
        self.assertIn("ip igmp snooping", out)
        self.assertIn("ip igmp snooping vlan 100", out)

    def test_msdp_renders(self):
        out = _render_loose(
            "msdp.j2",
            {
                "intent_id": "t-001",
                "peers": [{"ip": "10.0.0.2", "remote_as": 65002, "connect_source": "Loopback0", "sa_limit": None}],
                "originator_id": "10.0.0.1",
                "default_peer": None,
                "sa_filter": None,
            },
        )
        self.assertIn("ip msdp peer 10.0.0.2", out)

    def test_multicast_vrf_renders(self):
        out = _render_loose(
            "multicast_vrf.j2",
            {
                "intent_id": "t-001",
                "vrf": "CUST-A",
                "pim_mode": "sparse-mode",
                "rp_address": "10.0.0.10",
                "interfaces": [{"name": "Ethernet1"}],
                "mdt_default_group": None,
            },
        )
        self.assertIn("vrf instance CUST-A", out)
        self.assertIn("ip pim vrf CUST-A rp-address 10.0.0.10", out)

    def test_mvpn_renders(self):
        out = _render_loose(
            "mvpn.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "vrf": "CUST-A",
                "neighbors": [{"ip": "10.0.0.2"}],
                "mdt_default": "239.0.0.1",
            },
        )
        self.assertIn("address-family ipv4 multicast", out)

    def test_ip_sla_renders(self):
        out = _render_loose(
            "ip_sla.j2",
            {
                "intent_id": "t-001",
                "sla_id": "SLA-1",
                "probe_type": "icmp-echo",
                "target": "10.0.0.1",
                "interval": 60,
                "frequency": None,
                "threshold": 3000,
            },
        )
        self.assertIn("monitor connectivity", out)
        self.assertIn("SLA-1", out)

    def test_ipv6_interface_renders(self):
        out = _render_loose(
            "ipv6_interface.j2",
            {
                "intent_id": "t-001",
                "ipv6_unicast_routing": True,
                "interfaces": [
                    {"name": "Ethernet1", "ipv6_address": "2001:db8::1/64", "link_local": None, "ra_suppress": True}
                ],
            },
        )
        self.assertIn("ipv6 unicast-routing", out)
        self.assertIn("ipv6 address 2001:db8::1/64", out)

    def test_loopback_renders(self):
        out = _render_loose(
            "loopback.j2",
            {
                "intent_id": "t-001",
                "interface": "Loopback0",
                "ip_address": "10.0.0.1",
                "description": "Router ID",
            },
        )
        self.assertIn("interface Loopback0", out)
        self.assertIn("ip address 10.0.0.1/32", out)

    def test_stp_renders(self):
        out = _render_loose(
            "stp.j2",
            {
                "intent_id": "t-001",
                "mode": "mstp",
                "priority": 4096,
                "portfast_default": True,
                "bpdu_guard_default": True,
                "loopguard_default": False,
                "vlans": [],
            },
        )
        self.assertIn("spanning-tree mode mstp", out)
        self.assertIn("spanning-tree priority 4096", out)

    def test_stp_root_renders(self):
        out = _render_loose(
            "stp_root.j2",
            {
                "intent_id": "t-001",
                "primary_vlans": [10, 20, 30],
                "secondary_vlans": [40, 50],
                "priority": 4096,
                "secondary_priority": 8192,
            },
        )
        self.assertIn("spanning-tree vlan 10 priority 4096", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — Core Routing
# ─────────────────────────────────────────────────────────────────────────────


class EOSCoreRoutingRemovalTest(SimpleTestCase):
    """Render tests for Arista EOS core routing removal templates."""

    def test_bgp_neighbor_removal_renders(self):
        out = _render_loose(
            "bgp_neighbor_removal.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "neighbor_ip": "10.0.0.2",
                "vrf_name": None,
            },
        )
        self.assertIn("no neighbor 10.0.0.2", out)
        self.assertIn("router bgp 65001", out)

    def test_bgp_network_removal_renders(self):
        out = _render_loose(
            "bgp_network_removal.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "networks": ["10.0.0.0/8"],
                "vrf": None,
            },
        )
        self.assertIn("no network 10.0.0.0/8", out)

    def test_bgp_evpn_af_removal_renders(self):
        out = _render_loose(
            "bgp_evpn_af_removal.j2",
            {
                "intent_id": "t-001",
                "local_asn": 65001,
                "neighbors": [{"ip": "10.0.0.2"}],
            },
        )
        self.assertIn("no address-family evpn", out)

    def test_ospf_removal_renders(self):
        out = _render_loose(
            "ospf_removal.j2",
            {
                "intent_id": "t-001",
                "process_id": 1,
                "interfaces": [{"name": "Ethernet1"}],
            },
        )
        self.assertIn("no router ospf 1", out)
        self.assertIn("no ip ospf area", out)

    def test_isis_removal_renders(self):
        out = _render_loose(
            "isis_removal.j2",
            {
                "intent_id": "t-001",
                "process_tag": "CORE",
                "interfaces": [{"name": "Ethernet1"}],
            },
        )
        self.assertIn("no router isis CORE", out)
        self.assertIn("no isis enable", out)

    def test_static_route_removal_renders(self):
        out = _render_loose(
            "static_route_removal.j2",
            {
                "intent_id": "t-001",
                "prefix": "10.0.0.0/8",
                "next_hop": "192.168.1.1",
                "vrf": None,
                "exit_interface": None,
                "admin_distance": None,
            },
        )
        self.assertIn("no ip route 10.0.0.0/8 192.168.1.1", out)

    def test_route_policy_removal_renders(self):
        out = _render_loose(
            "route_policy_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "RM-OUT",
            },
        )
        self.assertIn("no route-map RM-OUT", out)

    def test_prefix_list_removal_renders(self):
        out = _render_loose(
            "prefix_list_removal.j2",
            {
                "intent_id": "t-001",
                "list_name": "PFX-IN",
            },
        )
        self.assertIn("no ip prefix-list PFX-IN", out)

    def test_pbr_removal_renders(self):
        out = _render_loose(
            "pbr_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "PBR-OUT",
                "apply_interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no ip policy route-map", out)
        self.assertIn("no route-map PBR-OUT", out)

    def test_vrf_removal_renders(self):
        out = _render_loose(
            "vrf_removal.j2",
            {
                "intent_id": "t-001",
                "vrf_name": "CUST-A",
                "interfaces": [],
            },
        )
        self.assertIn("no vrf instance CUST-A", out)

    def test_vlan_removal_renders(self):
        out = _render_loose(
            "vlan_removal.j2",
            {
                "intent_id": "t-001",
                "vlan_id": 100,
            },
        )
        self.assertIn("no vlan 100", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — L2 / DC / Overlay
# ─────────────────────────────────────────────────────────────────────────────


class EOSL2DCRemovalTest(SimpleTestCase):
    """Render tests for Arista EOS L2/DC/overlay removal templates."""

    def test_l2_port_removal_renders(self):
        out = _render_loose(
            "l2_port_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "voice_vlan": None,
            },
        )
        self.assertIn("no switchport mode", out)

    def test_l2vni_removal_renders(self):
        out = _render_loose(
            "l2vni_removal.j2",
            {
                "intent_id": "t-001",
                "vlan_id": 100,
                "bgp_asn": 65001,
            },
        )
        self.assertIn("no vxlan vlan 100 vni", out)
        self.assertIn("no vlan 100", out)

    def test_l3vni_removal_renders(self):
        out = _render_loose(
            "l3vni_removal.j2",
            {
                "intent_id": "t-001",
                "vrf_name": "CUST-A",
                "vlan_id": 3001,
                "bgp_asn": 65001,
            },
        )
        self.assertIn("no vxlan vrf CUST-A vni", out)
        self.assertIn("no vrf instance CUST-A", out)

    def test_mlag_removal_renders(self):
        out = _render_loose(
            "mlag_removal.j2",
            {
                "intent_id": "t-001",
                "peer_link_interfaces": ["Ethernet47", "Ethernet48"],
                "keepalive_vlan": 4093,
                "peer_link_vlan": 4094,
            },
        )
        self.assertIn("no mlag configuration", out)

    def test_lag_removal_renders(self):
        out = _render_loose(
            "lag_removal.j2",
            {
                "intent_id": "t-001",
                "channel_id": 10,
                "member_interfaces": ["Ethernet1", "Ethernet2"],
            },
        )
        self.assertIn("no channel-group", out)
        self.assertIn("no interface Port-Channel10", out)

    def test_vtep_removal_renders(self):
        out = _render_loose(
            "vtep_removal.j2",
            {
                "intent_id": "t-001",
                "l2_vni": [{"vlan_id": 100, "vni": 10100}],
                "l3_vni": [],
                "nve_interface": "Vxlan1",
            },
        )
        self.assertIn("no vxlan vlan 100 vni", out)
        self.assertIn("no interface Vxlan1", out)

    def test_anycast_gateway_removal_renders(self):
        out = _render_loose(
            "anycast_gateway_removal.j2",
            {
                "intent_id": "t-001",
                "vlan_id": 100,
            },
        )
        self.assertIn("no ip address virtual", out)
        self.assertIn("Vlan100", out)

    def test_loopback_removal_renders(self):
        out = _render_loose(
            "loopback_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Loopback0",
            },
        )
        self.assertIn("no interface Loopback0", out)

    def test_fhrp_removal_renders(self):
        out = _render_loose(
            "fhrp_removal.j2",
            {
                "intent_id": "t-001",
                "groups": [{"interface": "Vlan100", "group_id": 10}],
            },
        )
        self.assertIn("no vrrp 10", out)

    def test_storm_control_removal_renders(self):
        out = _render_loose(
            "storm_control_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
            },
        )
        self.assertIn("no storm-control broadcast level", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — Management / Security
# ─────────────────────────────────────────────────────────────────────────────


class EOSManagementSecurityRemovalTest(SimpleTestCase):
    """Render tests for Arista EOS management and security removal templates."""

    def test_ntp_removal_renders(self):
        out = _render_loose(
            "ntp_removal.j2",
            {
                "intent_id": "t-001",
                "servers": ["10.0.0.1"],
                "source_interface": "Management1",
                "authentication": False,
            },
        )
        self.assertIn("no ntp server 10.0.0.1", out)
        self.assertIn("no ntp local-interface Management1", out)

    def test_snmp_removal_renders(self):
        out = _render_loose(
            "snmp_removal.j2",
            {
                "intent_id": "t-001",
                "version": "v2c",
                "community": "public",
                "location": "DC-EAST",
                "contact": None,
                "views": [],
                "groups": [],
                "users": [],
                "trap_targets": ["10.0.0.5"],
            },
        )
        self.assertIn("no snmp-server community public", out)
        self.assertIn("no snmp-server host 10.0.0.5", out)

    def test_syslog_removal_renders(self):
        out = _render_loose(
            "syslog_removal.j2",
            {
                "intent_id": "t-001",
                "servers": ["10.0.0.10"],
                "source_interface": None,
            },
        )
        self.assertIn("no logging host 10.0.0.10", out)
        self.assertIn("no logging on", out)

    def test_ssh_removal_renders(self):
        out = _render_loose(
            "ssh_removal.j2",
            {
                "intent_id": "t-001",
                "allowed_networks": None,
                "acl_name": None,
            },
        )
        self.assertIn("management ssh", out)
        self.assertIn("shutdown", out)

    def test_motd_removal_renders(self):
        out = _render_loose(
            "motd_removal.j2",
            {
                "intent_id": "t-001",
                "motd_banner": "Authorized access only",
                "login_banner": None,
            },
        )
        self.assertIn("no banner motd", out)

    def test_netconf_removal_renders(self):
        out = _render_loose(
            "netconf_removal.j2",
            {
                "intent_id": "t-001",
                "enable_restconf": False,
            },
        )
        self.assertIn("no management api netconf", out)

    def test_netflow_removal_renders(self):
        out = _render_loose(
            "netflow_removal.j2",
            {
                "intent_id": "t-001",
                "apply_interfaces": ["Ethernet1"],
                "collector_ip": "10.0.0.10",
                "source_interface": None,
            },
        )
        self.assertIn("no sflow run", out)
        self.assertIn("no sflow destination 10.0.0.10", out)

    def test_telemetry_removal_renders(self):
        out = _render_loose(
            "telemetry_removal.j2",
            {"intent_id": "t-001"},
        )
        self.assertIn("no management api gnmi", out)

    def test_lldp_cdp_removal_renders(self):
        out = _render_loose(
            "lldp_cdp_removal.j2",
            {
                "intent_id": "t-001",
                "lldp_global": True,
                "disable_on": [],
            },
        )
        self.assertIn("no lldp run", out)

    def test_global_config_removal_renders(self):
        out = _render_loose(
            "global_config_removal.j2",
            {
                "intent_id": "t-001",
                "ntp_servers": ["10.0.0.1"],
                "ntp_source_interface": None,
                "syslog_servers": ["10.0.0.10"],
                "syslog_source_interface": None,
                "snmp_version": "v2c",
                "snmp_community": "public",
                "snmp_users": [],
                "snmp_groups": [],
                "snmp_views": [],
                "snmp_trap_targets": [],
                "snmp_location": "DC-EAST",
                "snmp_contact": None,
                "dns_servers": ["8.8.8.8"],
                "domain_name": "corp.example.com",
                "login_banner": None,
                "motd_banner": None,
                "enable_netconf": False,
                "enable_restconf": False,
                "enable_lldp": None,
                "dhcp_pools": [],
            },
        )
        self.assertIn("no ntp server 10.0.0.1", out)
        self.assertIn("no logging host 10.0.0.10", out)

    def test_macsec_removal_renders(self):
        out = _render_loose(
            "macsec_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
                "policy_name": "MACSEC-POL",
                "key_chain": "MACSEC-KEYS",
            },
        )
        self.assertIn("no mac security profile", out)

    def test_fw_rule_removal_renders(self):
        out = _render_loose(
            "fw_rule_removal.j2",
            {
                "intent_id": "t-001",
                "policy_name": "FW-POLICY",
                "apply_interfaces": ["Ethernet1"],
                "direction": "in",
            },
        )
        self.assertIn("no ip access-group FW-POLICY in", out)
        self.assertIn("no ip access-list FW-POLICY", out)

    def test_port_security_removal_renders(self):
        out = _render_loose(
            "port_security_removal.j2",
            {
                "intent_id": "t-001",
                "interface": "Ethernet1",
            },
        )
        self.assertIn("no switchport port-security", out)


# ─────────────────────────────────────────────────────────────────────────────
# Removal templates — DHCP / DNS / Multicast
# ─────────────────────────────────────────────────────────────────────────────


class EOSDhcpDnsMulticastRemovalTest(SimpleTestCase):
    """Render tests for Arista EOS DHCP, DNS, and multicast removal templates."""

    def test_dhcp_server_removal_renders(self):
        out = _render_loose(
            "dhcp_server_removal.j2",
            {
                "intent_id": "t-001",
                "pools": [{"network": "10.0.0.0/24"}],
            },
        )
        self.assertIn("no dhcp server", out)

    def test_dhcp_snooping_removal_renders(self):
        out = _render_loose(
            "dhcp_snooping_removal.j2",
            {
                "intent_id": "t-001",
                "vlans": [100],
                "trusted_interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no ip dhcp snooping vlan 100", out)
        self.assertIn("no ip dhcp snooping", out)

    def test_dns_removal_renders(self):
        out = _render_loose(
            "dns_removal.j2",
            {
                "intent_id": "t-001",
                "servers": ["8.8.8.8"],
                "domain_name": "corp.example.com",
                "domain_list": [],
            },
        )
        self.assertIn("no name-server 8.8.8.8", out)
        self.assertIn("no dns domain corp.example.com", out)

    def test_dot1x_removal_renders(self):
        out = _render_loose(
            "dot1x_removal.j2",
            {
                "intent_id": "t-001",
                "interfaces": [{"name": "Ethernet1"}],
            },
        )
        self.assertIn("no dot1x system-auth-control", out)
        self.assertIn("no dot1x port-control", out)

    def test_dai_removal_renders(self):
        out = _render_loose(
            "dai_removal.j2",
            {
                "intent_id": "t-001",
                "vlans": [100],
                "trusted_interfaces": ["Ethernet1"],
            },
        )
        self.assertIn("no ip arp inspection vlan 100", out)
        self.assertIn("no ip arp inspection trust", out)

    def test_bfd_removal_renders(self):
        out = _render_loose(
            "bfd_removal.j2",
            {
                "intent_id": "t-001",
                "interfaces": [{"name": "Ethernet1"}],
            },
        )
        self.assertIn("no bfd", out)

    def test_igmp_snooping_removal_renders(self):
        out = _render_loose(
            "igmp_snooping_removal.j2",
            {
                "intent_id": "t-001",
                "vlans": [100],
                "querier_enabled": True,
            },
        )
        self.assertIn("no ip igmp snooping vlan 100", out)
        self.assertIn("no ip igmp snooping querier", out)

    def test_pim_removal_renders(self):
        out = _render_loose(
            "pim_removal.j2",
            {
                "intent_id": "t-001",
                "mode": "sparse-mode",
                "interfaces": [{"name": "Ethernet1"}],
                "rp_address": "10.0.0.10",
                "ssm_range": None,
            },
        )
        self.assertIn("no ip pim sparse-mode", out)
        self.assertIn("no ip pim rp-address 10.0.0.10", out)

    def test_ip_sla_removal_renders(self):
        out = _render_loose(
            "ip_sla_removal.j2",
            {
                "intent_id": "t-001",
                "sla_id": "SLA-1",
            },
        )
        self.assertIn("no host SLA-1", out)

    def test_stp_removal_renders(self):
        out = _render_loose(
            "stp_removal.j2",
            {
                "intent_id": "t-001",
                "priority": None,
                "portfast_default": True,
                "bpdu_guard_default": True,
                "loopguard_default": False,
            },
        )
        self.assertIn("no spanning-tree mode", out)

    def test_qos_classify_removal_renders(self):
        out = _render_loose(
            "qos_classify_removal.j2",
            {
                "intent_id": "t-001",
                "policy_map": "QOS-IN",
                "class_maps": [{"name": "VOICE", "acl": None}],
                "apply_interfaces": ["Ethernet1"],
                "direction": "input",
            },
        )
        self.assertIn("no service-policy input", out)
        self.assertIn("no policy-map QOS-IN", out)
