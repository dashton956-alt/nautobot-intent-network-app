#!/usr/bin/env python3
"""Test all 92 Arista EOS primitive templates render without errors.

Runs inside the Nautobot container via:
  docker exec intent-networking-worker-1 python /source/development/test_all_primitives.py
"""

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, UndefinedError

TEMPLATE_DIR = Path("/source/intent_networking/jinja_templates/arista/eos")

# Sample data for each primitive type — covers every variable used in templates
PRIMITIVE_TEST_DATA = {
    # ── L2 / Switching ─────────────────────────────────────
    "vlan": {"vlan_id": 100, "vlan_name": "SERVERS", "description": "Server VLAN", "intent_id": "test-vlan"},
    "l2_port": {
        "interface": "Ethernet1",
        "mode": "access",
        "access_vlan": 100,
        "voice_vlan": 200,
        "portfast": True,
        "bpdu_guard": True,
        "description": "Server port",
        "intent_id": "test-l2",
    },
    "lag": {
        "channel_id": 1,
        "member_interfaces": ["Ethernet1", "Ethernet2"],
        "lacp_mode": "active",
        "mode": "trunk",
        "allowed_vlans": [100, 200],
        "mtu": 9214,
        "description": "LAG to server",
        "intent_id": "test-lag",
    },
    "mlag": {
        "domain_id": "MLAG-DC1",
        "peer_link_interfaces": ["Ethernet49", "Ethernet50"],
        "peer_address": "10.0.0.2",
        "keepalive_vlan": 4093,
        "peer_link_vlan": 4094,
        "peer_link_channel": 2000,
        "reload_delay": 300,
        "reload_delay_non_mlag": 330,
        "description": "MLAG peer link",
        "intent_id": "test-mlag",
    },
    "stp": {
        "mode": "mstp",
        "priority": 4096,
        "portfast_default": True,
        "bpdu_guard_default": True,
        "loopguard_default": False,
        "vlans": [100, 200],
        "intent_id": "test-stp",
    },
    "qinq": {
        "interfaces": [{"name": "Ethernet3", "outer_vlan": 500, "description": "Q-in-Q port"}],
        "intent_id": "test-qinq",
    },
    "pvlan": {
        "primary_vlan": 100,
        "secondary_vlans": [101, 102],
        "secondary_type": "isolated",
        "promiscuous_interfaces": ["Ethernet1"],
        "host_interfaces": ["Ethernet2"],
        "intent_id": "test-pvlan",
    },
    "storm_control": {
        "interface": "Ethernet1",
        "broadcast_level": 80,
        "multicast_level": 80,
        "unicast_level": 80,
        "action": "shutdown",
        "intent_id": "test-storm",
    },
    "port_security": {
        "interface": "Ethernet1",
        "max_mac": 5,
        "violation_action": "protect",
        "sticky": True,
        "aging_time": 300,
        "intent_id": "test-portsec",
    },
    "dhcp_snooping": {
        "vlans": [100, 200],
        "trusted_interfaces": ["Ethernet49", "Ethernet50"],
        "rate_limit": 100,
        "verify_mac": True,
        "intent_id": "test-dhcpsnoop",
    },
    "dai": {"vlans": [100, 200], "trusted_interfaces": ["Ethernet49"], "rate_limit": 100, "intent_id": "test-dai"},
    "ip_source_guard": {"interfaces": ["Ethernet1", "Ethernet2"], "intent_id": "test-ipsg"},
    "macsec": {
        "interface": "Ethernet49",
        "policy_name": "MACSEC-UPLINK",
        "cipher_suite": "aes256-gcm-xpn",
        "key_chain": "MACSEC-KEYS",
        "key_id": "01",
        "replay_protection": True,
        "replay_window": 64,
        "intent_id": "test-macsec",
    },
    # ── L3 / Routing ───────────────────────────────────────
    "vrf": {
        "vrf_name": "TENANT-A",
        "route_distinguisher": "65000:100",
        "rt_export": "65000:100",
        "rt_import": "65000:100",
        "description": "Tenant A VRF",
        "interfaces": ["Vlan100"],
        "bgp_asn": 65000,
        "redistribute_connected": True,
        "redistribute_static": False,
        "intent_id": "test-vrf",
    },
    "static_route": {
        "prefix": "10.0.0.0/8",
        "next_hop": "192.168.1.1",
        "exit_interface": "",
        "admin_distance": 1,
        "vrf": "",
        "tag": 100,
        "track": "",
        "name": "to-DC",
        "intent_id": "test-static",
    },
    "ospf": {
        "process_id": 1,
        "router_id": "1.1.1.1",
        "area": "0.0.0.0",  # noqa: S104
        "interfaces": [{"name": "Ethernet1", "area": "0.0.0.0", "cost": 10, "network_type": "point-to-point"}],  # noqa: S104
        "hello_interval": 10,
        "dead_interval": 40,
        "authentication": False,
        "passive_interfaces": ["Loopback0"],
        "redistribute": ["connected"],
        "max_lsa": 12000,
        "intent_id": "test-ospf",
    },
    "bgp_neighbor": {
        "local_asn": 65000,
        "neighbor_ip": "10.0.0.1",
        "neighbor_asn": 65001,
        "neighbor_description": "eBGP-ISP1",
        "vrf_name": "",
        "route_map_in": "ISP-IN",
        "route_map_out": "ISP-OUT",
        "prefix_list_in": "",
        "prefix_list_out": "",
        "bfd_enabled": True,
        "max_prefix": 1000,
        "timers_keepalive": 60,
        "timers_hold": 180,
        "multihop": 2,
        "password": "",
        "update_source": "",
        "next_hop_self": False,
        "route_reflector_client": False,
        "send_community": "extended",
        "maximum_paths": 2,
        "local_preference": 200,
        "graceful_restart": True,
        "default_originate": False,
        "allowas_in": "",
        "intent_id": "test-bgp",
    },
    "isis": {
        "process_tag": "CORE",
        "net": "49.0001.0010.0000.0001.00",
        "level": "level-2",
        "interfaces": [{"name": "Ethernet1", "metric": 10, "network_type": "point-to-point", "passive": False}],
        "metric_style": "wide",
        "authentication": None,
        "intent_id": "test-isis",
    },
    "eigrp": {
        "asn": 100,
        "router_id": "1.1.1.1",
        "networks": ["10.0.0.0/8"],
        "passive_interfaces": ["Loopback0"],
        "redistribute": ["connected"],
        "intent_id": "test-eigrp",
    },
    "route_redistribution": {
        "protocol": "bgp",
        "asn": 65000,
        "vrf": "",
        "sources": [{"protocol": "connected", "route_map": "CONNECTED-TO-BGP"}],
        "intent_id": "test-redistrib",
    },
    "route_policy": {
        "policy_name": "ISP-IN",
        "entries": [
            {
                "action": "permit",
                "seq": 10,
                "match_prefix_list": "ALLOWED-PREFIXES",
                "set_local_preference": 200,
                "match_community": "",
                "match_as_path": "",
                "set_med": "",
                "set_community": "",
                "set_next_hop": "",
                "set_weight": "",
                "set_as_path_prepend": "",
            },
        ],
        "intent_id": "test-rpolicy",
    },
    "prefix_list": {
        "list_name": "ALLOWED-PREFIXES",
        "entries": [
            {"action": "permit", "prefix": "10.0.0.0/8", "le": 24},
        ],
        "intent_id": "test-pfxlist",
    },
    "bfd": {
        "interfaces": [{"name": "Ethernet1", "interval": 300, "min_rx": 300, "multiplier": 3}],
        "echo_mode": True,
        "interval": 300,
        "min_rx": 300,
        "multiplier": 3,
        "intent_id": "test-bfd",
    },
    "pbr": {
        "policy_name": "PBR-WEB",
        "entries": [
            {"action": "permit", "seq": 10, "match_acl": "WEB-TRAFFIC", "set_next_hop": "10.0.0.1", "set_vrf": ""},
        ],
        "apply_interfaces": ["Ethernet1"],
        "intent_id": "test-pbr",
    },
    "ipv6_interface": {
        "ipv6_unicast_routing": True,
        "interfaces": [
            {"name": "Ethernet1", "ipv6_address": "2001:db8::1/64", "link_local": "", "ra_suppress": True},
        ],
        "intent_id": "test-ipv6if",
    },
    "ospfv3": {
        "process_id": 1,
        "router_id": "1.1.1.1",
        "area": "0.0.0.0",  # noqa: S104
        "interfaces": [{"name": "Ethernet1", "area": "0.0.0.0"}],  # noqa: S104
        "redistribute": ["connected"],
        "intent_id": "test-ospfv3",
    },
    "bgp_ipv6_af": {
        "local_asn": 65000,
        "neighbors": [{"ip": "2001:db8::1", "route_map_in": "v6-IN", "route_map_out": "v6-OUT"}],
        "networks": ["2001:db8::/32"],
        "intent_id": "test-bgpv6",
    },
    "fhrp": {
        "groups": [
            {
                "interface": "Vlan100",
                "group_id": 1,
                "virtual_ip": "10.0.0.1",
                "priority": 110,
                "preempt": True,
                "track_interface": "",
                "track_decrement": 10,
                "authentication": "",
            },
        ],
        "intent_id": "test-fhrp",
    },
    "bgp_network": {
        "local_asn": 65000,
        "networks": ["10.0.0.0/24", "10.0.1.0/24"],
        "vrf": "",
        "route_map": "",
        "intent_id": "test-bgpnet",
    },
    # ── MPLS / SP ──────────────────────────────────────────
    "l2vpn_vpls": {
        "vpls_id": 100,
        "vlan_id": 100,
        "route_distinguisher": "65000:100",
        "route_target": "65000:100",
        "local_asn": 65000,
        "pseudowires": [{"neighbor": "2.2.2.2", "vc_id": 100}],
        "intent_id": "test-vpls",
    },
    "pseudowire": {
        "pseudowires": [
            {"interface": "Pseudowire1", "neighbor": "2.2.2.2", "vc_id": 100, "pw_class": "", "control_word": False},
        ],
        "intent_id": "test-pw",
    },
    "evpn_mpls": {
        "local_asn": 65000,
        "neighbors": [{"ip": "2.2.2.2"}],
        "evpn_instances": [{"vlan_id": 100, "route_distinguisher": "auto", "route_target": "65000:100", "label": 100}],
        "intent_id": "test-evpnmpls",
    },
    "ldp": {
        "router_id": "Loopback0",
        "interfaces": ["Ethernet1", "Ethernet2"],
        "neighbor": "",
        "password": "",
        "intent_id": "test-ldp",
    },
    "rsvp_te_tunnel": {
        "tunnel_interface": "Tunnel1",
        "tunnel_source": "Loopback0",
        "tunnel_destination": "2.2.2.2",
        "unnumbered_interface": "Loopback0",
        "setup_priority": 7,
        "hold_priority": 7,
        "bandwidth": 1000000,
        "affinity": "",
        "explicit_path": "",
        "interfaces": ["Ethernet1"],
        "rsvp_bandwidth": 1000000,
        "intent_id": "test-rsvp",
    },
    "sr_mpls": {
        "process_tag": "CORE",
        "label_range_start": 16000,
        "label_range_end": 23999,
        "srgb_start": 16000,
        "srgb_end": 23999,
        "srlb_start": "",
        "srlb_end": "",
        "interfaces": [{"name": "Loopback0", "prefix_sid": 1, "adjacency_sid": ""}],
        "ti_lfa": True,
        "ti_lfa_mode": "node-protection",
        "intent_id": "test-sr",
    },
    "srv6": {
        "locator_name": "SRv6-LOC",
        "prefix": "fc00:0:1::/48",
        "sids": [{"function": "End", "behavior": "End"}],
        "interfaces": [{"name": "Ethernet1"}],
        "intent_id": "test-srv6",
    },
    "6pe_6vpe": {
        "local_asn": 65000,
        "neighbors": [{"ip": "2.2.2.2"}],
        "networks": ["2001:db8::/32"],
        "vrf": "",
        "intent_id": "test-6pe",
    },
    "mvpn": {
        "local_asn": 65000,
        "neighbors": [{"ip": "2.2.2.2"}],
        "vrf": "MCAST-VRF",
        "mdt_default": "239.1.1.1",
        "intent_id": "test-mvpn",
    },
    # ── DC / EVPN / VXLAN ──────────────────────────────────
    "loopback": {"interface": "Loopback0", "ip_address": "1.1.1.1", "description": "Router ID", "intent_id": "test-lo"},
    "vtep": {
        "nve_interface": "Vxlan1",
        "source_interface": "Loopback1",
        "replication_mode": "ingress-replication",
        "vni_map": [],
        "l2_vni": [{"vlan_id": 100, "vni": 10100}],
        "l3_vni": [{"vrf_name": "TENANT-A", "vni": 50001}],
        "intent_id": "test-vtep",
    },
    "bgp_evpn_af": {
        "local_asn": 65000,
        "neighbors": [{"ip": "10.0.0.1", "remote_asn": 65000, "update_source": "Loopback0"}],
        "advertise_all_vni": True,
        "route_target_auto": True,
        "intent_id": "test-evpnaf",
    },
    "l2vni": {
        "vlan_id": 100,
        "vni": 10100,
        "vlan_name": "SERVERS",
        "replication_mode": "ingress-replication",
        "mcast_group": "",
        "bgp_asn": 65000,
        "intent_id": "test-l2vni",
    },
    "l3vni": {
        "vrf_name": "TENANT-A",
        "vni": 50001,
        "vlan_id": 3001,
        "anycast_gateway_mac": "00:1c:73:00:00:01",
        "redistribute_connected": True,
        "bgp_asn": 65000,
        "intent_id": "test-l3vni",
    },
    "anycast_gateway": {
        "vlan_id": 100,
        "virtual_ip": "10.0.100.1",
        "subnet_mask": 24,
        "anycast_mac": "00:1c:73:00:00:01",
        "vrf": "TENANT-A",
        "intent_id": "test-agw",
    },
    "evpn_multisite": {
        "local_asn": 65000,
        "site_id": 1,
        "dci_neighbors": [{"ip": "10.0.0.1", "remote_asn": 65001, "update_source": "Loopback0", "multihop": 3}],
        "intent_id": "test-evpnms",
    },
    # ── Security / Firewalling ─────────────────────────────
    "acl": {
        "acl_name": "SERVERS-IN",
        "acl_type": "extended",
        "address_family": "ipv4",
        "entries": [
            {
                "seq": 10,
                "action": "permit",
                "protocol": "tcp",
                "source": "10.0.0.0/8",
                "destination": "any",
                "port": 443,
                "log": True,
            }
        ],
        "apply_interfaces": ["Ethernet1"],
        "direction": "in",
        "intent_id": "test-acl",
    },
    "zbf": {
        "zones": [{"name": "INSIDE", "interfaces": ["Ethernet1"]}],
        "policies": [
            {
                "acl_name": "ZBF-INSIDE-OUT",
                "rules": [
                    {"seq": 10, "action": "permit", "protocol": "ip", "source": "10.0.0.0/8", "destination": "any"}
                ],
            }
        ],
        "intent_id": "test-zbf",
    },
    "ipsec_tunnel": {
        "peer_ip": "203.0.113.1",
        "pre_shared_key": "SECRET123",
        "isakmp_policy": {
            "priority": 10,
            "encryption": "aes256",
            "hash": "sha256",
            "auth": "pre-share",
            "dh_group": 14,
            "lifetime": 86400,
        },
        "transform_set": {
            "name": "TS-IPSEC",
            "encryption": "esp-aes 256",
            "integrity": "esp-sha256-hmac",
            "mode": "tunnel",
        },
        "crypto_map_name": "CRYPTO-MAP",
        "crypto_map_seq": 10,
        "acl_name": "VPN-TRAFFIC",
        "tunnel_interface": "",
        "tunnel_ip": "",
        "tunnel_source": "",
        "ipsec_profile": "",
        "intent_id": "test-ipsec",
    },
    "ipsec_ikev2": {
        "peer_ip": "203.0.113.1",
        "pre_shared_key": "SECRET123",
        "proposal": {"name": "IKEv2-PROP", "encryption": "aes256", "integrity": "sha256", "dh_group": 14},
        "policy": {"name": "IKEv2-POL"},
        "profile": {"name": "IKEv2-PROF"},
        "intent_id": "test-ikev2",
    },
    "gre_tunnel": {
        "tunnel_interface": "Tunnel1",
        "tunnel_ip": "10.255.0.1/30",
        "tunnel_source": "Ethernet1",
        "tunnel_destination": "203.0.113.1",
        "tunnel_key": 12345,
        "keepalive": {"interval": 10, "retries": 3},
        "mtu": 1400,
        "description": "GRE to DC2",
        "intent_id": "test-gre",
    },
    "dmvpn": {
        "tunnel_interface": "Tunnel100",
        "tunnel_ip": "10.255.0.1/24",
        "tunnel_source": "Ethernet1",
        "nhrp_network_id": 1,
        "nhrp_nhs": "10.255.0.254",
        "nhrp_map": {"tunnel_ip": "10.255.0.254", "nbma_ip": "203.0.113.1"},
        "tunnel_key": 100,
        "ipsec_profile": "DMVPN-PROF",
        "description": "DMVPN Hub",
        "intent_id": "test-dmvpn",
    },
    "copp": {
        "classes": [
            {
                "acl_name": "COPP-BGP",
                "rules": [
                    {
                        "seq": 10,
                        "action": "permit",
                        "protocol": "tcp",
                        "source": "any",
                        "destination": "any",
                        "port": 179,
                    }
                ],
            },
        ],
        "intent_id": "test-copp",
    },
    "urpf": {"interfaces": [{"name": "Ethernet1", "mode": "strict"}], "intent_id": "test-urpf"},
    "dot1x": {
        "radius_group": "radius",
        "interfaces": [
            {"name": "Ethernet1", "port_control": "auto", "host_mode": "multi-auth", "reauth_period": 3600, "mab": True}
        ],
        "intent_id": "test-dot1x",
    },
    "aaa": {
        "auth_methods": "group tacacs+ local",
        "enable_auth": "group tacacs+ enable",
        "authorization": "group tacacs+ local",
        "accounting": "group tacacs+",
        "radius_servers": [],
        "tacacs_servers": [{"ip": "10.0.0.50", "key": "TACKEY"}],
        "intent_id": "test-aaa",
    },
    "ra_guard": {
        "policy_name": "RA-GUARD",
        "trusted_ports": ["Ethernet49"],
        "untrusted_ports": ["Ethernet1", "Ethernet2"],
        "intent_id": "test-raguard",
    },
    "ssl_inspection": {
        "policy_name": "SSL-INSPECT",
        "ca_cert": "MY-CA",
        "bypass_categories": ["banking", "healthcare"],
        "decrypt_categories": ["social-media"],
        "intent_id": "test-ssl",
    },
    "fw_rule": {
        "policy_name": "FW-SERVERS",
        "firewall_type": "acl",
        "default_action": "deny",
        "address_family": "ipv4",
        "direction": "in",
        "intent_version": 1,
        "rules": [
            {
                "action": "permit",
                "protocol": "tcp",
                "source": "10.0.0.0/8",
                "destination": "any",
                "port": 443,
                "description": "HTTPS",
                "log": True,
            },
        ],
        "apply_interfaces": ["Ethernet1"],
        "intent_id": "test-fwrule",
    },
    # ── WAN ────────────────────────────────────────────────
    "wan_uplink": {
        "interface": "Ethernet1",
        "ip_address": "203.0.113.2/30",
        "isp_name": "ISP-A",
        "bandwidth": 1000000,
        "default_route": "203.0.113.1",
        "admin_distance": 1,
        "description": "WAN Uplink ISP-A",
        "intent_id": "test-wan",
    },
    "nat": {
        "nat_type": "pat",
        "inside_interface": "Vlan100",
        "outside_interface": "Ethernet1",
        "pool_name": "",
        "pool_start": "",
        "pool_end": "",
        "acl": "NAT-ACL",
        "static_mappings": [],
        "overload": True,
        "prefix_length": 24,
        "intent_id": "test-nat",
    },
    "nat64": {
        "prefix": "64:ff9b::/96",
        "mode": "stateful",
        "v4_pool": {"name": "NAT64-POOL", "start": "198.51.100.1", "end": "198.51.100.254"},
        "interfaces": ["Ethernet1"],
        "intent_id": "test-nat64",
    },
    "ip_sla": {
        "sla_id": "PROBE-1",
        "probe_type": "icmp-echo",
        "target": "8.8.8.8",
        "frequency": 60,
        "threshold": 500,
        "timeout": 5000,
        "interval": "",
        "intent_id": "test-ipsla",
    },
    # ── QoS ────────────────────────────────────────────────
    "qos_classify": {
        "policy_map": "QOS-CLASSIFY",
        "class_maps": [
            {
                "name": "VOICE",
                "dscp": "ef",
                "acl": "",
                "cos": "",
                "protocol": "",
                "set_dscp": "ef",
                "set_cos": "",
                "police_rate": "",
                "rules": [],
            },
        ],
        "apply_interfaces": ["Ethernet1"],
        "direction": "input",
        "intent_id": "test-qosc",
    },
    "qos_dscp_mark": {
        "policy_map": "QOS-MARK",
        "trust_boundary": "dscp",
        "markings": [{"class_name": "VOICE", "dscp": "ef"}],
        "apply_interfaces": ["Ethernet1"],
        "intent_id": "test-qosmark",
    },
    "qos_cos_remark": {
        "trust_cos": True,
        "cos_map": [{"cos": 5, "dscp": 46}],
        "apply_interfaces": ["Ethernet1"],
        "intent_id": "test-qoscos",
    },
    "qos_queue": {
        "policy_map": "QOS-QUEUE",
        "queues": [
            {"class_name": "VOICE", "bandwidth_percent": 30, "priority": True, "shape_rate": "", "queue_limit": ""},
        ],
        "apply_interfaces": ["Ethernet1"],
        "direction": "output",
        "intent_id": "test-qosq",
    },
    "qos_police": {
        "policy_map": "QOS-POLICE",
        "rate_bps": 1000000,
        "burst_bytes": 8000,
        "conform_action": "transmit",
        "exceed_action": "drop",
        "violate_action": "drop",
        "apply_interfaces": ["Ethernet1"],
        "intent_id": "test-qosp",
    },
    "qos_shape": {
        "policy_map": "QOS-SHAPE",
        "rate_bps": 50000000,
        "burst_bytes": "",
        "child_policy": "QOS-QUEUE",
        "apply_interfaces": ["Ethernet1"],
        "intent_id": "test-qoss",
    },
    "qos_trust": {"trust_type": "dscp", "apply_interfaces": ["Ethernet1", "Ethernet2"], "intent_id": "test-qost"},
    # ── Multicast ──────────────────────────────────────────
    "pim": {
        "mode": "sparse-mode",
        "rp_address": "10.0.0.1",
        "rp_type": "static",
        "bsr_candidate": "",
        "anycast_rp_set": [],
        "interfaces": [{"name": "Ethernet1"}, {"name": "Ethernet2"}],
        "ssm_range": "",
        "intent_id": "test-pim",
    },
    "igmp_snooping": {
        "vlans": [100, 200],
        "querier_enabled": True,
        "querier_address": "10.0.0.1",
        "fast_leave": True,
        "intent_id": "test-igmp",
    },
    "multicast_vrf": {
        "vrf": "MCAST-VRF",
        "pim_mode": "sparse-mode",
        "rp_address": "10.0.0.1",
        "mdt_default_group": "239.1.1.1",
        "interfaces": [{"name": "Ethernet1"}],
        "intent_id": "test-mcvrf",
    },
    "msdp": {
        "originator_id": "Loopback0",
        "peers": [{"ip": "2.2.2.2", "remote_as": 65001, "connect_source": "Loopback0", "sa_limit": 1000}],
        "default_peer": "",
        "sa_filter": "",
        "intent_id": "test-msdp",
    },
    # ── Management ─────────────────────────────────────────
    "ntp": {
        "servers": ["10.0.0.50", "10.0.0.51"],
        "prefer": "10.0.0.50",
        "authentication": False,
        "source_interface": "Loopback0",
        "intent_id": "test-ntp",
    },
    "dns": {
        "servers": ["8.8.8.8", "8.8.4.4"],
        "domain_name": "lab.local",
        "domain_list": ["lab.local", "corp.local"],
        "source_interface": "",
        "intent_id": "test-dns",
    },
    "dhcp_pool": {
        "pool_name": "SERVERS",
        "network": "10.0.100.0/24",
        "default_router": "10.0.100.1",
        "dns_server": "8.8.8.8",
        "lease_time": 86400,
        "ranges": [{"start": "10.0.100.10", "end": "10.0.100.200"}],
        "excluded_addresses": ["10.0.100.1"],
        "intent_id": "test-dhcpp",
    },
    "dhcp_relay": {"interface": "Vlan100", "helper_address": "10.0.0.50", "intent_id": "test-dhcpr"},
    "snmp": {
        "version": "v3",
        "community": "",
        "location": "DC-EAST",
        "contact": "noc@example.com",
        "views": [{"name": "ALL", "oid": "iso"}],
        "groups": [{"name": "MONITOR", "security_level": "priv", "read_view": "ALL", "write_view": ""}],
        "users": [
            {
                "name": "snmpuser",
                "group": "MONITOR",
                "auth_protocol": "sha",
                "auth_password": "AuthPass1",
                "priv_protocol": "aes128",
                "priv_password": "PrivPass1",
            }
        ],
        "trap_targets": ["10.0.0.50"],
        "intent_id": "test-snmp",
    },
    "syslog": {
        "servers": ["10.0.0.50"],
        "facility": "local7",
        "severity": "informational",
        "source_interface": "Loopback0",
        "intent_id": "test-syslog",
    },
    "netflow": {
        "exporter_name": "FLOW-1",
        "collector_ip": "10.0.0.50",
        "collector_port": 9996,
        "source_interface": "Loopback0",
        "sampler_rate": 1024,
        "version": 9,
        "apply_interfaces": ["Ethernet1"],
        "intent_id": "test-netflow",
    },
    "telemetry": {
        "destination_ip": "10.0.0.50",
        "destination_port": 6030,
        "protocol": "grpc",
        "encoding": "proto3",
        "source_interface": "Loopback0",
        "subscriptions": [{"path": "/interfaces/interface/state/counters", "name": "if-counters", "interval": 10000}],
        "intent_id": "test-telemetry",
    },
    "ssh": {
        "version": 2,
        "acl_name": "SSH-ACCESS",
        "allowed_networks": ["10.0.0.0/8"],
        "timeout": 60,
        "retries": 3,
        "key_type": "rsa",
        "key_size": 4096,
        "intent_id": "test-ssh",
    },
    "mgmt_interface": {
        "interface": "Management0",
        "ip_address": "192.168.1.10/24",
        "vrf": "MGMT",
        "gateway": "192.168.1.1",
        "intent_id": "test-mgmtif",
    },
    "lldp_cdp": {
        "lldp_global": True,
        "cdp_global": False,
        "lldp_interfaces": [],
        "cdp_interfaces": [],
        "disable_on": ["Ethernet1"],
        "intent_id": "test-lldp",
    },
    "stp_root": {
        "primary_vlans": [100, 200],
        "secondary_vlans": [300, 400],
        "priority": 4096,
        "secondary_priority": 8192,
        "intent_id": "test-stproot",
    },
    "motd": {
        "login_banner": "Authorized access only!",
        "motd_banner": "Welcome to the lab.",
        "exec_banner": "Lab device",
        "delimiter": "^C",
        "intent_id": "test-motd",
    },
    "netconf": {
        "netconf_enabled": True,
        "port": 830,
        "vrf": "",
        "enable_restconf": True,
        "restconf_port": 443,
        "restconf_vrf": "",
        "gnmi_enabled": True,
        "gnmi_port": 6030,
        "intent_id": "test-netconf",
    },
    "dhcp_server": {
        "pools": [
            {
                "network": "10.0.100.0/24",
                "default_router": "10.0.100.1",
                "dns_server": "8.8.8.8",
                "lease_time": 86400,
                "domain_name": "lab.local",
                "ranges": [{"start": "10.0.100.10", "end": "10.0.100.200"}],
                "excluded_addresses": ["10.0.100.1"],
            }
        ],
        "excluded_addresses": [],
        "lease_time": 86400,
        "intent_id": "test-dhcps",
    },
    "global_config": {
        "hostname": "lab-switch-01",
        "domain_name": "lab.local",
        "dns_servers": ["8.8.8.8"],
        "dns_domain_list": ["lab.local"],
        "ntp_servers": ["10.0.0.50"],
        "ntp_prefer": "10.0.0.50",
        "ntp_source_interface": "Loopback0",
        "timezone": "UTC",
        "timezone_offset": "",
        "syslog_servers": ["10.0.0.50"],
        "syslog_source_interface": "Loopback0",
        "syslog_facility": "local7",
        "syslog_trap_level": "informational",
        "snmp_community": "public",
        "snmp_location": "DC-EAST",
        "snmp_contact": "noc@example.com",
        "snmp_trap_targets": ["10.0.0.50"],
        "snmp_version": "v2c",
        "snmp_views": [],
        "snmp_groups": [],
        "snmp_users": [],
        "enable_ssh": True,
        "ssh_version": 2,
        "ssh_timeout": 60,
        "login_banner": "Authorized only!",
        "motd_banner": "Lab device",
        "enable_netconf": True,
        "netconf_port": 830,
        "enable_restconf": False,
        "dhcp_pools": [],
        "enable_lldp": True,
        "cdp_enabled": False,
        "intent_id": "test-globalcfg",
    },
    # ── Service ────────────────────────────────────────────
    "lb_vip": {
        "vip_address": "10.0.0.100",
        "vip_port": 443,
        "pool_name": "WEB-SERVERS",
        "pool_members": [{"ip": "10.0.1.1", "port": 8443, "weight": 1}],
        "health_check": {"type": "https", "path": "/health"},
        "intent_id": "test-lbvip",
    },
    "dns_record": {
        "record_name": "app.lab.local",
        "record_type": "A",
        "record_value": "10.0.0.100",
        "ttl": 300,
        "intent_id": "test-dnsrec",
    },
    "service_insertion": {
        "service_node": "FW-01",
        "redirect_interface": "Ethernet10",
        "service_chain": [{"name": "FW-CHAIN", "next_hop": "10.0.0.254"}],
        "intent_id": "test-svcins",
    },
}


