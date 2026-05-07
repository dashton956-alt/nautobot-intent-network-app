# Network-as-Code Example Intents

Reference YAML intent files for the **nautobot-app-intent-networking** plugin.

Each file covers one intent type with **every supported field documented**, marked as `MANDATORY` or `OPTIONAL`, with explanations of valid values and when to use each option.

## Structure

```
intents/
  layer2/
    vlan_provision.yaml       — Create VLANs across a set of switches
    l2_access_port.yaml       — Access port (single VLAN) configuration
    l2_trunk_port.yaml        — Trunk port with allowed VLAN list
    lag.yaml                  — Port-Channel / LAG (EtherChannel)

  layer3/
    static_route.yaml         — Static routes, floating statics, VRF routes
    ospf.yaml                 — OSPF area/adjacency + redistribution
    bgp_ebgp.yaml             — External BGP peering (eBGP)
    bgp_ibgp.yaml             — Internal BGP peering (iBGP / route-reflector)
    vrf_basic.yaml            — VRF (non-MPLS) for traffic segmentation
    fhrp.yaml                 — HSRP / VRRP / GLBP gateway redundancy

  mpls/
    mpls_l3vpn.yaml           — Full MPLS L3VPN service provisioning
    sr_mpls.yaml              — Segment Routing MPLS (SRGB, prefix-SIDs, TI-LFA)

  dc_evpn/
    evpn_vxlan_fabric.yaml    — Full VXLAN EVPN fabric bootstrap
    l2vni.yaml                — L2 VNI provisioning (VXLAN segment)
    l3vni.yaml                — L3VNI / IP VRF over VXLAN

  security/
    acl.yaml                  — Extended ACL (IPv4/IPv6, interface application)
    fw_rule.yaml              — Declarative firewall policy (stateful/stateless)
    ipsec_s2s.yaml            — IPSec site-to-site VPN
    ipsec_ikev2.yaml          — IKEv2-specific IPSec (OPA-compliant structure)
    aaa.yaml                  — TACACS+ / RADIUS authentication, authorisation, accounting

  wan/
    wan_uplink.yaml           — WAN uplinks with IP addressing and default routes
    nat_pat.yaml              — NAT overload (PAT), pool NAT, static NAT

  wireless/
    wireless_ssid.yaml        — SSID provisioning (WPA3, security, band, VLAN)

  cloud/
    cloud_vpc_peer.yaml       — AWS VPC / Azure VNet peering
    cloud_direct_connect.yaml — AWS Direct Connect / Azure ExpressRoute

  qos/
    qos_queue.yaml            — LLQ / CBWFQ queuing policy-map
    qos_classify.yaml         — Traffic classification class-maps (DSCP, ACL)

  multicast/
    multicast_pim_sm.yaml     — PIM Sparse Mode with static/BSR/Auto-RP

  management/
    mgmt_ntp.yaml             — NTP servers, authentication, source interface
    mgmt_snmp.yaml            — SNMPv3 / SNMPv2c, users, groups, trap targets
    mgmt_syslog.yaml          — Syslog servers, severity, buffering, timestamps

  reachability/
    reachability_ip_sla.yaml  — IP SLA probes for WAN failover tracking

  service/
    service_lb_vip.yaml       — Load balancer VIP, pool members, health checks
```

## Common Fields (present in every intent)

| Field | Mandatory? | Notes |
|---|---|---|
| `id` | **MANDATORY** | Unique across all files in the repo |
| `type` | **MANDATORY** | Must match an `IntentTypeChoices` value |
| `version` | **MANDATORY** | Positive integer (1–9999); increment on change |
| `tenant` | **MANDATORY** | Must match a Tenant in Nautobot exactly |
| `description` | **MANDATORY** | OPA enforces ≥ 10 characters |
| `change_ticket` | **MANDATORY** | OPA enforces `CHG` + 7 digits format |
| `approved_by` | OPTIONAL* | *MANDATORY for high-impact types: `dmvpn`, `ipsec_s2s`, `ipsec_ikev2`, `evpn_vxlan_fabric`, `mpls_l3vpn`, `fw_rule`, `sr_mpls`, `sdwan_overlay` |
| `scope` | **MANDATORY** | One of: `sites`, `devices`, `roles`, `all_tenant_devices` |
| `deployment.strategy` | OPTIONAL | `rolling` \| `canary` \| `all_at_once`; defaults to `rolling` |
| `deployment.save_config` | OPTIONAL | Defaults to `true` |
| `verification.level` | OPTIONAL | `basic` \| `nuts`; defaults to `basic` |
| `verification.trigger` | OPTIONAL | `on_deploy` \| `scheduled` \| `both`; PCI-DSS/HIPAA enforce `both` |
| `verification.fail_action` | OPTIONAL | `alert` \| `rollback` \| `remediate`; defaults to `alert` |

## OPA Compliance Notes

The plugin enforces compliance rules automatically when `policy.compliance` is set:

- **PCI-DSS**: Requires `encryption: required`, `verification.trigger: both`, `telnet` in `deny_protocols`, `max_latency_ms <= 20`, IKEv2 + AES-256 + SHA-256 + DH≥14 for tunnels
- **HIPAA**: Requires `encryption != none`, `verification.trigger: both`, AES-256 + SHA-256 for tunnels
- **SOC2**: Raises advisory warnings for `snmp_version: v2c`, `encryption: preferred`, `save_config: false` (non-blocking)

High-impact types enforce `deployment.strategy: rolling` or `canary` (never `all_at_once`).
