"""Full reset pipeline: retire all deployed intents then re-run the complete pipeline.

Steps for each deployed intent:
  0. Retire  — push removal config to devices, mark Retired

Then for ALL intents (in dependency order):
  1. Resolve — build the resolution plan
  2. Preview — render Jinja2 configs
  3. Dry-run — push to devices WITHOUT committing
  4. Approve — create / update IntentApproval record
  5. Deploy  — push to cEOS devices and commit
  6. Verify  — run outcome verification

Usage (inside nautobot shell):
    exec(open("development/run_pipeline_full_reset.py").read())
"""

import json
import time

from django.contrib.auth import get_user_model
from nautobot.extras.models import Job, JobResult

from intent_networking.models import Intent, IntentApproval

# ─── Auth ─────────────────────────────────────────────────────────────────────
User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
if not user:
    print("ERROR: No superuser found — run seed_data.py first")
    raise SystemExit(1)

# ─── Job handles (looked up dynamically — no hardcoded UUIDs) ─────────────────
MODULE = "intent_networking.jobs"


def _get_job(class_name):
    return Job.objects.get(module_name=MODULE, job_class_name=class_name)


JOBS = {
    "resolve": _get_job("IntentResolutionJob"),
    "preview": _get_job("IntentConfigPreviewJob"),
    "deploy":  _get_job("IntentDeploymentJob"),
    "verify":  _get_job("IntentVerificationJob"),
    "retire":  _get_job("IntentRetireJob"),
}

# ─── Dependency-aware intent order ───────────────────────────────────────────
ORDERED_INTENT_IDS = [
    # EVPN fabric first — everything else depends on it
    "lab-dc-evpn-fabric-001",
    "lab-bgp-underlay-001",
    # L2 / L3 VNI and anycast (depend on fabric)
    "lab-dc-l2vni-prod-001",
    "lab-dc-l3vni-tenant-001",
    "lab-anycast-gw-001",
    # MLAG
    "lab-mlag-pair-001",
    # VLANs
    "lab-vlans-dc1-001",
    # L2 access + trunk ports
    "lab-l2-trunk-uplink-001",
    "lab-l2-trunk-uplink-002",
    "lab-l2-access-mgmt-001",
    "lab-l2-access-prod-001",
    "lab-l2-access-dev-001",
    "lab-l2-access-storage-001",
    # STP
    "lab-stp-policy-001",
    "lab-stp-root-001",
    # Management
    "lab-mgmt-global-config-001",
    "lab-mgmt-motd-001",
    "lab-mgmt-ntp-001",
    "lab-mgmt-snmp-001",
    "lab-mgmt-lldp-001",
    "lab-mgmt-ssh-001",
    "lab-mgmt-netconf-001",
    "lab-mgmt-syslog-001",
    "lab-mgmt-netflow-001",
    "lab-mgmt-telemetry-001",
    "lab-mgmt-dhcp-server-001",
    "lab-mgmt-dns-001",
    # Security / ACLs
    "lab-acl-server-segment-001",
    "lab-acl-security-001",
    "lab-fw-rule-001",
    "lab-port-security-001",
    "lab-dhcp-snooping-001",
    "lab-storm-control-001",
    "lab-macsec-uplinks-001",
    "lab-zbf-001",
    "lab-aaa-001",
    "lab-copp-001",
    "lab-ra-guard-001",
    # QoS
    "lab-qos-classify-001",
    "lab-qos-trust-001",
    "lab-qos-police-001",
    "lab-qos-queue-001",
    "lab-qos-shape-001",
    # Routing
    "lab-route-redist-001",
    "lab-ospfv3-001",
    "lab-eigrp-001",
    "lab-sr-mpls-001",
    # L2 advanced
    "lab-pvlan-001",
    # Multicast
    "lab-msdp-001",
]

# ─── Helpers ──────────────────────────────────────────────────────────────────
RESULTS = {
    step: {"ok": [], "fail": []}
    for step in ["retire", "resolve", "preview", "dryrun", "approve", "deploy", "verify"]
}
ERRORS = []


