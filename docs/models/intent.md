# Intent

An **Intent** is the central record for a declarative network policy defined in the network-as-code Git repository.

Each `Intent` corresponds to one YAML file in the repo. It is created or updated when the CI pipeline calls the sync-from-git API on a pull request, or when Nautobot syncs a `GitRepository` with the `"intent definitions"` provided-content type.

## Fields

| Field | Type | Description |
|---|---|---|
| `intent_id` | string | Unique identifier — matches the `id` field in the YAML file, e.g. `fin-pci-connectivity-001` |
| `version` | integer | Version number, incremented each time the YAML changes |
| `intent_type` | choice | One of 134 supported types (see below) |
| `tenant` | FK → Tenant | Business owner of the intent |
| `status` | StatusField | Current lifecycle status: `Draft → Validated → Deploying → Deployed → Failed → Rolled Back → Deprecated / Retired` |
| `intent_data` | JSON | Full parsed YAML stored as JSON — the single source of truth |
| `rendered_configs` | JSON | Per-device rendered Jinja2 configuration output, populated during dry-run or live deployments |
| `deployment_strategy` | choice | How to deploy across multiple sites: `all_at_once`, `canary` (single site first), `rolling` (one site at a time) |
| `verification_level` | choice | Verification depth: `basic` or `extended` |
| `verification_trigger` | choice | When verification should run: `on_deploy`, `scheduled`, `both` |
| `verification_fail_action` | choice | Action when verification fails: `alert`, `rollback` (auto), `remediate` (auto) |
| `verification_schedule` | string | Cron expression for scheduled verification (required when trigger includes `scheduled`) |
| `controller_type` | choice | Deployment controller: `nornir` (SSH/NETCONF), `catalyst_center`, `meraki`, `mist` |
| `controller_site` | string | Controller site name (e.g. Catalyst Center fabric site) |
| `controller_org` | string | Controller organisation name (e.g. Meraki org name) |
| `change_ticket` | string | Change management ticket reference, e.g. `CHG0012345` |
| `approved_by` | string | GitHub username of the PR approver |
| `git_commit_sha` | string | Commit SHA that triggered the most recent deployment |
| `git_branch` | string | Source branch |
| `git_pr_number` | integer | Pull request number |
| `git_repository` | FK → GitRepository | Nautobot GitRepository that synced this intent |
| `deployed_at` | datetime | When the intent was last successfully deployed |
| `last_verified_at` | datetime | When the intent was last verified |

## Relationships

- `resolution_plans` — one or more `ResolutionPlan` records produced each time the intent is resolved
- `verifications` — one or more `VerificationResult` records produced after each deployment
- `approvals` — explicit `IntentApproval` records (who, when, comment)
- `audit_entries` — immutable `IntentAuditEntry` records for every lifecycle action
- `deployment_stages` — `DeploymentStage` records for staged/canary deployments

## Intent Type Categories

The 134 intent types are organised into 14 domains:

