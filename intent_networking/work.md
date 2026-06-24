Intent Networking Plugin — Code Review & Issue List
A review of the intent_networking Nautobot app. Issues are grouped by severity, each with location, explanation, and a concrete fix.

Severity Legend
Level	Meaning
🔴 Critical	Security risk, data corruption, or silent failure in core path
🟠 High	Functional bug or correctness issue likely to bite in production
🟡 Medium	Performance, maintainability, or robustness problem
🔵 Low	Cosmetic, placeholder, or minor inconsistency
🔴 Critical Issues
C1. Superuser privilege escalation in _enqueue_job
File: jobs.py — _enqueue_job()

Every enqueued job runs as an arbitrary superuser, regardless of who triggered it (job buttons, bulk actions, auto-remediation). A user with only view permission can cause superuser-context execution.

# Current
User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
Fix: Thread the requesting user through, or use a dedicated, least-privilege service account. Never grab an arbitrary superuser.

def _enqueue_job(job_class_name: str, *, requesting_user=None, **job_kwargs) -> None:
    from django.contrib.auth import get_user_model  # noqa: PLC0415

    try:
        job_model = JobModel.objects.get(
            module_name="intent_networking.jobs",
            job_class_name=job_class_name,
        )
    except JobModel.DoesNotExist:
        logger.error("Job '%s' not found in Nautobot registry — cannot enqueue.", job_class_name)
        return

    User = get_user_model()
    user = requesting_user
    if user is None:
        # Dedicated service account, NOT an arbitrary superuser
        user = User.objects.filter(username="intent-engine-svc").first()
    if not user:
        logger.error("No service account found — cannot enqueue '%s'.", job_class_name)
        return

    JobResult.enqueue_job(job_model, user, **job_kwargs)
Update job-button receivers and bulk views to pass requesting_user=self.user / request.user.

C2. Race condition in allocate_route_target
File: allocations.py — allocate_route_target()

The idempotency check (existing-RT lookup) happens outside the transaction.atomic() block. Two concurrent resolutions can both pass the check and create duplicate RTs for the same intent.

# Current — check is outside the transaction
existing = NautobotRouteTarget.objects.filter(description=rt_description).first()
if existing:
    return existing.name, existing.name

with transaction.atomic():
    ...
Fix: Move the existence check inside the transaction and lock it, matching the pattern in allocate_route_distinguisher().

with transaction.atomic():
    existing = (
        NautobotRouteTarget.objects.select_for_update()
        .filter(description=rt_description)
        .first()
    )
    if existing:
        logger.info("Reusing existing RT %s for %s", existing.name, intent.intent_id)
        return existing.name, existing.name

    max_rt_num = 0
    for rt in NautobotRouteTarget.objects.select_for_update().filter(name__startswith=f"{asn}:"):
        try:
            _, num_str = rt.name.rsplit(":", 1)
            max_rt_num = max(max_rt_num, int(num_str))
        except (ValueError, AttributeError):
            continue

    rt_value = f"{asn}:{max_rt_num + 1}"
    NautobotRouteTarget.objects.create(name=rt_value, description=rt_description, tenant=intent.tenant)
    return rt_value, rt_value
Note: the same "max counter + 1" strategy in both allocate_route_target and allocate_route_distinguisher is itself fragile — see M1.

C3. Controller adapters silently no-op
File: controller_adapters.py — WirelessControllerAdapter, SdWanControllerAdapter, CloudAdapter, FirewallControllerAdapter

All concrete _dispatch_push / _check_present / _dispatch_rollback methods are stubs returning {"ok": False, "reason": "no vendor implementation"}. Any intent routed through these adapters reports failure only via a warning log — wireless/SD-WAN/cloud/firewall deployments never actually deploy, and the failure is easy to miss.

Fix: Make the gap explicit. Either raise on use, or surface a clear, structured error that the deployment job treats as a hard failure.

class NotImplementedAdapterError(NotImplementedError):
    """Raised when a controller adapter has no vendor implementation."""

