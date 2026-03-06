"""Nautobot Jobs for the intent engine.

Jobs run asynchronously via Celery, log to Nautobot's job log,
and can be triggered via the REST API or UI.

Jobs defined here:
  IntentSyncFromGitJob      — creates/updates Intent records from YAML
  IntentResolutionJob       — resolves intent → normalized plan
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
from nautobot.dcim.models import Device
from nautobot.extras.jobs import BooleanVar, Job, StringVar
from nautobot.extras.models import Job as JobModel
from nautobot.extras.models import JobResult, Status
from nautobot.tenancy.models import Tenant

from intent_networking.models import Intent, ResolutionPlan, VerificationResult
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

        return {"plan_id": str(plan.pk), "cached": False}


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

        try:
            plan = ResolutionPlan.objects.get(intent=intent, intent_version=intent.version)
        except ResolutionPlan.DoesNotExist:
            self.logger.failure(
                "No resolution plan found for %s v%s. Run IntentResolutionJob first.",
                intent_id,
                intent.version,
            )
            return

        # Update status
        intent.status = Status.objects.get(name__iexact="Deploying")
        intent.git_commit_sha = kwargs["commit_sha"]
        intent.save()
        self.logger.info("Deploying %s to %s devices", intent_id, plan.affected_devices.count())

        # Render configs via Golden Config
        try:
            rendered_configs = self._render_via_golden_config(plan)
        except Exception as exc:
            self.logger.failure("Config rendering failed: %s", exc)
            self._mark_failed(intent)
            return

        # Push via Nornir
        push_results = self._push_configs(plan, rendered_configs, commit)

        if push_results["success"]:
            intent.status = Status.objects.get(name__iexact="Deployed")
            intent.deployed_at = timezone.now()
            intent.save()
            self.logger.info("Deployed %s", intent_id)

            # Trigger verification
            _enqueue_job("IntentVerificationJob", intent_id=intent_id, triggered_by="deployment")
        else:
            self.logger.failure("Deployment failed for %s: %s", intent_id, push_results["errors"])
            self._mark_failed(intent)
            self._trigger_rollback(intent, commit)

        return push_results

    def _render_via_golden_config(self, plan: ResolutionPlan) -> dict:
        """Use Nautobot Golden Config to render primitives into vendor config.

        Returns:
            dict: device_name → rendered config string.
        """
        rendered = {}

        for device in plan.affected_devices.all():
            platform = device.platform.name if device.platform else "cisco-ios-xe"
            device_primitives = [p for p in plan.primitives if p.get("device") == device.name]
            rendered[device.name] = self._render_device_config(device_primitives, platform)

        return rendered

    def _render_device_config(self, primitives: list, platform: str) -> str:
        """Render all primitives for one device using Jinja2 templates."""
        from jinja2 import Environment, FileSystemLoader, StrictUndefined  # noqa: PLC0415

        # Use bundled templates shipped with the plugin; allow override via env var.
        bundled_templates = Path(__file__).resolve().parent / "jinja_templates"
        templates_dir = os.environ.get("TEMPLATES_DIR", str(bundled_templates))
        platform_map = {
            "cisco-ios-xe": "cisco/ios-xe",
            "cisco-ios-xr": "cisco/ios-xr",
            "juniper-junos": "juniper/junos",
            "aruba-aos-cx": "aruba/aos-cx",
        }
        platform_dir = platform_map.get(platform, "cisco/ios-xe")
        template_path = Path(templates_dir) / platform_dir

        env = Environment(  # noqa: S701
            loader=FileSystemLoader(str(template_path)),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        primitive_template_map = {
            "vrf": "vrf.j2",
            "bgp_neighbor": "bgp_neighbor.j2",
            "acl": "acl.j2",
        }

        sections = []
        for primitive in primitives:
            ptype = primitive.get("primitive_type")
            tname = primitive_template_map.get(ptype)
            if tname:
                try:
                    tpl = env.get_template(tname)
                    sections.append(tpl.render(**primitive))
                except Exception as exc:
                    self.logger.warning("Template render error for %s: %s", ptype, exc)

        return "\n".join(sections)

    def _push_configs(self, _plan: ResolutionPlan, rendered_configs: dict, commit: bool) -> dict:
        """Push rendered configs to devices via Nornir + Netmiko."""
        from nornir import InitNornir  # noqa: PLC0415
        from nornir_netmiko.tasks import netmiko_send_config  # noqa: PLC0415

        nr = InitNornir(
            inventory={
                "plugin": "NautobotInventory",
                "options": {
                    "nautobot_url": _nautobot_url(),
                    "nautobot_token": _nautobot_token(),
                    "filter_parameters": {"name__in": list(rendered_configs.keys())},
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
        notify_slack(f"❌ Intent deployment FAILED: {intent.intent_id}\nTenant: {intent.tenant.name}")

    def _trigger_rollback(self, intent: Intent, commit: bool):
        """Enqueue a rollback job for the given intent."""
        _enqueue_job("IntentRollbackJob", intent_id=intent.intent_id, commit=commit)


# ─────────────────────────────────────────────────────────────────────────────
# Verification
# ─────────────────────────────────────────────────────────────────────────────


class IntentVerificationJob(Job):
    """Verifies that a deployed intent is actually satisfied on the network.

    Checks:
      - VRF present on all affected devices
      - BGP sessions established
      - Expected prefixes received
      - Latency SLA met (if specified in intent)

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
        intent_id = kwargs["intent_id"]
        triggered_by = kwargs.get("triggered_by", "manual")
        intent = Intent.objects.get(intent_id=intent_id)
        plan = intent.latest_plan

        if not plan:
            self.logger.failure("No resolution plan found for %s", intent_id)
            return

        checks = []
        all_passed = True
        measured_latency = None

        for device in plan.affected_devices.all():
            device_state = self._collect_device_state(device, plan)

            # Check 1: VRF present
            vrf_present = plan.vrf_name in device_state.get("vrfs", [])
            checks.append(
                {
                    "device": device.name,
                    "check": "vrf_present",
                    "passed": vrf_present,
                    "detail": f"VRF {plan.vrf_name} {'present' if vrf_present else 'MISSING'}",
                }
            )
            if not vrf_present:
                all_passed = False

            # Check 2: BGP established
            bgp_state = device_state.get("bgp_sessions", {}).get(plan.vrf_name, {}).get("state", "Unknown")
            bgp_up = bgp_state == "Established"
            checks.append(
                {
                    "device": device.name,
                    "check": "bgp_established",
                    "passed": bgp_up,
                    "detail": f"BGP state: {bgp_state}",
                }
            )
            if not bgp_up:
                all_passed = False

            # Check 3: Prefix count
            prefixes_received = device_state.get("prefix_count", {}).get(plan.vrf_name, 0)
            min_prefixes = intent.intent_data.get("policy", {}).get("min_prefixes", 1)
            prefix_ok = prefixes_received >= min_prefixes
            checks.append(
                {
                    "device": device.name,
                    "check": "prefix_count",
                    "passed": prefix_ok,
                    "detail": f"{prefixes_received} prefixes received (min: {min_prefixes})",
                }
            )
            if not prefix_ok:
                all_passed = False

        # Check 4: Latency SLA
        max_latency = intent.intent_data.get("policy", {}).get("max_latency_ms")
        if max_latency:
            # Pick first device + first destination prefix for the SLA probe
            probe_device = plan.affected_devices.first()
            dest_prefixes = intent.intent_data.get("destination", {}).get("prefixes", [])
            probe_dest = dest_prefixes[0].split("/")[0] if dest_prefixes else ""
            measured_latency = self._measure_latency(device=probe_device, destination=probe_dest)
            latency_ok = measured_latency <= max_latency
            checks.append(
                {
                    "check": "latency_sla",
                    "passed": latency_ok,
                    "detail": f"{measured_latency}ms measured, {max_latency}ms SLA",
                }
            )
            if not latency_ok:
                all_passed = False

        # Store result
        VerificationResult.objects.create(
            intent=intent,
            passed=all_passed,
            checks=checks,
            triggered_by=triggered_by,
            measured_latency_ms=measured_latency,
        )

        if all_passed:
            intent.last_verified_at = timezone.now()
            intent.save()
            self.logger.info("Intent %s verified", intent_id)
            notify_slack(f"✅ Intent verified: {intent_id}\nLatency: {measured_latency}ms" if measured_latency else "")
        else:
            failed_checks = [c for c in checks if not c["passed"]]
            self.logger.failure(
                "Intent %s verification FAILED. Failed checks: %s",
                intent_id,
                [c["check"] for c in failed_checks],
            )

        return {"passed": all_passed, "checks": checks}

    def _collect_device_state(self, device: Device, plan: ResolutionPlan) -> dict:
        """Collect live state from device via Nornir."""
        from nornir import InitNornir  # noqa: PLC0415
        from nornir_netmiko.tasks import netmiko_send_command  # noqa: PLC0415

        nr = InitNornir(
            inventory={
                "plugin": "NautobotInventory",
                "options": {
                    "nautobot_url": _nautobot_url(),
                    "nautobot_token": _nautobot_token(),
                    "filter_parameters": {"name": device.name},
                },
            },
            logging={"enabled": False},
        )

        state = {"vrfs": [], "bgp_sessions": {}, "prefix_count": {}}

        # Collect VRF list
        vrf_result = nr.run(task=netmiko_send_command, command_string="show vrf brief", use_textfsm=True)
        if not vrf_result[device.name].failed:
            for row in vrf_result[device.name].result:
                state["vrfs"].append(row.get("name", ""))

        # Collect BGP state for the VRF
        bgp_result = nr.run(
            task=netmiko_send_command,
            command_string=f"show bgp vpnv4 unicast vrf {plan.vrf_name} summary",
            use_textfsm=True,
        )
        if not bgp_result[device.name].failed:
            for neighbor in bgp_result[device.name].result:
                state["bgp_sessions"][plan.vrf_name] = {
                    "state": neighbor.get("state_pfxrcd", "Unknown"),
                    "prefixes": neighbor.get("state_pfxrcd", 0),
                }

        return state

    def _measure_latency(self, device: Device = None, destination: str = "") -> int:
        """Measure latency from *device* to *destination* via ping.

        Uses Nornir + Netmiko to execute a ping on the device and parses
        the average round-trip time from the output.

        Returns:
            Average round-trip time in milliseconds.  Returns 0 if
            measurement is unavailable or fails.
        """
        if not device or not destination:
            return 0

        try:
            from nornir import InitNornir  # noqa: PLC0415
            from nornir_netmiko.tasks import netmiko_send_command  # noqa: PLC0415
        except ImportError:
            self.logger.warning("nornir/nornir_netmiko not installed — latency measurement skipped.")
            return 0

        try:
            nr = InitNornir(
                inventory={
                    "plugin": "NautobotInventory",
                    "options": {
                        "nautobot_url": _nautobot_url(),
                        "nautobot_token": _nautobot_token(),
                        "filter_parameters": {"name": device.name},
                    },
                },
                logging={"enabled": False},
            )
            result = nr.run(
                task=netmiko_send_command,
                command_string=f"ping {destination} repeat 5",
            )
            if result[device.name].failed:
                return 0

            import re  # noqa: PLC0415

            output = str(result[device.name].result)
            # Parse 'round-trip min/avg/max = X/Y/Z ms' or similar
            match = re.search(r"[=/]\s*(\d+)/(\d+)/(\d+)", output)
            if match:
                return int(match.group(2))  # avg
            return 0
        except Exception as exc:
            self.logger.warning("Latency measurement failed: %s", exc)
            return 0


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
            "juniper-junos": "juniper/junos",
            "aruba-aos-cx": "aruba/aos-cx",
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
                p.get("acl_name", "") for p in plan.primitives
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
        deployed = Intent.objects.filter(status__name__iexact="Deployed").select_related("tenant")

        self.logger.info("Reconciling %s deployed intents", deployed.count())

        results = {"checked": 0, "drifted": 0, "remediated": 0, "escalated": 0}

        for intent in deployed:
            results["checked"] += 1

            # Run verification check inline
            verify = IntentVerificationJob()
            verify_result = verify.run(
                intent_id=intent.intent_id,
                triggered_by="reconciliation",
            )

            if verify_result and not verify_result.get("passed"):
                results["drifted"] += 1
                self.logger.warning("Drift detected: %s", intent.intent_id)

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
                    # Record on the verification result
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


def _nautobot_token() -> str:
    """Return the Nautobot API token from environment."""
    token = os.environ.get("NAUTOBOT_TOKEN")
    if not token:
        raise RuntimeError("NAUTOBOT_TOKEN environment variable is required")
    return token


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
