# Intent

An **Intent** is the central record for a declarative network policy defined in the network-as-code Git repository.

Each `Intent` corresponds to one YAML file in the repo. It is created or updated when the CI pipeline calls the sync-from-git API on a pull request, or when Nautobot syncs a `GitRepository` with the `"intent definitions"` provided-content type.

## Fields

| Field | Type | Description |
|---|---|---|
| `intent_id` | string | Unique identifier — matches the `id` field in the YAML file, e.g. `fin-pci-connectivity-001` |
| `version` | integer | Version number, incremented each time the YAML changes |
| `intent_type` | choice | One of 133 supported types (see below) |
| `tenant` | FK → Tenant | Business owner of the intent |
| `status` | StatusField | Current lifecycle status: `Draft → Validated → Deploying → Deployed → Failed → Rolled Back → Deprecated` |
| `intent_data` | JSON | Full parsed YAML stored as JSON — the single source of truth |
| `rendered_configs` | JSON | Per-device rendered Jinja2 configuration output, populated during dry-run or live deployments |
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

The 133 intent types are organised into 14 domains:

| Domain | Example Types |
|--------|--------------|
| Layer 2 / Switching | `vlan_provision`, `l2_access_port`, `l2_trunk_port`, `lag`, `mlag`, `stp_policy`, `macsec` |
| Layer 3 / Routing | `static_route`, `ospf`, `bgp_ebgp`, `bgp_ibgp`, `isis`, `vrf_basic`, `bfd`, `fhrp` |
| MPLS & Service Provider | `mpls_l3vpn`, `mpls_l2vpn`, `evpn_mpls`, `sr_mpls`, `srv6`, `rsvp_te` |
| Data Centre / EVPN/VXLAN | `evpn_vxlan_fabric`, `vxlan_l2_vni`, `vxlan_l3_vni`, `vtep`, `dc_dci_interconnect` |
| Security | `acl_ipv4`, `acl_ipv6`, `zone_based_firewall`, `ipsec_tunnel`, `nac_802_1x` |
| WAN / SD-WAN | `dmvpn_hub`, `dmvpn_spoke`, `sdwan_edge`, `sdwan_policy`, `wan_optimisation` |
| Wireless | `wireless_ssid`, `wireless_rf_profile`, `wireless_roaming`, `wireless_mesh` |
| Cloud / Hybrid | `cloud_interconnect`, `cloud_vpn_gw`, `cloud_vnet_peering`, `hybrid_dns` |
| QoS | `qos_policy`, `traffic_shaping`, `dscp_marking`, `ecn`, `wred` |
| Multicast | `igmp`, `pim_sparse`, `pim_ssm`, `msdp`, `multicast_boundary` |
| Management | `snmp`, `syslog`, `ntp`, `aaa_radius`, `aaa_tacacs`, `netflow`, `mgmt_motd`, `mgmt_netconf`, `mgmt_dhcp_server`, `mgmt_global_config` |
| Reachability | `reachability` |
| Service | `service` |
| Legacy | `connectivity`, `security` |

## Lifecycle Status Flow

```
Draft → Validated → Deploying → Deployed
                        ↓           ↓
                      Failed    (drift detected)
                        ↓           ↓
                   Rolled Back  Auto-remediate / Alert
```

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
