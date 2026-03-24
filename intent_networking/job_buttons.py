"""Job Button receivers for the intent_networking plugin.

These allow users to trigger lifecycle jobs (Resolve, Deploy, Verify,
Rollback) directly from the Intent detail page in the Nautobot UI —
no need to navigate to the Jobs menu and manually type intent IDs.
"""

import logging

from nautobot.core.celery import register_jobs
from nautobot.extras.jobs import JobButtonReceiver

from intent_networking.jobs import _enqueue_job
from intent_networking.models import Intent

logger = logging.getLogger(__name__)


class ResolveIntentButton(JobButtonReceiver):
    """Job button: resolve an intent from its detail page."""

    class Meta:
        """Nautobot job metadata for ResolveIntentButton."""

        name = "Resolve Intent"
        has_sensitive_variables = False

    def receive_job_button(self, obj):
        """Enqueue an IntentResolutionJob for the clicked intent."""
        if not isinstance(obj, Intent):
            self.logger.failure("ResolveIntentButton only works on Intent objects.")
            return

        self.logger.info("Queuing resolution for %s", obj.intent_id)
        _enqueue_job("IntentResolutionJob", intent_id=obj.intent_id)
        self.logger.info("Resolution job queued for %s", obj.intent_id)


class DeployIntentButton(JobButtonReceiver):
    """Job button: deploy an intent from its detail page."""

    class Meta:
        """Nautobot job metadata for DeployIntentButton."""

        name = "Deploy Intent"
        has_sensitive_variables = True

    def receive_job_button(self, obj):
        """Enqueue an IntentDeploymentJob for the clicked intent."""
        if not isinstance(obj, Intent):
            self.logger.failure("DeployIntentButton only works on Intent objects.")
            return

        if not obj.status or obj.status.name.lower() not in ("validated", "rolled back"):
            self.logger.failure(
                "Intent %s is in status '%s' — must be 'Validated' or 'Rolled Back' to deploy.",
                obj.intent_id,
                obj.status,
            )
            return

        self.logger.info("Queuing deployment for %s", obj.intent_id)
        _enqueue_job(
            "IntentDeploymentJob",
            intent_id=obj.intent_id,
            commit_sha=obj.git_commit_sha or "manual-deploy",
        )
        self.logger.info("Deployment job queued for %s", obj.intent_id)


class DryRunDeployIntentButton(JobButtonReceiver):
    """Job button: dry-run deploy (no commit) from the detail page."""

    class Meta:
        """Nautobot job metadata for DryRunDeployIntentButton."""

        name = "Dry-Run Deploy Intent"
        has_sensitive_variables = False

    def receive_job_button(self, obj):
        """Enqueue a dry-run IntentDeploymentJob for the clicked intent."""
        if not isinstance(obj, Intent):
            self.logger.failure("DryRunDeployIntentButton only works on Intent objects.")
            return

        self.logger.info("Queuing dry-run deployment for %s", obj.intent_id)
        _enqueue_job(
            "IntentDeploymentJob",
            intent_id=obj.intent_id,
            commit_sha=obj.git_commit_sha or "dry-run",
            commit=False,
        )
        self.logger.info("Dry-run deployment job queued for %s", obj.intent_id)


class VerifyIntentButton(JobButtonReceiver):
    """Job button: verify an intent from its detail page."""

    class Meta:
        """Nautobot job metadata for VerifyIntentButton."""

        name = "Verify Intent"
        has_sensitive_variables = False

    def receive_job_button(self, obj):
        """Enqueue an IntentVerificationJob for the clicked intent."""
        if not isinstance(obj, Intent):
            self.logger.failure("VerifyIntentButton only works on Intent objects.")
            return

        self.logger.info("Queuing verification for %s", obj.intent_id)
        _enqueue_job("IntentVerificationJob", intent_id=obj.intent_id, triggered_by="manual")
        self.logger.info("Verification job queued for %s", obj.intent_id)


class ConfigPreviewIntentButton(JobButtonReceiver):
    """Job button: render and cache config preview from the detail page."""

    class Meta:
        """Nautobot job metadata for ConfigPreviewIntentButton."""

        name = "Config Preview Intent"
        has_sensitive_variables = False

    def receive_job_button(self, obj):
        """Enqueue an IntentConfigPreviewJob for the clicked intent."""
        if not isinstance(obj, Intent):
            self.logger.failure("ConfigPreviewIntentButton only works on Intent objects.")
            return

        self.logger.info("Queuing config preview for %s", obj.intent_id)
        _enqueue_job("IntentConfigPreviewJob", intent_id=obj.intent_id)
        self.logger.info("Config preview job queued for %s", obj.intent_id)


class RollbackIntentButton(JobButtonReceiver):
    """Job button: rollback an intent from its detail page."""

    class Meta:
        """Nautobot job metadata for RollbackIntentButton."""

        name = "Rollback Intent"
        has_sensitive_variables = True

    def receive_job_button(self, obj):
        """Enqueue an IntentRollbackJob for the clicked intent."""
        if not isinstance(obj, Intent):
            self.logger.failure("RollbackIntentButton only works on Intent objects.")
            return

        self.logger.info("Queuing rollback for %s", obj.intent_id)
        _enqueue_job("IntentRollbackJob", intent_id=obj.intent_id)
        self.logger.info("Rollback job queued for %s", obj.intent_id)


# ─────────────────────────────────────────────────────────────────────────────
# Registration — Nautobot 3.x discovers jobs via this list + register_jobs()
# ─────────────────────────────────────────────────────────────────────────────

jobs = [
    ResolveIntentButton,
    DeployIntentButton,
    DryRunDeployIntentButton,
    ConfigPreviewIntentButton,
    VerifyIntentButton,
    RollbackIntentButton,
]
register_jobs(*jobs)
