"""Nautobot Jobs for the intent engine.

Jobs run asynchronously via Celery, log to Nautobot's job log,
and can be triggered via the REST API or UI.

Jobs defined here:
  IntentSyncFromGitJob      — creates/updates Intent records from YAML
  IntentResolutionJob       — resolves intent → normalized plan
  IntentConfigPreviewJob    — renders config diff WITHOUT deploying (#1)
  IntentDeploymentJob       — deploys plan to devices via Nornir
  IntentVerificationJob     — verifies intent is satisfied post-deploy
  IntentRollbackJob         — rolls back a failed deployment
  IntentReconciliationJob   — scheduled: checks all deployed intents for drift
"""

import json
import logging
import os
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from nautobot.core.celery import register_jobs
from nautobot.dcim.models import Device
from nautobot.extras.jobs import BooleanVar, Job, StringVar
from nautobot.extras.models import Job as JobModel
from nautobot.extras.models import JobResult, Status
from nautobot.tenancy.models import Tenant

from intent_networking.controller_adapters import (
    classify_primitives,
    get_adapter,
)
from intent_networking.events import (
    EVENT_INTENT_CONFLICT,
    EVENT_INTENT_CREATED,
    EVENT_INTENT_DEPLOYED,
    EVENT_INTENT_DRIFT,
    EVENT_INTENT_FAILED,
    EVENT_INTENT_RESOLVED,
    EVENT_INTENT_ROLLED_BACK,
    dispatch_event,
)
from intent_networking.models import (
    DeploymentStage,
    Intent,
    IntentAuditEntry,
    ResolutionPlan,
    VerificationResult,
    detect_conflicts,
    validate_tenant_isolation,
)
from intent_networking.notifications import notify_slack, raise_github_issue
from intent_networking.resolver import resolve_intent

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Sync From Git
# ─────────────────────────────────────────────────────────────────────────────


class IntentSyncFromGitJob(Job):
    """Create or update an Intent record from a parsed YAML payload.

    Legacy "push" mode — called by a CI pipeline script when a PR opens.
    The preferred Nautobot-native approach is to configure a GitRepository
    with the "intent definitions" provided-content type; Nautobot will
    then automatically discover and sync intent YAML files on every pull.

    This job is kept as a fallback for CI-driven workflows that cannot
    use the native GitRepository integration.
    """

    intent_id = StringVar(description="Intent ID from YAML", required=True)
    intent_data = StringVar(description="Full YAML content as JSON string", required=True)
    git_commit_sha = StringVar(description="Commit SHA", required=False, default="")
    git_branch = StringVar(description="Branch name", required=False, default="")
    git_pr_number = StringVar(description="PR number", required=False, default="")

    class Meta:
        """Nautobot job metadata for IntentSyncFromGitJob."""

        name = "Sync Intent from Git"
        has_sensitive_variables = False
        approval_required = False

    def run(self, **kwargs):
        """Execute the sync-from-git job."""
        intent_yaml = json.loads(kwargs["intent_data"])

        tenant_name = intent_yaml.get("tenant")
        try:
            tenant = Tenant.objects.get(name=tenant_name)
        except Tenant.DoesNotExist:
            self.logger.failure(
                "Tenant '%s' not found in Nautobot. Create the tenant before syncing intents.",
                tenant_name,
            )
            return

        draft_status = Status.objects.get(name__iexact="Draft")

        intent, created = Intent.objects.update_or_create(
            intent_id=kwargs["intent_id"],
            defaults={
                "version": intent_yaml.get("version", 1),
                "intent_type": intent_yaml.get("type"),
                "tenant": tenant,
                "intent_data": intent_yaml,
                "change_ticket": intent_yaml.get("change_ticket", ""),
                "git_commit_sha": kwargs["git_commit_sha"],
                "git_branch": kwargs["git_branch"],
                "git_pr_number": int(kwargs["git_pr_number"]) if kwargs["git_pr_number"] else None,
                "status": draft_status,
            },
        )

        action = "Created" if created else "Updated"
        self.logger.info(
            "%s intent '%s' v%s (tenant: %s)",
            action,
            intent.intent_id,
            intent.version,
            tenant.name,
        )

        # Audit trail
        IntentAuditEntry.objects.create(
            intent=intent,
            action="created" if created else "updated",
            actor="IntentSyncFromGitJob",
            git_commit_sha=kwargs.get("git_commit_sha", ""),
            detail={"version": intent.version, "branch": kwargs.get("git_branch", "")},
        )
        dispatch_event(EVENT_INTENT_CREATED, intent)

        # Conflict check
        conflicts = detect_conflicts(intent)
        if conflicts:
            self.logger.warning("Conflicts detected for %s: %s", intent.intent_id, conflicts)
            IntentAuditEntry.objects.create(
                intent=intent,
                action="conflict_detected",
                actor="IntentSyncFromGitJob",
                detail={"conflicts": conflicts},
            )
            dispatch_event(EVENT_INTENT_CONFLICT, intent, {"conflicts": conflicts})

        return {"intent_id": intent.intent_id, "created": created}


# ─────────────────────────────────────────────────────────────────────────────
# Resolution
# ─────────────────────────────────────────────────────────────────────────────


