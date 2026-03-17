# Security Review — nautobot-intent-network-app

**Review Date:** 2026-03-16
**Scope:** Full codebase review of the `intent_networking` Nautobot plugin
**Standards Applied:**

| Standard | Full Title |
|---|---|
| ISO/IEC 27001:2022 | Information Security Management Systems |
| NIST SP 800-171 Rev 3 | Protecting Controlled Unclassified Information |
| NIST CSF 2.0 | Cybersecurity Framework |
| NIST SP 1800-5 | IT Asset Management |
| COBIT 2019 | Control Objectives for Information and Related Technologies |
| CIS Controls v8 | Center for Internet Security Critical Security Controls |
| GDPR | EU General Data Protection Regulation 2016/679 |

---

## Executive Summary

The `nautobot-intent-network-app` plugin is a network intent engine built on top of the Nautobot network source-of-truth platform. It manages the full lifecycle of network intents — from definition through approval, deployment, verification, and rollback — across a broad set of network domains (Layer 2/3, MPLS, EVPN/VXLAN, Security, WAN, Wireless, Cloud, QoS, Management).

The codebase demonstrates a solid security posture in several important areas, including an immutable audit trail, formal approval workflow with RBAC, secrets integration with HashiCorp Vault and other providers, multi-tenancy isolation, conflict detection, change-window scheduling, and policy-as-code enforcement via OPA. However, several gaps were identified that require remediation before the application can be considered fully compliant with the referenced standards.

### Risk Rating Summary

| Severity | Count |
|---|---|
| Critical | 1 |
| High | 2 |
| Medium | 6 |
| Low | 6 |
| Informational | 4 |

---

## Strengths Identified

Before enumerating findings, the following security-positive design decisions are noted:

1. **Immutable Audit Trail (`IntentAuditEntry`)** — every lifecycle action is recorded with actor, timestamp, and detailed JSON payload. This directly supports non-repudiation requirements across all referenced standards.
2. **Formal Approval Workflow** — the `IntentApproval` model plus the `approve_intent` custom Django permission enforce segregation between those who submit intents and those who approve them for production deployment.
3. **RBAC with Custom Permissions** — three custom permissions (`approve_intent`, `deploy_intent`, `rollback_intent`) are enforced consistently in both REST API views and Django UI views.
4. **Nautobot Secrets Integration (`secrets.py`)** — device credentials and API tokens can be stored in Nautobot's encrypted secrets framework, HashiCorp Vault, AWS Secrets Manager, or CyberArk, avoiding plaintext credentials in code.
5. **Policy-as-Code via OPA (`opa_client.py`)** — intent policies are evaluated against an Open Policy Agent instance before any resource allocation occurs, providing a programmable compliance boundary.
6. **Multi-Tenancy Isolation** — `validate_tenant_isolation()` in `models.py` and `IntentResolutionJob` enforce that intents cannot inadvertently affect resources belonging to another tenant.
7. **Status Workflow Enforcement** — `Intent.VALID_STATUS_TRANSITIONS` and the `clean()` method prevent ad-hoc status changes that bypass the governance lifecycle.
8. **Input Validation** — `INTENT_REQUIRED_FIELDS` in `api/serializers.py` validates per-intent-type required fields at the API boundary before any job is enqueued.
9. **Safe YAML Parsing** — `yaml.safe_load()` is used throughout `datasources.py`, preventing YAML deserialisation attacks.
10. **Conflict Detection** — `detect_conflicts()` in `models.py` is called at sync time and during resolution, preventing overlapping resource allocation.
11. **Scheduled Change Windows** — `scheduled_deploy_at` on the `Intent` model and checks in `_pre_deploy_checks()` enforce change-window scheduling requirements.
12. **Authentication Required on Topology API** — `TopologyGraphView` explicitly sets `permission_classes = [IsAuthenticated]`.
13. **Canary and Rolling Deployments** — staged deployment strategies (`canary`, `rolling`) reduce the blast radius of any single deployment failure.
14. **TLS for External Calls** — PagerDuty events use the HTTPS endpoint (`https://events.pagerduty.com`); ServiceNow uses `https://{instance}.service-now.com`.

---

## Security Findings

### Finding 1 — Hardcoded Fallback Credentials in Debug Mode

**Severity:** Critical
**File:** `intent_networking/secrets.py` lines 71–76
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.5 — Secure authentication |
| NIST SP 800-171 | 3.5.2 — Authenticate users, processes, and devices |
| CIS Controls v8 | Control 5.2 — Use Unique Passwords |
| COBIT 2019 | DSS05.04 — Manage user and access rights |
| NIST CSF 2.0 | PR.AA-02 — Identities, credentials managed |