def run_job(job, data, timeout=240):
    """Enqueue a job and block until it finishes. Returns (ok, job_result_or_msg)."""
    jr = JobResult.enqueue_job(job, user, **data)
    elapsed = 0
    while elapsed < timeout:
        jr.refresh_from_db()
        if jr.status in ("SUCCESS", "FAILURE", "ERROR"):
            break
        time.sleep(2)
        elapsed += 2
    if elapsed >= timeout:
        return False, f"Timeout after {timeout}s (status={jr.status})"
    if jr.status == "SUCCESS":
        return True, jr
    msgs = list(
        jr.job_log_entries.filter(log_level__in=["error", "critical"]).values_list("message", flat=True)[:5]
    )
    return False, "; ".join(msgs) if msgs else f"Job status: {jr.status}"


def note_error(iid, step, msg):
    ERRORS.append({"intent_id": iid, "step": step, "message": str(msg)[:400]})
    print(f"    ✗ [{step}] {str(msg)[:250]}")


# ─── Phase 0: Retire all currently Deployed or Rolled Back intents ────────────
deployed_intents = list(
    Intent.objects.filter(status__name__in=["Deployed", "Rolled Back"]).order_by("intent_id")
)
print(f"\n{'=' * 60}")
print(f"  PHASE 0: Retiring {len(deployed_intents)} deployed/rolled-back intents")
print(f"{'=' * 60}")

for intent in deployed_intents:
    iid = intent.intent_id
    print(f"\n  Retiring {iid} (was {intent.status}) ...")
    ok, result = run_job(JOBS["retire"], {"intent_id": iid, "commit": True}, timeout=240)
    intent.refresh_from_db()
    if ok:
        RESULTS["retire"]["ok"].append(iid)
        print(f"    ✓ Retired  (status={intent.status})")
    else:
        RESULTS["retire"]["fail"].append(iid)
        note_error(iid, "retire", result)
        print(f"    Status after failed retire: {intent.status}")
    time.sleep(5)  # brief pause between device SSH sessions

print(f"\n  Retire complete — OK: {len(RESULTS['retire']['ok'])}  FAIL: {len(RESULTS['retire']['fail'])}")

# ─── Phase 1–6: Full pipeline for all intents in dependency order ─────────────

# Build ordered list — any intents in DB but not in ORDERED_INTENT_IDS go to the end
db_ids = set(Intent.objects.values_list("intent_id", flat=True))
ordered = [iid for iid in ORDERED_INTENT_IDS if iid in db_ids]
ordered += sorted(db_ids - set(ORDERED_INTENT_IDS))  # add any unlisted intents alphabetically

print(f"\n{'=' * 60}")
print(f"  PHASE 1-6: Full pipeline for {len(ordered)} intents")
print(f"{'=' * 60}")

