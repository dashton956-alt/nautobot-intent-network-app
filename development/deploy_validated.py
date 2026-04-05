#!/usr/bin/env python3
"""Deploy all Validated+Approved intents. No resolve/preview needed."""

import time

import requests

API = "http://localhost:8080/api"
TOKEN = "0123456789abcdef0123456789abcdef01234567"  # noqa: S105
HEADERS = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

DEPLOY_JOB = "4b639452-b25d-4090-86ec-9e5c967a6d56"
STEP_DELAY = 15

# Priority order
PRIORITY_ORDER = [
    "lab-dc-evpn-fabric-001",
    "lab-dc-l2vni-prod-001",
    "lab-dc-l3vni-tenant-001",
    "lab-anycast-gw-001",
    "lab-mlag-pair-001",
    "lab-vlans-dc1-001",
    "lab-acl-server-segment-001",
    "lab-macsec-uplinks-001",
    "lab-port-security-001",
    "lab-storm-control-001",
    "lab-qos-classify-001",
    "lab-stp-policy-001",
    "lab-mgmt-global-config-001",
    "lab-mgmt-snmp-001",
    "lab-mgmt-netconf-001",
    "lab-mgmt-ssh-001",
    "lab-mgmt-syslog-001",
    "lab-mgmt-telemetry-001",
]


def get_status_name(status_obj):
    """Extract status name from a status dict or string."""
    if isinstance(status_obj, dict):
        return status_obj.get("name", status_obj.get("value", status_obj.get("label", "unknown")))
    return str(status_obj)


def run_job(job_id, intent_id, extra_data=None):
    """Enqueue a job and poll until completion."""
    data = {"intent_id": intent_id}
    if extra_data:
        data.update(extra_data)
    url = f"{API}/extras/jobs/{job_id}/run/"
    resp = requests.post(url, headers=HEADERS, json={"data": data}, timeout=30)
    if resp.status_code not in (200, 201):
        print(f"    ERROR: {resp.status_code} - {resp.text[:300]}")
        return None
    result = resp.json()
    jr = result.get("job_result", result)
    job_result_url = jr.get("url")
    if not job_result_url:
        jr_id = jr.get("id")
        if jr_id:
            job_result_url = f"{API}/extras/job-results/{jr_id}/"
        else:
            return result

    for _ in range(90):  # max ~7.5 minutes
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
    print("    TIMEOUT waiting for job")
    return None


def get_intent_status(intent_id):
    """Return the current status name for an intent."""
    url = f"{API}/plugins/intent-networking/intents/?intent_id={intent_id}&depth=1"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        if results:
            return get_status_name(results[0].get("status", {}))
    return "unknown"


def main():
    """Deploy all validated and approved intents."""
    # Get validated intents
    url = f"{API}/plugins/intent-networking/intents/?limit=50&depth=1"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    all_intents = resp.json().get("results", [])

    validated = {}
    for i in all_intents:
        s = get_status_name(i.get("status", {}))
        if s == "Validated":
            validated[i["intent_id"]] = i

    ordered = [iid for iid in PRIORITY_ORDER if iid in validated]
    remaining = [iid for iid in validated if iid not in set(PRIORITY_ORDER)]
    ordered.extend(remaining)

    print(f"=== Deploy: {len(ordered)} Validated intents ===")
    for iid in ordered:
        print(f"  - {iid}")
    print()

    results = {"deployed": [], "rolled_back": [], "failed": [], "other": []}

    for idx, intent_id in enumerate(ordered, 1):
        print(f"\n[{idx}/{len(ordered)}] Deploying: {intent_id}")
        print(f"{'='*60}")

        jr = run_job(DEPLOY_JOB, intent_id, extra_data={"commit_sha": "manual-lab-deploy", "commit": True})

        if jr:
            jr_status = get_status_name(jr.get("status", {}))
            print(f"  Job status: {jr_status}")

            # Print log summary if failure
            if jr_status == "FAILURE":
                jr_id = jr.get("id", "")
                logs_resp = requests.get(f"{API}/extras/job-results/{jr_id}/logs/", headers=HEADERS, timeout=15)
                if logs_resp.status_code == 200:
                    logs_data = logs_resp.json()
                    log_list = logs_data.get("results", logs_data) if isinstance(logs_data, dict) else logs_data
                    if isinstance(log_list, list):
                        for log in log_list:
                            if isinstance(log, dict) and log.get("log_level") in ("error", "failure", "warning"):
                                print(f"    [{log['log_level']}] {log.get('message', '')[:200]}")

        time.sleep(STEP_DELAY)

        final = get_intent_status(intent_id)
        print(f"  Intent status: {final}")

        if final == "Deployed":
            results["deployed"].append(intent_id)
        elif final == "Rolled Back":
            results["rolled_back"].append(intent_id)
        elif final == "Failed":
            results["failed"].append(intent_id)
        else:
            results["other"].append((intent_id, final))

    print(f"\n\n{'='*60}")
    print("DEPLOY RESULTS SUMMARY")
    print(f"{'='*60}")
    total_deployed = len(results["deployed"]) + 9  # 9 already deployed
    print("Previously Deployed: 9")
    print(f"Newly Deployed:      {len(results['deployed'])}")
    print(f"Total Deployed:      {total_deployed}/27")
    for i in results["deployed"]:
        print(f"  ✓ {i}")
    if results["rolled_back"]:
        print(f"Rolled Back:         {len(results['rolled_back'])}")
        for i in results["rolled_back"]:
            print(f"  ↩ {i}")
    if results["failed"]:
        print(f"Failed:              {len(results['failed'])}")
        for i in results["failed"]:
            print(f"  ✗ {i}")
    if results["other"]:
        print(f"Other:               {len(results['other'])}")
        for i, s in results["other"]:
            print(f"  ? {i} ({s})")


if __name__ == "__main__":
    main()