**Description:**
When `settings.DEBUG` is `True` and no device credentials are found in environment variables or Nautobot Secrets, the code falls back to hardcoded credentials `("admin", "admin")`:

```python
if settings.DEBUG:
    logger.warning(
        "No device credentials configured; using debug fallback credentials (admin/admin). ..."
    )
    return ("admin", "admin")
```

**Risk:**
If a production environment accidentally has `DEBUG=True` (a known Django misconfiguration risk), or if this code path is exercised in a staging environment connected to real devices, default credentials will be used for device authentication. Default credentials are one of the top exploited attack vectors.

**Recommendation:**
Remove the hardcoded fallback entirely. If debug convenience is needed, require explicit opt-in via a dedicated environment variable (e.g., `ALLOW_DEBUG_CREDENTIALS=true`) with additional safeguards such as restricting to loopback addresses only.

---

### Finding 2 — Example Credential File Contains Weak Default Values

**Severity:** High
**File:** `development/creds.example.env`
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.5 — Secure authentication; A.5.23 — Supplier relationships |
| NIST SP 800-171 | 3.5.2 — Authenticate users/devices |
| CIS Controls v8 | Control 4.7 — Manage Default Accounts |
| COBIT 2019 | DSS05.04 — Manage user and access rights |
| GDPR | Article 32 — Security of processing |

**Description:**
The example credentials file contains weak default values that an operator could accidentally promote to a production or pre-production environment:

```
NAUTOBOT_DB_PASSWORD=changeme
NAUTOBOT_REDIS_PASSWORD=changeme
NAUTOBOT_SECRET_KEY='changeme'
NAUTOBOT_SUPERUSER_PASSWORD=admin
NAUTOBOT_SUPERUSER_API_TOKEN=0123456789abcdef0123456789abcdef01234567
```

**Risk:**
If this file is copied and deployed without modification, the Nautobot superuser account, database, and Redis instance will be protected by trivially guessable credentials. The hardcoded API token (`0123456789abcdef...`) is particularly dangerous as it is predictable and publicly visible in version control.

**Recommendation:**
Replace all example values with clearly invalid placeholders (e.g., `NAUTOBOT_DB_PASSWORD=<REPLACE_WITH_STRONG_PASSWORD>`) or use a secret generation script. Add explicit documentation warning that these values must be replaced before any deployment. Ensure the file is explicitly labelled as "example only" in both the filename and its header comment.

---

### Finding 3 — ServiceNow Password Stored in Plugin Configuration

**Severity:** Medium
**File:** `intent_networking/events.py` lines 164–168; `development/nautobot_config.py`
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.24 — Use of cryptography; A.8.10 — Information deletion |
| NIST SP 800-171 | 3.13.10 — Establish and manage cryptographic keys |
| CIS Controls v8 | Control 3.11 — Encrypt sensitive data at rest |
| COBIT 2019 | APO13.01 — Establish and maintain an information security management system |
| NIST CSF 2.0 | PR.DS-01 — Data-at-rest is protected |

**Description:**
The ServiceNow integration in `events.py` retrieves its credentials via `_cfg("servicenow_password")`, which reads from `PLUGINS_CONFIG` in the Django settings file. This means the ServiceNow username and password are stored as plaintext in the application settings, not in Nautobot's encrypted Secrets framework.

**Risk:**
Any process, user, or attacker with read access to the Django settings file (or environment variables that back it) can obtain the ServiceNow password. These credentials would also appear in any settings export, configuration backups, or logging of the settings dict.

**Recommendation:**
Migrate ServiceNow credentials to use Nautobot's SecretsGroup pattern already implemented in `secrets.py`. Add `servicenow_secrets_group` as a config option parallel to `device_secrets_group` and `nautobot_api_secrets_group`.

---

### Finding 4 — GitHub Token Retrieved from Environment Variable Instead of Secrets Framework

**Severity:** Medium
**File:** `intent_networking/notifications.py` line 40
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.5 — Secure authentication |
| NIST SP 800-171 | 3.5.2 — Authenticate users, processes, and devices |
| CIS Controls v8 | Control 3.11 — Encrypt sensitive data at rest |
| NIST CSF 2.0 | PR.AA-02 — Identities, credentials managed |

**Description:**
`raise_github_issue()` in `notifications.py` retrieves the GitHub Personal Access Token via:

```python
token = os.environ.get("GITHUB_TOKEN")
```

Unlike device credentials and Nautobot API tokens (which have SecretsGroup integration), this token is not retrievable from Nautobot Secrets. Environment variables are generally less secure than an encrypted secrets backend because they can be read by any process in the same environment, appear in `/proc/<pid>/environ`, and may be logged by container orchestration systems.

