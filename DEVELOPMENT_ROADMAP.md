# Development Roadmap

---

## Section 1 — Multi-Interface Layer 2 Support (Release v2.0.11)

### Problem

`l2_access_port` and `l2_trunk_port` currently accept a single `interface` field. One intent per port is required, which is noisy and inefficient — a 48-port switch needs 48 intents to configure all access ports.

### Goal

Support a `ports` list so one intent can configure many ports in a single deployment, while remaining fully backward-compatible with existing single-`interface` intents.

---

### YAML Shape After Change

**`l2_access_port` — new multi-port form:**
```yaml
type: l2_access_port
ports:
  - interface: GigabitEthernet0/1
    vlan_id: 100
    voice_vlan: 150       # OPTIONAL
    description: "Server rack A"
  - interface: GigabitEthernet0/2
    vlan_id: 200
  - interface: GigabitEthernet0/3
    vlan_id: 100
```

**`l2_access_port` — old single-port form (still works, no changes required):**
```yaml
type: l2_access_port
interface: GigabitEthernet0/1
vlan_id: 100
```

**`l2_trunk_port` — new multi-port form:**
```yaml
type: l2_trunk_port
ports:
  - interface: GigabitEthernet0/47
    allowed_vlans: [100, 200, 300]
    native_vlan: 1
  - interface: GigabitEthernet0/48
    allowed_vlans: [100, 200]
```

---

### Files to Change

| File | Change |
|------|--------|
| `intent_networking/resolver.py` | `resolve_l2_access_port()` — detect `ports` list vs single `interface`; inner loop per port |
| `intent_networking/resolver.py` | `resolve_l2_trunk_port()` — same pattern |
| `network_as_code_example/intents/layer2/l2_access_port.yaml` | Add multi-port example with MANDATORY/OPTIONAL markers |
| `network_as_code_example/intents/layer2/l2_trunk_port.yaml` | Add multi-port example with MANDATORY/OPTIONAL markers |
| `pyproject.toml` | `version = "2.0.10"` → `"2.0.11"` |
| `docs/admin/release_notes/version_2.0.11.md` | New release notes file |
| `docs/admin/release_notes/index.md` | Add v2.0.11 row |
| `docs/admin/upgrade.md` | Add v2.0.11 upgrade section (no migrations, drop-in) |
| `docs/admin/compatibility_matrix.md` | Update `Current (latest: 2.0.10)` → `2.0.11` |
| `mkdocs.yml` | Add v2.0.11 entry above v2.0.10 in nav |

---

### Resolver Logic Change (`resolver.py`)

The key change in `resolve_l2_access_port()` and `resolve_l2_trunk_port()`:

```python
# Before — single port only
interface_name = intent_data.get("interface")
vlan_id = intent_data.get("vlan_id")

for device in devices:
    primitives.append({..., "interface": interface_name, "access_vlan": vlan_id})


# After — ports list OR single interface (backward compat)
ports = intent_data.get("ports")
if ports:
    port_list = ports  # new form: [{interface, vlan_id, ...}, ...]
else:
    # legacy single-port form — wrap in list so the loop below works for both
    port_list = [{"interface": intent_data.get("interface"), "vlan_id": intent_data.get("vlan_id"), ...}]

for device in devices:
    for port in port_list:
        primitives.append({..., "interface": port["interface"], "access_vlan": port["vlan_id"]})
```

No database migrations needed. Existing intents using `interface`/`vlan_id` continue to work unchanged.

---

### Effort Estimate

| Task | Time |
|------|------|
| Resolver changes (both functions) | 1 hour |
| Example YAML updates | 30 min |
| Docs + release notes | 30 min |
| **Total** | **~2 hours** |

---

---

## Section 2 — Comprehensive Nautobot Data Validation (Release v3.0.0)

### Problem

Intents are deployed without checking whether the objects they reference actually exist in Nautobot. A YAML file can reference VLAN 500 that was never created, an interface name that was renamed, a VRF that belongs to a different tenant, or a VNI that is already allocated — and the resolver only fails at template render time with an unhelpful error.

### Goal

Validate every intent against the current Nautobot inventory **before** deployment is attempted. Cover all 14 domains and 141 intent types. Provide field-level feedback, not just a pass/fail. Run automatically on Git sync (existence checks) and as a hard gate before deployment (full conflict checks). Expose a "Validate" button in the UI and a REST API endpoint for CI pipelines.

---

### Nautobot Version Compatibility

