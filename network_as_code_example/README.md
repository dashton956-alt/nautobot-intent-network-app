# Network-as-Code Example

Reference implementation for the **nautobot-app-intent-networking** plugin.
Shows how to structure a git-ops workflow where every network change goes through
a pull request with automated validation before reaching any device.

## How It Works

```
Engineer writes YAML intent
       │
       ▼
  Git Pull Request
       │
       ▼
  CI Pipeline (GitHub Actions)
  ├── YAML syntax check
  ├── Schema validation (pykwalify)
  └── OPA policy checks
       │
       ▼
  Human Review + Approval
       │
       ▼
  PR Merged → Nautobot datasource sync triggered
       │
       ▼
  Nautobot resolves intent → renders config → deploys via Nornir
       │
       ▼
  Verification → Intent status updated ✓
```

## Directory Structure

```
network_as_code_example/
├── intents/                      # Intent YAML files (the source of truth)
│   ├── cloud/                    # Cloud / hybrid cloud intents
│   ├── connectivity/             # Legacy connectivity intents
│   ├── dc/                       # Real DC/EVPN customer examples
│   ├── dc_evpn/                  # DC/EVPN reference templates
│   ├── examples/                 # Header, scope, policy, verification examples
│   ├── ipsec-wan/                # IPSec WAN examples
│   ├── l2/                       # Real L2 customer examples
│   ├── layer2/                   # L2 reference templates (every field documented)
│   ├── l3/                       # Real L3 customer examples
│   ├── layer3/                   # L3 reference templates
│   ├── management/               # Management reference templates
│   ├── mgmt/                     # Real management customer examples
│   ├── mpls/                     # MPLS / SP reference templates
│   ├── multicast/                # Multicast reference templates
│   ├── qos/                      # QoS reference templates
│   ├── reachability/             # Reachability reference templates
│   ├── security/                 # Security reference templates
│   ├── service/                  # Service reference templates
│   ├── wan/                      # WAN reference templates
│   └── wireless/                 # Wireless reference templates
│
├── templates/                    # Jinja2 config templates per vendor OS
│   ├── arista_eos/               # Arista EOS (76 intent-type templates)
│   ├── cisco_ios/                # Cisco IOS / IOS-XE (58 templates)
│   └── cisco_nxos/               # Cisco NX-OS (47 templates)
│
├── schemas/
│   └── intent.schema.yml         # pykwalify schema (used by CI)
│
└── policies/
    └── compliance.rego           # OPA policy (PCI-DSS, HIPAA, SOC2)
```

## Intent File Naming

Two styles coexist in `intents/`:

| Style | Example | Purpose |
|-------|---------|---------|
| **Reference** | `layer2/l2_access_port.yaml` | Every field shown with MANDATORY/OPTIONAL annotations |
| **Real example** | `l2/corp-l2-access-servers-dc-east-001.yaml` | Realistic customer intent |

Reference files are named by intent type and document all supported fields.
Real examples show production-ready intents with realistic values.

## Common Fields (every intent requires these)

| Field | Mandatory | Notes |
|-------|-----------|-------|
| `id` | **Yes** | Unique slug: lowercase, alphanumeric + hyphens |
| `type` | **Yes** | Must match an `IntentTypeChoices` value |
| `version` | **Yes** | Positive integer — increment on every edit |
| `tenant` | **Yes** | Must match a Tenant slug in Nautobot |
| `description` | **Yes** | Minimum 10 characters |
| `change_ticket` | **Yes** | Format: `CHG0000000` (CHG + 7 digits) |
| `scope` | **Yes** | One of: `sites`, `devices`, `roles`, `all_tenant_devices` |
| `approved_by` | Conditional | Required for high-impact types (see below) |

### High-impact types that require `approved_by`

`dmvpn`, `ipsec_s2s`, `ipsec_ikev2`, `evpn_vxlan_fabric`, `mpls_l3vpn`,
`fw_rule`, `sr_mpls`, `sdwan_overlay`

## Deployment & Verification Options

```yaml
deployment:
  strategy: rolling      # rolling | canary | all_at_once (default: rolling)
  save_config: true      # write memory after deploy (default: true)

verification:
  level: basic           # basic | nuts (default: basic)
  trigger: on_deploy     # on_deploy | scheduled | both (default: on_deploy)
  fail_action: alert     # alert | rollback | remediate (default: alert)
```

## OPA Compliance

Set `policy.compliance` to enforce compliance rules automatically:

| Standard | Key enforcements |
|----------|-----------------|
| **PCI-DSS** | `encryption: required`, `verification.trigger: both`, telnet denied, `max_latency_ms ≤ 20`, IKEv2 + AES-256 + SHA-256 + DH≥14 |
| **HIPAA** | `encryption != none`, `verification.trigger: both`, AES-256 + SHA-256 |
| **SOC2** | Advisory warnings for SNMPv2c, preferred encryption, `save_config: false` |

High-impact intents enforce `strategy: rolling` or `canary` — never `all_at_once`.

## Templates

The `templates/` directory contains Jinja2 templates for rendering intent YAMLs
directly to device config. These templates take intent YAML fields as variables
and are organized by vendor OS:

- `arista_eos/` — EOS 4.x syntax (76 templates)
- `cisco_ios/` — IOS / IOS-XE syntax (58 templates)
- `cisco_nxos/` — NX-OS syntax (47 templates)

> **Note:** These example templates render directly from intent YAML fields.
> The plugin's internal templates at `intent_networking/jinja_templates/` render
> from resolver primitive output — they use different variable names and serve
> the Nautobot deployment pipeline.

## CI Validation

The GitHub Actions workflow (`.github/workflows/validate-intents.yml`) runs
automatically on any PR that touches `network_as_code_example/intents/**`:

1. **YAML syntax** — every changed file parses cleanly
2. **Schema validation** — pykwalify validates against `schemas/intent.schema.yml`

To run locally:

```bash
pip install pykwalify pyyaml
pykwalify \
  --data-file network_as_code_example/intents/layer2/l2_access_port.yaml \
  --schema-file network_as_code_example/schemas/intent.schema.yml
```