**Recommendation:**
Add a `github_secrets_group` config option and implement the same SecretsGroup lookup pattern used in `secrets.py`. Fall back to the environment variable for backward compatibility but emit a deprecation warning.

---

### Finding 5 — OPA Communication Defaults to Unencrypted HTTP

**Severity:** Medium
**File:** `intent_networking/opa_client.py` line 18
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.20 — Networks security; A.8.26 — Application security requirements |
| NIST SP 800-171 | 3.13.8 — Implement cryptographic mechanisms to protect CUI during transmission |
| CIS Controls v8 | Control 3.10 — Encrypt sensitive data in transit |
| NIST SP 1800-5 | Network Security / Encrypted Communications |
| GDPR | Article 32(1)(a) — Encryption of personal data in transit |

**Description:**
The OPA URL defaults to `http://opa:8181` (unencrypted HTTP):

```python
OPA_URL = os.environ.get("OPA_URL", "http://opa:8181")
```

Intent data sent to OPA for policy evaluation may include sensitive fields such as tenant identifiers, VRF names, IP addresses, and other network topology information. Transmitting this data unencrypted allows any actor with network access to the path between Nautobot and OPA to read or modify policy evaluation inputs and results.

Additionally, `_query_opa()` in the same file does not validate TLS certificates even when HTTPS is used, because `requests.post()` is called without `verify=` parameter (it defaults to `True` for verify, which is correct, but the default URL itself is HTTP).

**Recommendation:**
Update the default OPA URL to `https://opa:8181` and document the TLS certificate requirement in the deployment guide. Consider adding a config option `opa_verify_ssl` for environments where self-signed certificates are used, defaulting to `True`.

---

### Finding 6 — Rendered Device Configurations Stored in Plaintext

**Severity:** Medium
**File:** `intent_networking/models.py` (`Intent.rendered_configs` and `IntentAuditEntry.detail`)
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.10 — Information deletion; A.8.24 — Use of cryptography |
| NIST SP 800-171 | 3.13.16 — Protect the confidentiality of backup CUI at storage locations |
| CIS Controls v8 | Control 3.11 — Encrypt sensitive data at rest |
| COBIT 2019 | APO13.01 — ISMS; DSS05.02 — Manage network and connectivity security |
| GDPR | Article 32(1)(a) — Pseudonymisation and encryption of personal data |

**Description:**
Rendered device configurations (CLI or structured config) are cached in two places in the database:

1. `Intent.rendered_configs` — a `JSONField` on the Intent model.
2. `IntentAuditEntry.detail` — the `detail` JSONField of audit entries created by `IntentDeploymentJob` includes the full `rendered_configs` dict.

Device configurations for security-sensitive intent types (e.g., `ipsec_s2s`, `aaa`, `mgmt_snmp`, `fw_rule`) may contain pre-shared keys, SNMP community strings, RADIUS/TACACS shared secrets, or banner text that could be considered sensitive operational data. These are stored in plaintext JSON in the application database with no encryption at the application layer.

**Recommendation:**
1. Evaluate which intent types produce configurations containing credentials or secrets and redact those fields before caching (e.g., replace SNMP community strings with `***` in stored configs).
2. Do not store full rendered configs in `IntentAuditEntry.detail` — store only a reference (e.g., a hash or S3/object-store URL) for the actual config content.
3. Ensure the database itself uses transparent data encryption (TDE) at the infrastructure level.

---

### Finding 7 — No Rate Limiting on High-Impact API Endpoints

**Severity:** Medium
**File:** `intent_networking/api/views.py` (approve, deploy, rollback, sync-from-git endpoints)
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.20 — Networks security; A.8.6 — Capacity management |
| NIST SP 800-171 | 3.1.3 — Control the flow of CUI |
| CIS Controls v8 | Control 13.10 — Perform Application Layer Filtering |
| COBIT 2019 | DSS05.02 — Manage network and connectivity security |
| NIST CSF 2.0 | PR.IR-01 — Networks and environments are protected |

**Description:**
High-impact API endpoints — including `/approve/`, `/deploy/`, `/rollback/`, `/sync-from-git/`, and `/schedule/` — have no explicit rate limiting. An authenticated attacker (or a misconfigured automation script) could rapidly repeat requests, potentially:

- Spamming approval records on an intent.
- Triggering multiple concurrent deployment jobs, causing race conditions.
- Flooding the `IntentAuditEntry` table.
- Exhausting database connections via rapid `sync-from-git` calls.

**Recommendation:**
Apply Django REST Framework's throttling classes (`UserRateThrottle`, `AnonRateThrottle`) on the `IntentViewSet`, scoped specifically to the mutating actions (`approve`, `deploy`, `rollback`, `sync-from-git`, `schedule`). A conservative default of 10 requests/minute per user is appropriate for production deploy and approve actions.

