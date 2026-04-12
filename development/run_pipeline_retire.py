"""Full pipeline test for Feature/improved-EOS lab intents.

Runs every intent through all 7 steps:
  1. Seed    — create/update the 16 lab intents in Nautobot (Draft)
  2. Resolve — build the resolution plan
  3. Preview — render Jinja2 configs (dry output, no device contact)
  4. Dry-run — push to devices WITHOUT committing (commit=False)
  5. Approve — create IntentApproval record
  6. Deploy  — push to cEOS devices and commit (commit=True)
  7. Retire  — push removal config to devices and mark Retired

Step 5 (Approve) is required before step 6 will push config.
Steps 6 and 7 require live SSH access to the cEOS Containerlab devices.

Usage (inside nautobot shell / nbshell):
    exec(open("development/run_pipeline_retire.py").read())
"""

import json
import time

from django.contrib.auth import get_user_model
from nautobot.extras.models import Job, JobResult

from intent_networking.models import Intent, IntentApproval

# ─── Seed first ───────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  STEP 0: Seeding lab intents")
print("=" * 60)
exec(open("development/seed_lab_intents.py").read())  # noqa: S102

# ─── Auth ─────────────────────────────────────────────────────────────────────
User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
if not user:
    print("ERROR: No superuser found — run seed_data.py first")
    raise SystemExit(1)

# ─── Job handles ──────────────────────────────────────────────────────────────
MODULE = "intent_networking.jobs"


def _get_job(class_name):
    return Job.objects.get(module_name=MODULE, job_class_name=class_name)


JOBS = {
    "resolve": _get_job("IntentResolutionJob"),
    "preview": _get_job("IntentConfigPreviewJob"),
    "deploy": _get_job("IntentDeploymentJob"),
    "verify": _get_job("IntentVerificationJob"),
    "retire": _get_job("IntentRetireJob"),
}

# ─── Helpers ──────────────────────────────────────────────────────────────────
LAB_INTENT_IDS = [
    "lab-acl-security-001",
    "lab-zbf-001",
    "lab-aaa-001",
    "lab-copp-001",
    "lab-ra-guard-001",
    "lab-route-redist-001",
    "lab-ospfv3-001",
    "lab-eigrp-001",
    "lab-sr-mpls-001",
    "lab-pvlan-001",
    "lab-stp-root-001",
    "lab-qos-police-001",
    "lab-qos-queue-001",
    "lab-qos-shape-001",
    "lab-qos-trust-001",
    "lab-msdp-001",
]

intents = list(Intent.objects.filter(intent_id__in=LAB_INTENT_IDS).order_by("intent_id"))
print(f"\nFound {len(intents)} lab intents to process\n")

RESULTS = {
    step: {"ok": [], "fail": []} for step in ["resolve", "preview", "dryrun", "approve", "deploy", "verify", "retire"]
}
ERRORS = []


def run_job(job, data, timeout=180):
    """Enqueue a Nautobot job and block until it finishes. Returns (ok, result)."""
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
    msgs = list(jr.job_log_entries.filter(log_level__in=["error", "critical"]).values_list("message", flat=True)[:5])
    return False, "; ".join(msgs) if msgs else f"Job status: {jr.status}"


def note_error(iid, step, msg):
    """Record a step failure in ERRORS and print it."""
    ERRORS.append({"intent_id": iid, "step": step, "message": str(msg)[:400]})
    print(f"    ✗ [{step}] {str(msg)[:200]}")


