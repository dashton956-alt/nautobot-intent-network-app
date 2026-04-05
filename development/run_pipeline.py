"""Run all intents through the full pipeline: Resolve → Preview → Dry-Run → Approve → Deploy."""

import json
import time

from django.contrib.auth import get_user_model
from nautobot.extras.models import Job, JobResult

from intent_networking.models import Intent, IntentApproval

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
if not user:
    print("ERROR: No superuser found")
    exit(1)

# Job lookup
JOBS = {}
for jcn in [
    "IntentResolutionJob",
    "IntentConfigPreviewJob",
    "IntentDeploymentJob",
    "IntentVerificationJob",
]:
    JOBS[jcn] = Job.objects.get(module_name="intent_networking.jobs", job_class_name=jcn)

intents = list(Intent.objects.all().order_by("intent_id"))
print(f"Processing {len(intents)} intents through pipeline\n")

# Results tracking
results = {
    "resolution": {"success": [], "failed": []},
    "preview": {"success": [], "failed": []},
    "dryrun": {"success": [], "failed": []},
    "approval": {"success": [], "failed": []},
    "deploy": {"success": [], "failed": []},
}
errors = []  # list of (intent_id, step, error_message)


def run_job_sync(job, data_dict, timeout=120):
    """Enqueue a job and wait for it to finish. Return (success, job_result)."""
    jr = JobResult.enqueue_job(job, user, **data_dict)
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
    else:
        # Get log entries for error details
        log_entries = jr.job_log_entries.filter(log_level__in=["error", "critical", "warning"]).values_list(
            "message", flat=True
        )
        error_msg = "; ".join(log_entries[:5]) if log_entries else f"Job status: {jr.status}"
        return False, error_msg


def log_error(intent_id, step, message):
    """Record an error."""
    errors.append((intent_id, step, str(message)[:500]))
    print(f"  ERROR [{step}]: {str(message)[:200]}")


# ─── Process each intent ──────────────────────────────────────────────────────
for idx, intent in enumerate(intents, 1):
    iid = intent.intent_id
    print(f"\n{'='*60}")
    print(f"[{idx}/{len(intents)}] {iid} (type={intent.intent_type})")
    print(f"{'='*60}")

    # ── Step 1: Resolution ──
    print("  Step 1: Resolution...")
    try:
        ok, result = run_job_sync(JOBS["IntentResolutionJob"], {"intent_id": iid})
        if ok:
            results["resolution"]["success"].append(iid)
            print("  Resolution: OK")
        else:
            results["resolution"]["failed"].append(iid)
            log_error(iid, "resolution", result)
            # If resolution fails, skip the rest for this intent
            continue
    except Exception as e:
        results["resolution"]["failed"].append(iid)
        log_error(iid, "resolution", f"{type(e).__name__}: {e}")
        continue

    # Refresh intent status
    intent.refresh_from_db()
    print(f"  Status after resolution: {intent.status.name}")

    # ── Step 2: Config Preview ──
    print("  Step 2: Config Preview...")
    try:
        ok, result = run_job_sync(JOBS["IntentConfigPreviewJob"], {"intent_id": iid})
        if ok:
            results["preview"]["success"].append(iid)
            intent.refresh_from_db()
            cfg_devices = list(intent.rendered_configs.keys()) if intent.rendered_configs else []
            print(f"  Preview: OK (configs for: {cfg_devices})")
        else:
            results["preview"]["failed"].append(iid)
            log_error(iid, "preview", result)
    except Exception as e:
        results["preview"]["failed"].append(iid)
        log_error(iid, "preview", f"{type(e).__name__}: {e}")

    # ── Step 3: Dry-Run Deploy ──
    print("  Step 3: Dry-Run Deploy...")
    try:
        ok, result = run_job_sync(
            JOBS["IntentDeploymentJob"],
            {"intent_id": iid, "commit_sha": "pipeline-test", "commit": False},
        )
        if ok:
            results["dryrun"]["success"].append(iid)
            print("  Dry-Run: OK")
        else:
            results["dryrun"]["failed"].append(iid)
            log_error(iid, "dryrun", result)
    except Exception as e:
        results["dryrun"]["failed"].append(iid)
        log_error(iid, "dryrun", f"{type(e).__name__}: {e}")

    # ── Step 4: Approve ──
    print("  Step 4: Approval...")
    try:
        approval, created = IntentApproval.objects.get_or_create(
            intent=intent,
            defaults={
                "approver": user,
                "decision": "approved",
                "comment": "Pipeline auto-approval for testing",
            },
        )
        if not created and approval.decision != "approved":
            approval.decision = "approved"
            approval.comment = "Pipeline auto-approval for testing"
            approval.save()
        results["approval"]["success"].append(iid)
        print(f"  Approval: OK (is_approved={intent.is_approved})")
    except Exception as e:
        results["approval"]["failed"].append(iid)
        log_error(iid, "approval", f"{type(e).__name__}: {e}")

    # ── Step 5: Deploy (commit=True) ──
    print("  Step 5: Deploy...")
    try:
        ok, result = run_job_sync(
            JOBS["IntentDeploymentJob"],
            {"intent_id": iid, "commit_sha": "pipeline-test", "commit": True},
            timeout=180,
        )
        intent.refresh_from_db()
        if ok:
            results["deploy"]["success"].append(iid)
            print(f"  Deploy: OK (status={intent.status.name})")
        else:
            results["deploy"]["failed"].append(iid)
            log_error(iid, "deploy", result)
            print(f"  Deploy: FAILED (status={intent.status.name})")
    except Exception as e:
        results["deploy"]["failed"].append(iid)
        log_error(iid, "deploy", f"{type(e).__name__}: {e}")

# ─── Final Summary ────────────────────────────────────────────────────────────
print(f"\n\n{'='*60}")
print("PIPELINE SUMMARY")
print(f"{'='*60}")
for step in ["resolution", "preview", "dryrun", "approval", "deploy"]:
    s = len(results[step]["success"])
    f = len(results[step]["failed"])
    print(f"  {step:12s}: {s} success, {f} failed")

print(f"\n  Total errors: {len(errors)}")

# Output JSON for parsing
output = {
    "results": {k: {"success": v["success"], "failed": v["failed"]} for k, v in results.items()},
    "errors": [{"intent_id": e[0], "step": e[1], "message": e[2]} for e in errors],
}
print("\n__JSON_START__")
print(json.dumps(output, indent=2))
print("__JSON_END__")
