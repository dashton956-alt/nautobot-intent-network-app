"""Unit tests for intent_networking.jobs module.

Focuses on the testable utilities and data structures in jobs.py:
  - primitive_template_map completeness
  - platform_map entries
  - render_device_configs() function
  - _enqueue_job() error handling
  - Job class Meta properties
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from intent_networking.jobs import (
    IntentConfigPreviewJob,
    IntentDeploymentJob,
    IntentReconciliationJob,
    IntentResolutionJob,
    IntentRetireJob,
    IntentRollbackJob,
    IntentSyncFromGitJob,
    IntentVerificationJob,
    _platform_slug,
    jobs,
)


class PlatformSlugTest(SimpleTestCase):
    """Render template-dir resolution must key off network_driver, not just name."""

    @staticmethod
    def _dev(name=None, network_driver=None):
        plat = SimpleNamespace(name=name, network_driver=network_driver) if (name or network_driver) else None
        return SimpleNamespace(platform=plat)

    def test_driver_preferred_over_human_name(self):
        self.assertEqual(_platform_slug(self._dev(name="Arista EOS", network_driver="arista_eos")), "arista-eos")

    def test_slug_name_still_works(self):
        self.assertEqual(_platform_slug(self._dev(name="arista-eos")), "arista-eos")

    def test_no_platform_defaults_to_ios_xe(self):
        self.assertEqual(_platform_slug(self._dev()), "cisco-ios-xe")


# ─────────────────────────────────────────────────────────────────────────────
# Job registration
# ─────────────────────────────────────────────────────────────────────────────


class JobRegistrationTest(SimpleTestCase):
    """Verify all job classes are registered."""

    def test_jobs_list_contains_all_registered(self):
        """The `jobs` list has all 8 job classes."""
        self.assertEqual(len(jobs), 8)
        expected = {
            IntentSyncFromGitJob,
            IntentResolutionJob,
            IntentConfigPreviewJob,
            IntentDeploymentJob,
            IntentVerificationJob,
            IntentRollbackJob,
            IntentReconciliationJob,
            IntentRetireJob,
        }
        self.assertEqual(set(jobs), expected)

    def test_all_jobs_have_meta_name(self):
        """Every job must define a human-readable Meta.name."""
        for job_cls in jobs:
            meta_name = getattr(job_cls.Meta, "name", None)
            self.assertIsNotNone(meta_name, f"{job_cls.__name__} missing Meta.name")
            self.assertGreater(len(meta_name), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Job Meta attributes
# ─────────────────────────────────────────────────────────────────────────────


class JobMetaTest(SimpleTestCase):
    """Test Job Meta attribute values."""

    def test_sync_from_git_meta(self):
        """IntentSyncFromGitJob has expected meta."""
        self.assertEqual(IntentSyncFromGitJob.Meta.name, "Sync Intent from Git")
        self.assertFalse(IntentSyncFromGitJob.Meta.has_sensitive_variables)

    def test_resolution_meta(self):
        """IntentResolutionJob has expected meta."""
        self.assertEqual(IntentResolutionJob.Meta.name, "Intent Resolution")

    def test_deployment_meta(self):
        """IntentDeploymentJob has expected meta."""
        self.assertEqual(IntentDeploymentJob.Meta.name, "Intent Deployment")

    def test_verification_meta(self):
        """IntentVerificationJob has expected meta."""
        self.assertEqual(IntentVerificationJob.Meta.name, "Intent Verification")

    def test_rollback_meta(self):
        """IntentRollbackJob has expected meta."""
        self.assertEqual(IntentRollbackJob.Meta.name, "Intent Rollback")

    def test_reconciliation_meta(self):
        """IntentReconciliationJob has expected meta."""
        self.assertEqual(IntentReconciliationJob.Meta.name, "Intent Reconciliation")

    def test_config_preview_meta(self):
        """IntentConfigPreviewJob has expected meta."""
        self.assertEqual(IntentConfigPreviewJob.Meta.name, "Intent Config Preview")


# ─────────────────────────────────────────────────────────────────────────────
# Jinja template directory structure
# ─────────────────────────────────────────────────────────────────────────────


class JinjaTemplateDirectoryTest(SimpleTestCase):
    """Verify the jinja_templates directory exists with expected platforms."""

    EXPECTED_PLATFORMS = [
        "cisco/ios-xe",
        "cisco/ios-xr",
        "cisco/nxos",
        "juniper/junos",
        "aruba/aos-cx",
        "arista/eos",
    ]

    def test_templates_base_dir_exists(self):
        """jinja_templates/ directory exists in the plugin package."""
        base_dir = Path(__file__).resolve().parent.parent / "jinja_templates"
        self.assertTrue(base_dir.is_dir(), f"Missing templates directory: {base_dir}")

    def test_all_platform_dirs_exist(self):
        """Each platform has a sub-directory under jinja_templates/."""
        base_dir = Path(__file__).resolve().parent.parent / "jinja_templates"
        for platform_path in self.EXPECTED_PLATFORMS:
            platform_dir = base_dir / platform_path
            self.assertTrue(
                platform_dir.is_dir(),
                f"Missing platform template directory: {platform_dir}",
            )

    def test_each_platform_has_at_least_one_template(self):
        """Each platform should have at least one .j2 template file."""
        base_dir = Path(__file__).resolve().parent.parent / "jinja_templates"
        for platform_path in self.EXPECTED_PLATFORMS:
            platform_dir = base_dir / platform_path
            j2_files = list(platform_dir.glob("*.j2"))
            self.assertGreater(
                len(j2_files),
                0,
                f"No .j2 templates found for {platform_path}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# _enqueue_job
# ─────────────────────────────────────────────────────────────────────────────


class EnqueueJobTest(SimpleTestCase):
    """Test _enqueue_job helper."""

    @patch("django.contrib.auth.get_user_model")
    @patch("intent_networking.jobs.JobResult")
    @patch("intent_networking.jobs.JobModel")
    def test_enqueue_calls_job_result(self, mock_jm, mock_jr, mock_get_user):
        """Successful enqueue calls JobResult.enqueue_job."""
        from intent_networking.jobs import _enqueue_job

        mock_job_model = MagicMock()
        mock_jm.objects.get.return_value = mock_job_model
        mock_user = MagicMock()
        # No requesting_user -> falls back to the auto-provisioned service account.
        mock_get_user.return_value.objects.get_or_create.return_value = (mock_user, False)

        _enqueue_job("IntentResolutionJob", intent_id="test-001")

        mock_jm.objects.get.assert_called_once_with(
            module_name="intent_networking.jobs",
            job_class_name="IntentResolutionJob",
        )
        mock_jr.enqueue_job.assert_called_once()

    @patch("django.contrib.auth.get_user_model")
    @patch("intent_networking.jobs.JobResult")
    @patch("intent_networking.jobs.JobModel")
    def test_enqueue_uses_requesting_user_without_service_account(self, mock_jm, mock_jr, mock_get_user):
        """A supplied requesting_user is used directly (no service-account lookup)."""
        from intent_networking.jobs import _enqueue_job

        mock_jm.objects.get.return_value = MagicMock()
        requester = MagicMock()

        _enqueue_job("IntentVerificationJob", requesting_user=requester, intent_id="test-002")

        mock_get_user.return_value.objects.get_or_create.assert_not_called()
        args, _kwargs = mock_jr.enqueue_job.call_args
        self.assertIs(args[1], requester)

    @patch("intent_networking.jobs.JobModel")
    def test_enqueue_handles_missing_job(self, mock_jm):
        """When job not found, logs error but doesn't raise."""
        from intent_networking.jobs import _enqueue_job

        mock_jm.DoesNotExist = Exception
        mock_jm.objects.get.side_effect = Exception("not found")

        # Should not raise
        _enqueue_job("NonexistentJob")