def _dispatch_push(self, ptype: str, prim: dict, intent_id: str) -> dict:
    raise NotImplementedAdapterError(
        f"{self.__class__.__name__} has no vendor implementation for '{ptype}'. "
        f"Subclass and override _dispatch_push before deploying intent '{intent_id}'."
    )
In jobs.py::_push_configs, treat adapter exceptions as deployment failures rather than warnings, so the intent is correctly marked Failed.

C4. check_intent_policy fails open while check_approval_gate fails closed
File: opa_client.py

check_approval_gate() correctly blocks when OPA is unreachable (fail-closed). But check_intent_policy() (used during resolution) treats an unreachable OPA as "no violations" because _query_opa() returns {} on ConnectionError. Resolution therefore proceeds with no policy enforcement when OPA is down — inconsistent and unsafe.

Fix: Add an explicit, configurable failure mode and make _query_opa distinguish "package not found" (404, safe) from "OPA unreachable" (unsafe).

class OpaUnreachableError(RuntimeError):
    """OPA could not be contacted."""

def check_intent_policy(intent, topology_context: dict) -> dict:
    fail_open = _plugin_cfg("opa_fail_open_on_resolution", False)
    ...
    try:
        # ... existing query loop ...
    except OpaUnreachableError as exc:
        if fail_open:
            logger.error("OPA unreachable during resolution — failing OPEN: %s", exc)
            return {"allowed": True, "violations": [], "warnings": [f"OPA unreachable: {exc}"]}
        logger.error("OPA unreachable during resolution — failing CLOSED: %s", exc)
        return {"allowed": False, "violations": [f"OPA unreachable: {exc}"], "warnings": []}
And in _query_opa, raise OpaUnreachableError on ConnectionError instead of returning {}.

🟠 High-Severity Issues
H1. ApprovalListView.table_class = None will crash
File: views.py — ApprovalListView

ObjectListView requires a table. Setting table_class = None (and also using the wrong attribute name — see below) raises AttributeError/ImproperlyConfigured when the view is hit.

Fix: Provide the existing IntentApprovalTable (already defined in tables.py) via the correct attribute.

from intent_networking.tables import IntentApprovalTable

class ApprovalListView(ObjectListView):
    queryset = IntentApproval.objects.all().select_related("intent", "approver")
    table = IntentApprovalTable          # ObjectListView uses `table`, not `table_class`
    action_buttons = ("export",)
Note the attribute inconsistency: ObjectListView subclasses use table, while NautobotUIViewSet subclasses use table_class. ApprovalListView mixed them.

H2. ScheduledJob created with a string interval
File: __init__.py — _ensure_reconciliation_schedule()

ScheduledJob.objects.create(
    name="Intent Reconciliation (auto)",
    task=job_model.class_path,
    interval="hours",      # ← likely invalid
    every=interval_hours,
    ...
)
Nautobot's ScheduledJob typically expects an interval choice consistent with its scheduler model (e.g. JobExecutionType/enabled, crontab, or an IntervalSchedule FK depending on version), not a free-form "hours" string plus every. As written this likely raises at startup (which the broad except Exception then hides — see M3).

Fix: Verify against your target Nautobot version and use the supported API. For recent Nautobot:

from nautobot.extras.choices import JobExecutionType

ScheduledJob.objects.create(
    name="Intent Reconciliation (auto)",
    task=job_model.class_path,
    job_model=job_model,
    interval=JobExecutionType.TYPE_HOURLY,
    user=<service_user>,
    approval_required=False,
    start_time=timezone.now(),
    kwargs={},                # JSONField in recent versions — not json.dumps(...)
    enabled=True,
)
Confirm whether kwargs is a JSONField (pass a dict) or text (keep json.dumps) for your version.

H3. Rollback runs deployment synchronously, losing audit granularity
File: jobs.py — IntentRollbackJob.run()

deploy_job = IntentDeploymentJob()
deploy_job.run(intent_id=..., commit_sha=..., commit=commit)
Calling .run() directly executes the deployment inside the rollback's Celery task. The inner deployment gets no JobResult, its self.logger may not be wired the same way, and unhandled exceptions propagate awkwardly.

