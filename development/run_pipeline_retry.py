"""Re-run pipeline for all non-Deployed intents.

Reset them to Draft, resolve, preview, approve, and deploy one at a time
with 20s gaps to let SSH idle timeouts clean up connections.
"""

import time

import requests
from django.contrib.auth import get_user_model
from nautobot.extras.models.statuses import Status

from intent_networking.models import Intent, IntentApproval

API = "http://localhost:8080/api"
HDR = {
    "Authorization": "Token 0123456789abcdef0123456789abcdef01234567",
    "Content-Type": "application/json",
}

RESOLVE_JOB = "492d6643-3a3a-4e43-b5b0-251bc3159a05"
PREVIEW_JOB = "bc5cabcf-8d7b-489f-88f4-f38fef24f50a"
DEPLOY_JOB = "4b639452-b25d-4090-86ec-9e5c967a6d56"

User = get_user_model()
admin = User.objects.filter(is_superuser=True).first()
draft_status = Status.objects.get(name="Draft")

# Get non-deployed intents
targets = list(Intent.objects.exclude(status__name="Deployed").order_by("intent_id"))
print(f"Found {len(targets)} non-Deployed intents to retry\n")

# Reset to Draft
for intent in targets:
    intent.status = draft_status
    intent.save()
    print(f"  Reset {intent.intent_id} ({intent.status})")

# Resolve all
print("\n--- Resolving ---")
for intent in targets:
    r = requests.post(
        f"{API}/extras/jobs/{RESOLVE_JOB}/run/",
        headers=HDR,
        json={"data": {"intent_id": intent.intent_id, "force_re_resolve": True}},
        timeout=30,
    )
    print(f"  Resolve {intent.intent_id}: {r.status_code}")
    time.sleep(3)
time.sleep(20)

# Preview all
print("\n--- Previewing ---")
for intent in targets:
    r = requests.post(
        f"{API}/extras/jobs/{PREVIEW_JOB}/run/",
        headers=HDR,
        json={"data": {"intent_id": intent.intent_id}},
        timeout=30,
    )
    print(f"  Preview {intent.intent_id}: {r.status_code}")
    time.sleep(2)
time.sleep(15)

# Approve all
print("\n--- Approving ---")
for intent in targets:
    IntentApproval.objects.update_or_create(
        intent=intent,
        defaults={
            "approved_by": admin,
            "decision": "Approved",
            "comments": "Auto-approved retry",
        },
    )
    print(f"  Approved {intent.intent_id}")
time.sleep(5)

# Deploy one at a time with 20s gaps
print("\n--- Deploying (20s gaps) ---")
for intent in targets:
    intent.refresh_from_db()
    print(f"\n  Deploying {intent.intent_id} (status={intent.status})...")
    r = requests.post(
        f"{API}/extras/jobs/{DEPLOY_JOB}/run/",
        headers=HDR,
        json={"data": {"intent_id": intent.intent_id, "commit_sha": "retry-2", "commit": True}},
        timeout=30,
    )
    print(f"    API: {r.status_code}")
    time.sleep(20)
    intent.refresh_from_db()
    print(f"    Result: {intent.status}")

# Final report
print("\n" + "=" * 60)
print("  FINAL RESULTS (retry run)")
print("=" * 60)
results = {}
for intent in Intent.objects.all().order_by("intent_id"):
    status = str(intent.status)
    results.setdefault(status, []).append(intent.intent_id)
    print(f"  {intent.intent_id:40s} → {intent.status}")

print("\n  Summary:")
for status, ids in sorted(results.items()):
    print(f"    {status}: {len(ids)}")
print("=" * 60)