# ─────────────────────────────────────────────────────────────────────────────
# Intent Dependency Graph — deployment and rollback guards
# ─────────────────────────────────────────────────────────────────────────────


class IntentDependencyDeploymentTest(SimpleTestCase):
    """Test dependency checks in deployment and rollback jobs."""

    @patch("intent_networking.jobs.IntentAuditEntry")
    def test_deployment_blocked_when_dependency_not_deployed(self, mock_audit):
        """IntentDeploymentJob._pre_deploy_checks returns False when dependency is blocked."""
        mock_intent = MagicMock()
        mock_intent.intent_id = "child-001"
        mock_intent.dependency_status = "blocked"
        mock_intent.blocking_dependencies = ["parent-001", "parent-002"]
        mock_intent.is_approved = True
        mock_intent.scheduled_deploy_at = None

        job = IntentDeploymentJob()
        job.logger = MagicMock()

        result = job._pre_deploy_checks(mock_intent, True)  # pylint: disable=protected-access
        self.assertFalse(result)
        job.logger.failure.assert_called_once()
        self.assertIn("parent-001", job.logger.failure.call_args[0][2])

    @patch("intent_networking.jobs.IntentAuditEntry")
    def test_deployment_proceeds_when_all_deps_deployed(self, mock_audit):
        """IntentDeploymentJob._pre_deploy_checks returns True when dependencies are ready."""
        mock_intent = MagicMock()
        mock_intent.intent_id = "child-001"
        mock_intent.dependency_status = "ready"
        mock_intent.is_approved = True
        mock_intent.scheduled_deploy_at = None

        job = IntentDeploymentJob()
        job.logger = MagicMock()

        result = job._pre_deploy_checks(mock_intent, True)  # pylint: disable=protected-access
        self.assertTrue(result)

    @patch("intent_networking.jobs.Intent")
    @patch("intent_networking.jobs.IntentAuditEntry")
    @patch("intent_networking.jobs.notify_slack")
    def test_rollback_blocked_when_dependents_exist(self, mock_slack, mock_audit, mock_intent_cls):
        """IntentRollbackJob.run aborts when deployed intents depend on this one."""
        mock_intent = MagicMock()
        mock_intent.intent_id = "parent-001"

        mock_dependent = MagicMock()
        mock_dependent.intent_id = "child-001"
        mock_dependents_qs = MagicMock()
        mock_dependents_qs.exists.return_value = True
        mock_dependents_qs.values_list.return_value = ["child-001"]
        mock_intent.dependents.filter.return_value = mock_dependents_qs

        mock_intent_cls.objects.get.return_value = mock_intent

        job = IntentRollbackJob()
        job.logger = MagicMock()

        job.run(intent_id="parent-001")

        job.logger.failure.assert_called_once()
        self.assertIn("child-001", job.logger.failure.call_args[0][2])