---

### Finding 8 — No Data Retention or Right-to-Erasure Mechanism for Audit Trail

**Severity:** Medium
**File:** `intent_networking/models.py` (`IntentAuditEntry`)
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| GDPR | Article 5(1)(e) — Storage limitation; Article 17 — Right to erasure |
| GDPR | Article 25 — Data protection by design and by default |
| ISO 27001:2022 | A.8.10 — Information deletion |
| COBIT 2019 | APO09.04 — Monitor and report service levels |
| CIS Controls v8 | Control 3.2 — Establish and maintain a data inventory |

**Description:**
`IntentAuditEntry` is explicitly described as an "immutable audit record" and is used for SOC2/PCI-DSS compliance. However, it stores `actor` (a username string) in audit records, and the `detail` JSONField may indirectly contain personal data (e.g., approver comments, user-provided metadata in intent files).

There is no data retention policy, automatic purging, or pseudonymisation mechanism. GDPR requires a documented retention period and the ability to erase or pseudonymise personal data when it is no longer necessary for the purpose for which it was collected.

**Recommendation:**
1. Define and document a data retention period for audit records (e.g., 7 years for financial services, 1–3 years for general operations).
2. Implement an automated data purge or pseudonymisation job that replaces `actor` usernames with a non-identifiable token (e.g., a one-way hash) after the retention period expires.
3. Avoid storing personal identifiers in the `detail` JSON field; use only functional identifiers (intent IDs, approval IDs, job IDs).
4. Document in the privacy notice that usernames are recorded in the audit trail and for what purpose and retention period.

---

### Finding 9 — Audit Actor Falls Back to Hardcoded User ID

**Severity:** Low
**File:** `intent_networking/models.py` lines 508–511
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.15 — Logging; A.8.17 — Clock synchronisation |
| NIST SP 800-171 | 3.3.1 — Create and retain system audit logs |
| CIS Controls v8 | Control 8.5 — Collect Detailed Audit Logs |
| COBIT 2019 | MEA02.01 — Monitor internal controls |

**Description:**
`_get_workflow_requesting_user_id()` falls back to returning `1` (assumed to be the admin user primary key) when it cannot resolve the requesting user from a native Nautobot ApprovalWorkflow:

```python
return 1  # fallback to admin
```

This causes audit records created via the native workflow path (`on_workflow_approved`, `on_workflow_denied`, `on_workflow_canceled`) to be incorrectly attributed to user ID 1 instead of the actual decision-maker, breaking non-repudiation.

**Recommendation:**
Instead of falling back to `1`, raise an exception or log an error and return `None`. The `IntentApproval.approver` field can be made nullable with `null=True, blank=True` for these edge cases, and the `IntentAuditEntry.actor` can record `"unknown (workflow)"` to preserve auditability without incorrect attribution.

---

### Finding 10 — Canary Deployment Verification Not Fully Implemented

**Severity:** Low
**File:** `intent_networking/jobs.py` lines 563–571
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| NIST CSF 2.0 | DE.CM-09 — Computing hardware and software verified |
| ISO 27001:2022 | A.8.8 — Management of technical vulnerabilities |
| COBIT 2019 | BAI06.03 — Track and report change status |
| CIS Controls v8 | Control 16.13 — Conduct Application Penetration Testing |

**Description:**
The canary deployment strategy includes a code comment explicitly noting that verification before advancing to the next stage is not yet implemented:

```python
# In a real implementation this would wait for verification result
# before proceeding. For now, we log the intent.
stage.status = "verifying"
stage.save()
stage.status = "verified"
stage.save()
```

This means that even when `deployment_strategy = "canary"`, the plugin immediately proceeds to deploy all remaining stages without waiting for confirmation that the canary stage succeeded. This defeats the purpose of canary deployments as a risk-reduction mechanism.

**Recommendation:**
Implement a blocking verification step after the canary stage, either by synchronously running `IntentVerificationJob` and checking the result, or by using Celery chains to sequence the verification before proceeding to subsequent stages.

---

### Finding 11 — GraphQL Endpoint Exposes Full `intent_data` Field

**Severity:** Low
**File:** `intent_networking/graphql.py` line 35
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.3 — Information access restriction |
| NIST SP 800-171 | 3.1.3 — Control the flow of CUI |
| CIS Controls v8 | Control 3.3 — Configure data access control lists |
| GDPR | Article 5(1)(c) — Data minimisation |
| NIST CSF 2.0 | PR.DS-02 — Data-in-transit is protected |