# ─── Main loop ────────────────────────────────────────────────────────────────
for idx, intent in enumerate(intents, 1):
    iid = intent.intent_id
    itype = intent.intent_type
    print(f"\n{'=' * 60}")
    print(f"[{idx}/{len(intents)}] {iid}  (type={itype})")
    print("=" * 60)

    # ── 1. Resolve ────────────────────────────────────────────────────────────
    print("  1. Resolution...")
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

    # ── 2. Config preview ─────────────────────────────────────────────────────
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

    # ── 3. Dry-run deploy (no commit) ─────────────────────────────────────────
    print("  3. Dry-run Deploy (commit=False)...")
    ok, result = run_job(JOBS["deploy"], {"intent_id": iid, "commit_sha": "lab-improved-eos", "commit": False})
    if ok:
        RESULTS["dryrun"]["ok"].append(iid)
        print("    ✓ Dry-run OK")
    else:
        RESULTS["dryrun"]["fail"].append(iid)
        note_error(iid, "dryrun", result)

    # ── 4. Approve ────────────────────────────────────────────────────────────
    print("  4. Approve...")
    try:
        approval, created = IntentApproval.objects.get_or_create(
            intent=intent,
            defaults={
                "approver": user,
                "decision": "approved",
                "comment": "Auto-approved by run_pipeline_retire.py — Feature/improved-EOS lab test",
            },
        )
        if not created and approval.decision != "approved":
            approval.decision = "approved"
            approval.comment = "Auto-approved — Feature/improved-EOS lab test"
            approval.save()
        RESULTS["approve"]["ok"].append(iid)
        intent.refresh_from_db()
        print(f"    ✓ Approved  (is_approved={intent.is_approved})")
    except Exception as exc:
        RESULTS["approve"]["fail"].append(iid)
        note_error(iid, "approve", exc)

    # ── 5. Deploy (commit=True) ───────────────────────────────────────────────
    print("  5. Deploy (commit=True)...")
    ok, result = run_job(
        JOBS["deploy"], {"intent_id": iid, "commit_sha": "lab-improved-eos", "commit": True}, timeout=240
    )
    intent.refresh_from_db()
    if ok:
        RESULTS["deploy"]["ok"].append(iid)
        print(f"    ✓ Deployed  (status={intent.status})")
    else:
        RESULTS["deploy"]["fail"].append(iid)
        note_error(iid, "deploy", result)
        print(f"    Status after failed deploy: {intent.status}")
        # Continue to retire even if deploy failed — clean up any partial config
        print("    Continuing to retire step to clean up partial config...")

    # ── 6. Verify ─────────────────────────────────────────────────────────────
    print("  6. Verify...")
    ok, result = run_job(JOBS["verify"], {"intent_id": iid})
    if ok:
        RESULTS["verify"]["ok"].append(iid)
        print("    ✓ Verified")
    else:
        RESULTS["verify"]["fail"].append(iid)
        note_error(iid, "verify", result)
        print("    Verification failed — proceeding to retire anyway")

    # ── 7. Retire (removes config + marks Retired) ────────────────────────────
    print("  7. Retire (commit=True)...")
    ok, result = run_job(JOBS["retire"], {"intent_id": iid, "commit": True}, timeout=240)
    intent.refresh_from_db()
    if ok:
        RESULTS["retire"]["ok"].append(iid)
        print(f"    ✓ Retired   (status={intent.status})")
    else:
        RESULTS["retire"]["fail"].append(iid)
        note_error(iid, "retire", result)
        print(f"    Status after retire: {intent.status}")

# ─── Summary ──────────────────────────────────────────────────────────────────
print(f"\n\n{'=' * 60}")
print("  PIPELINE SUMMARY — Feature/improved-EOS Lab Test")
print(f"{'=' * 60}")
print(f"  {'Step':<10}  {'OK':>4}  {'FAIL':>4}")
print(f"  {'-'*10}  {'-'*4}  {'-'*4}")
for step in ["resolve", "preview", "dryrun", "approve", "deploy", "verify", "retire"]:
    ok_n = len(RESULTS[step]["ok"])
    fail_n = len(RESULTS[step]["fail"])
    flag = "  " if fail_n == 0 else "⚠ "
    print(f"  {flag}{step:<10}  {ok_n:>4}  {fail_n:>4}")

total_errors = len(ERRORS)
print(f"\n  Total errors: {total_errors}")

if ERRORS:
    print(f"\n{'─' * 60}")
    print("  ERRORS:")
    for e in ERRORS:
        print(f"  [{e['step']:>8}] {e['intent_id']}")
        print(f"             {e['message']}")

# JSON output for scripted parsing
output = {
    "results": {k: {"ok": v["ok"], "fail": v["fail"]} for k, v in RESULTS.items()},
    "errors": ERRORS,
}
print(f"\n{'─' * 60}")
print("__JSON_START__")
print(json.dumps(output, indent=2))
print("__JSON_END__")