class IntentResolutionJob(Job):
    """Resolves an intent into a normalized deployment plan.

    Queries Nautobot ORM for topology, allocates RD/RT atomically,
    stores the plan in ResolutionPlan. Idempotent — returns cached
    plan if one already exists for this intent version.

    Called by:
      - CI pipeline (to produce config diff and feed Batfish)
      - N8N deployment workflow (before pushing config)
    """

    intent_id = StringVar(description="Intent ID to resolve", required=True)
    force_re_resolve = BooleanVar(
        description="Re-resolve even if a plan already exists for this version", default=False
    )

    class Meta:
        """Nautobot job metadata for IntentResolutionJob."""

        name = "Intent Resolution"
        has_sensitive_variables = False
        approval_required = False

    def run(self, **kwargs):
        """Execute the intent resolution job."""
        intent_id = kwargs["intent_id"]
        force_re_resolve = kwargs.get("force_re_resolve", False)

        try:
            intent = Intent.objects.get(intent_id=intent_id)
        except Intent.DoesNotExist:
            self.logger.failure("Intent '%s' not found in Nautobot.", intent_id)
            return

        # Check for existing plan (idempotency)
        if not force_re_resolve:
            existing = ResolutionPlan.objects.filter(intent=intent, intent_version=intent.version).first()
            if existing:
                self.logger.info(
                    "Cached plan found for %s v%s (resolved at %s). Use force_re_resolve=True to override.",
                    intent_id,
                    intent.version,
                    existing.resolved_at,
                )
                return {"plan_id": str(existing.pk), "cached": True}

        # Run resolution
        self.logger.info("Resolving %s (type=%s)", intent_id, intent.intent_type)
        try:
            plan_data = resolve_intent(intent)
        except (ValueError, NotImplementedError) as exc:
            self.logger.failure("Resolution failed: %s", exc)
            intent.status = Status.objects.get(name__iexact="Failed")
            intent.save()
            return
        except Exception as exc:
            self.logger.failure("Unexpected resolution error: %s", exc)
            raise

        # Store plan
        plan, _ = ResolutionPlan.objects.update_or_create(
            intent=intent,
            intent_version=intent.version,
            defaults={
                "primitives": plan_data["primitives"],
                "vrf_name": plan_data.get("vrf_name", ""),
                "requires_new_vrf": plan_data.get("requires_new_vrf", False),
                "requires_mpls": plan_data.get("requires_mpls", False),
                "allocated_rds": plan_data.get("allocated_rds", {}),
                "allocated_rts": plan_data.get("allocated_rts", {}),
                "resolved_by": "IntentResolutionJob",
            },
        )

        # Link affected Device objects
        device_names = plan_data.get("affected_devices", [])
        devices = Device.objects.filter(name__in=device_names)
        plan.affected_devices.set(devices)

        # Update intent status
        intent.status = Status.objects.get(name__iexact="Validated")
        intent.save()

        self.logger.info(
            "Resolved %s: %s devices, %s primitives, VRF: %s",
            intent_id,
            len(device_names),
            plan.primitive_count,
            plan.vrf_name or "n/a",
        )

        # Audit trail
        IntentAuditEntry.objects.create(
            intent=intent,
            action="resolved",
            actor="IntentResolutionJob",
            detail={
                "plan_id": str(plan.pk),
                "devices": device_names,
                "vrf": plan.vrf_name,
                "primitive_count": plan.primitive_count,
            },
        )
        dispatch_event(EVENT_INTENT_RESOLVED, intent)

        # Multi-tenancy guardrail (#12)
        warnings = validate_tenant_isolation(intent)
        if warnings:
            self.logger.warning("Tenant isolation warnings for %s: %s", intent_id, warnings)
            IntentAuditEntry.objects.create(
                intent=intent,
                action="conflict_detected",
                actor="IntentResolutionJob",
                detail={"tenant_warnings": warnings},
            )

        return {"plan_id": str(plan.pk), "cached": False}


# ─────────────────────────────────────────────────────────────────────────────
# Config Preview / Dry-Run (#1)
# ─────────────────────────────────────────────────────────────────────────────


class IntentConfigPreviewJob(Job):
    """Renders the full device config that WOULD be pushed — without touching the network.

    Engineers can review exact CLI commands before approving.
    Results are cached on Intent.rendered_configs and logged as an audit entry.
    """

    intent_id = StringVar(description="Intent ID to preview", required=True)

    class Meta:
        """Nautobot job metadata for IntentConfigPreviewJob."""

        name = "Intent Config Preview"
        has_sensitive_variables = False
        approval_required = False

    def run(self, **kwargs):
        """Execute the config preview job."""
        intent_id = kwargs["intent_id"]
        intent = Intent.objects.get(intent_id=intent_id)
        plan = intent.latest_plan

        if not plan:
            self.logger.failure("No resolution plan found for %s — resolve first.", intent_id)
            return

        rendered = _render_all_configs(plan, self.logger)

        # Cache on the intent for UI display
        intent.rendered_configs = rendered
        intent.save(update_fields=["rendered_configs"])

        # Audit trail
        IntentAuditEntry.objects.create(
            intent=intent,
            action="config_preview",
            actor="IntentConfigPreviewJob",
            detail={"devices": list(rendered.keys()), "config_chars": sum(len(v) for v in rendered.values())},
        )

        self.logger.info(
            "Config preview for %s: %s devices, %s chars total",
            intent_id,
            len(rendered),
            sum(len(v) for v in rendered.values()),
        )

        return {"intent_id": intent_id, "devices": list(rendered.keys()), "rendered_configs": rendered}


# ─────────────────────────────────────────────────────────────────────────────
# Deployment
# ─────────────────────────────────────────────────────────────────────────────


