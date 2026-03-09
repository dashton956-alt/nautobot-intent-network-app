"""Prometheus metrics for the intent_networking plugin (#7).

Exposes counters and gauges that can be scraped by Prometheus at
``/api/plugins/intent-networking/metrics/``.

Metrics exported:
  intent_total                    — gauge, by status
  intent_deployments_total        — counter, by outcome (success/failure)
  intent_verifications_total      — counter, by outcome (pass/fail)
  intent_reconciliation_runs      — counter
  intent_drift_detected_total     — counter
  intent_verification_latency_ms  — histogram
  intent_rd_pool_utilisation      — gauge per pool (0-100)
  intent_rt_pool_utilisation      — gauge per pool (0-100)
  intent_approval_pending         — gauge (intents awaiting approval)
  intent_conflicts_detected       — gauge
"""

import logging

from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.views import View

from intent_networking.models import (
    Intent,
    RouteDistinguisherPool,
    RouteTargetPool,
    VerificationResult,
)

logger = logging.getLogger(__name__)


def _prom_line(name, value, labels=None, help_text="", metric_type="gauge"):
    """Format a single Prometheus metric line."""
    lines = []
    if help_text:
        lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {metric_type}")
    if labels:
        label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
        lines.append(f"{name}{{{label_str}}} {value}")
    else:
        lines.append(f"{name} {value}")
    return "\n".join(lines)


class PrometheusMetricsView(View):
    """Expose Prometheus-compatible metrics at /api/plugins/intent-networking/metrics/."""

    def get(self, request):  # noqa: PLR0914  pylint: disable=unused-argument
        """Return all plugin metrics in Prometheus text exposition format."""
        lines = []

        # ── intent_total (by status) ──────────────────────────────────────
        status_counts = Intent.objects.values("status__name").annotate(count=Count("id")).order_by("status__name")
        lines.append("# HELP intent_total Total intents by status")
        lines.append("# TYPE intent_total gauge")
        for row in status_counts:
            sname = row["status__name"] or "unknown"
            lines.append(f'intent_total{{status="{sname}"}} {row["count"]}')

        # ── intent_deployments_total ──────────────────────────────────────
        deployed = Intent.objects.filter(deployed_at__isnull=False).count()
        failed = Intent.objects.filter(status__name__iexact="Failed").count()
        lines.append(_prom_line("intent_deployments_total", deployed, {"outcome": "success"}, metric_type="counter"))
        lines.append(_prom_line("intent_deployments_total", failed, {"outcome": "failure"}, metric_type="counter"))

        # ── intent_verifications_total ────────────────────────────────────
        v_pass = VerificationResult.objects.filter(passed=True).count()
        v_fail = VerificationResult.objects.filter(passed=False).count()
        lines.append(_prom_line("intent_verifications_total", v_pass, {"outcome": "pass"}, metric_type="counter"))
        lines.append(_prom_line("intent_verifications_total", v_fail, {"outcome": "fail"}, metric_type="counter"))

        # ── intent_drift_detected_total ───────────────────────────────────
        drift = VerificationResult.objects.filter(passed=False, triggered_by="reconciliation").count()
        lines.append(
            _prom_line(
                "intent_drift_detected_total",
                drift,
                help_text="Total drift events detected by reconciliation",
                metric_type="counter",
            )
        )

        # ── intent_verification_latency_ms (avg over last 100) ───────────
        avg_latency = (
            VerificationResult.objects.filter(measured_latency_ms__isnull=False)
            .order_by("-verified_at")[:100]
            .aggregate(avg=Avg("measured_latency_ms"))["avg"]
            or 0
        )
        lines.append(
            _prom_line(
                "intent_verification_latency_avg_ms",
                round(avg_latency, 2),
                help_text="Average verification latency over last 100 runs (ms)",
            )
        )

        # ── RD pool utilisation ───────────────────────────────────────────
        lines.append("# HELP intent_rd_pool_utilisation_pct RD pool utilisation percentage")
        lines.append("# TYPE intent_rd_pool_utilisation_pct gauge")
        for pool in RouteDistinguisherPool.objects.all():
            lines.append(f'intent_rd_pool_utilisation_pct{{pool="{pool.name}"}} {pool.utilisation_pct}')

        # ── RT pool utilisation ───────────────────────────────────────────
        lines.append("# HELP intent_rt_pool_utilisation_pct RT pool utilisation percentage")
        lines.append("# TYPE intent_rt_pool_utilisation_pct gauge")
        for pool in RouteTargetPool.objects.all():
            alloc_count = pool.allocations.count()
            total = pool.range_end - pool.range_start + 1
            pct = int(alloc_count / total * 100) if total > 0 else 0
            lines.append(f'intent_rt_pool_utilisation_pct{{pool="{pool.name}"}} {pct}')

        # ── intent_approval_pending ───────────────────────────────────────
        # Intents in 'Validated' status that have zero approvals
        pending = (
            Intent.objects.filter(
                status__name__iexact="Validated",
            )
            .annotate(
                approval_count=Count("approvals", filter=Q(approvals__decision="approved")),
            )
            .filter(approval_count=0)
            .count()
        )
        lines.append(
            _prom_line(
                "intent_approval_pending",
                pending,
                help_text="Intents awaiting approval before deployment",
            )
        )

        # ── intent_conflicts_detected ─────────────────────────────────────
        conflict_count = 0
        for intent in Intent.objects.filter(status__name__in=["Draft", "Validated", "Deploying", "Deployed"]).only(
            "pk", "intent_data"
        ):
            from intent_networking.models import detect_conflicts  # noqa: PLC0415

            if detect_conflicts(intent):
                conflict_count += 1
        lines.append(
            _prom_line(
                "intent_conflicts_detected",
                conflict_count,
                help_text="Number of intents with active resource conflicts",
            )
        )

        body = "\n".join(lines) + "\n"
        return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")
