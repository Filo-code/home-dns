"""Execute a CleanupPlan (core.storage.plan_cleanup) against real storage.

Only touches files it can prove belong to a registered category (see
docs/specs/a4-storage-maintenance.md §4): temp files by age via storage.tempfiles, backups by the
module's own naming pattern via storage.backup, blocklist artifacts via ArtifactStore.reconcile
(unchanged A2 pruning logic). Dry-run by default throughout; idempotent.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from home_dns.core.storage import (
    CleanupActionKind,
    CleanupPlan,
    CleanupResult,
    CleanupStepResult,
    RetentionPolicy,
)
from home_dns.storage.artifacts import ArtifactStore
from home_dns.storage.backup import prune_backups
from home_dns.storage.tempfiles import sweep_temp_dir


def execute_cleanup(
    plan: CleanupPlan,
    *,
    tmp_dir: Path,
    backup_dir: Path,
    artifact_store: ArtifactStore,
    artifact_sources: Sequence[str],
    retention: RetentionPolicy,
    now: datetime,
    dry_run: bool = True,
) -> CleanupResult:
    steps: list[CleanupStepResult] = []
    for step in plan.steps:
        if step.target == "tmp":
            max_age = (
                timedelta(0)
                if plan.action is CleanupActionKind.AGGRESSIVE
                else timedelta(hours=retention.temp_max_age_hours)
            )
            result = sweep_temp_dir(tmp_dir, max_age=max_age, now=now, dry_run=dry_run)
            steps.append(CleanupStepResult(step.target, step.description, result.removed, dry_run))
        elif step.target == "backups":
            keep = 1 if plan.action is CleanupActionKind.AGGRESSIVE else retention.backups_keep
            prune_result = prune_backups(backup_dir, keep=keep, dry_run=dry_run)
            steps.append(
                CleanupStepResult(step.target, step.description, prune_result.removed, dry_run)
            )
        elif step.target == "blocklists":
            removed: list[str] = []
            for source_id in artifact_sources:
                change = artifact_store.reconcile(source_id, dry_run=dry_run)
                removed.extend(f"{source_id}/{name}" for name in change.pruned)
            steps.append(CleanupStepResult(step.target, step.description, tuple(removed), dry_run))
    return CleanupResult(plan, tuple(steps))