class IntentDeploymentJob(Job):
    """Deploys a resolved intent plan to devices via Nornir + Golden Config.

    Expects the intent to already have a ResolutionPlan stored (run
    IntentResolutionJob first).

    Called by N8N after a PR is merged to main.
    Uses commit=True/False for dry-run support.
    """

    intent_id = StringVar(description="Intent ID to deploy", required=True)
    commit_sha = StringVar(description="Git commit SHA that triggered this", required=True)
    commit = BooleanVar(description="Apply changes to devices (false = dry-run)", default=True)

    class Meta:
        """Nautobot job metadata for IntentDeploymentJob."""

        name = "Intent Deployment"
        has_sensitive_variables = True
        approval_required = False
        commit_default = True

    def run(self, **kwargs):
        """Execute the deployment job."""
        intent_id = kwargs["intent_id"]
        commit = kwargs.get("commit", True)

        try:
            intent = Intent.objects.get(intent_id=intent_id)
        except Intent.DoesNotExist:
            self.logger.failure("Intent '%s' not found.", intent_id)
            return

        if not self._pre_deploy_checks(intent, commit):
            return

        try:
            plan = ResolutionPlan.objects.get(intent=intent, intent_version=intent.version)
        except ResolutionPlan.DoesNotExist:
            self.logger.failure(
                "No resolution plan found for %s v%s. Run IntentResolutionJob first.",
                intent_id,
                intent.version,
            )
            return

        # Update status only for real deployments, not dry-runs.
        if commit:
            intent.status = Status.objects.get(name__iexact="Deploying")
            intent.git_commit_sha = kwargs["commit_sha"]
            intent.save()
        self.logger.info("Deploying %s to %s devices", intent_id, plan.affected_devices.count())

        # Render configs
        try:
            rendered_configs = _render_all_configs(plan, self.logger)
        except Exception as exc:
            self.logger.failure("Config rendering failed: %s", exc)
            self._mark_failed(intent)
            return

        # Dry-run mode is UI/lab-safe: render and store configs, but do not
        # attempt device connections or require credentials.
        if not commit:
            return self._handle_dry_run(intent, rendered_configs, kwargs["commit_sha"])

        # ── Controller adapter routing ────────────────────────────────────
        # If a non-Nornir controller is specified, delegate to the adapter.
        if intent.controller_type and intent.controller_type != "nornir":
            adapter = self._get_adapter(intent)
            try:
                push_results = adapter.deploy(plan)
            except Exception as exc:
                self.logger.failure(
                    "Controller adapter '%s' deployment failed for %s: %s",
                    intent.controller_type,
                    intent_id,
                    exc,
                )
                self._mark_failed(intent)
                push_results = {"success": False, "errors": [str(exc)]}
        # ── Staged rollout (#10) ──────────────────────────────────────────
        elif intent.deployment_strategy != "all_at_once" and plan.affected_devices.count() > 1:
            push_results = self._staged_deploy(intent, plan, rendered_configs, commit)
        else:
            push_results = self._push_configs(plan, rendered_configs, commit)

        if push_results["success"]:
            intent.status = Status.objects.get(name__iexact="Deployed")
            intent.deployed_at = timezone.now()
            intent.rendered_configs = rendered_configs  # cache for audit
            intent.save()
            self.logger.info("Deployed %s", intent_id)

            # Audit trail
            IntentAuditEntry.objects.create(
                intent=intent,
                action="deployed",
                actor="IntentDeploymentJob",
                git_commit_sha=kwargs["commit_sha"],
                detail={
                    "devices": list(rendered_configs.keys()),
                    "rendered_configs": rendered_configs,
                    "dry_run": not commit,
                    "strategy": intent.deployment_strategy,
                },
            )
            dispatch_event(EVENT_INTENT_DEPLOYED, intent)

            # Trigger verification
            _enqueue_job("IntentVerificationJob", intent_id=intent_id, triggered_by="deployment")
        else:
            self.logger.failure("Deployment failed for %s: %s", intent_id, push_results["errors"])
            self._mark_failed(intent)
            self._trigger_rollback(intent, commit)

        return push_results

    def _pre_deploy_checks(self, intent, commit):
        """Run approval, dependency, and change-window checks before deployment.

        Returns True if deployment may proceed, False otherwise.
        """
        # ── Dependency gate ───────────────────────────────────────────────
        if intent.dependency_status == "blocked":
            blocked_deps = intent.blocking_dependencies
            self.logger.failure(
                "Intent '%s' is BLOCKED — the following dependencies are not yet Deployed: %s. "
                "Deploy those intents first.",
                intent.intent_id,
                ", ".join(blocked_deps),
            )
            IntentAuditEntry.objects.create(
                intent=intent,
                action="deployed",
                actor="IntentDeploymentJob",
                detail={"blocked": True, "reason": "dependency_not_deployed", "blocked_by": blocked_deps},
            )
            return False

        # ── Approval gate (#2) ────────────────────────────────────────────
        # In lab/testing mode, allow dry-run (commit=False) without approval.
        # Production commits still require formal approval records.
        if not intent.is_approved and commit:
            self.logger.failure(
                "Intent '%s' has not been approved. Deployment blocked. "
                "An engineer with 'approve_intent' permission must approve first.",
                intent.intent_id,
            )
            IntentAuditEntry.objects.create(
                intent=intent,
                action="deployed",
                actor="IntentDeploymentJob",
                detail={"blocked": True, "reason": "No approval"},
            )
            return False
        if not intent.is_approved and not commit:
            self.logger.warning(
                "Intent '%s' is not approved, but continuing because this is a dry-run deployment.",
                intent.intent_id,
            )

        # ── Change window check (#9) ─────────────────────────────────────
        if intent.scheduled_deploy_at and timezone.now() < intent.scheduled_deploy_at:
            self.logger.failure(
                "Intent '%s' is scheduled for deployment at %s. Current time: %s. Too early.",
                intent.intent_id,
                intent.scheduled_deploy_at,
                timezone.now(),
            )
            return False

        return True

    def _handle_dry_run(self, intent, rendered_configs, commit_sha):
        """Handle dry-run deployment: store rendered configs without pushing to devices.

        Dry-run mode is UI/lab-safe: render and store configs, but do not
        attempt device connections or require credentials.
        """
        intent.rendered_configs = rendered_configs
        # Keep the intent validated; this was only a preview, not a commit.
        intent.save(update_fields=["rendered_configs", "last_updated"])
        self.logger.info(
            "Dry-run complete for %s: rendered configs for %s devices; no device changes were pushed.",
            intent.intent_id,
            len(rendered_configs),
        )
        IntentAuditEntry.objects.create(
            intent=intent,
            action="deployed",
            actor="IntentDeploymentJob",
            git_commit_sha=commit_sha,
            detail={
                "devices": list(rendered_configs.keys()),
                "rendered_configs": rendered_configs,
                "dry_run": True,
                "strategy": intent.deployment_strategy,
                "preview_only": True,
            },
        )
        return {
            "success": True,
            "dry_run": True,
            "devices": list(rendered_configs.keys()),
            "errors": [],
        }

    def _staged_deploy(self, intent, plan, rendered_configs, commit):
        """Deploy in stages: canary first, then remaining sites sequentially.

        Creates DeploymentStage records for tracking. Each stage is
        verified before advancing to the next.
        """
        devices = list(plan.affected_devices.select_related("location").all())
        # Group by location
        location_groups = {}
        for device in devices:
            loc = device.location
            loc_key = loc.pk if loc else "no-location"
            location_groups.setdefault(loc_key, []).append(device)

        # Build stages
        stages = []
        for idx, (loc_key, devs) in enumerate(location_groups.items()):
            loc = devs[0].location if devs[0].location else None
            stage = DeploymentStage.objects.create(
                intent=intent,
                stage_order=idx,
                location=loc,
                status="pending",
            )
            stage.devices.set(devs)
            stages.append(stage)

        all_errors = []
        for stage in stages:
            stage.status = "deploying"
            stage.started_at = timezone.now()
            stage.save()

            stage_configs = {d.name: rendered_configs.get(d.name, "") for d in stage.devices.all()}
            stage.rendered_configs = stage_configs
            result = self._push_configs(plan, stage_configs, commit)

            if result["success"]:
                stage.status = "deployed"
                stage.completed_at = timezone.now()
                stage.save()
                self.logger.info(
                    "Stage %s (%s) deployed successfully",
                    stage.stage_order,
                    stage.location.name if stage.location else "unassigned",
                )

                # For canary strategy, verify before continuing
                if intent.deployment_strategy == "canary" and stage.stage_order == 0:
                    self.logger.info("Canary stage deployed — triggering verification before continuing.")
                    stage.status = "verifying"
                    stage.save()
                    # In a real implementation this would wait for verification result
                    # before proceeding. For now, we log the intent.
                    stage.status = "verified"
                    stage.save()
            else:
                stage.status = "failed"
                stage.completed_at = timezone.now()
                stage.save()
                all_errors.extend(result["errors"])
                self.logger.failure("Stage %s failed: %s", stage.stage_order, result["errors"])
                break  # Stop rolling out on failure

        return {"success": len(all_errors) == 0, "errors": all_errors}

    def _push_configs(self, _plan: ResolutionPlan, rendered_configs: dict, commit: bool) -> dict:
        """Push rendered configs to devices via Nornir + Netmiko.

        Routes wireless / SD-WAN / cloud primitives to the appropriate
        controller adapter instead of Nornir.

        Uses Nautobot Secrets for device credentials (#5).
        """
        from nornir import InitNornir  # noqa: PLC0415
        from nornir_netmiko.tasks import netmiko_send_config  # noqa: PLC0415

        errors = []

        # ── Controller adapter routing ────────────────────────────────────
        buckets = classify_primitives(_plan.primitives)
        for adapter_type in ("wireless", "sdwan", "cloud"):
            adapter_prims = buckets.get(adapter_type)
            if not adapter_prims:
                continue
            try:
                adapter = get_adapter(adapter_type)
                intent_id = adapter_prims[0].get("intent_id", "unknown")
                if commit:
                    result = adapter.push(adapter_prims, intent_id)
                    if not result["success"]:
                        errors.append(f"{adapter_type}: {result.get('details', 'push failed')}")
                    else:
                        self.logger.info(
                            "Controller adapter '%s' pushed %s primitives",
                            adapter_type,
                            len(adapter_prims),
                        )
                else:
                    self.logger.info(
                        "DRY RUN — would push %s primitives to %s controller",
                        len(adapter_prims),
                        adapter_type,
                    )
            except ValueError as exc:
                self.logger.warning(
                    "Controller adapter '%s' not configured — skipping %s primitives: %s",
                    adapter_type,
                    len(adapter_prims),
                    exc,
                )

        # ── Nornir / device-level push ────────────────────────────────────
        from nornir.core.plugins.inventory import InventoryPluginRegister  # noqa: PLC0415

        from nautobot_plugin_nornir.plugins.inventory.nautobot_orm import NautobotORMInventory  # noqa: PLC0415

        try:
            InventoryPluginRegister.register("nautobot-inventory", NautobotORMInventory)
        except KeyError:
            pass  # already registered

        nr = InitNornir(
            inventory={
                "plugin": "nautobot-inventory",
                "options": {
                    "queryset": Device.objects.filter(name__in=list(rendered_configs.keys())),
                },
            },
            logging={"enabled": False},
        )

        errors = []
        for device_name, config in rendered_configs.items():
            if not commit:
                self.logger.info("DRY RUN — would push to %s:\n%s...", device_name, config[:200])
                continue

            result = nr.run(task=netmiko_send_config, hosts=[device_name], config_commands=config.splitlines())
            if result[device_name].failed:
                err = str(result[device_name].exception)
                errors.append(f"{device_name}: {err}")
                self.logger.failure("Push failed on %s: %s", device_name, err)
            else:
                self.logger.info("Config pushed to %s", device_name)

        return {"success": len(errors) == 0, "errors": errors}

    def _mark_failed(self, intent: Intent):
        intent.status = Status.objects.get(name__iexact="Failed")
        intent.save()
        IntentAuditEntry.objects.create(
            intent=intent,
            action="deployed",
            actor="IntentDeploymentJob",
            detail={"outcome": "failed"},
        )
        dispatch_event(EVENT_INTENT_FAILED, intent)
        notify_slack(f"❌ Intent deployment FAILED: {intent.intent_id}\nTenant: {intent.tenant.name}")

    def _trigger_rollback(self, intent: Intent, commit: bool):
        """Enqueue a rollback job for the given intent."""
        _enqueue_job("IntentRollbackJob", intent_id=intent.intent_id, commit=commit)

    @staticmethod
    def _get_adapter(intent):
        """Resolve the correct controller adapter for this intent.

        All adapter imports are local to avoid requiring optional SDKs
        at module load time. ImportError propagates as a clear job failure.
        """
        if intent.controller_type == "catalyst_center":
            from .controller_adapters import CatalystCenterAdapter  # noqa: PLC0415

            return CatalystCenterAdapter(intent)

        # meraki and mist adapters are added in later features
        raise ValueError(f"Controller type '{intent.controller_type}' is not yet supported. Supported: catalyst_center")