Fix: Enqueue the deployment as its own job, or factor the push logic into a shared, logger-injected helper that both jobs call. Preferred:

_enqueue_job(
    "IntentDeploymentJob",
    intent_id=intent_id,
    commit_sha=f"rollback-from-v{intent.version}",
    commit=commit,
    requesting_user=getattr(self, "user", None),
)
The same pattern appears in IntentReconciliationJob (auto-remediation calls IntentDeploymentJob().run(...)) and IntentRetireJob (IntentRollbackJob()._push_removal_config(...)) — apply consistently.

H4. Deprecated-status fallback silently does nothing
File: datasources.py — _delete_repo_intents() and orphan handling in _sync_repo_intents()

deprecated_status = Status.objects.filter(name__iexact="Deprecated").first()
if deprecated_status:
    managed.update(status=deprecated_status)
# else: nothing happens, no log
If a "Deprecated" status doesn't exist, intents are neither updated nor flagged, and the operator gets no signal.

Fix: Log a warning (and ideally surface via job_result) when the status is missing.

deprecated_status = Status.objects.filter(name__iexact="Deprecated").first()
if deprecated_status:
    managed.update(status=deprecated_status)
else:
    msg = "Cannot deprecate intents — no 'Deprecated' status exists in Nautobot."
    logger.warning(msg)
    job_result.log(msg, level_choice=LogLevelChoices.LOG_WARNING, grouping="intent definitions")
H5. Bypassed status-workflow validation is undocumented at call sites
File: models.py (Intent.clean) + jobs.py (many intent.save() calls)

Intent.clean() enforces VALID_STATUS_TRANSITIONS, but jobs set intent.status and call intent.save() / save(update_fields=[...]) without full_clean(), so the workflow is enforced only for UI/API edits. Some job transitions (e.g. deploying → validated on dry-run paths, failed → deployed) may not even be in the allowed map, making the rules misleading.

Fix: Decide the contract explicitly:

If jobs are intentionally exempt, add a short module-level docstring note in jobs.py and a comment on each status-setting block, e.g. # bypasses clean(): job-driven transition.
If jobs should be validated, route them through a helper:
def _set_status(intent, status_name, *, validate=False):
    intent.status = Status.objects.get(name__iexact=status_name)
    if validate:
        intent.full_clean()
    intent.save()
Also audit VALID_STATUS_TRANSITIONS so every transition the jobs actually perform is representable.

H6. IntentReconciliationJob excludes "Retired" via a contradictory filter
File: jobs.py — IntentReconciliationJob.run()

deployed = (
    Intent.objects.filter(status__name__iexact="Deployed")
    .exclude(status__name__iexact="Retired")
    .select_related("tenant")
)
The .exclude(... "Retired") is dead code: a row whose status is exactly "Deployed" can never also be "Retired". If the intent was meant to skip intents that were once deployed but are now retired, the status field alone can't express that.

Fix: Remove the redundant exclude, or if the real intent is "reconcile deployed intents that aren't paused/retired by some other flag," filter on that flag explicitly. As written, simplify:

deployed = Intent.objects.filter(status__name__iexact="Deployed").select_related("tenant")
🟡 Medium-Severity Issues
M1. RD/RT counter allocation is O(n) and fragile
File: allocations.py — allocate_route_distinguisher(), allocate_route_target()

Both compute max(existing counters) + 1 by scanning every VRF/RT and string-splitting rd/name. This is O(n) per allocation, breaks if any RD/RT uses a different format, and can collide if a lower-numbered entry was released (reuse) or if formats are mixed across namespaces.

Fix: Use a dedicated sequence/counter model with select_for_update, or a DB sequence, rather than deriving from existing rows. Minimal version:

class RdRtCounter(BaseModel):
    namespace = models.CharField(max_length=200, unique=True)
    last_value = models.PositiveIntegerField(default=0)

# allocation:
with transaction.atomic():
    counter, _ = RdRtCounter.objects.select_for_update().get_or_create(namespace=key)
    counter.last_value += 1
    counter.save(update_fields=["last_value"])
    rd_value = f"{asn}:{counter.last_value}"