This release must work on **both** Nautobot 3.0.x and Nautobot 3.1.x (including 3.1.1).

| Concern | Approach |
|---------|----------|
| ViewSet FilterSet registration (the 3.1.1 crash fixed in app v2.0.9) | All new UIViewSets include `filterset_class` and `filterset_form_class` from the start |
| Bootstrap 5 data attributes (fixed in app v2.0.10) | All new templates use `data-bs-toggle`, `data-bs-target`, `data-bs-parent` exclusively |
| Nautobot ORM API | The `.get()` / `.filter()` / `.exists()` ORM surface is stable across all 3.x minor versions — no shims needed |
| Any 3.0.x vs 3.1.x API divergence discovered during dev | Wrap in `try/except ImportError` version guard with a comment citing the Nautobot version that introduced the change |
| CI | Test matrix runs against Nautobot `3.0.x` and `3.1.1` (pinned) |

---

### Architecture

#### New Module: `intent_networking/validators/`

```
intent_networking/validators/
    __init__.py
    base.py          # IntentValidator base class, ValidationResult, FieldError
    registry.py      # maps IntentTypeChoices → validator class
    layer2.py        # L2 validators
    layer3.py        # L3 validators
    mpls.py          # MPLS validators
    dc_evpn.py       # DC / EVPN / VXLAN validators
    security.py      # Security / Firewall validators
    wan.py           # WAN / SD-WAN validators
    wireless.py      # Wireless validators
    cloud.py         # Cloud / Hybrid Cloud validators
    qos.py           # QoS validators
    multicast.py     # Multicast validators
    management.py    # Management & Operations validators
    reachability.py  # Reachability validators
    service.py       # Service validators
```

#### Core Types (`base.py`)

```python
from dataclasses import dataclass, field

@dataclass
class FieldError:
    field: str        # e.g. "ports[0].interface", "vlans[1].id"
    message: str      # human-readable description
    severity: str     # "error" (blocks deploy) | "warning" (informational)

@dataclass
class ValidationResult:
    passed: bool
    errors: list[FieldError] = field(default_factory=list)
    warnings: list[FieldError] = field(default_factory=list)

class IntentValidator:
    def validate(self, intent, nautobot_context: dict) -> ValidationResult:
        raise NotImplementedError
```

#### Registry (`registry.py`)

```python
from intent_networking.models import IntentTypeChoices
from intent_networking.validators.layer2 import L2AccessPortValidator, VlanProvisionValidator
# ... etc

VALIDATOR_REGISTRY: dict[str, IntentValidator] = {
    IntentTypeChoices.TYPE_L2_ACCESS_PORT: L2AccessPortValidator(),
    IntentTypeChoices.TYPE_L2_TRUNK_PORT: L2TrunkPortValidator(),
    IntentTypeChoices.TYPE_VLAN_PROVISION: VlanProvisionValidator(),
    # ... all 141 types
}

def validate_intent(intent) -> ValidationResult:
    validator = VALIDATOR_REGISTRY.get(intent.intent_type)
    if validator is None:
        return ValidationResult(passed=True, warnings=[FieldError("type", "No validator registered for this intent type", "warning")])
    return validator.validate(intent, {})
```

---

### Per-Domain Validation Coverage

#### Layer 2

| Intent Type | Checks |
|-------------|--------|
| `vlan_provision` | VLAN IDs are within 1–4094; VLAN names are unique per site; VLANs don't already exist with a conflicting name on target devices |
| `l2_access_port` | Each interface exists on each scoped device; interface is not already a trunk; VLAN ID exists in Nautobot VLAN model |
| `l2_trunk_port` | Each interface exists; all `allowed_vlans` exist in Nautobot VLAN model; interface not already configured as access |
| `l2vni` | VNI pool exists and has capacity; VNI ID not already allocated elsewhere |
| `lag` | All member interfaces exist on device; no member is already in a different LAG |
| `spanning_tree_*` | Interface exists |
| `storm_control` | Interface exists |
| `mac_security` | Interface exists; prefix valid |

#### Layer 3