class RenderAllConfigsTest(SimpleTestCase):
    """_render_all_configs must hard-fail on render errors, never emit partial config."""

    @staticmethod
    def _plan(primitives, driver="arista_eos", platform_name="arista-eos"):
        device = SimpleNamespace(
            name="leaf-01",
            platform=SimpleNamespace(name=platform_name, network_driver=driver),
        )
        return SimpleNamespace(
            affected_devices=SimpleNamespace(all=lambda: [device]),
            primitives=primitives,
        )

    def test_complete_primitive_renders(self):
        from intent_networking.jobs import _render_all_configs

        plan = self._plan(
            [
                {
                    "primitive_type": "static_route",
                    "device": "leaf-01",
                    "prefix": "10.0.0.0/8",
                    "next_hop": "192.0.2.1",
                    "exit_interface": "",
                    "admin_distance": 1,
                    "vrf": "",
                    "tag": None,
                    "track": None,
                    "name": "",
                    "intent_id": "t-001",
                }
            ]
        )
        rendered = _render_all_configs(plan)
        self.assertIn("ip route 10.0.0.0/8 192.0.2.1", rendered["leaf-01"])

    def test_render_error_raises_instead_of_partial_config(self):
        from intent_networking.jobs import ConfigRenderError, _render_all_configs

        # static_route missing every field the template references → UndefinedError
        plan = self._plan([{"primitive_type": "static_route", "device": "leaf-01", "intent_id": "t-002"}])
        job_logger = MagicMock()
        with self.assertRaises(ConfigRenderError) as ctx:
            _render_all_configs(plan, job_logger)
        self.assertIn("leaf-01", str(ctx.exception))
        self.assertIn("static_route", str(ctx.exception))
        job_logger.warning.assert_called()

    def test_unmapped_primitive_is_skipped_not_fatal(self):
        from intent_networking.jobs import _render_all_configs

        # Adapter-routed types have no template mapping and must not raise.
        plan = self._plan([{"primitive_type": "wireless_ssid", "device": "leaf-01"}])
        rendered = _render_all_configs(plan)
        self.assertEqual(rendered["leaf-01"], "")


class RenderRemovalConfigsTest(SimpleTestCase):
    """_render_removal_configs must warn (not silently skip) on missing removal templates."""

    def test_missing_removal_template_logs_warning(self):
        from intent_networking.jobs import _render_removal_configs

        # eigrp has no removal template on cisco/ios-xe — must warn, not raise.
        device = SimpleNamespace(
            name="rtr-01",
            platform=SimpleNamespace(name="cisco-ios-xe", network_driver="cisco_xe"),
        )
        plan = SimpleNamespace(
            affected_devices=SimpleNamespace(all=lambda: [device]),
            primitives=[{"primitive_type": "eigrp", "device": "rtr-01", "asn": 100}],
        )
        job_logger = MagicMock()
        rendered = _render_removal_configs(plan, job_logger)
        self.assertEqual(rendered["rtr-01"], "")
        warning_text = " ".join(str(c) for c in job_logger.warning.call_args_list)
        self.assertIn("No removal template", warning_text)
        self.assertIn("eigrp", warning_text)
