#!/usr/bin/env python3
"""Seed L2 access + trunk port intents for Arista Lab, then run full pipeline."""

import time

import requests

API = "http://localhost:8080/api"
TOKEN = "0123456789abcdef0123456789abcdef01234567"  # noqa: S105
HEADERS = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

RESOLVE_JOB = "492d6643-3a3a-4e43-b5b0-251bc3159a05"
PREVIEW_JOB = "bc5cabcf-8d7b-489f-88f4-f38fef24f50a"
DEPLOY_JOB = "4b639452-b25d-4090-86ec-9e5c967a6d56"

L2_INTENTS = [
    # Access ports
    {
        "intent_id": "lab-l2-access-prod-001",
        "intent_type": "l2_access_port",
        "version": 1,
        "change_ticket": "CHG0012360",
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "interface": "Ethernet1",
            "vlan_id": 100,
            "voice_vlan": None,
            "description": "Server PROD — VLAN 100",
            "portfast": True,
            "bpdu_guard": True,
        },
    },
    {
        "intent_id": "lab-l2-access-dev-001",
        "intent_type": "l2_access_port",
        "version": 1,
        "change_ticket": "CHG0012361",
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "interface": "Ethernet2",
            "vlan_id": 101,
            "voice_vlan": None,
            "description": "Server DEV — VLAN 101",
            "portfast": True,
            "bpdu_guard": True,
        },
    },
    {
        "intent_id": "lab-l2-access-storage-001",
        "intent_type": "l2_access_port",
        "version": 1,
        "change_ticket": "CHG0012362",
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "interface": "Ethernet3",
            "vlan_id": 200,
            "voice_vlan": None,
            "description": "Storage — VLAN 200",
            "portfast": True,
            "bpdu_guard": True,
        },
    },
    {
        "intent_id": "lab-l2-access-mgmt-001",
        "intent_type": "l2_access_port",
        "version": 1,
        "change_ticket": "CHG0012363",
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "interface": "Ethernet4",
            "vlan_id": 300,
            "voice_vlan": None,
            "description": "Management — VLAN 300",
            "portfast": True,
            "bpdu_guard": True,
        },
    },
    # Trunk uplinks
    {
        "intent_id": "lab-l2-trunk-uplink-001",
        "intent_type": "l2_trunk_port",
        "version": 1,
        "change_ticket": "CHG0012364",
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "interface": "Ethernet49",
            "allowed_vlans": [100, 101, 200, 300, 999],
            "native_vlan": 1,
            "description": "Trunk uplink to spine — Ethernet49",
        },
    },
    {
        "intent_id": "lab-l2-trunk-uplink-002",
        "intent_type": "l2_trunk_port",
        "version": 1,
        "change_ticket": "CHG0012365",
        "intent_data": {
            "scope": {"sites": ["LAB-DC1"]},
            "interface": "Ethernet50",
            "allowed_vlans": [100, 101, 200, 300, 999],
            "native_vlan": 1,
            "description": "Trunk uplink to spine — Ethernet50",
        },
    },
]


def get_status_name(status_obj):
    """Extract status name from a status dict or string."""
    if isinstance(status_obj, dict):
        return status_obj.get("name", status_obj.get("value", str(status_obj)))
    return str(status_obj)