def main():  # noqa: D103
    env = Environment(  # noqa: S701
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    passed = 0
    failed = 0
    errors = []

    # Get all primitive types from the test data
    primitive_types = sorted(PRIMITIVE_TEST_DATA.keys())
    print(f"Testing {len(primitive_types)} primitive types...\n")

    for ptype in primitive_types:
        tname = f"{ptype}.j2"
        data = PRIMITIVE_TEST_DATA[ptype]

        try:
            tpl = env.get_template(tname)
            rendered = tpl.render(**data)
            lines = [line for line in rendered.strip().split("\n") if line.strip() and not line.strip().startswith("!")]
            config_lines = len(lines)

            if config_lines == 0:
                errors.append((ptype, "WARN: Template rendered 0 config lines"))
                print(f"  WARN  {ptype:30s} — rendered OK but 0 config lines")
            else:
                passed += 1
                print(f"  PASS  {ptype:30s} — {config_lines} config lines")

        except UndefinedError as e:
            failed += 1
            errors.append((ptype, f"UndefinedError: {e}"))
            print(f"  FAIL  {ptype:30s} — UndefinedError: {e}")
        except Exception as e:
            failed += 1
            errors.append((ptype, f"{type(e).__name__}: {e}"))
            print(f"  FAIL  {ptype:30s} — {type(e).__name__}: {e}")

    # Also test removal templates
    print(f"\n{'='*60}")
    print("Testing removal templates...\n")
    removal_passed = 0
    removal_failed = 0

    for ptype in primitive_types:
        removal_tname = f"{ptype}_removal.j2"
        removal_path = TEMPLATE_DIR / removal_tname
        if not removal_path.exists():
            continue

        data = PRIMITIVE_TEST_DATA[ptype]
        try:
            tpl = env.get_template(removal_tname)
            rendered = tpl.render(**data)
            lines = [line for line in rendered.strip().split("\n") if line.strip() and not line.strip().startswith("!")]
            removal_passed += 1
            print(f"  PASS  {removal_tname:40s} — {len(lines)} config lines")
        except UndefinedError as e:
            removal_failed += 1
            errors.append((removal_tname, f"UndefinedError: {e}"))
            print(f"  FAIL  {removal_tname:40s} — UndefinedError: {e}")
        except Exception as e:
            removal_failed += 1
            errors.append((removal_tname, f"{type(e).__name__}: {e}"))
            print(f"  FAIL  {removal_tname:40s} — {type(e).__name__}: {e}")

    # Also test trunk mode for l2_port
    print(f"\n{'='*60}")
    print("Testing variant inputs...\n")

    # l2_port trunk mode
    try:
        tpl = env.get_template("l2_port.j2")
        rendered = tpl.render(
            interface="Ethernet10",
            mode="trunk",
            allowed_vlans=[100, 200, 300],
            native_vlan=1,
            description="Trunk to switch",
            portfast=False,
            bpdu_guard=False,
            voice_vlan="",
            access_vlan="",
            intent_id="test-l2-trunk",
        )
        lines = [line for line in rendered.strip().split("\n") if line.strip() and not line.strip().startswith("!")]
        passed += 1
        print(f"  PASS  l2_port (trunk mode)                — {len(lines)} config lines")
    except Exception as e:
        failed += 1
        errors.append(("l2_port-trunk", str(e)))
        print(f"  FAIL  l2_port (trunk mode)                — {e}")

    # ACL IPv6
    try:
        tpl = env.get_template("acl.j2")
        rendered = tpl.render(
            acl_name="v6-FILTER",
            acl_type="extended",
            address_family="ipv6",
            entries=[
                {
                    "seq": 10,
                    "action": "permit",
                    "protocol": "tcp",
                    "source": "2001:db8::/32",
                    "destination": "any",
                    "port": 443,
                }
            ],
            apply_interfaces=["Ethernet1"],
            direction="in",
            intent_id="test-acl-v6",
        )
        lines = [line for line in rendered.strip().split("\n") if line.strip() and not line.strip().startswith("!")]
        if "ipv6 access-list" in rendered:
            passed += 1
            print(f"  PASS  acl (IPv6 mode)                     — {len(lines)} config lines")
        else:
            failed += 1
            errors.append(("acl-ipv6", "Missing 'ipv6 access-list' in output"))
            print("  FAIL  acl (IPv6 mode)                     — no ipv6 access-list found")
    except Exception as e:
        failed += 1
        errors.append(("acl-ipv6", str(e)))
        print(f"  FAIL  acl (IPv6 mode)                     — {e}")

    # PIM SSM mode
    try:
        tpl = env.get_template("pim.j2")
        rendered = tpl.render(
            mode="ssm",
            ssm_range="232.0.0.0/8",
            rp_address="",
            rp_type="",
            bsr_candidate="",
            anycast_rp_set=[],
            interfaces=[{"name": "Ethernet1"}],
            intent_id="test-pim-ssm",
        )
        passed += 1
        print("  PASS  pim (SSM mode)                      — ok")
    except Exception as e:
        failed += 1
        errors.append(("pim-ssm", str(e)))
        print(f"  FAIL  pim (SSM mode)                      — {e}")

    # NAT static mode
    try:
        tpl = env.get_template("nat.j2")
        rendered = tpl.render(
            nat_type="static",
            inside_interface="Vlan100",
            outside_interface="Ethernet1",
            static_mappings=[{"inside": "10.0.0.10", "outside": "203.0.113.10"}],
            pool_name="",
            pool_start="",
            pool_end="",
            acl="",
            overload=False,
            prefix_length=24,
            intent_id="test-nat-static",
        )
        passed += 1
        print("  PASS  nat (static mode)                   — ok")
    except Exception as e:
        failed += 1
        errors.append(("nat-static", str(e)))
        print(f"  FAIL  nat (static mode)                   — {e}")

    # Summary
    print(f"\n{'='*60}")
    total_p = passed + removal_passed
    total_f = failed + removal_failed
    print(f"RESULTS: {total_p} passed, {total_f} failed, {len(errors)} warnings/errors")
    print(f"  Primary templates: {passed} passed, {failed} failed")
    print(f"  Removal templates: {removal_passed} passed, {removal_failed} failed")

    if errors:
        print("\nErrors/Warnings:")
        for name, msg in errors:
            print(f"  {name}: {msg}")

    return 0 if total_f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
