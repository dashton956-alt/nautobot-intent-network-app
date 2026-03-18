"""Nautobot GitRepository datasource integration for intent YAML files.

When a user configures a GitRepository in Nautobot with the
"intent definitions" provided content type, syncing that repo will
automatically discover ``intents/*.yaml`` files, parse them and
create / update Intent records — no CI pipeline or REST API call needed.

This is the Nautobot-native "pull" model for Git integration.
The legacy ``sync-from-git`` REST endpoint still works as a "push"
alternative for CI-driven workflows.

File exclusion
--------------
Users can place a ``.intentignore`` file in the repository root **or**
inside the intent directory to exclude files from sync.  The file uses
``fnmatch``-style glob patterns, one per line:

    # Skip test fixtures
    tests/**
    test_*.yaml
    **/scratch/**

Blank lines and lines starting with ``#`` are treated as comments.
"""

import fnmatch
import logging
import os
import re
from pathlib import PurePosixPath

import yaml
from django.core.exceptions import ValidationError
from nautobot.extras.choices import LogLevelChoices
from nautobot.extras.models import Status
from nautobot.extras.registry import DatasourceContent
from nautobot.tenancy.models import Tenant

logger = logging.getLogger(__name__)

CONTENT_IDENTIFIER = "intent_networking.intent_definitions"
INTENT_DIRS = ("intents", "intent_definitions", "intent-definitions")
INTENTIGNORE_FILENAME = ".intentignore"


# ─────────────────────────────────────────────────────────────────────────────
# .intentignore helpers
# ─────────────────────────────────────────────────────────────────────────────