**Description:**
The GraphQL type definition for `IntentType` includes `intent_data` in its exposed fields:

```python
fields = [
    ...
    "intent_data",
    ...
]
```

`intent_data` is the full parsed YAML stored as JSON, which is the single source of truth for all intent fields. For security-sensitive intent types (e.g., `ipsec_s2s`, `macsec`, `aaa`, `mgmt_snmp`), this field may contain credentials, pre-shared keys, SNMP community strings, or other sensitive operational parameters.

Any authenticated user with access to the GraphQL endpoint can query `intentData` across all intents, bypassing any field-level access controls that might be in place on the REST API.

**Recommendation:**
Either exclude `intent_data` from the GraphQL type entirely and provide only derived/promoted fields, or implement a custom resolver that applies per-field redaction based on the intent type and the requesting user's permissions (e.g., only return `intent_data` to users with `intent_networking.view_sensitive_intent_data` permission).

---

### Finding 12 — No Explicit Segregation-of-Duties Enforcement for Self-Approval

**Severity:** Low
**File:** `intent_networking/api/views.py` and `intent_networking/views.py` (approve endpoints)
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.5.3 — Segregation of duties |
| NIST SP 800-171 | 3.1.4 — Separate the duties of individuals |
| COBIT 2019 | DSS05.04 — Manage user and access rights |
| CIS Controls v8 | Control 6.3 — Require MFA for Externally-Exposed Applications |
| NIST CSF 2.0 | PR.AA-05 — Access permissions managed |

**Description:**
There is no code-level check preventing the user who created (or last modified) an intent from also approving it. A user with both `change_intent` and `approve_intent` permissions could create an intent and immediately approve it themselves, bypassing the intended segregation of duties.

This is particularly relevant in smaller teams or in environments where roles are not tightly managed, and in financial services, government, or regulated industries where four-eyes / dual-control is a compliance requirement (e.g., PCI-DSS 3.4, SOX change management).

