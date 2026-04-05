#!/usr/bin/env python3
"""Run the intent pipeline for all Draft intents from the HOST machine.

Uses the Nautobot API via localhost:8080 (Docker port mapping).
Pipeline: Resolve → Preview → Approve → Deploy (with delays between steps).
"""

import sys
import time

import requests

API = "http://localhost:8080/api"
TOKEN = "0123456789abcdef0123456789abcdef01234567"  # noqa: S105
HEADERS = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Job IDs
RESOLVE_JOB = "492d6643-3a3a-4e43-b5b0-251bc3159a05"
PREVIEW_JOB = "bc5cabcf-8d7b-489f-88f4-f38fef24f50a"
DEPLOY_JOB = "4b639452-b25d-4090-86ec-9e5c967a6d56"

STEP_DELAY = 15  # seconds between pipeline steps

# Priority order — deploy dependencies first
PRIORITY_ORDER = [
    # EVPN fabric first (others depend on it)
    "lab-dc-evpn-fabric-001",
    # L2/L3 VNI and anycast (depend on fabric)
    "lab-dc-l2vni-prod-001",
    "lab-dc-l3vni-tenant-001",
    "lab-anycast-gw-001",
    # MLAG
    "lab-mlag-pair-001",
    # VLANs
    "lab-vlans-dc1-001",
    # Security / ACLs
    "lab-acl-server-segment-001",
    "lab-macsec-uplinks-001",
    "lab-port-security-001",
    "lab-storm-control-001",
    # QoS
    "lab-qos-classify-001",
    # STP
    "lab-stp-policy-001",
    # Management intents
    "lab-mgmt-global-config-001",
    "lab-mgmt-snmp-001",
    "lab-mgmt-netconf-001",
    "lab-mgmt-ssh-001",
    "lab-mgmt-syslog-001",
    "lab-mgmt-telemetry-001",
]


def get_status_name(status_obj):
    """Extract status name from API status object."""
    if isinstance(status_obj, dict):
        return status_obj.get("value", status_obj.get("label", status_obj.get("name", "unknown")))
    return str(status_obj)


def run_job(job_id, intent_id, extra_data=None):
    """Run a Nautobot job and wait for completion."""
    data = {"intent_id": intent_id}
    if extra_data:
        data.update(extra_data)
    url = f"{API}/extras/jobs/{job_id}/run/"
    resp = requests.post(url, headers=HEADERS, json={"data": data}, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"    ERROR: {resp.status_code} - {resp.text[:200]}")
        return None
    result = resp.json()
    jr = result.get("job_result", result)
    job_result_url = jr.get("url")
    if not job_result_url:
        jr_id = jr.get("id")
        if jr_id:
            job_result_url = f"{API}/extras/job-results/{jr_id}/"
        else:
            print("    WARNING: No job result URL in response")
            return result

    # Poll for completion
    for _ in range(60):  # max 5 minutes
        time.sleep(5)
        try:
            poll = requests.get(job_result_url, headers=HEADERS, timeout=15)
            if poll.status_code == 200:
                jr_data = poll.json()
                status_val = get_status_name(jr_data.get("status", {}))
                if status_val in ("SUCCESS", "FAILURE", "REVOKED"):
                    return jr_data
        except Exception as e:
            print(f"    Poll error: {e}")
            continue
    print("    TIMEOUT waiting for job")
    return None


def get_intent_status(intent_id):
    """Get the current status of an intent."""
    url = f"{API}/plugins/intent-networking/intents/?intent_id={intent_id}&depth=1"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        if results:
            return get_status_name(results[0].get("status", {}))
    return "unknown"


def approve_intent(intent_id):
    """Approve an intent via API."""
    url = f"{API}/plugins/intent-networking/intents/?intent_id={intent_id}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        if results:
            intent_uuid = results[0]["id"]
            approve_url = f"{API}/plugins/intent-networking/intents/{intent_uuid}/approve/"
            resp2 = requests.post(approve_url, headers=HEADERS, json={}, timeout=15)
            if resp2.status_code in (200, 201):
                return True
            print(f"    Approve failed: {resp2.status_code} - {resp2.text[:200]}")
    return False