def _load_ignore_patterns(*search_dirs):
    """Load glob patterns from ``.intentignore`` files in the given directories.

    Patterns are collected from every ``.intentignore`` found (repo root and
    the intent directory may both contain one).  Blank lines and comment
    lines (starting with ``#``) are skipped.

    Returns:
        list[str]: De-duplicated list of glob patterns (order-preserved).
    """
    patterns: list[str] = []
    seen: set[str] = set()
    for directory in search_dirs:
        ignore_path = os.path.join(directory, INTENTIGNORE_FILENAME)
        if not os.path.isfile(ignore_path):
            continue
        with open(ignore_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line not in seen:
                    seen.add(line)
                    patterns.append(line)
    return patterns


def _is_ignored(rel_path, patterns):
    """Check whether *rel_path* matches any of the ignore *patterns*.

    Supports familiar globs (``*.yaml``, ``tests/*``) and recursive
    double-star patterns (``**/scratch/**``).  The match is tested against:

    1. The full relative path  (``subdir/file.yaml``)
    2. The filename alone      (``file.yaml``)

    This gives both directory-level and filename-level control.
    """
    # Normalise to forward slashes for consistent matching (covers Windows backslashes too)
    rel_path = rel_path.replace("\\", "/")
    basename = rel_path.rsplit("/", 1)[-1]
    path = PurePosixPath(rel_path)
    for pattern in patterns:
        if "**" in pattern:
            # PurePosixPath.match with leading ** won't match zero directories,
            # so also try stripping the leading **/ to allow zero-segment matches.
            if path.match(pattern):
                return True
            stripped = pattern.lstrip("*").lstrip("/")
            if stripped and path.match(stripped):
                return True
        elif fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(basename, pattern):
            return True
    return False


# Regex for a standard 5-field cron expression (minute hour dom month dow).
_CRON_FIELD = r"(\*(/\d+)?|(\d+(-\d+)?(,\d+(-\d+)?)*)(/\d+)?)"
_CRON_RE = re.compile(rf"^\s*{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s+{_CRON_FIELD}\s*$")


def _is_valid_cron(expression):
    """Return True if *expression* looks like a valid 5-field cron expression.

    Uses a lightweight regex check. For production use, ``croniter`` provides
    stricter validation and is preferred when available.
    """
    try:
        from croniter import croniter  # noqa: PLC0415

        croniter(expression)
        return True
    except (ImportError, ValueError, TypeError, KeyError):
        # croniter not installed or invalid expression — fall back to regex
        pass
    return bool(_CRON_RE.match(expression))


# ─────────────────────────────────────────────────────────────────────────────
# Callback (registered in datasource_contents below)
# ─────────────────────────────────────────────────────────────────────────────


def refresh_git_intent_definitions(repository_record, job_result, delete=False):
    """Callback invoked by Nautobot when a GitRepository is synced.

    Args:
        repository_record: The GitRepository model instance being synced.
        job_result: A JobResult for structured logging.
        delete: True when the repo is being removed from Nautobot.
    """
    if CONTENT_IDENTIFIER not in repository_record.provided_contents:
        return

    if delete:
        _delete_repo_intents(repository_record, job_result)
    else:
        _sync_repo_intents(repository_record, job_result)


def _sync_repo_intents(repository_record, job_result):
    """Walk the repo filesystem and create / update Intent records."""
    from intent_networking.models import Intent

    repo_path = repository_record.filesystem_path

    # Locate the intent directory inside the cloned repo
    intent_dir = None
    for candidate in INTENT_DIRS:
        candidate_path = os.path.join(repo_path, candidate)
        if os.path.isdir(candidate_path):
            intent_dir = candidate_path
            break

    if intent_dir is None:
        msg = (
            f"No intent directory found in repository '{repository_record.name}'. "
            f"Expected one of: {', '.join(INTENT_DIRS)}"
        )
        logger.warning(msg)
        job_result.log(msg, level_choice=LogLevelChoices.LOG_WARNING, grouping="intent definitions")
        return

    # Load .intentignore patterns (repo root + intent directory)
    ignore_patterns = _load_ignore_patterns(repo_path, intent_dir)
    if ignore_patterns:
        msg = f"Loaded {len(ignore_patterns)} ignore pattern(s) from .intentignore"
        job_result.log(msg, grouping="intent definitions")

    # Collect all YAML files (including nested subdirectories)
    yaml_files = []
    ignored_count = 0
    for root, _dirs, files in os.walk(intent_dir):
        for fname in sorted(files):
            if not fname.endswith((".yaml", ".yml", ".json")):
                continue
            full_path = os.path.join(root, fname)
            rel_to_intent_dir = os.path.relpath(full_path, intent_dir)
            if ignore_patterns and _is_ignored(rel_to_intent_dir, ignore_patterns):
                ignored_count += 1
                logger.debug("Ignoring '%s' (matched .intentignore pattern)", rel_to_intent_dir)
                continue
            yaml_files.append(full_path)

    if ignored_count:
        msg = f"Skipped {ignored_count} file(s) matching .intentignore patterns"
        job_result.log(msg, grouping="intent definitions")

    if not yaml_files:
        msg = f"No YAML/JSON files found in '{intent_dir}'"
        job_result.log(msg, level_choice=LogLevelChoices.LOG_WARNING, grouping="intent definitions")
        return

    msg = f"Found {len(yaml_files)} intent file(s) in '{repository_record.name}'"
    job_result.log(msg, grouping="intent definitions")

    try:
        draft_status = Status.objects.get(name__iexact="Draft")
    except Status.DoesNotExist:
        draft_status = Status.objects.first()
        logger.warning("'Draft' status not found in Nautobot; falling back to '%s'", draft_status)

    synced_intent_ids = set()
    stats = {"created": 0, "updated": 0, "errors": 0}

    for filepath in yaml_files:
        rel_path = os.path.relpath(filepath, repo_path)
        try:
            with open(filepath, "r", encoding="utf-8") as fd:
                intent_yaml = yaml.safe_load(fd)

            if not isinstance(intent_yaml, dict):
                raise ValueError("File must contain a YAML mapping (dict)")  # noqa: TRY301

            # Unwrap top-level "intent:" key if present (e.g. `intent: { id: ... }`)
            if "intent" in intent_yaml and isinstance(intent_yaml["intent"], dict):
                intent_yaml = intent_yaml["intent"]

            intent_id = intent_yaml.get("id")
            if not intent_id:
                raise ValueError("Intent file must have an 'id' field")  # noqa: TRY301

            # Resolve tenant — case-insensitive match so "acme-corp" == "Acme-Corp"
            tenant_name = intent_yaml.get("tenant")
            if not tenant_name:
                raise ValueError("Intent file must have a 'tenant' field")  # noqa: TRY301

            try:
                tenant = Tenant.objects.get(name__iexact=tenant_name)
            except Tenant.DoesNotExist as exc:
                raise ValueError(  # noqa: TRY301
                    f"Tenant '{tenant_name}' not found in Nautobot. Create the tenant before syncing intents."
                ) from exc

            # Build update fields; include status only for new records so that
            # existing intents keep whatever status they already have.
            # Parse optional verification block with safe defaults
            verification_block = intent_yaml.get("verification", {})
            v_level = verification_block.get("level", "basic")
            v_trigger = verification_block.get("trigger", "on_deploy")
            v_schedule = verification_block.get("schedule", None)
            v_fail_action = verification_block.get("fail_action", "alert")

            # Validate cron expression when trigger requires a schedule
            if v_trigger in ("scheduled", "both") and v_schedule:
                if not _is_valid_cron(v_schedule):
                    raise ValidationError(  # noqa: TRY301
                        f"Invalid cron expression '{v_schedule}' in verification.schedule for intent '{intent_id}'."
                    )

            update_fields = {
                "version": intent_yaml.get("version", 1),
                "intent_type": intent_yaml.get("type", "connectivity"),
                "tenant": tenant,
                "intent_data": intent_yaml,
                "change_ticket": intent_yaml.get("change_ticket", ""),
                "git_commit_sha": repository_record.current_head or "",
                "git_branch": repository_record.branch or "",
                "git_repository": repository_record,
                "verification_level": v_level,
                "verification_trigger": v_trigger,
                "verification_schedule": v_schedule,
                "verification_fail_action": v_fail_action,
            }
            is_new = not Intent.objects.filter(intent_id=intent_id).exists()
            if is_new:
                update_fields["status"] = draft_status

            intent, created = Intent.objects.update_or_create(
                intent_id=intent_id,
                defaults=update_fields,
            )
            # Allow the YAML to explicitly override status on existing intents.
            if "status" in intent_yaml and not created:
                status_name = intent_yaml["status"]
                try:
                    new_status = Status.objects.get(name__iexact=status_name)
                    intent.status = new_status
                    intent.save()
                except Status.DoesNotExist:
                    pass

            synced_intent_ids.add(intent_id)
            action = "Created" if created else "Updated"
            stats["created" if created else "updated"] += 1

            msg = f"{action} intent '{intent_id}' v{intent.version} from `{rel_path}`"
            job_result.log(msg, grouping="intent definitions")

        except Exception as exc:
            stats["errors"] += 1
            msg = f"Error loading intent from `{rel_path}`: {exc}"
            logger.error(msg)
            job_result.log(msg, level_choice=LogLevelChoices.LOG_ERROR, grouping="intent definitions")

    # Mark intents that were previously managed by this repo but are no
    # longer present in it as deprecated (soft-delete).
    orphaned = Intent.objects.filter(git_repository=repository_record).exclude(intent_id__in=synced_intent_ids)
    orphan_count = orphaned.count()
    if orphan_count:
        deprecated_status = Status.objects.filter(name__iexact="Deprecated").first()
        if deprecated_status:
            orphaned.update(status=deprecated_status)
        msg = f"Deprecated {orphan_count} intent(s) no longer present in repo"
        job_result.log(msg, level_choice=LogLevelChoices.LOG_WARNING, grouping="intent definitions")

    summary = (
        f"Sync complete: {stats['created']} created, "
        f"{stats['updated']} updated, {stats['errors']} errors, "
        f"{orphan_count} deprecated"
    )
    job_result.log(summary, grouping="intent definitions")


def _delete_repo_intents(repository_record, job_result):
    """Handle GitRepository deletion — deprecate (don't hard-delete) intents."""
    from intent_networking.models import Intent

    managed = Intent.objects.filter(git_repository=repository_record)
    count = managed.count()

    if count:
        deprecated_status = Status.objects.filter(name__iexact="Deprecated").first()
        if deprecated_status:
            managed.update(status=deprecated_status)

        msg = f"Git repository '{repository_record.name}' deleted — deprecated {count} managed intent(s)"
        job_result.log(msg, level_choice=LogLevelChoices.LOG_WARNING, grouping="intent definitions")
    else:
        msg = f"Git repository '{repository_record.name}' deleted — no managed intents to update"
        job_result.log(msg, grouping="intent definitions")


# ─────────────────────────────────────────────────────────────────────────────
# Registration list — auto-discovered by NautobotAppConfig.ready() from
# the ``datasource_contents`` attribute (default path: datasources.datasource_contents)
# ─────────────────────────────────────────────────────────────────────────────

datasource_contents = [
    (
        "extras.gitrepository",
        DatasourceContent(
            name="intent definitions",
            content_identifier=CONTENT_IDENTIFIER,
            icon="mdi-file-document-multiple-outline",
            callback=refresh_git_intent_definitions,
        ),
    ),
]