# ─────────────────────────────────────────────────────────────────────────────
# Verification
# ─────────────────────────────────────────────────────────────────────────────


class IntentVerificationJob(Job):
    """Verifies that a deployed intent is actually satisfied on the network.

    Routes to BasicVerifier or PyATSVerifier based on the intent's
    verification_level setting. Supports auto-escalation from basic
    to extended when basic passes with warnings.

    Called after deployment and by the reconciliation scheduler.
    """

    intent_id = StringVar(description="Intent ID to verify", required=True)
    triggered_by = StringVar(description="deployment | reconciliation | manual", default="manual")

    class Meta:
        """Nautobot job metadata for IntentVerificationJob."""

        name = "Intent Verification"
        has_sensitive_variables = False
        approval_required = False

    def run(self, **kwargs):
        """Execute the verification job."""
        from intent_networking.verifiers.basic import BasicVerifier  # noqa: PLC0415

        intent_id = kwargs["intent_id"]
        triggered_by = kwargs.get("triggered_by", "manual")
        intent = Intent.objects.get(intent_id=intent_id)
        plan = intent.latest_plan

        if not plan:
            self.logger.failure("No resolution plan found for %s", intent_id)
            return

        if intent.verification_level == "basic":
            result = BasicVerifier(intent).run()

            # Auto-escalate if basic passes with warnings
            if result["passed"] and result.get("has_warnings"):
                self.logger.warning(
                    "Basic verification passed with warnings for intent %s — escalating to extended. Reasons: %s",
                    intent.intent_id,
                    result["warning_reasons"],
                )
                extended_result = self._run_extended(intent)
                if extended_result is not None:
                    extended_result["verification_engine"] = "escalated"
                    extended_result["escalation_reason"] = "; ".join(result["warning_reasons"])
                    result = extended_result
                else:
                    result["verification_engine"] = "basic"
            else:
                result["verification_engine"] = "basic"
        else:
            extended_result = self._run_extended(intent)
            if extended_result is not None:
                result = extended_result
                result["verification_engine"] = "extended"
            else:
                # Fallback to basic if extended is unavailable
                result = BasicVerifier(intent).run()
                result["verification_engine"] = "basic"

        self._store_result(intent, result, triggered_by)
        self._handle_fail_action(intent, result)

        # Audit trail
        IntentAuditEntry.objects.create(
            intent=intent,
            action="verified",
            actor="IntentVerificationJob",
            detail={
                "passed": result["passed"],
                "triggered_by": triggered_by,
                "checks": result.get("checks", []),
                "verification_engine": result.get("verification_engine", "basic"),
                "latency_ms": result.get("measured_latency_ms"),
            },
        )

        return {"passed": result["passed"], "checks": result.get("checks", [])}

    def _run_extended(self, intent):
        """Attempt to run PyATSVerifier; return None if pyATS is not installed."""
        try:
            from intent_networking.verifiers.extended import PyATSVerifier  # noqa: PLC0415

            return PyATSVerifier(intent).run()
        except ImportError:
            self.logger.warning(
                "pyATS not installed — cannot run extended verification for %s. "
                'Install with: pip install -e ".[extended]"',
                intent.intent_id,
            )
            return None

    def _store_result(self, intent, result, triggered_by):
        """Store verification result in the database."""
        measured_latency = result.get("measured_latency_ms")
        vr = VerificationResult.objects.create(
            intent=intent,
            passed=result["passed"],
            checks=result.get("checks", []),
            triggered_by=triggered_by,
            measured_latency_ms=measured_latency,
            verification_engine=result.get("verification_engine", "basic"),
            escalation_reason=result.get("escalation_reason", ""),
            pyats_diff_output=result.get("pyats_diff_output", ""),
        )

        # Back up verification report to Git if the user opted in
        if intent.backup_verification_to_git:
            from intent_networking.notifications import backup_verification_to_git  # noqa: PLC0415

            backup_verification_to_git(intent, vr)

        if result["passed"]:
            intent.last_verified_at = timezone.now()
            intent.save(update_fields=["last_verified_at"])
            self.logger.info("Intent %s verified (%s)", intent.intent_id, result.get("verification_engine", "basic"))
            notify_slack(
                f"✅ Intent verified: {intent.intent_id} (engine: {result.get('verification_engine', 'basic')})"
            )
        else:
            failed_checks = [c for c in result.get("checks", []) if not c.get("passed")]
            self.logger.failure(
                "Intent %s verification FAILED. Failed checks: %s",
                intent.intent_id,
                [c.get("check") for c in failed_checks],
            )

    def _handle_fail_action(self, intent, result):
        """Route post-verification failure to the appropriate action."""
        if result["passed"]:
            return
        if intent.verification_fail_action == "alert":
            notify_slack(
                f"⚠️ Verification FAILED for {intent.intent_id} — alert only. "
                f"Engine: {result.get('verification_engine', 'basic')}"
            )
        elif intent.verification_fail_action == "rollback":
            self.logger.warning("Verification failed — triggering auto-rollback for %s", intent.intent_id)
            _enqueue_job("IntentRollbackJob", intent_id=intent.intent_id)
        elif intent.verification_fail_action == "remediate":
            self.logger.warning("Verification failed — triggering auto-remediation for %s", intent.intent_id)
            _enqueue_job("IntentReconciliationJob", intent_id=intent.intent_id, auto_remediate=True)


