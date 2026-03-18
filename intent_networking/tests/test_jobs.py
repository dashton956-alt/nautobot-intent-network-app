"""Unit tests for intent_networking.jobs module.

Focuses on the testable utilities and data structures in jobs.py:
  - primitive_template_map completeness
  - platform_map entries
  - render_device_configs() function
  - _enqueue_job() error handling
  - Job class Meta properties
"""

from pathlib import Path
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
    jobs,
)

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

    @patch("intent_networking.jobs.JobResult")
    @patch("intent_networking.jobs.JobModel")
    def test_enqueue_calls_job_result(self, mock_jm, mock_jr):
        """Successful enqueue calls JobResult.enqueue_job."""
        from intent_networking.jobs import _enqueue_job

        mock_job_model = MagicMock()
        mock_jm.objects.get.return_value = mock_job_model

        _enqueue_job("IntentResolutionJob", intent_id="test-001")

        mock_jm.objects.get.assert_called_once_with(
            module_name="intent_networking.jobs",
            job_class_name="IntentResolutionJob",
        )
        mock_jr.enqueue_job.assert_called_once()

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

        result = job._pre_deploy_checks(mock_intent, True)
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

        result = job._pre_deploy_checks(mock_intent, True)
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