for idx, iid in enumerate(ordered, 1):
    try:
        intent = Intent.objects.get(intent_id=iid)
    except Intent.DoesNotExist:
        print(f"\n[{idx}/{len(ordered)}] {iid} — not found in DB, skipping")
        continue

    print(f"\n{'=' * 60}")
    print(f"[{idx}/{len(ordered)}] {iid}  (type={intent.intent_type}  status={intent.status})")
    print("=" * 60)

    # ── 1. Resolve ────────────────────────────────────────────────────────────
    print("  1. Resolve...")
    ok, result = run_job(JOBS["resolve"], {"intent_id": iid, "force_re_resolve": True})
    if ok:
        RESULTS["resolve"]["ok"].append(iid)
        intent.refresh_from_db()
        print(f"    ✓ Resolved  (status={intent.status})")
    else:
        RESULTS["resolve"]["fail"].append(iid)
        note_error(iid, "resolve", result)
        print("    Skipping remaining steps for this intent.")
        continue

    # ── 2. Config Preview ─────────────────────────────────────────────────────
    print("  2. Config Preview...")
    ok, result = run_job(JOBS["preview"], {"intent_id": iid})
    if ok:
        RESULTS["preview"]["ok"].append(iid)
        intent.refresh_from_db()
        devices = list(intent.rendered_configs.keys()) if intent.rendered_configs else []
        print(f"    ✓ Previewed (devices: {devices})")
    else:
        RESULTS["preview"]["fail"].append(iid)
        note_error(iid, "preview", result)

    # ── 3. Dry-run ────────────────────────────────────────────────────────────
    print("  3. Dry-run...")
    ok, result = run_job(JOBS["deploy"], {"intent_id": iid, "commit_sha": "full-reset", "commit": False})
    if ok:
        RESULTS["dryrun"]["ok"].append(iid)
        print("    ✓ Dry-run OK")
    else:
        RESULTS["dryrun"]["fail"].append(iid)
        note_error(iid, "dryrun", result)

    # ── 4. Approve ────────────────────────────────────────────────────────────
    print("  4. Approve...")
    try:
        # Delete any stale approvals from previous pipeline runs to avoid
        # get_or_create raising MultipleObjectsReturned on duplicate records.
        IntentApproval.objects.filter(intent=intent).delete()
        IntentApproval.objects.create(
            intent=intent,
            approver=user,
            decision="approved",
            comment="Auto-approved by run_pipeline_full_reset.py",
        )
        RESULTS["approve"]["ok"].append(iid)
        intent.refresh_from_db()
        print(f"    ✓ Approved  (is_approved={intent.is_approved})")
    except Exception as exc:
        RESULTS["approve"]["fail"].append(iid)
        note_error(iid, "approve", exc)

    # ── 5. Deploy (commit=True) ───────────────────────────────────────────────
    print("  5. Deploy (commit=True)...")
    ok, result = run_job(
        JOBS["deploy"], {"intent_id": iid, "commit_sha": "full-reset", "commit": True}, timeout=300
    )
    intent.refresh_from_db()
    if ok:
        RESULTS["deploy"]["ok"].append(iid)
        print(f"    ✓ Deployed  (status={intent.status})")
    else:
        RESULTS["deploy"]["fail"].append(iid)
        note_error(iid, "deploy", result)
        print(f"    Status after failed deploy: {intent.status}")

    # ── 6. Verify ─────────────────────────────────────────────────────────────
    print("  6. Verify...")
    ok, result = run_job(JOBS["verify"], {"intent_id": iid}, timeout=180)
    if ok:
        RESULTS["verify"]["ok"].append(iid)
        print("    ✓ Verified")
    else:
        RESULTS["verify"]["fail"].append(iid)
        note_error(iid, "verify", result)

    time.sleep(8)  # pause between intents to avoid SSH exhaustion


# ─── Final summary ─────────────────────────────────────────────────────────────
print(f"\n\n{'=' * 60}")
print("  PIPELINE SUMMARY — Full Reset")
print(f"{'=' * 60}")
print(f"  {'Step':<10}  {'OK':>4}  {'FAIL':>4}")
print(f"  {'-'*10}  {'-'*4}  {'-'*4}")
for step in ["retire", "resolve", "preview", "dryrun", "approve", "deploy", "verify"]:
    ok_n = len(RESULTS[step]["ok"])
    fail_n = len(RESULTS[step]["fail"])
    flag = "  " if fail_n == 0 else "! "
    print(f"  {flag}{step:<10}  {ok_n:>4}  {fail_n:>4}")

print(f"\n  Total errors logged: {len(ERRORS)}")

if ERRORS:
    print(f"\n{'─' * 60}")
    print("  ERRORS:")
    for e in ERRORS:
        print(f"  [{e['step']:>8}] {e['intent_id']}")
        print(f"             {e['message']}")

print(f"\n{'─' * 60}")
print("__JSON_START__")
print(json.dumps({"results": {k: v for k, v in RESULTS.items()}, "errors": ERRORS}, indent=2))
print("__JSON_END__")