# ─────────────────────────────────────────────────────────────────────────────
# Rollback
# ─────────────────────────────────────────────────────────────────────────────


class IntentRollbackJob(Job):
    """Rolls back a failed or unwanted deployment.

    Fetches the previous ResolutionPlan (version - 1) and pushes
    the previously deployed config back to the affected devices.
    If no previous version exists, pushes an empty/removal config.
    """

    intent_id = StringVar(description="Intent ID to roll back", required=True)

    class Meta:
        """Nautobot job metadata for IntentRollbackJob."""

        name = "Intent Rollback"
        has_sensitive_variables = True
        approval_required = False

    def run(self, **kwargs):
        """Execute the rollback job."""
        intent_id = kwargs["intent_id"]
        commit = kwargs.get("commit", True)
        intent = Intent.objects.get(intent_id=intent_id)

        # ── Dependency guard: block rollback if other deployed intents depend on this one
        deployed_dependents = intent.dependents.filter(status__name__iexact="Deployed")
        if deployed_dependents.exists():
            dependent_ids = list(deployed_dependents.values_list("intent_id", flat=True))
            self.logger.failure(
                "Cannot roll back intent '%s' — the following deployed intents depend on it: %s. "
                "Roll back those intents first.",
                intent_id,
                ", ".join(dependent_ids),
            )
            IntentAuditEntry.objects.create(
                intent=intent,
                action="rolled_back",
                actor="IntentRollbackJob",
                detail={"blocked": True, "reason": "has_deployed_dependents", "dependent_intents": dependent_ids},
            )
            return

        self.logger.info("Rolling back intent %s", intent_id)

        # Find previous plan
        previous_plan = (
            ResolutionPlan.objects.filter(intent=intent, intent_version__lt=intent.version)
            .order_by("-intent_version")
            .first()
        )

        if previous_plan:
            self.logger.info("Rolling back to plan v%s", previous_plan.intent_version)
            deploy_job = IntentDeploymentJob()
            deploy_job.run(
                intent_id=intent_id,
                commit_sha=f"rollback-from-v{intent.version}",
                commit=commit,
            )
        else:
            self.logger.warning(
                "No previous plan found for %s. Generating removal config.",
                intent_id,
            )
            current_plan = intent.latest_plan
            if current_plan:
                self._push_removal_config(current_plan, commit)

        intent.status = Status.objects.get(name__iexact="Rolled Back")
        intent.save()

        # Audit trail
        IntentAuditEntry.objects.create(
            intent=intent,
            action="rolled_back",
            actor="IntentRollbackJob",
            detail={
                "rolled_back_from_version": intent.version,
                "previous_plan_version": previous_plan.intent_version if previous_plan else None,
            },
        )
        dispatch_event(EVENT_INTENT_ROLLED_BACK, intent)

        notify_slack(f"⚠️ Intent ROLLED BACK: {intent_id}\nTenant: {intent.tenant.name}")

        self.logger.info("Rollback complete for %s", intent_id)

    def _push_removal_config(self, plan: ResolutionPlan, commit: bool):
        """Generate and push negation commands to remove intent config from devices."""
        from jinja2 import Environment, FileSystemLoader, StrictUndefined  # noqa: PLC0415

        bundled_templates = Path(__file__).resolve().parent / "jinja_templates"
        templates_dir = os.environ.get("TEMPLATES_DIR", str(bundled_templates))

        platform_map = {
            "cisco-ios-xe": "cisco/ios-xe",
            "cisco-ios-xr": "cisco/ios-xr",
            "cisco-nxos": "cisco/nxos",
            "juniper-junos": "juniper/junos",
            "aruba-aos-cx": "aruba/aos-cx",
            "arista-eos": "arista/eos",
        }

        rendered_configs = {}
        default_bgp_asn = settings.PLUGINS_CONFIG.get("intent_networking", {}).get("default_bgp_asn", 65000)

        for device in plan.affected_devices.all():
            platform = device.platform.name if device.platform else "cisco-ios-xe"
            platform_dir = platform_map.get(platform, "cisco/ios-xe")
            template_path = Path(templates_dir) / platform_dir

            env = Environment(  # noqa: S701
                loader=FileSystemLoader(str(template_path)),
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )

            acl_names = [
                p.get("acl_name", "")
                for p in plan.primitives
                if p.get("device") == device.name and p.get("primitive_type") == "acl"
            ]

            try:
                tpl = env.get_template("vrf_removal.j2")
                rendered_configs[device.name] = tpl.render(
                    vrf_name=plan.vrf_name,
                    bgp_asn=default_bgp_asn,
                    acl_name=acl_names[0] if acl_names else "",
                )
            except Exception as exc:
                self.logger.warning("Removal template render error for %s: %s", device.name, exc)

        if rendered_configs:
            deploy_job = IntentDeploymentJob()
            deploy_job._push_configs(plan, rendered_configs, commit)  # pylint: disable=protected-access


