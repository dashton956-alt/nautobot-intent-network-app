# Intent Pipeline Deployment Report

**Date:** 2026-04-01  
**Target Device:** lab-arista-sw01 (172.20.20.3) — Arista cEOS 4.35.2F  
**Pipeline:** Resolution → Preview → Dry-Run → Approve → Deploy  
**Total Intents:** 27

## Summary

| Step | Total | Success | Failed |
|------|-------|---------|--------|
| Resolution | 27 | 27 | 0 |
| Config Preview | 27 | 27 | 0 |
| Dry-Run Deploy | 27 | 27 | 0 |
| Approval | 27 | 27 | 0 |
| Deploy (commit) | 27 | 7 | 20 |

### Final Intent Status Breakdown

| Status | Count | Intents |
|--------|-------|---------|
| Deployed | 7 | dhcp-snooping, fw-rule, mgmt-dhcp-server, mgmt-dns, mgmt-lldp, mgmt-motd, mgmt-netflow |
| Rolled Back | 16 | acl, bgp-underlay, evpn-fabric, macsec, mgmt-global-config, mgmt-netconf, mgmt-ntp, mgmt-snmp, mgmt-ssh, mgmt-syslog, mgmt-telemetry, port-security, qos-classify, storm-control, stp-policy, vlans |
| Draft | 2 | dc-l2vni, dc-l3vni |
| Validated | 1 | anycast-gw |
| Failed | 1 | mlag-pair |

## Config Applied to Device

The following config was confirmed on the cEOS switch after the pipeline run:

```
! NTP (from lab-mgmt-ntp-001 — deployed then rolled back, but config persisted)
ntp server 10.0.0.1
ntp server 10.255.0.1 prefer
ntp server 10.255.0.2
ntp server pool.ntp.org

! BGP (from lab-bgp-underlay-001 — deployed then rolled back)
router bgp 65000

! ACL (from lab-fw-rule-001 — Deployed successfully)
ip access-list SERVER-INGRESS
   10 remark Allow SSH from management
   20 permit tcp 10.255.0.0/24 10.20.0.0/16 eq ssh
   30 remark Allow HTTPS from any
   40 permit tcp any 10.20.0.0/24 eq https log
   50 remark Allow ICMP
   60 permit icmp any any
   70 remark Deny all other traffic
   80 deny ip any any log

interface Ethernet1
   ip access-group SERVER-INGRESS in
interface Ethernet2
   ip access-group SERVER-INGRESS in
```

## Errors

### Category 1: SSH Connection Exhaustion (16 intents)

**Root Cause:** All 27 intents were deployed in rapid succession. The cEOS device's SSH server was overwhelmed by concurrent connections, causing `paramiko.ssh_exception.SSHException: Error reading SSH protocol banner [Errno 104] Connection reset by peer`. The auto-rollback mechanism then set these intents to "Rolled Back."

**Affected Intents:**

- lab-acl-server-segment-001
- lab-bgp-underlay-001
- lab-dc-evpn-fabric-001
- lab-macsec-uplinks-001
- lab-mgmt-global-config-001
- lab-mgmt-netconf-001
- lab-mgmt-ntp-001
- lab-mgmt-snmp-001
- lab-mgmt-ssh-001
- lab-mgmt-syslog-001
- lab-mgmt-telemetry-001
- lab-port-security-001
- lab-qos-classify-001
- lab-storm-control-001
- lab-stp-policy-001
- lab-vlans-dc1-001

**Worker Log Example:**
```
paramiko.ssh_exception.SSHException: Error reading SSH protocol banner
  [Errno 104] Connection reset by peer
netmiko.exceptions.NetmikoTimeoutException:
  A paramiko SSHException occurred during connection creation
```

**Fix:** Add a delay between deployments or use connection pooling/retry logic to avoid overwhelming the device SSH server.

### Category 2: Dependency Gate (2 intents — Draft)

**Root Cause:** These intents have dependencies that were not in "Deployed" state, so the deploy was blocked by the dependency gate.

| Intent | Depends On | Dependency Status |
|--------|-----------|-------------------|
| lab-dc-l2vni-prod-001 | lab-dc-evpn-fabric-001 | Rolled Back |
| lab-dc-l3vni-tenant-001 | lab-dc-evpn-fabric-001 | Rolled Back |

### Category 3: Dependency Gate (1 intent — Validated)

| Intent | Depends On | Dependency Status |
|--------|-----------|-------------------|
| lab-anycast-gw-001 | lab-dc-l3vni-tenant-001 | Draft |