M2. N+1 / repeated conflict detection in metrics endpoint
File: metrics.py — PrometheusMetricsView.get() (conflict loop) and models.py::detect_conflicts

for intent in Intent.objects.filter(...).only("pk", "intent_data"):
    if detect_conflicts(intent):
        conflict_count += 1
detect_conflicts() issues multiple queries per intent (other intents, their plans, devices). On a Prometheus scrape interval this can hammer the DB and slow/blow the endpoint.

Fix: Pre-compute conflicts asynchronously (e.g. in the reconciliation job, store a boolean/has_conflict field or a cached count) and have the metrics view read the cached value. Alternatively, gate the conflict gauge behind a config flag and compute it in one bulk pass.

M3. Broad except Exception: pass hides startup errors
File: __init__.py — _ensure_reconciliation_schedule()

except Exception:  # noqa: BLE001, S110
    pass
Genuine misconfiguration (e.g. the ScheduledJob API mismatch in H2) is swallowed with no trace.

Fix: Keep the guard for the migration race, but log at debug/warning so operators can diagnose:

except Exception as exc:  # noqa: BLE001
    logger.debug("Skipped reconciliation schedule setup: %s", exc)
M4. resolver.py is a ~2,500-line monolith
File: resolver.py

A single module holds 100+ resolver functions plus the dispatch map. Hard to navigate, review, and test.

Fix: Split into a resolvers/ package by domain, keeping a thin dispatch module:

intent_networking/resolvers/
    __init__.py        # builds RESOLVERS by importing each domain module
    layer2.py
    layer3.py
    mpls.py
    datacenter.py
    security.py
    wan_sdwan.py
    wireless.py
    cloud.py
    qos.py
    multicast.py
    management.py
    reachability.py
    service.py
    helpers.py         # _get_scope_devices, generate_vrf_name, build_acl_entries, ...
resolve_intent() and RESOLVERS live in __init__.py. No behavioural change — pure refactor for maintainability.

M5. IntentAuditEntry immutability isn't actually enforced
File: models.py — IntentAuditEntry.Meta.default_permissions = ("add", "view")

Removing the delete/change permissions only affects Django's permission checks. Superusers and direct DB access can still mutate/delete audit rows — insufficient for SOC2/PCI immutability claims in the docstring.

Fix: Enforce at the DB layer (append-only) or override save/delete:

def save(self, *args, **kwargs):
    if self.pk and IntentAuditEntry.objects.filter(pk=self.pk).exists():
        raise ValidationError("Audit entries are immutable and cannot be modified.")
    super().save(*args, **kwargs)

def delete(self, *args, **kwargs):
    raise ValidationError("Audit entries are immutable and cannot be deleted.")
For true immutability, add a Postgres trigger/rule blocking UPDATE/DELETE, and consider write-once storage.

M6. Inconsistent Nornir inventory strategy
File: jobs.py (NautobotORMInventory) vs topology_api.py (SimpleInventory with temp files)

Two different inventory mechanisms for talking to the same devices. The temp-file approach in topology_api.py writes plaintext credentials to disk (under tempfile.mkdtemp, cleaned in finally) — a minor exposure window and an extra failure mode.

Fix: Standardise on NautobotORMInventory everywhere; if live-collection needs a single-host run, use the ORM inventory filtered to one device rather than writing credential YAML to disk.

M7. last write wins counter reuse after release_allocations
File: allocations.py — release_allocations() + the counter logic in M1

When VRFs/RTs are deleted on retire/rollback, the max + 1 scheme can re-issue a previously used counter value, which may collide with stale device config or audit references.

Fix: Resolved by the monotonic counter model in M1 (never decremented). Until then, document that RD/RT values may be reused after release.

M8. _is_ignored double-star handling is brittle
File: datasources.py — _is_ignored()

The ** handling strips leading *// and retries path.match, but PurePosixPath.match doesn't implement true ** semantics, so patterns like **/scratch/** may match inconsistently (e.g. fail to match scratch/x.yaml at the root).

Fix: Use a globbing library with real ** support (e.g. pathspec / wcmatch) or normalise patterns explicitly:

from wcmatch import glob as wcglob

def _is_ignored(rel_path, patterns):
    rel_path = rel_path.replace("\\", "/")
    return wcglob.globmatch(rel_path, patterns, flags=wcglob.GLOBSTAR | wcglob.DOTGLOB)
🔵 Low-Severity Issues
L1. app-config-schema.json is a placeholder
File: app-config-schema.json — contents are literally true.

Fix: Provide a real JSON Schema describing default_settings keys (types, required fields, enums for adapter types) so Nautobot can validate PLUGINS_CONFIG.

L2. required_settings duplicates default_settings
File: __init__.py

vrf_namespace and default_bgp_asn are listed in required_settings but also have defaults in default_settings, so startup never actually fails for a missing value (the default satisfies it). The comment "startup fails if missing" is misleading.

Fix: Remove them from default_settings if they must be explicitly set, or drop them from required_settings and fix the comment.

L3. Several config keys read but never defaulted
File: allocations.py (vni_pool_name, tunnel_id_pool_name, loopback_pool_name), controller_adapters.py, events.py, secrets.py

Many _get_plugin_config(...) keys aren't in default_settings, so they silently return None and surface only as runtime errors ("pool 'None' not found").

Fix: Add all referenced keys to default_settings (even as None) and document them, so the config surface is discoverable in one place.

L4. bgp_neighbors filter mismatch in _get_scope_devices
File: resolver.py — _get_scope_devices() excludes Maintenance via .exclude(status__name__iexact="Maintenance") after already filtering status__name__iexact="Active".