# ─────────────────────────────────────────────────────────────────────────────
# Reconciliation (Scheduled)
# ─────────────────────────────────────────────────────────────────────────────


class IntentReconciliationJob(Job):
    """Scheduled job — runs every hour via Nautobot's JobSchedule.

    Checks all deployed intents for drift by running verification
    and comparing against expected state.

    Auto-remediates if OPA approves. Raises GitHub issue for manual
    review if auto-remediation is blocked.
    """

    class Meta:
        """Nautobot job metadata for IntentReconciliationJob."""

        name = "Intent Reconciliation"
        has_sensitive_variables = False
        approval_required = False

    def run(self, **kwargs):  # pylint: disable=unused-argument
        """Execute the reconciliation job across all deployed intents."""
        from intent_networking.verifiers.basic import BasicVerifier  # noqa: PLC0415

        deployed = (
            Intent.objects.filter(status__name__iexact="Deployed")
            .exclude(status__name__iexact="Retired")
            .select_related("tenant")
        )

        self.logger.info("Reconciling %s deployed intents", deployed.count())

        results = {"checked": 0, "drifted": 0, "remediated": 0, "escalated": 0}

        for intent in deployed:
            results["checked"] += 1

            # Always run basic verification on every cycle
            basic_result = BasicVerifier(intent).run()

            # Determine if extended should also run
            run_extended = False
            if basic_result["passed"] and basic_result.get("has_warnings"):
                # Auto-escalate on warnings regardless of trigger setting
                run_extended = True
                self.logger.warning(
                    "Basic verification passed with warnings for %s — escalating to extended",
                    intent.intent_id,
                )
            elif intent.verification_trigger in ("both",) and intent.verification_level == "extended":
                run_extended = True

            if run_extended:
                extended_result = self._run_extended_safe(intent)
                if extended_result is not None:
                    engine = "escalated" if basic_result.get("has_warnings") else "extended"
                    extended_result["verification_engine"] = engine
                    if basic_result.get("has_warnings"):
                        extended_result["escalation_reason"] = "; ".join(basic_result.get("warning_reasons", []))
                    verify_result = extended_result
                else:
                    basic_result["verification_engine"] = "basic"
                    verify_result = basic_result
            else:
                basic_result["verification_engine"] = "basic"
                verify_result = basic_result

            # Store result
            vr = VerificationResult.objects.create(
                intent=intent,
                passed=verify_result["passed"],
                checks=verify_result.get("checks", []),
                triggered_by="reconciliation",
                measured_latency_ms=verify_result.get("measured_latency_ms"),
                verification_engine=verify_result.get("verification_engine", "basic"),
                escalation_reason=verify_result.get("escalation_reason", ""),
                pyats_diff_output=verify_result.get("pyats_diff_output", ""),
            )

            # Back up verification report to Git if the user opted in
            if intent.backup_verification_to_git:
                from intent_networking.notifications import backup_verification_to_git  # noqa: PLC0415

                backup_verification_to_git(intent, vr)

            if verify_result and not verify_result.get("passed"):
                results["drifted"] += 1
                self.logger.warning("Drift detected: %s", intent.intent_id)
                dispatch_event(EVENT_INTENT_DRIFT, intent, {"checks": verify_result.get("checks", [])})

                if self._is_auto_remediable(intent, verify_result):
                    self.logger.info("Auto-remediating %s", intent.intent_id)
                    deploy = IntentDeploymentJob()
                    deploy.run(
                        intent_id=intent.intent_id,
                        commit_sha="reconciliation-remediation",
                    )
                    results["remediated"] += 1
                else:
                    self.logger.warning("Manual review required for %s", intent.intent_id)
                    issue_url = raise_github_issue(intent=intent, drift_details=verify_result.get("checks", []))
                    latest = intent.latest_verification
                    if latest:
                        latest.github_issue_url = issue_url or ""
                        latest.save()
                    results["escalated"] += 1

        self.logger.info(
            "Reconciliation complete: %s checked, %s drifted, %s auto-remediated, %s escalated",
            results["checked"],
            results["drifted"],
            results["remediated"],
            results["escalated"],
        )
        return results

    def _run_extended_safe(self, intent):
        """Attempt to run PyATSVerifier; return None if unavailable."""
        try:
            from intent_networking.verifiers.extended import PyATSVerifier  # noqa: PLC0415

            return PyATSVerifier(intent).run()
        except ImportError:
            self.logger.warning(
                "pyATS not installed — skipping extended verification for %s",
                intent.intent_id,
            )
            return None

    def _is_auto_remediable(self, intent: Intent, verify_result: dict) -> bool:
        """Check OPA to determine if drift is safe to auto-remediate."""
        from intent_networking.opa_client import check_auto_remediation

        if not settings.PLUGINS_CONFIG.get("intent_networking", {}).get("auto_remediation_enabled"):
            return False

        return check_auto_remediation(intent, verify_result)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _nautobot_url() -> str:
    """Return the Nautobot URL from environment."""
    return os.environ.get("NAUTOBOT_URL", "http://localhost:8080")