def get_tenant_id():
    """Fetch the Arista Lab tenant ID from the API."""
    resp = requests.get(f"{API}/tenancy/tenants/?name=Arista+Lab", headers=HEADERS, timeout=10)
    results = resp.json().get("results", [])
    if results:
        return results[0]["id"]
    raise RuntimeError("Tenant 'Arista Lab' not found")


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
    for _ in range(60):
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
    print("    TIMEOUT")
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
    tenant_id = get_tenant_id()
    print(f"Tenant ID: {tenant_id}\n")

    # ── Step 1: Create intents via API ──
    print("=" * 60)
    print("STEP 1: Create L2 port intents")
    print("=" * 60)

    created_ids = []
    for idata in L2_INTENTS:
        iid = idata["intent_id"]
        # Check if already exists
        check = requests.get(
            f"{API}/plugins/intent-networking/intents/?intent_id={iid}",
            headers=HEADERS,
            timeout=10,
        )
        existing = check.json().get("results", [])
        if existing:
            print(f"  EXISTS: {iid} (status={get_status_name(existing[0].get('status', {}))})")
            # Reset to Draft for re-deploy
            intent_uuid = existing[0]["id"]
            draft_status = requests.get(f"{API}/extras/statuses/?name=Draft", headers=HEADERS, timeout=10).json()[
                "results"
            ][0]["id"]
            requests.patch(
                f"{API}/plugins/intent-networking/intents/{intent_uuid}/",
                headers=HEADERS,
                json={"status": draft_status, "intent_data": idata["intent_data"]},
                timeout=10,
            )
            print("    → Reset to Draft")
            created_ids.append(iid)
            continue

        # Get Draft status ID
        draft_resp = requests.get(f"{API}/extras/statuses/?name=Draft", headers=HEADERS, timeout=10)
        draft_status = draft_resp.json()["results"][0]["id"]

        payload = {
            "intent_id": iid,
            "intent_type": idata["intent_type"],
            "version": idata["version"],
            "change_ticket": idata.get("change_ticket", ""),
            "tenant": tenant_id,
            "status": draft_status,
            "intent_data": idata["intent_data"],
        }
        resp = requests.post(
            f"{API}/plugins/intent-networking/intents/",
            headers=HEADERS,
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            print(f"  CREATED: {iid}")
            created_ids.append(iid)
        else:
            print(f"  FAILED:  {iid} — {resp.status_code}: {resp.text[:300]}")

    if not created_ids:
        print("\nNo intents to deploy!")
        return

    # ── Step 2: Resolve → Preview → Deploy each intent ──
    print(f"\n{'=' * 60}")
    print(f"STEP 2: Pipeline — Resolve → Preview → Deploy ({len(created_ids)} intents)")
    print("=" * 60)

    results = {"deployed": [], "failed": []}

    for idx, iid in enumerate(created_ids, 1):
        print(f"\n[{idx}/{len(created_ids)}] {iid}")
        print("-" * 40)

        # Resolve
        print("  Resolving...")
        jr = run_job(RESOLVE_JOB, iid)
        if not jr or get_status_name(jr.get("status", {})) != "SUCCESS":
            print("  RESOLVE FAILED")
            results["failed"].append((iid, "resolve"))
            continue
        print(f"  Resolved OK → status: {get_intent_status(iid)}")

        # Preview
        print("  Previewing...")
        jr = run_job(PREVIEW_JOB, iid)
        if not jr or get_status_name(jr.get("status", {})) != "SUCCESS":
            print("  PREVIEW FAILED")
            results["failed"].append((iid, "preview"))
            continue
        print(f"  Preview OK → status: {get_intent_status(iid)}")

        # Deploy (commit=True)
        print("  Deploying...")
        jr = run_job(DEPLOY_JOB, iid, extra_data={"commit_sha": "l2-port-deploy", "commit": True})
        time.sleep(10)
        final = get_intent_status(iid)
        if final == "Deployed":
            results["deployed"].append(iid)
            print("  DEPLOYED ✓")
        else:
            results["failed"].append((iid, f"deploy ({final})"))
            print(f"  DEPLOY RESULT: {final}")

            # Print error logs
            if jr:
                jr_id = jr.get("id", "")
                if jr_id:
                    logs_resp = requests.get(
                        f"{API}/extras/job-results/{jr_id}/logs/",
                        headers=HEADERS,
                        timeout=15,
                    )
                    if logs_resp.status_code == 200:
                        logs = logs_resp.json()
                        log_list = logs.get("results", logs) if isinstance(logs, dict) else logs
                        if isinstance(log_list, list):
                            for log in log_list:
                                if isinstance(log, dict) and log.get("log_level") in ("error", "warning"):
                                    print(f"    [{log['log_level']}] {log.get('message', '')[:200]}")

    # ── Summary ──
    print(f"\n\n{'=' * 60}")
    print("L2 PORT DEPLOYMENT SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Deployed: {len(results['deployed'])}/{len(created_ids)}")
    for iid in results["deployed"]:
        print(f"    ✓ {iid}")
    if results["failed"]:
        print(f"  Failed:   {len(results['failed'])}")
        for iid, step in results["failed"]:
            print(f"    ✗ {iid} ({step})")


if __name__ == "__main__":
    main()