The exclude is redundant (Active rows can't be Maintenance). Harmless but dead.

Fix: Drop the redundant .exclude(...).

L5. except (ImportError, Exception) is redundant
File: models.py — is_approved, _get_workflow_requesting_user_id, _get_workflow_requesting_username

except (ImportError, Exception):  # pylint: disable=broad-exception-caught
Exception already covers ImportError; the tuple is misleading.

Fix: Use except Exception: (or, better, catch only the specific expected exceptions — ImportError for the missing model, plus whatever ORM error you actually anticipate).

L6. OSPF area = "0.0.0.0" # noqa: S104 lacks explanation
File: resolver.py — multiple OSPF resolvers

The Bandit suppression is correct (it's an OSPF area ID, not a bind address) but unexplained for future readers — though most occurrences do carry the inline comment; a couple are terser.

Fix: Ensure every suppression has the same inline rationale: # noqa: S104 — OSPF area ID, not a bind address.

L7. Mixed UI attribute naming (table vs table_class)
File: views.py

ObjectListView subclasses use table; NautobotUIViewSet subclasses use table_class. Easy to misremember (this caused H1).

Fix: Add a short comment in views.py documenting which base class expects which attribute, to prevent recurrence.

L8. _yaml alias is misleading
File: topology_api.py — import yaml as _yaml

The _ prefix usually signals "private"; here it's just a local alias.

Fix: Import as yaml (it's already a function-local import) or name it yaml_lib.

L9. Emoji in nav/menu names may not render everywhere
File: navigation.py — menu item names like "📊 Dashboard", "🌐 Topology", "🔍 Audit Trail"

Cosmetic, but emoji in nav labels can render inconsistently across browsers/terminals and complicate i18n.

Fix: Move the visual cue to the icon= parameter (MDI icons) and keep labels text-only.

L10. dispatch_event fans out synchronously inside request/job path
File: events.py — dispatch_event() calls Slack/PagerDuty/ServiceNow/webhooks with blocking requests.post(..., timeout=10/15).

Several sequential HTTP calls (up to ~50s worst case) run inline in the deploy/verify path. A slow webhook delays the job.

Fix: Dispatch events to a Celery task (fire-and-forget) so notification latency never blocks deployment/verification.

📐 Schema Adherence — schemas/intent.schema.yml
Requirement: every intent YAML file must be validated against schemas/intent.schema.yml before it is allowed to create or update an Intent record. This should be enforced in two places: (1) a CI / pre-commit gate on the network-as-code repo, and (2) at ingest time inside the plugin, so a malformed intent can never reach the resolver/deploy pipeline.

⚠️ Important caveat: the schema as written is significantly out of sync with the resolvers in resolver.py and the parsing in datasources.py. Enforcing it as-is would both reject many valid intents and fail to validate the fields the resolvers actually require. Reconcile the schema (issues S2–S9 below) before turning on hard enforcement, or the gate will block legitimate changes.

S1 — Validation is never invoked 🔴
File: datasources.py → _sync_repo_intents(); jobs.py → IntentSyncFromGitJob

The schema file exists but nothing calls pykwalify. Both the Git-native sync (_sync_repo_intents) and the legacy push job parse YAML and go straight to update_or_create with no structural validation. "Must adhere to the schema" is currently aspirational only.

Fix: validate the raw document (with its intent: wrapper, before unwrapping) at ingest, and hard-fail the file on error.

# datasources.py — per-file, before the "unwrap intent:" step
from pykwalify.core import Core  # noqa: PLC0415

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "schemas", "intent.schema.yml"
)

def _validate_against_schema(raw_doc, rel_path):
    try:
        Core(source_data=raw_doc, schema_files=[SCHEMA_PATH]).validate(raise_exception=True)
    except Exception as exc:  # pykwalify raises SchemaError
        raise ValueError(f"`{rel_path}` failed schema validation: {exc}") from exc
Call it right after yaml.safe_load(...) and surface failures into the existing stats["errors"] / job_result.log(...) path. Add the same gate to a CI step (pykwalify -d intents/<file>.yaml -s schemas/intent.schema.yml) and/or pre-commit so bad files never merge.

S2 — Schema demands the intent: wrapper, code accepts flat files 🟠
File: schema (intent: required: true) vs datasources.py

The loader unwraps a top-level intent: key only if present (if "intent" in intent_yaml ...), so flat, un-wrapped intent files are valid to the code but rejected by the schema, which makes intent mandatory.

Fix: pick one canonical shape. Recommended: keep the intent: wrapper as the standard, validate the wrapped document, and have the loader reject flat files for consistency — or make the wrapper optional in the schema with matching-rule: any plus an alternative top-level branch. Don't leave the two layers disagreeing.

S3 — Resolvers read flat top-level keys the schema doesn't define 🟠
File: schema vs many resolvers in resolver.py

pykwalify rejects undefined keys by default (the intent map has no allowempty: true). But the schema models intents as nested blocks (source, destination, routing, tunnel, wireless, cloud, qos, management), while a large number of resolvers read flat top-level keys that the schema never declares. Examples:

Resolver	Reads (top-level)	In schema?
resolve_l2_access_port / _trunk_port	ports, interface, vlan_id, allowed_vlans, native_vlan	❌ (only port singular + vlans)
resolve_static_route / reachability_*	routes, probes, backup_routes	❌
resolve_ospf / bgp_ebgp / bgp_ibgp / isis / eigrp	process_id, area, interfaces, local_asn, neighbor_ip, neighbor_asn, net, as_number, networks	❌ (nested under routing)
resolve_acl	acl_name, entries, apply_interfaces, direction, acl_type	❌
resolve_fw_rule	policy_name, rules, default_action	❌
resolve_wireless_*	ssid_name, security_mode, band, radius_servers	❌ (nested under wireless, and key is ssid, not ssid_name)
resolve_l2vni / l3vni / vtep	vlan_id, vrf_name, nve_interface	❌
Net effect: the schema simultaneously (a) fails to validate the fields resolvers actually require (so a missing routes/policy_name slips through to a runtime ValueError in the resolver), and (b) rejects otherwise-valid intents that carry these undefined top-level keys.

Fix (choose one direction and commit to it):

Preferred: rewrite the schema to match the flat structure the resolvers expect, ideally as per-type schemas (one schema fragment per type, selected after reading type), so each intent type validates exactly the keys its resolver reads. This is the only way to get meaningful required-field validation.
Interim: add allowempty: true (or matching-rule: any) to the intent map so unknown keys don't hard-fail — but understand this reduces the schema to validating only the universal fields (id, type, tenant, …) and provides no per-type guarantees.
S4 — type enum is missing valid resolver types 🟠
File: schema type.enum vs resolver.py::RESOLVERS / models.py::IntentTypeChoices

These types are dispatchable in code but absent from the schema enum, so valid intents are rejected:

reachability and service (legacy bare types — RESOLVERS handles both)
mgmt_motd, mgmt_netconf, mgmt_dhcp_server, mgmt_global_config
Fix: add the six values to the schema enum. Better, generate the enum from a single source of truth (e.g. dump RESOLVERS.keys() into the schema during a build step) so the two can never drift again.

S5 — Two conflicting verification blocks 🟡
File: schema (top-level verification vs deployment.verification)

The schema defines both a top-level verification map (level enum [basic, nuts]) and a nested deployment.verification map (level enum [basic, extended]). The code (datasources.py) reads only the top-level block, and the model's VerificationLevel is basic / nuts. So deployment.verification is dead config and its extended value doesn't exist in the model.

Fix: delete the nested deployment.verification block (keep the top-level one that the code reads), or, if nesting is intended, make datasources.py read it and align the enum to [basic, nuts]. One location, one enum.

S6 — status enum mismatch + value-format mismatch 🟡
File: schema status.enum vs models.py statuses / datasources.py

The enum omits retired, which is a real status in VALID_STATUS_TRANSITIONS.
Values use underscores (rolled_back), but the Nautobot Status names use spaces ("Rolled Back"). datasources.py resolves status via Status.objects.get(name__iexact=status_name), so rolled_back won't match "Rolled Back" — it raises DoesNotExist, which is silently swallowed, so the YAML-specified status is ignored without warning.
Fix: add retired to the enum; normalise the value→name mapping (e.g. map rolled_back → "Rolled Back" before lookup) and log when a status string can't be resolved instead of passing silently.

S7 — scope lacks group, includes unused fields 🟡
File: schema scope vs resolver.py::_get_scope_devices

_get_scope_devices filters on scope.sites and scope.group (tag service-group-{group}), but the schema's scope defines sites, devices, roles, all_tenant_devices — no group, while devices/roles/all_tenant_devices are not read by _get_scope_devices. So group-scoped intents fail validation, and the schema advertises scoping fields the resolver ignores.

Fix: add group to scope; either implement devices/roles/all_tenant_devices in _get_scope_devices or remove them from the schema so it reflects reality.

S8 — destination.prefixes pattern is IPv4-only and unbounded 🔵
File: schema destination.prefixes

Pattern ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$ rejects IPv6 (the code supports v6 via ipv6_dual_stack, bgp_ipv6_af, nat64 64:ff9b::/96, srv6) and doesn't bound octets/mask (accepts 999.999.999.999/99).

Fix: accept both families (separate v4/v6 alternation) and tighten octet/mask ranges, or validate CIDR semantics in code (ipaddress.ip_network) and keep the regex loose.

S9 — Schema mandates fields the model treats as optional 🔵
File: schema (change_ticket required + pattern, description required 10–500) vs models.py

change_ticket is blank=True in the model and defaulted to "" in the loader; there's no top-level description field at all. The schema makes both mandatory. This may be deliberate governance (enforce at PR time), but the two layers currently disagree on what's required.

Fix: decide the source of truth. If governance requires them, keep the schema strict and document that the model intentionally stores them loosely; if not, relax the schema to required: false.

Suggested Fix Ordering
C1, C2, C3, C4 — security and silent-failure issues first.
H1, H2, H4, H6 — quick functional bugs / crashes.
S2–S9 — reconcile the schema with the resolvers/model before enforcing it, so the gate doesn't reject valid intents.
S1 — once the schema is accurate, wire validation into ingest (datasources.py) and CI/pre-commit so every intent must adhere to it.
H3, H5, M2, M6 — correctness and performance in the job pipeline.
M1, M4, M5 — structural/maintainability investments.
Remaining M and L items as cleanup.
Order matters here: turning on S1 (enforcement) before fixing S2–S9 would block legitimate intents. Fix the schema first, then enforce.