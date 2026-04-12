"""Diagnostic script: fetch error logs from the last N failed IntentDeploymentJob runs."""

from nautobot.extras.models import JobResult

for class_name in ["IntentDeploymentJob"]:
    jrs = JobResult.objects.filter(job_model__job_class_name=class_name, status="FAILURE").order_by("-date_created")[:3]

    for jr in jrs:
        intent_id = jr.task_kwargs.get("intent_id", "?") if jr.task_kwargs else "?"
        print(f"\n=== {class_name} | {intent_id} | {jr.date_created} ===")
        logs = jr.job_log_entries.filter(log_level__in=["error", "critical", "warning"]).order_by("created")[:10]
        for entry in logs:
            print(f"  [{entry.log_level}] {entry.message[:400]}")
        if not logs.exists():
            print("  (no error/warning log entries)")
            print(jr.traceback[:800] if jr.traceback else "  no traceback")