### Category 4: Resolution Failure (1 intent — Failed)

**Intent:** lab-mlag-pair-001  
**Cause:** No rendered configs produced (empty config). The MLAG intent requires a peer device (lab-arista-sw02) that doesn't exist in the lab, so resolution could not generate per-device primitives. The deploy attempted but had no config to push.

### Category 5: Jinja2 Template Errors (3 intents — warnings during render)

These intents rendered with template variable errors, producing partial or empty configs:

| Intent | Template Error |
|--------|---------------|
| lab-mgmt-global-config-001 | `'enable_netconf' is undefined` |
| lab-mgmt-netconf-001 | `'port' is undefined` |
| lab-mgmt-snmp-001 | `'dict object' has no attribute 'group'` |

**Cause:** The Jinja2 templates expect variables in a different structure than what the intent_data provides. The template variable names don't match the intent_data keys.

---

## Retest Run (with 10s delay)

### Retest Summary

| Status | Count | Intents |
|--------|-------|---------|
| Deployed | 7 (new) | mgmt-ntp, mgmt-ssh, mgmt-syslog, mgmt-telemetry, port-security, qos-classify, storm-control |
| Rolled Back | 7 | acl, bgp-underlay, evpn-fabric, macsec, mgmt-global-config, mgmt-netconf, mgmt-snmp |
| Rolled Back (SSH) | 2 | stp-policy, vlans-dc1 |
| Blocked (dependency) | 2 | dc-l2vni, dc-l3vni (depend on evpn-fabric) |

### Error Category A: Empty Rendered Config (7 intents)

**Error:** `Must specify either config_commands or config_file`

The Jinja2 templates for these intent types rendered to empty/whitespace-only output. Netmiko received no config commands to push, causing a `ValueError`. The deploy job reported this as a push failure and auto-rolled-back.

| Intent | Type | Root Cause |
|--------|------|------------|
| lab-acl-server-segment-001 | acl | No Arista EOS ACL template, or template rendered empty |
| lab-bgp-underlay-001 | bgp_ebgp | No Arista EOS BGP template, or template rendered empty |
| lab-dc-evpn-fabric-001 | evpn_vxlan_fabric | No Arista EOS EVPN template, or template rendered empty |
| lab-macsec-uplinks-001 | macsec | No Arista EOS MACsec template, or template rendered empty |
| lab-mgmt-global-config-001 | mgmt_global_config | Template error: `'enable_netconf' is undefined` — rendered empty |
| lab-mgmt-netconf-001 | mgmt_netconf | Template error: `'port' is undefined` — rendered empty |
| lab-mgmt-snmp-001 | mgmt_snmp | Template error: `'dict object' has no attribute 'group'` — rendered empty |

**Fix:** Either create proper Arista EOS Jinja2 templates for these intent types, or fix the template variable mapping between `intent_data` and the template context.

### Error Category B: SSH Connection Reset (2 intents)

**Error:** `paramiko.ssh_exception.SSHException: Error reading SSH protocol banner [Errno 104] Connection reset by peer`

These were the last two intents in the queue. Despite the 10s delay, the cEOS SSH server was still overwhelmed (likely from the previous successful deploy sessions not fully closing).

| Intent | Type |
|--------|------|
| lab-stp-policy-001 | stp_policy |
| lab-vlans-dc1-001 | vlan_provision |

### Error Category C: Dependency Blocked (2 intents)

These remain blocked because their dependency (`lab-dc-evpn-fabric-001`) still can't deploy (empty config).

| Intent | Depends On |
|--------|-----------|
| lab-dc-l2vni-prod-001 | lab-dc-evpn-fabric-001 |
| lab-dc-l3vni-tenant-001 | lab-dc-evpn-fabric-001 |

### Cumulative Status After Both Runs

| Status | Count | Intents |
|--------|-------|---------|
| Deployed | 14 | dhcp-snooping, fw-rule, mgmt-dhcp-server, mgmt-dns, mgmt-lldp, mgmt-motd, mgmt-netflow, mgmt-ntp, mgmt-ssh, mgmt-syslog, mgmt-telemetry, port-security, qos-classify, storm-control |
| Rolled Back | 9 | acl, bgp-underlay, evpn-fabric, macsec, mgmt-global-config, mgmt-netconf, mgmt-snmp, stp-policy, vlans-dc1 |
| Draft/Blocked | 3 | dc-l2vni, dc-l3vni, anycast-gw |
| Failed | 1 | mlag-pair |
