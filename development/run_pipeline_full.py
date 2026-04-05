"""Run all 27 intents through the full pipeline: resolve → preview → deploy (dry-run) → approve → deploy.

Uses the Intent Resolution / Config Preview / Deployment jobs with correct parameter names.
Deploys one at a time with 15s gaps to avoid SSH exhaustion on cEOS devices.
"""

import time

import requests
from django.contrib.auth import get_user_model

from intent_networking.models import Intent, IntentApproval

API = "http://localhost:8080/api"
HDR = {
    "Authorization": "Token 0123456789abcdef0123456789abcdef01234567",
    "Content-Type": "application/json",
}

# Job IDs
RESOLVE_JOB = "492d6643-3a3a-4e43-b5b0-251bc3159a05"
PREVIEW_JOB = "bc5cabcf-8d7b-489f-88f4-f38fef24f50a"
DEPLOY_JOB = "4b639452-b25d-4090-86ec-9e5c967a6d56"

User = get_user_model()
admin = User.objects.filter(is_superuser=True).first()

all_intents = list(Intent.objects.all().order_by("intent_id"))
print(f"Found {len(all_intents)} intents to process\n")

# Phase 1: Resolve all
print("=" * 60)
print("  PHASE 1: Resolution")
print("=" * 60)
for intent in all_intents:
    r = requests.post(
        f"{API}/extras/jobs/{RESOLVE_JOB}/run/",
        headers=HDR,
        json={"data": {"intent_id": intent.intent_id, "force_re_resolve": True}},
    )
    print(f"  Resolve {intent.intent_id}: {r.status_code}")
    time.sleep(3)

print("\nWaiting 20s for resolution jobs to complete...")
time.sleep(20)

for intent in all_intents:
    intent.refresh_from_db()
    print(f"  {intent.intent_id}: {intent.status}")

# Phase 2: Preview all
print("\n" + "=" * 60)
print("  PHASE 2: Config Preview")
print("=" * 60)
for intent in all_intents:
    r = requests.post(
        f"{API}/extras/jobs/{PREVIEW_JOB}/run/",
        headers=HDR,
        json={"data": {"intent_id": intent.intent_id}},
    )
    print(f"  Preview {intent.intent_id}: {r.status_code}")
    time.sleep(2)

print("\nWaiting 20s for preview jobs to complete...")
time.sleep(20)

# Phase 3: Dry-run all
print("\n" + "=" * 60)
print("  PHASE 3: Dry-Run Deploy")
print("=" * 60)
for intent in all_intents:
    r = requests.post(
        f"{API}/extras/jobs/{DEPLOY_JOB}/run/",
        headers=HDR,
        json={"data": {"intent_id": intent.intent_id, "commit_sha": "pipeline-test", "commit": False}},
    )
    print(f"  Dry-run {intent.intent_id}: {r.status_code}")
    time.sleep(2)

print("\nWaiting 20s for dry-run jobs to complete...")
time.sleep(20)

# Phase 4: Approve all
print("\n" + "=" * 60)
print("  PHASE 4: Approval")
print("=" * 60)
for intent in all_intents:
    IntentApproval.objects.update_or_create(
        intent=intent,
        defaults={
            "approved_by": admin,
            "decision": "Approved",
            "comments": "Auto-approved for pipeline test",
        },
    )
    print(f"  Approved {intent.intent_id}")

time.sleep(5)

# Phase 5: Deploy one at a time with 15s gaps
print("\n" + "=" * 60)
print("  PHASE 5: Deploy (real)")
print("=" * 60)
for intent in all_intents:
    intent.refresh_from_db()
    print(f"\n  Deploying {intent.intent_id} (status={intent.status})...")
    r = requests.post(
        f"{API}/extras/jobs/{DEPLOY_JOB}/run/",
        headers=HDR,
        json={"data": {"intent_id": intent.intent_id, "commit_sha": "pipeline-deploy-full", "commit": True}},
    )
    print(f"    API: {r.status_code}")
    time.sleep(15)
    intent.refresh_from_db()
    print(f"    Result: {intent.status}")

# Final summary
print("\n" + "=" * 60)
print("  FINAL RESULTS")
print("=" * 60)
results = {}
for intent in all_intents:
    intent.refresh_from_db()
    status = str(intent.status)
    results.setdefault(status, []).append(intent.intent_id)
    print(f"  {intent.intent_id:40s} → {intent.status}")

print(f"\n  Summary:")
for status, ids in sorted(results.items()):
    print(f"    {status}: {len(ids)}")
print("=" * 60)