| Intent Type | Checks |
|-------------|--------|
| `vrf_basic` | VRF name not already assigned to a different tenant on device; namespace exists in `ipam.Namespace` |
| `svi_create` | VLAN exists in Nautobot; IP address exists in `ipam.IPAddress` and its prefix exists in `ipam.Prefix` |
| `l3_interface` | Interface exists; IP address in IPAM; prefix covers the IP |
| `bgp_ebgp` / `bgp_ibgp` | Neighbor IP exists as `ipam.IPAddress`; local ASN matches device record if set; VRF exists if specified |
| `bgp_route_reflector` | RR cluster IP in IPAM |
| `ospf` / `ospf3` | Interface exists; area format valid (dotted-decimal or integer) |
| `isis` | Interface exists |
| `static_route` | Next-hop IP reachable via IPAM prefix tree; VRF exists if specified |
| `policy_routing` | Interface exists; route-map referenced objects exist |
| `route_redistribution` | Source/destination protocol pair is valid |

#### MPLS & SP

| Intent Type | Checks |
|-------------|--------|
| `mpls_vpn_l3vpn` | VRF exists; RD format valid (`ASN:NN` or `IP:NN`) |
| `mpls_vpn_l2vpn` / `pseudowire` | Interface exists; peer IP in IPAM |
| `ldp` / `rsvp` | Interface exists |
| `segment_routing` | Interface exists; prefix-SID range valid |

#### DC / EVPN / VXLAN

| Intent Type | Checks |
|-------------|--------|
| `l2vni` | VNI pool exists; VNI within pool range; VNI not double-allocated |
| `l3vni` | Same as l2vni; VRF exists |
| `evpn_mpls` | BGP ASN in device record; VRF exists |
| `evpn_multisite` | Border gateway IP in IPAM |
| `vxlan_flood_learn` | VNI pool exists |

#### Security

| Intent Type | Checks |
|-------------|--------|
| `ipsec_s2s` / `ipsec_ikev2` | Peer IP in IPAM; local interface exists |
| `acl_standard` / `acl_extended` | Source/destination prefixes valid; interface exists if specified |
| `fw_rule` | Source/destination zone exists; interface exists |
| `urpf` | Interface exists |
| `macsec` | Interface exists |

#### WAN / SD-WAN

| Intent Type | Checks |
|-------------|--------|
| `wan_circuit` | Site exists in Nautobot; provider exists |
| `cloud_direct_connect` | Peer IP in IPAM; BGP ASNs valid |
| `sd_wan_policy` | Interface exists; traffic class valid |

#### Wireless

| Intent Type | Checks |
|-------------|--------|
| `wireless_ssid` | VLAN exists; IP range in IPAM |
| `wireless_rf_profile` | Channel list valid for regulatory domain |

#### Management

| Intent Type | Checks |
|-------------|--------|
| `mgmt_ntp` | Server IPs exist as `ipam.IPAddress` objects or are valid public IPs |
| `mgmt_snmp` | Management IP in IPAM |
| `mgmt_syslog` | Server IPs exist in IPAM |
| `mgmt_aaa` | Server IPs exist in IPAM |
| `mgmt_banner` | Length within platform limit |
| `mgmt_dns` | Server IPs exist in IPAM |

#### QoS

| Intent Type | Checks |
|-------------|--------|
| `qos_policy` | Interface exists; DSCP values in valid range 0–63 |
| `qos_marking` | Interface exists |

#### Multicast

| Intent Type | Checks |
|-------------|--------|
| `multicast_pim` | Interface exists; RP address in IPAM |
| `multicast_igmp` | Interface exists |

#### Reachability

| Intent Type | Checks |
|-------------|--------|
| `reachability` | Target IPs in IPAM |

---

### Integration Points

#### 1. Git Sync Hook (Existence Checks Only)

On every Git sync, run lightweight existence checks (no conflict detection — too expensive). Warnings logged to the sync job output. Does not block sync.

```python
# In the git sync job, after YAML is parsed:
result = validate_intent(intent)
for warning in result.warnings:
    job.log_warning(f"{intent.intent_id}: {warning.field} — {warning.message}")
```

#### 2. Pre-Deployment Gate (Full Checks, Blocks on Error)

In `deploy()` / the deployment Job, run the full validator (existence + conflict) before the resolver is called. Errors block deployment and surface in the Job log.

```python
result = validate_intent(intent)
if not result.passed:
    for err in result.errors:
        job.log_failure(f"{intent.intent_id}: [{err.field}] {err.message}")
    raise ValidationError(f"Intent {intent.intent_id} failed Nautobot data validation.")
```

#### 3. On-Demand `ValidateIntentJob`

A new Nautobot Job that runs validation on one or more intents without deploying. Usable from the UI Jobs menu and via the API for CI pipelines.

#### 4. UI "Validate" Button