def main():
    """Run the full pipeline for all Draft intents."""
    # Get all Draft intents
    url = f"{API}/plugins/intent-networking/intents/?limit=50&depth=1"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        print(f"ERROR: Cannot list intents: {resp.status_code}")
        sys.exit(1)

    all_intents = resp.json().get("results", [])
    draft_ids = set()
    for i in all_intents:
        status_val = get_status_name(i.get("status", {}))
        if status_val == "Draft":
            draft_ids.add(i.get("intent_id"))

    # Order by priority
    ordered = [iid for iid in PRIORITY_ORDER if iid in draft_ids]
    # Add any not in priority list
    remaining = [iid for iid in draft_ids if iid not in set(PRIORITY_ORDER)]
    ordered.extend(remaining)

    print(f"=== Pipeline: {len(ordered)} Draft intents to process ===")
    for iid in ordered:
        print(f"  - {iid}")
    print()

    results = {"deployed": [], "failed": [], "rolled_back": [], "other": []}

    for idx, intent_id in enumerate(ordered, 1):
        print(f"\n[{idx}/{len(ordered)}] Processing: {intent_id}")
        print(f"{'='*60}")

        # Step 1: Resolve (force re-resolve since we reset to Draft)
        print("  Step 1: Resolving...")
        jr = run_job(RESOLVE_JOB, intent_id, extra_data={"force_re_resolve": True})
        if jr and jr.get("status") not in ("SUCCESS", {"value": "SUCCESS"}):
            status_val = jr.get("status")
            if isinstance(status_val, dict):
                status_val = status_val.get("value", "")
            if status_val != "SUCCESS":
                print(f"  RESOLVE FAILED (status={status_val})")
                results["failed"].append(intent_id)
                continue
        time.sleep(STEP_DELAY)

        # Check status after resolve
        current = get_intent_status(intent_id)
        print(f"  Status after resolve: {current}")
        if current != "Validated":
            print("  Skipping (not Validated after resolve)")
            results["failed"].append(intent_id)
            continue

        # Step 2: Preview
        print("  Step 2: Previewing...")
        jr = run_job(PREVIEW_JOB, intent_id)
        time.sleep(STEP_DELAY)

        # Step 3: Approve
        print("  Step 3: Approving...")
        ok = approve_intent(intent_id)
        if not ok:
            print("  APPROVE FAILED")
            results["failed"].append(intent_id)
            continue
        time.sleep(5)

        # Step 4: Deploy
        print("  Step 4: Deploying...")
        jr = run_job(DEPLOY_JOB, intent_id, extra_data={"commit_sha": "manual-lab-deploy", "commit": True})
        time.sleep(STEP_DELAY)

        # Check final status
        final = get_intent_status(intent_id)
        print(f"  Final status: {final}")

        if final == "Deployed":
            results["deployed"].append(intent_id)
        elif final == "Rolled Back":
            results["rolled_back"].append(intent_id)
        elif final == "Failed":
            results["failed"].append(intent_id)
        else:
            results["other"].append((intent_id, final))

    # Summary
    print(f"\n\n{'='*60}")
    print("PIPELINE RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Deployed:    {len(results['deployed'])}")
    for i in results["deployed"]:
        print(f"  ✓ {i}")
    print(f"Failed:      {len(results['failed'])}")
    for i in results["failed"]:
        print(f"  ✗ {i}")
    print(f"Rolled Back: {len(results['rolled_back'])}")
    for i in results["rolled_back"]:
        print(f"  ↩ {i}")
    if results["other"]:
        print(f"Other:       {len(results['other'])}")
        for i, s in results["other"]:
            print(f"  ? {i} ({s})")


if __name__ == "__main__":
    main()