**Recommendation:**
In the `approve` API action and `IntentApproveView.post`, add a check that `request.user` is not the same as the user who last updated or created the intent. If the intent has a `created_by` or `last_updated_by` field (via Nautobot's change logging), compare against those values. If not, compare against the `actor` field in the most recent `IntentAuditEntry`.

---

### Finding 13 — Slack Webhook URL Stored in Plugin Configuration

**Severity:** Low
**File:** `development/nautobot_config.py` line 137; `intent_networking/events.py` line 93
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.5 — Secure authentication |
| CIS Controls v8 | Control 3.11 — Encrypt sensitive data at rest |
| GDPR | Article 32 — Security of processing |

**Description:**
The Slack webhook URL is stored in `PLUGINS_CONFIG` (plaintext in the Django settings file). While a Slack Incoming Webhook URL is lower sensitivity than a password, it does grant the ability to post arbitrary messages to a Slack channel, which could be used to deliver phishing messages, social engineering attacks, or to disrupt incident response communications.

**Recommendation:**
Store Slack webhook URLs and other integration URLs (PagerDuty routing key, generic webhook URLs) in Nautobot Secrets or in an encrypted secrets backend rather than in the settings file.

---

### Finding 14 — No TLS Certificate Verification Configured for Generic Webhooks

**Severity:** Low
**File:** `intent_networking/events.py` line 197
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.20 — Networks security |
| NIST SP 800-171 | 3.13.8 — Implement cryptographic mechanisms |
| CIS Controls v8 | Control 3.10 — Encrypt sensitive data in transit |

**Description:**
The generic webhook dispatch in `_send_generic_webhooks()` posts to user-configured URLs without any TLS certificate validation option:

```python
requests.post(url, json=event, timeout=10)
```

If a user configures an HTTPS webhook URL with a self-signed certificate, the request will fail with a certificate verification error (which is the correct, safe default). However, there is no documentation or configuration option to manage this case securely (e.g., supplying a CA bundle). This may lead operators to disable certificate verification globally in their environment, which is a security regression.

**Recommendation:**
Add an optional `webhook_ca_bundle` config option per webhook URL that allows specifying a CA certificate bundle path. Document that disabling certificate verification is not supported or recommended.

---

### Finding 15 — Development Configuration Not Explicitly Restricted for Production Use

**Severity:** Informational
**File:** `development/nautobot_config.py`
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.31 — Separation of development, test and production environments |
| NIST SP 800-171 | 3.4.1 — Establish and maintain baseline configurations |
| COBIT 2019 | BAI03.11 — Manage changes to test and production environments |
| CIS Controls v8 | Control 4.1 — Establish and maintain a secure configuration process |

**Description:**
The `development/nautobot_config.py` is clearly labelled as a development configuration, but there is no technical guard or documentation explicitly preventing it from being used in production. The file sets `ALLOWED_HOSTS` from an environment variable with an empty string default, and `SECRET_KEY` from an environment variable that defaults to an empty string — both of which would silently produce a misconfigured production deployment.

**Recommendation:**
Add a startup guard that raises `ImproperlyConfigured` if `DEBUG=True` and the hostname is not `localhost`, or if `SECRET_KEY` is empty or equals `'changeme'`. Add a prominent warning in the README and installation docs that this file must not be used in production.

---

### Finding 16 — Nautobot Job Approval Bypassed for Deployment Jobs

**Severity:** Informational
**File:** `intent_networking/jobs.py` — `IntentDeploymentJob.Meta`, `IntentRollbackJob.Meta`
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.32 — Change management |
| NIST SP 800-171 | 3.4.3 — Track, review, approve, log changes |
| COBIT 2019 | BAI06.01 — Evaluate and authorise requests for changes |
| CIS Controls v8 | Control 4.1 — Establish and maintain a secure configuration process |

**Description:**
`IntentDeploymentJob` and `IntentRollbackJob` set `approval_required = False` in their `Meta` class, meaning Nautobot's built-in job approval mechanism is disabled for these jobs. While the intent engine implements its own approval gate (`Intent.is_approved`, `_pre_deploy_checks`), bypassing the platform-level job approval means that:

1. A user who can directly enqueue jobs (via the Nautobot Jobs UI) could bypass the intent-level approval check by directly running `IntentDeploymentJob`.
2. Any future refactoring that removes the `_pre_deploy_checks` call would silently remove the approval gate without a platform-level safety net.

**Recommendation:**
Set `approval_required = True` on `IntentDeploymentJob` and `IntentRollbackJob` and document that Nautobot's job approval is the second layer of defence. Alternatively, add an explicit comment explaining why `approval_required = False` is intentional and what the compensating control is.

---

### Finding 17 — No Integrity Check on YAML Files Loaded from Git Repository

**Severity:** Informational
**File:** `intent_networking/datasources.py` lines 182–186
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.8 — Management of technical vulnerabilities |
| NIST SP 800-171 | 3.13.10 — Establish and manage cryptographic keys |
| NIST CSF 2.0 | PR.DS-06 — Integrity checking mechanisms used |
| CIS Controls v8 | Control 2.3 — Address unauthorized software |

**Description:**
When syncing intent YAML files from a Git repository, the code reads files directly from the filesystem without verifying their integrity (e.g., via GPG signatures or SHA-256 checksums):

```python
with open(filepath, "r", encoding="utf-8") as fd:
    intent_yaml = yaml.safe_load(fd)
```

If an attacker were to compromise the Git repository or the filesystem where it is cloned (a supply-chain attack), they could introduce malicious intent files that would be silently imported into Nautobot and potentially deployed to the network.

**Recommendation:**
1. Require that intent YAML files in production repositories are GPG-signed by authorised committers.
2. Validate the Git commit signature as part of the `refresh_git_intent_definitions` callback.
3. At minimum, log the `git_commit_sha` for every file loaded (already done at the intent level) and use Nautobot's GitRepository branch protection to restrict who can push to the main/production branch.

---

### Finding 18 — Missing `fw_rule` Intent Type in SecurityFinding on Validation

**Severity:** Informational
**File:** `intent_networking/api/serializers.py` — `INTENT_REQUIRED_FIELDS`
**Standards Mapped:**

| Standard | Clause / Control |
|---|---|
| ISO 27001:2022 | A.8.22 — Segregation in networks |
| NIST SP 800-171 | 3.1.3 — Control the flow of CUI |
| CIS Controls v8 | Control 12.8 — Manage Access Control for Remote Assets |

**Description:**
Several security-critical intent types have empty required-field lists in `INTENT_REQUIRED_FIELDS`, meaning they can be created and synced with no field validation:

```python
"ipsec_ikev2": [],
"gre_over_ipsec": ["tunnel_destination"],
"dot1x_nac": [],
"aaa": [],
"ssl_inspection": [],
```

In particular, `aaa` (RADIUS/TACACS) and `dot1x_nac` (802.1X / NAC) are security-critical and should require at minimum a server list or policy name to prevent the creation of empty/non-functional security intents that misleadingly appear configured.

**Recommendation:**
Review and populate the required-field lists for all security-critical intent types (`aaa`, `dot1x_nac`, `ssl_inspection`, `ipsec_ikev2`, `copp`, `urpf`). Even requiring a single meaningful field (e.g., `servers` for `aaa`) will improve data quality and prevent the submission of semantically empty security configurations.

---

## Compliance Mapping Matrix

The table below maps each finding to the applicable clauses/controls across all seven referenced standards.

| Finding | ISO 27001 | NIST 800-171 | NIST CSF | CIS Controls | COBIT | GDPR |
|---|---|---|---|---|---|---|
| F1 — Hardcoded debug credentials | A.8.5 | 3.5.2 | PR.AA-02 | Ctrl 5.2 | DSS05.04 | — |
| F2 — Weak example credentials | A.8.5, A.5.23 | 3.5.2 | PR.AA-02 | Ctrl 4.7 | DSS05.04 | Art.32 |
| F3 — ServiceNow password in config | A.8.24, A.8.10 | 3.13.10 | PR.DS-01 | Ctrl 3.11 | APO13.01 | Art.32 |
| F4 — GitHub token in env var | A.8.5 | 3.5.2 | PR.AA-02 | Ctrl 3.11 | — | — |
| F5 — OPA uses HTTP by default | A.8.20, A.8.26 | 3.13.8 | PR.DS-02 | Ctrl 3.10 | — | Art.32(1)(a) |
| F6 — Rendered configs plaintext | A.8.10, A.8.24 | 3.13.16 | PR.DS-01 | Ctrl 3.11 | DSS05.02 | Art.32(1)(a) |
| F7 — No rate limiting | A.8.20, A.8.6 | 3.1.3 | PR.IR-01 | Ctrl 13.10 | DSS05.02 | — |
| F8 — No data retention/erasure | A.8.10 | — | — | Ctrl 3.2 | APO09.04 | Art.5(1)(e), Art.17, Art.25 |
| F9 — Audit fallback to user ID 1 | A.8.15, A.8.17 | 3.3.1 | — | Ctrl 8.5 | MEA02.01 | — |
| F10 — Canary verification incomplete | A.8.8 | — | DE.CM-09 | Ctrl 16.13 | BAI06.03 | — |
| F11 — GraphQL exposes intent_data | A.8.3 | 3.1.3 | PR.DS-02 | Ctrl 3.3 | — | Art.5(1)(c) |
| F12 — No self-approval prevention | A.5.3 | 3.1.4 | PR.AA-05 | Ctrl 6.3 | DSS05.04 | — |
| F13 — Slack URL in config | A.8.5 | — | — | Ctrl 3.11 | — | Art.32 |
| F14 — Generic webhook TLS | A.8.20 | 3.13.8 | — | Ctrl 3.10 | — | — |
| F15 — Dev config not guarded | A.8.31 | 3.4.1 | — | Ctrl 4.1 | BAI03.11 | — |
| F16 — Job approval bypassed | A.8.32 | 3.4.3 | — | Ctrl 4.1 | BAI06.01 | — |
| F17 — No YAML integrity check | A.8.8 | 3.13.10 | PR.DS-06 | Ctrl 2.3 | — | — |
| F18 — Empty security intent validation | A.8.22 | 3.1.3 | — | Ctrl 12.8 | — | — |

---

## GDPR-Specific Assessment

### Personal Data Inventory

The following categories of personal data are processed by this plugin:

| Data Item | Location | Lawful Basis | Retention |
|---|---|---|---|
| Nautobot username (actor) | `IntentAuditEntry.actor` | Legitimate interest (audit/accountability) | Not defined — **GAP** |
| Nautobot username (approver) | `IntentApproval.approver`, `Intent.approved_by` | Legitimate interest (change management) | Not defined — **GAP** |
| GitHub username | `IntentAuditEntry.detail` (when source=ui) | Legitimate interest | Not defined — **GAP** |
| GitHub issue author/committer | Via `GITHUB_TOKEN` API calls | Legitimate interest | Stored at GitHub |
| Comment text in approvals | `IntentApproval.comment` | Legitimate interest | Not defined — **GAP** |

### Data Protection by Design (Article 25)

- **Data Minimisation** — The plugin stores full intent YAML (`intent_data`) rather than only the fields required for its operation. For sensitive intent types, this may result in storing more information than necessary. **(Partial gap)**
- **Purpose Limitation** — Audit records serve a legitimate change-management and accountability purpose. However, the purpose is not formally documented in a Record of Processing Activity (RoPA). **(Documentation gap)**
- **Storage Limitation** — No retention policy or automatic deletion is implemented. **(Gap — see Finding 8)**
- **Integrity and Confidentiality** — Device configs with sensitive fields are stored in plaintext JSON. **(Gap — see Finding 6)**

### Recommended GDPR Actions

1. Define and document a data retention period for `IntentAuditEntry` and `IntentApproval` records.
2. Implement an automated pseudonymisation or deletion process when records exceed the retention period.
3. Add a Record of Processing Activity (RoPA) entry for the audit and approval trail data.
4. Review the `intent_data` JSONField for any intent types that accept user-identifiable data and apply data minimisation where possible.
5. Ensure the privacy notice / Data Protection Impact Assessment (DPIA) for the Nautobot deployment covers data processed by this plugin.

---

## Remediation Priority

| Priority | Finding | Effort |
|---|---|---|
| 1 — Immediate | F1 — Hardcoded debug credentials | Low |
| 2 — Short-term | F2 — Weak example credentials | Low |
| 3 — Short-term | F5 — OPA HTTP default | Low |
| 4 — Short-term | F3 — ServiceNow password in config | Medium |
| 5 — Short-term | F4 — GitHub token in env var | Medium |
| 6 — Medium-term | F7 — No rate limiting | Medium |
| 7 — Medium-term | F6 — Rendered configs plaintext | High |
| 8 — Medium-term | F8 — Data retention (GDPR) | Medium |
| 9 — Medium-term | F12 — No self-approval prevention | Low |
| 10 — Medium-term | F16 — Job approval bypassed | Low |
| 11 — Medium-term | F11 — GraphQL exposes intent_data | Medium |
| 12 — Long-term | F10 — Canary verification incomplete | High |
| 13 — Long-term | F17 — YAML integrity check | Medium |
| 14 — Long-term | F9 — Audit fallback to user ID 1 | Low |
| 15 — Long-term | F18 — Empty security intent validation | Low |
| 16 — Long-term | F13 — Slack URL in config | Low |
| 17 — Long-term | F14 — Webhook TLS options | Low |
| 18 — Long-term | F15 — Dev config guard | Low |

---

## Remediation Status

The following findings have been remediated as of 2026-03-16:

| Finding | Status | Implementation Details |
|---|---|---|
| F1 — Hardcoded debug credentials | **REMEDIATED** | Removed `("admin", "admin")` fallback from `secrets.py`. Now raises `RuntimeError` if no credentials are configured, regardless of `DEBUG` setting. |
| F2 — Weak example credentials | **REMEDIATED** | Replaced all `changeme`/`admin`/hardcoded values in `creds.example.env` with `<REPLACE_WITH_...>` placeholders. Added prominent warning header. |
| F3 — ServiceNow password in config | **REMEDIATED** | Added `get_servicenow_credentials()` in `secrets.py` using `servicenow_secrets_group` SecretsGroup. `events.py` now imports from secrets module. Legacy config fallback retained with deprecation warning. |
| F4 — GitHub token in env var | **REMEDIATED** | Added `get_github_token()` in `secrets.py` using `github_secrets_group` SecretsGroup. `notifications.py` now imports from secrets module. Env var fallback retained with deprecation warning. |
| F5 — OPA uses HTTP by default | **REMEDIATED** | Default OPA URL changed to `https://opa:8181`. Added `opa_verify_ssl` and `opa_ca_bundle` config options for TLS certificate management. |
| F13 — Slack URL in config | **REMEDIATED** | Added `get_slack_webhook_url()` in `secrets.py` using `slack_secrets_group` SecretsGroup. Both `events.py` and `notifications.py` now use the secrets module. |

### Additional Improvements

| Improvement | Details |
|---|---|
| Intent Retirement with Config Removal | Added `IntentRetireJob` that generates and pushes removal (negation) config to all affected devices before marking an intent as Retired. Also releases allocated resources (VNI, tunnel IDs, loopbacks, wireless VLANs). Exposed via `POST /api/plugins/intent-networking/intents/{id}/retire/` endpoint. |
| Custom OPA Policy Support | Extended `opa_client.py` to query per-intent-type policies (`network.intent_types.<type>`) and user-configured custom packages via `opa_custom_packages` plugin config. Documented Rego policy authoring in module docstring. |
| Secrets Group Configuration | Documented all `*_secrets_group` config options in `nautobot_config.py` with setup instructions. |

---

## References

- ISO/IEC 27001:2022 — <https://www.iso.org/standard/82875.html>
- NIST SP 800-171 Rev 3 — <https://csrc.nist.gov/publications/detail/sp/800-171/rev-3/final>
- NIST Cybersecurity Framework 2.0 — <https://www.nist.gov/cyberframework>
- NIST SP 1800-5 (IT Asset Management) — <https://www.nccoe.nist.gov/projects/building-blocks/it-asset-management>
- COBIT 2019 — <https://www.isaca.org/resources/cobit>
- CIS Controls v8 — <https://www.cisecurity.org/controls/v8>
- GDPR — <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679>
- OWASP Top 10 2021 — <https://owasp.org/Top10/>
- Nautobot Secrets Documentation — <https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/secret/>