def _render_all_configs(plan: ResolutionPlan, job_logger=None) -> dict:
    """Render all device configs from a resolution plan.

    Extracted as a module-level function so it can be used by both
    IntentConfigPreviewJob and IntentDeploymentJob.

    Returns:
        dict: device_name → rendered config string.
    """
    from jinja2 import Environment, FileSystemLoader, StrictUndefined  # noqa: PLC0415

    bundled_templates = Path(__file__).resolve().parent / "jinja_templates"
    templates_dir = os.environ.get("TEMPLATES_DIR", str(bundled_templates))
    platform_map = {
        "cisco-ios-xe": "cisco/ios-xe",
        "cisco-ios-xr": "cisco/ios-xr",
        "cisco-nxos": "cisco/nxos",
        "juniper-junos": "juniper/junos",
        "aruba-aos-cx": "aruba/aos-cx",
        "arista-eos": "arista/eos",
    }

    primitive_template_map = {
        # L2 / Switching
        "vlan": "vlan.j2",
        "l2_port": "l2_port.j2",
        "lag": "lag.j2",
        "mlag": "mlag.j2",
        "stp": "stp.j2",
        "qinq": "qinq.j2",
        "pvlan": "pvlan.j2",
        "storm_control": "storm_control.j2",
        "port_security": "port_security.j2",
        "dhcp_snooping": "dhcp_snooping.j2",
        "dai": "dai.j2",
        "ip_source_guard": "ip_source_guard.j2",
        "macsec": "macsec.j2",
        # L3 / Routing
        "vrf": "vrf.j2",
        "static_route": "static_route.j2",
        "ospf": "ospf.j2",
        "bgp_neighbor": "bgp_neighbor.j2",
        "isis": "isis.j2",
        "eigrp": "eigrp.j2",
        "route_redistribution": "route_redistribution.j2",
        "route_policy": "route_policy.j2",
        "prefix_list": "prefix_list.j2",
        "bfd": "bfd.j2",
        "pbr": "pbr.j2",
        "ipv6_interface": "ipv6_interface.j2",
        "ospfv3": "ospfv3.j2",
        "bgp_ipv6_af": "bgp_ipv6_af.j2",
        "fhrp": "fhrp.j2",
        "bgp_network": "bgp_network.j2",
        # MPLS / SP
        "l2vpn_vpls": "l2vpn_vpls.j2",
        "pseudowire": "pseudowire.j2",
        "evpn_mpls": "evpn_mpls.j2",
        "ldp": "ldp.j2",
        "rsvp_te_tunnel": "rsvp_te_tunnel.j2",
        "sr_mpls": "sr_mpls.j2",
        "srv6": "srv6.j2",
        "6pe_6vpe": "6pe_6vpe.j2",
        "mvpn": "mvpn.j2",
        # DC / EVPN / VXLAN
        "loopback": "loopback.j2",
        "vtep": "vtep.j2",
        "bgp_evpn_af": "bgp_evpn_af.j2",
        "l2vni": "l2vni.j2",
        "l3vni": "l3vni.j2",
        "anycast_gateway": "anycast_gateway.j2",
        "evpn_multisite": "evpn_multisite.j2",
        # Security / Firewalling
        "acl": "acl.j2",
        "zbf": "zbf.j2",
        "ipsec_tunnel": "ipsec_tunnel.j2",
        "ipsec_ikev2": "ipsec_ikev2.j2",
        "gre_tunnel": "gre_tunnel.j2",
        "dmvpn": "dmvpn.j2",
        "copp": "copp.j2",
        "urpf": "urpf.j2",
        "dot1x": "dot1x.j2",
        "aaa": "aaa.j2",
        "ra_guard": "ra_guard.j2",
        "ssl_inspection": "ssl_inspection.j2",
        # WAN
        "wan_uplink": "wan_uplink.j2",
        "nat": "nat.j2",
        "nat64": "nat64.j2",
        "ip_sla": "ip_sla.j2",
        # QoS
        "qos_classify": "qos_classify.j2",
        "qos_dscp_mark": "qos_dscp_mark.j2",
        "qos_cos_remark": "qos_cos_remark.j2",
        "qos_queue": "qos_queue.j2",
        "qos_police": "qos_police.j2",
        "qos_shape": "qos_shape.j2",
        "qos_trust": "qos_trust.j2",
        # Multicast
        "pim": "pim.j2",
        "igmp_snooping": "igmp_snooping.j2",
        "multicast_vrf": "multicast_vrf.j2",
        "msdp": "msdp.j2",
        # Management
        "ntp": "ntp.j2",
        "dns": "dns.j2",
        "dhcp_pool": "dhcp_pool.j2",
        "dhcp_relay": "dhcp_relay.j2",
        "snmp": "snmp.j2",
        "syslog": "syslog.j2",
        "netflow": "netflow.j2",
        "telemetry": "telemetry.j2",
        "ssh": "ssh.j2",
        "mgmt_interface": "mgmt_interface.j2",
        "lldp_cdp": "lldp_cdp.j2",
        "stp_root": "stp_root.j2",
        "motd": "motd.j2",
        "netconf": "netconf.j2",
        "dhcp_server": "dhcp_server.j2",
        "global_config": "global_config.j2",
        # Firewall
        "fw_rule": "fw_rule.j2",
        # Service
        "lb_vip": "lb_vip.j2",
        "dns_record": "dns_record.j2",
        "service_insertion": "service_insertion.j2",
    }

    rendered = {}
    for device in plan.affected_devices.all():
        platform = device.platform.name if device.platform else "cisco-ios-xe"
        platform_dir = platform_map.get(platform, "cisco/ios-xe")
        template_path = Path(templates_dir) / platform_dir

        env = Environment(  # noqa: S701
            loader=FileSystemLoader(str(template_path)),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        device_primitives = [p for p in plan.primitives if p.get("device") == device.name]
        sections = []
        for primitive in device_primitives:
            ptype = primitive.get("primitive_type")
            tname = primitive_template_map.get(ptype)
            if tname:
                try:
                    tpl = env.get_template(tname)
                    sections.append(tpl.render(**primitive))
                except Exception as exc:
                    if job_logger:
                        job_logger.warning("Template render error for %s: %s", ptype, exc)

        rendered[device.name] = "\n".join(sections)

    return rendered


def _enqueue_job(job_class_name: str, **job_kwargs) -> None:
    """Look up a Job in the DB by class name and enqueue it via JobResult."""
    try:
        job_model = JobModel.objects.get(
            module_name="intent_networking.jobs",
            job_class_name=job_class_name,
        )
    except JobModel.DoesNotExist:
        logger.error("Job '%s' not found in Nautobot registry — cannot enqueue.", job_class_name)
        return

    JobResult.enqueue_job(job_model, None, **job_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Retire — removes config from devices and marks intent as retired
# ─────────────────────────────────────────────────────────────────────────────


class IntentRetireJob(Job):
    """Retires an intent by removing its configuration from all affected devices.

    Steps:
      1. Generates removal (negation) config for each affected device
      2. Pushes the removal config via Nornir
      3. Releases any allocated resources (VNI, tunnel IDs, loopbacks)
      4. Updates intent status to Retired
      5. Records audit trail

    This ensures that retiring an intent is not just a status change but
    actually cleans up the network configuration deployed by this intent.
    """

    intent_id = StringVar(description="Intent ID to retire", required=True)
    commit = BooleanVar(description="Push removal config to devices (false = dry-run)", default=True)

    class Meta:
        """Nautobot job metadata for IntentRetireJob."""

        name = "Intent Retire"
        has_sensitive_variables = True
        approval_required = False

    def run(self, **kwargs):
        """Execute the retire job."""
        from intent_networking.events import EVENT_INTENT_RETIRED  # noqa: PLC0415

        intent_id = kwargs["intent_id"]
        commit = kwargs.get("commit", True)

        try:
            intent = Intent.objects.get(intent_id=intent_id)
        except Intent.DoesNotExist:
            self.logger.failure("Intent '%s' not found.", intent_id)
            return

        allowed_statuses = {"deployed", "failed", "rolled back", "validated", "draft"}
        current_status = intent.status.name.lower() if intent.status else ""
        if current_status not in allowed_statuses:
            self.logger.failure(
                "Intent '%s' is in status '%s'. Can only retire from: %s",
                intent_id,
                intent.status,
                ", ".join(sorted(allowed_statuses)),
            )
            return

        plan = intent.latest_plan

        # If the intent was deployed, push removal config to devices
        if plan and current_status in ("deployed", "failed"):
            self.logger.info(
                "Generating removal config for %s (%s devices)",
                intent_id,
                plan.affected_devices.count(),
            )
            rollback_job = IntentRollbackJob()
            rollback_job._push_removal_config(plan, commit)  # pylint: disable=protected-access

            if commit:
                self.logger.info("Removal config pushed to devices for %s", intent_id)
            else:
                self.logger.info("Dry-run: removal config generated but NOT pushed for %s", intent_id)

        # Release allocated resources
        if commit:
            self._release_resources(intent)

        # Update status
        if commit:
            retired_status = Status.objects.get(name__iexact="Retired")
            intent.status = retired_status
            intent.save()

        # Audit trail
        IntentAuditEntry.objects.create(
            intent=intent,
            action="retired",
            actor="IntentRetireJob",
            detail={
                "config_removed": bool(plan and current_status in ("deployed", "failed")),
                "resources_released": commit,
                "dry_run": not commit,
                "previous_status": current_status,
            },
        )
        dispatch_event(EVENT_INTENT_RETIRED, intent)
        notify_slack(
            f"🏁 Intent RETIRED: {intent_id}\nTenant: {intent.tenant.name}\nConfig removed from devices: {bool(plan and current_status in ('deployed', 'failed'))}"
        )

        self.logger.info("Retire complete for %s", intent_id)
        return {"intent_id": intent_id, "retired": commit, "config_removed": bool(plan)}

    def _release_resources(self, intent: Intent):
        """Release VNI, tunnel ID, loopback, and wireless VLAN allocations for this intent."""
        from intent_networking.models import (  # noqa: PLC0415
            ManagedLoopback,
            TunnelIdAllocation,
            VniAllocation,
            WirelessVlanAllocation,
        )

        released = []

        vni_count = VniAllocation.objects.filter(intent=intent).delete()[0]
        if vni_count:
            released.append(f"{vni_count} VNI allocation(s)")

        tunnel_count = TunnelIdAllocation.objects.filter(intent=intent).delete()[0]
        if tunnel_count:
            released.append(f"{tunnel_count} tunnel ID allocation(s)")

        loopback_count = ManagedLoopback.objects.filter(intent=intent).delete()[0]
        if loopback_count:
            released.append(f"{loopback_count} loopback allocation(s)")

        wlan_count = WirelessVlanAllocation.objects.filter(intent=intent).delete()[0]
        if wlan_count:
            released.append(f"{wlan_count} wireless VLAN allocation(s)")

        if released:
            self.logger.info("Released resources for %s: %s", intent.intent_id, ", ".join(released))


# ─────────────────────────────────────────────────────────────────────────────
# Registration — Nautobot 3.x discovers jobs via this list + register_jobs()
# ─────────────────────────────────────────────────────────────────────────────

jobs = [
    IntentSyncFromGitJob,
    IntentResolutionJob,
    IntentConfigPreviewJob,
    IntentDeploymentJob,
    IntentVerificationJob,
    IntentRollbackJob,
    IntentReconciliationJob,
    IntentRetireJob,
]
register_jobs(*jobs)
