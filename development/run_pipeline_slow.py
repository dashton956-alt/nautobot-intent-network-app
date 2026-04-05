"""Re-run rolled-back intents through the pipeline with delays to avoid SSH exhaustion."""

import json
import time

from django.contrib.auth import get_user_model
from nautobot.extras.models import Job, JobResult, Status

from intent_networking.models import Intent, IntentApproval

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()

JOBS = {}
for jcn in ["IntentResolutionJob", "IntentConfigPreviewJob", "IntentDeploymentJob"]:
    JOBS[jcn] = Job.objects.get(module_name="intent_networking.jobs", job_class_name=jcn)

draft = Status.objects.get(name="Draft")
intents = list(Intent.objects.filter(status=draft).order_by("intent_id"))
print(f"Re-processing {len(intents)} Draft intents with 10s delay between deploys\n")

errors = []
results = {"deployed": [], "failed": [], "rolled_back": [], "other": []}

DEPLOY_DELAY = 10  # seconds between each deploy


def run_job_sync(job, data_dict, timeout=180):
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
    log_entries = jr.job_log_entries.filter(
        log_level__in=["error", "critical", "warning"]
    ).values_list("message", flat=True)
    return False, "; ".join(log_entries[:5]) if log_entries else f"Job status: {jr.status}"


for idx, intent in enumerate(intents, 1):
    iid = intent.intent_id
    print(f"[{idx}/{len(intents)}] {iid}")

    # Step 1: Resolve
    ok, r = run_job_sync(JOBS["IntentResolutionJob"], {"intent_id": iid})
    if not ok:
        errors.append((iid, "resolution", str(r)[:300]))
        print(f"  Resolution FAILED: {str(r)[:100]}")
        results["failed"].append(iid)
        continue
    print(f"  Resolved OK")

    # Step 2: Preview
    ok, r = run_job_sync(JOBS["IntentConfigPreviewJob"], {"intent_id": iid})
    if not ok:
        errors.append((iid, "preview", str(r)[:300]))
        print(f"  Preview FAILED: {str(r)[:100]}")
    else:
        print(f"  Preview OK")

    # Step 3: Approve (ensure approval exists)
    IntentApproval.objects.get_or_create(
        intent=intent,
        defaults={"approver": user, "decision": "approved", "comment": "Re-test approval"},
    )

    # Step 4: Deploy with commit=True
    print(f"  Deploying (waiting {DEPLOY_DELAY}s before SSH)...")
    time.sleep(DEPLOY_DELAY)

    ok, r = run_job_sync(
        JOBS["IntentDeploymentJob"],
        {"intent_id": iid, "commit_sha": "pipeline-retest", "commit": True},
        timeout=180,
    )

    # Wait for any auto-triggered verification/rollback to finish
    time.sleep(5)
    intent.refresh_from_db()
    final_status = intent.status.name
    print(f"  Deploy result: job_ok={ok}, final_status={final_status}")

    if final_status == "Deployed":
        results["deployed"].append(iid)
    elif final_status == "Rolled Back":
        results["rolled_back"].append(iid)
        log_entries = []
        if not ok:
            log_entries.append(str(r)[:300])
        errors.append((iid, "deploy", "; ".join(log_entries) if log_entries else f"Rolled back (status={final_status})"))
    elif final_status == "Failed":
        results["failed"].append(iid)
        errors.append((iid, "deploy", str(r)[:300] if not ok else "Failed"))
    else:
        results["other"].append(iid)
        if not ok:
            errors.append((iid, "deploy", str(r)[:300]))

    print()

print("=" * 60)
print("RETEST SUMMARY")
print("=" * 60)
print(f"  Deployed:    {len(results['deployed'])}")
print(f"  Rolled Back: {len(results['rolled_back'])}")
print(f"  Failed:      {len(results['failed'])}")
print(f"  Other:       {len(results['other'])}")
print(f"  Errors:      {len(errors)}")
print()

for cat, ids in results.items():
    if ids:
        print(f"\n  {cat}:")
        for i in ids:
            print(f"    - {i}")

if errors:
    print(f"\n  ERRORS:")
    for iid, step, msg in errors:
        print(f"    [{step}] {iid}: {msg[:200]}")

print("\n__JSON_START__")
print(json.dumps({"results": results, "errors": [{"id": e[0], "step": e[1], "msg": e[2]} for e in errors]}, indent=2))
print("__JSON_END__")