| Domain | Types |
|--------|-------|
| Layer 2 / Switching | `vlan_provision`, `l2_access_port`, `l2_trunk_port`, `lag`, `mlag`, `stp_policy`, `qinq`, `pvlan`, `storm_control`, `port_security`, `dhcp_snooping`, `dai`, `ip_source_guard`, `macsec` |
| Layer 3 / Routing | `static_route`, `ospf`, `bgp_ebgp`, `bgp_ibgp`, `isis`, `eigrp`, `route_redistribution`, `route_policy`, `prefix_list`, `vrf_basic`, `bfd`, `pbr`, `ipv6_dual_stack`, `ospfv3`, `bgp_ipv6_af`, `fhrp` |
| MPLS & Service Provider | `mpls_l3vpn`, `mpls_l2vpn`, `pseudowire`, `evpn_mpls`, `ldp`, `rsvp_te`, `sr_mpls`, `srv6`, `6pe_6vpe`, `mvpn` |
| Data Centre / EVPN/VXLAN | `evpn_vxlan_fabric`, `l2vni`, `l3vni`, `bgp_evpn_af`, `anycast_gateway`, `vtep`, `evpn_multisite`, `dc_underlay`, `dc_mlag` |
| Security & Firewalling | `acl`, `zbf`, `ipsec_s2s`, `ipsec_ikev2`, `gre_tunnel`, `gre_over_ipsec`, `dmvpn`, `macsec_policy`, `copp`, `urpf`, `dot1x_nac`, `aaa`, `ra_guard`, `ssl_inspection`, `fw_rule` |
| WAN & SD-WAN | `wan_uplink`, `bgp_isp`, `sdwan_overlay`, `sdwan_app_policy`, `sdwan_qos`, `sdwan_dia`, `nat_pat`, `nat64`, `wan_failover` |
| Wireless | `wireless_ssid`, `wireless_vlan_map`, `wireless_dot1x`, `wireless_guest`, `wireless_rf`, `wireless_qos`, `wireless_band_steer`, `wireless_roam`, `wireless_segment`, `wireless_mesh`, `wireless_flexconnect` |
| Cloud & Hybrid Cloud | `cloud_vpc_peer`, `cloud_transit_gw`, `cloud_direct_connect`, `cloud_vpn_gw`, `cloud_bgp`, `cloud_security_group`, `cloud_nat`, `cloud_route_table`, `hybrid_dns`, `cloud_sdwan` |
| QoS | `qos_classify`, `qos_dscp_mark`, `qos_cos_remark`, `qos_queue`, `qos_police`, `qos_shape`, `qos_trust` |
| Multicast | `multicast_pim_sm`, `multicast_pim_ssm`, `igmp_snooping`, `multicast_vrf`, `msdp` |
| Management & Operations | `mgmt_ntp`, `mgmt_dns_dhcp`, `mgmt_snmp`, `mgmt_syslog`, `mgmt_netflow`, `mgmt_telemetry`, `mgmt_ssh`, `mgmt_aaa_device`, `mgmt_interface`, `mgmt_lldp_cdp`, `mgmt_stp_root`, `mgmt_motd`, `mgmt_netconf`, `mgmt_dhcp_server`, `mgmt_global_config` |
| Reachability | `reachability`, `reachability_static`, `reachability_bgp_network`, `reachability_floating`, `reachability_ip_sla` |
| Service | `service`, `service_lb_vip`, `service_dns`, `service_dhcp`, `service_nat`, `service_proxy` |
| Legacy | `connectivity`, `security` |

## Lifecycle Status Flow

```
Draft → Validated → Deploying → Deployed
  ↑         ↓            ↓          ↓
  │     Deprecated    Failed    (drift detected)
  │     Retired          ↓          ↓
  │                  Rolled Back  Auto-remediate / Alert
  │                      ↓
  └──────────── Retired (re-activatable → Draft)
```

`Deprecated` and `Retired` are both terminal-ish states reachable from any active status. `Retired` is the only state that can transition back to `Draft` for re-activation.

---

# Lifecycle Models

## IntentApproval

An explicit approval record for an intent. Supports multi-reviewer workflows.

| Field | Type | Description |
|-------|------|-------------|
| `intent` | FK → Intent | The approved intent |
| `approver` | string | Username or email of the approver |
| `approved_at` | datetime | When the approval was given |
| `comment` | text | Reviewer comment |

## IntentAuditEntry

An immutable audit trail entry. One is created for every lifecycle action (sync, resolve, deploy, verify, rollback, etc.).

| Field | Type | Description |
|-------|------|-------------|
| `intent` | FK → Intent | Related intent |
| `action` | string | Action name (e.g. `"resolved"`, `"deployed"`, `"rolled_back"`) |
| `actor` | string | User or system that performed the action |
| `timestamp` | datetime | When the action occurred |
| `details` | JSON | Additional context (e.g. error messages, diff summaries) |

## DeploymentStage

Tracks staged (canary) deployments where an intent is rolled out to devices in phases.

| Field | Type | Description |
|-------|------|-------------|
| `intent` | FK → Intent | Related intent |
| `stage_number` | integer | Stage sequence (1, 2, 3, …) |
| `devices` | M2M → Device | Devices in this stage |
| `status` | string | Stage status (`pending`, `deploying`, `deployed`, `failed`) |
| `started_at` | datetime | When the stage began |
| `completed_at` | datetime | When the stage finished |

## ResolutionPlan

The resolved deployment plan for a specific intent version. Contains the vendor-neutral primitives and allocated resources needed to configure devices.

| Field | Type | Description |
|-------|------|-------------|
| `intent` | FK → Intent | Parent intent |
| `plan_data` | JSON | Resolved plan: primitives, device configs, allocated resources |
| `created` | datetime | When this plan was generated |
| `is_current` | boolean | Whether this is the active plan for the intent |

## VerificationResult

The result of a post-deployment or reconciliation verification check.

| Field | Type | Description |
|-------|------|-------------|
| `intent` | FK → Intent | Verified intent |
| `passed` | boolean | Whether the verification passed |
| `details` | JSON | Per-device verification results and any drift detected |
| `verified_at` | datetime | When verification ran |