On the intent detail page, a "Validate" button that calls the validate endpoint and renders field-level results inline (green checkmarks / red errors per field). Uses the existing Bootstrap 5 pattern from v2.0.10.

#### 5. REST API Endpoint

```
POST /api/plugins/intent-networking/intents/{id}/validate/
```

Returns:
```json
{
  "passed": false,
  "errors": [
    {"field": "ports[0].interface", "message": "Interface GigabitEthernet0/99 does not exist on device core-sw-01", "severity": "error"}
  ],
  "warnings": [
    {"field": "vlans[0].id", "message": "VLAN 100 already exists on core-sw-01 with name PROD — will be updated", "severity": "warning"}
  ]
}
```

---

### Files to Create / Modify

| File | Action |
|------|--------|
| `intent_networking/validators/__init__.py` | New |
| `intent_networking/validators/base.py` | New — `IntentValidator`, `ValidationResult`, `FieldError` |
| `intent_networking/validators/registry.py` | New — validator registry + `validate_intent()` entry point |
| `intent_networking/validators/layer2.py` | New — L2 validators |
| `intent_networking/validators/layer3.py` | New — L3 validators |
| `intent_networking/validators/mpls.py` | New — MPLS validators |
| `intent_networking/validators/dc_evpn.py` | New — DC/EVPN/VXLAN validators |
| `intent_networking/validators/security.py` | New — Security validators |
| `intent_networking/validators/wan.py` | New — WAN validators |
| `intent_networking/validators/wireless.py` | New — Wireless validators |
| `intent_networking/validators/cloud.py` | New — Cloud validators |
| `intent_networking/validators/qos.py` | New — QoS validators |
| `intent_networking/validators/multicast.py` | New — Multicast validators |
| `intent_networking/validators/management.py` | New — Management validators |
| `intent_networking/validators/reachability.py` | New — Reachability validators |
| `intent_networking/validators/service.py` | New — Service validators |
| `intent_networking/jobs.py` | Add `ValidateIntentJob` |
| `intent_networking/views.py` | Add `validate_intent_view` |
| `intent_networking/api/views.py` | Add `IntentValidateView` (POST endpoint) |
| `intent_networking/api/serializers.py` | Add `ValidationResultSerializer` |
| `intent_networking/api/urls.py` | Register validate endpoint |
| `intent_networking/templates/intent_networking/intent_detail.html` | Add Validate button + result panel |
| `intent_networking/urls.py` | Register validate view |
| `pyproject.toml` | `version = "2.0.11"` → `"3.0.0"` |
| `docs/admin/release_notes/version_3.0.0.md` | New |
| `docs/admin/release_notes/index.md` | Add v3.0.0 row |
| `docs/admin/upgrade.md` | Add v3.0.0 upgrade section |
| `docs/admin/compatibility_matrix.md` | Add 3.0.x row; mark 2.0.x as Supported |
| `mkdocs.yml` | Add v3.0.0 entry at top of nav |

---

### Compatibility Matrix Update for v3.0.0

| App Version | Nautobot Min | Nautobot Max | Python | Status |
|-------------|-------------|-------------|--------|--------|
| 3.0.x | 3.0.0 | 3.x | 3.10–3.12 | Current |
| 2.0.x | 3.0.0 | 3.x | 3.10–3.12 | Supported |
| 1.1.8 | 3.0.0 | 3.x | 3.10–3.12 | Deprecated |

---

### Breaking Changes in v3.0.0

- **Deployment is blocked** if the intent fails Nautobot data validation. Previously, invalid references would only fail at template render time. Existing intents with references to deleted or renamed objects will now surface errors before deployment.
- No database migrations.
- No YAML schema changes (all new checks are read-only against existing `intent_data`).
- Validators can be disabled per-intent-type via `PLUGINS_CONFIG` if needed during migration.

---

### Effort Estimate

| Task | Time |
|------|------|
| `validators/` scaffolding (base, registry) | 1 day |
| Layer 2 + Layer 3 validators (highest traffic) | 2 days |
| DC/EVPN, Security, Management validators | 2 days |
| Remaining 10 domain validators | 3 days |
| Pre-deployment gate integration | 1 day |
| Git sync hook integration | 0.5 days |
| `ValidateIntentJob` | 0.5 days |
| UI Validate button + result panel | 1 day |
| REST API endpoint | 1 day |
| Tests | 2 days |
| Docs + release notes | 1 day |
| **Total** | **~15 days** |
