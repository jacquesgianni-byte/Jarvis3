"""
Autonomous Engineering Execution — ExecutionWorker and RollbackWorker
Genesis-041 Sprint-003

ExecutionWorker:
  Executes an approved engineering plan by writing files.
  Deterministic — no AI calls, no re-interpretation.
  The approved plan is the specification. It is executed verbatim.
  Backs up every modified file before overwriting.
  On any failure, signals for rollback.

RollbackWorker:
  Restores the repository to its pre-execution state.
  Uses GitRollbackStrategy as primary mechanism.
  Uses file backups as secondary safety net.
  Called automatically on test failure or execution error.

Design principles:
  - No AI calls during execution (deterministic)
  - Backup before overwrite (always)
  - Rollback on any failure (automatic)
  - requires_approval=False for execution and rollback
    (these are safety operations within an already-approved workflow)
  - requires_approval=True is reserved for commit and push
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask
from core.engineering.execution.safety import (
    ExecutionResult,
    ExecutionStatus,
    FileChange,
    GitRollbackStrategy,
    PlanValidator,
    RollbackResult,
    RollbackStatus,
    RollbackStrategy,
    ValidationResult,
)

logger = logging.getLogger(__name__)

_BACKUP_DIR = ".jarvis_backup"


class ExecutionWorker(Worker):
    """
    Executes an approved engineering plan by writing files.

    Capability: execute_approved_plan

    Payload contract:
        task.payload["plan"]          — validated plan dict:
                                          files_to_create: list[dict{path, content}]
                                          files_to_modify: list[dict{path, content}]
                                          files_to_delete: list[str]
        task.payload["session_id"]    — collaboration session ID
        task.payload["snapshot_sha"]  — git HEAD SHA from git_snapshot
        task.payload["repo_root"]     — repository root path (optional)
        task.payload["description"]   — human-readable description

    WorkerResult.data:
        "execution_result"   — ExecutionResult (as dict)
        "files_written"      — count of files written
        "backup_dir"         — path to backup directory

    No AI calls. No re-interpretation.
    The plan is executed exactly as provided.
    """

    def __init__(
        self,
        repo_root: Optional[str] = None,
        validator: Optional[PlanValidator] = None,
    ) -> None:
        super().__init__()
        self._repo_root = repo_root or os.getcwd()
        self._validator = validator or PlanValidator()

    @property
    def name(self) -> str:
        return "execution_worker"

    @property
    def description(self) -> str:
        return (
            "Executes an approved engineering plan by writing files. "
            "Deterministic — no AI calls. Backs up all modified files."
        )

    @property
    def capabilities(self) -> list[str]:
        return ["execute_approved_plan"]

    def validate(self, task: WorkerTask) -> bool:
        return task.task_type == "execute_approved_plan"

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)

        session_id   = task.payload.get("session_id", "unknown")
        snapshot_sha = task.payload.get("snapshot_sha", "")
        description  = task.payload.get("description", "Execute approved plan")
        repo_root    = task.payload.get("repo_root", self._repo_root)
        plan         = task.payload.get("plan", {})

        execution = ExecutionResult.pending(session_id, description)

        try:
            # Step 1: Validate plan before touching any file
            validation = self._validator.validate(plan, repo_root)
            if not validation.is_valid:
                error = "Plan validation failed:\n" + validation.to_text()
                return self._fail(task.task_id, error)

            # Step 2: Create backup directory
            backup_dir = os.path.join(repo_root, _BACKUP_DIR)
            os.makedirs(backup_dir, exist_ok=True)

            # Step 3: Execute plan — backup then write
            files_written: list[FileChange] = []
            files_created: list[str] = []
            files_modified: list[str] = []

            # Create new files
            for item in plan.get("files_to_create", []):
                path    = item["path"]
                content = item.get("content", "")
                abs_path = os.path.join(repo_root, path)

                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                self._write_file(abs_path, content)

                fc = FileChange(path=path, operation="create", backup_path="")
                files_written.append(fc)
                files_created.append(path)
                logger.info("[EXEC_WORKER] Created: %s", path)

            # Modify existing files (backup first)
            for item in plan.get("files_to_modify", []):
                path    = item["path"]
                content = item.get("content", "")
                abs_path = os.path.join(repo_root, path)

                # Backup before overwrite
                backup_path = self._backup_file(abs_path, backup_dir, path)

                self._write_file(abs_path, content)

                fc = FileChange(path=path, operation="modify", backup_path=backup_path)
                files_written.append(fc)
                files_modified.append(path)
                logger.info("[EXEC_WORKER] Modified: %s (backup: %s)", path, backup_path)

            # Delete files (backup first)
            for path in plan.get("files_to_delete", []):
                abs_path = os.path.join(repo_root, path)
                if os.path.exists(abs_path):
                    backup_path = self._backup_file(abs_path, backup_dir, path)
                    os.remove(abs_path)
                    fc = FileChange(path=path, operation="delete", backup_path=backup_path)
                    files_written.append(fc)
                    logger.info("[EXEC_WORKER] Deleted: %s (backup: %s)", path, backup_path)

            # Step 4: Record success
            execution = execution.with_success(
                files_written=tuple(files_written),
                files_created=tuple(files_created),
                files_modified=tuple(files_modified),
                snapshot_sha=snapshot_sha,
            )

            logger.info(
                "[EXEC_WORKER] Complete: %d file(s) written.",
                len(files_written),
            )

            return self._succeed(WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=True,
                observations=(
                    f"Executed plan: {len(files_written)} file operation(s).",
                    f"Created: {len(files_created)}, "
                    f"Modified: {len(files_modified)}",
                    f"Backup: {backup_dir}",
                ),
                recommendations=(
                    "Run regression tests before committing.",
                ),
                requires_approval=False,
                data={
                    "execution_result": {
                        "result_id":      execution.result_id,
                        "session_id":     execution.session_id,
                        "status":         execution.status.value,
                        "files_created":  list(execution.files_created),
                        "files_modified": list(execution.files_modified),
                        "snapshot_sha":   execution.snapshot_sha,
                        "duration_seconds": execution.duration_seconds,
                    },
                    "files_written": len(files_written),
                    "backup_dir":    backup_dir,
                    "snapshot_sha":  snapshot_sha,
                    "files_created": list(files_created),
                    "files_modified": list(files_modified),
                },
            ))

        except Exception as exc:
            logger.exception("[EXEC_WORKER] Unexpected error.")
            execution = execution.with_failure(str(exc))
            return self._fail(task.task_id, str(exc))

    # -- Internal ----------------------------------------------------------

    @staticmethod
    def _write_file(abs_path: str, content: str) -> None:
        """Write content to a file, creating parent directories as needed."""
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content)

    @staticmethod
    def _backup_file(abs_path: str, backup_dir: str, rel_path: str) -> str:
        """
        Copy a file to the backup directory before modification.
        Returns the backup path, or "" if the file doesn't exist.
        """
        if not os.path.exists(abs_path):
            return ""
        # Flatten path for backup filename: core/agent.py -> core__agent.py
        flat_name = rel_path.replace(os.sep, "__").replace("/", "__")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{timestamp}__{flat_name}"
        backup_path = os.path.join(backup_dir, backup_name)
        shutil.copy2(abs_path, backup_path)
        return backup_path


class RollbackWorker(Worker):
    """
    Restores the repository to its pre-execution state.

    Capability: rollback_execution

    Payload contract:
        task.payload["snapshot_sha"]  — git HEAD SHA from git_snapshot
        task.payload["files_created"] — new files to delete (list[str])
        task.payload["repo_root"]     — repository root path (optional)

    Uses GitRollbackStrategy as the primary mechanism.
    Falls back to file-level backup restoration if git fails.

    requires_approval=False — rollback is an automatic safety operation.
    """

    def __init__(
        self,
        repo_root: Optional[str] = None,
        strategy: Optional[RollbackStrategy] = None,
    ) -> None:
        super().__init__()
        self._repo_root = repo_root or os.getcwd()
        self._strategy  = strategy or GitRollbackStrategy()

    @property
    def name(self) -> str:
        return "rollback_worker"

    @property
    def description(self) -> str:
        return (
            "Restores the repository to its pre-execution state. "
            "Primary: git checkout. Secondary: file backup restoration."
        )

    @property
    def capabilities(self) -> list[str]:
        return ["rollback_execution"]

    def validate(self, task: WorkerTask) -> bool:
        return task.task_type == "rollback_execution"

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)

        snapshot_sha  = task.payload.get("snapshot_sha", "").strip()
        files_created = task.payload.get("files_created", [])
        repo_root     = task.payload.get("repo_root", self._repo_root)

        try:
            if not snapshot_sha:
                return self._fail(
                    task.task_id,
                    "No snapshot SHA — cannot rollback. Manual intervention required.",
                )

            # Primary: git rollback
            result: RollbackResult = self._strategy.rollback(
                repo_root=repo_root,
                anchor=snapshot_sha,
                files_created=tuple(files_created),
            )

            if result.status == RollbackStatus.SUCCEEDED:
                logger.info("[ROLLBACK_WORKER] %s", result.message)
                return self._succeed(WorkerResult(
                    task_id=task.task_id,
                    worker_name=self.name,
                    success=True,
                    observations=(
                        f"Rollback succeeded: {result.message}",
                        f"Strategy: {self._strategy.name}",
                    ),
                    recommendations=(
                        "Verify working tree matches expected state.",
                    ),
                    requires_approval=False,
                    data={
                        "sha":             result.sha,
                        "strategy":        self._strategy.name,
                        "rollback_status": result.status.value,
                        "message":         result.message,
                        "files_created_deleted": files_created,
                    },
                ))

            # Primary failed — attempt backup restoration
            logger.warning(
                "[ROLLBACK_WORKER] Primary rollback failed: %s. "
                "Attempting backup restoration.",
                result.message,
            )
            backup_restored = self._restore_from_backup(repo_root)

            if backup_restored:
                return self._succeed(WorkerResult(
                    task_id=task.task_id,
                    worker_name=self.name,
                    success=True,
                    observations=(
                        f"Git rollback failed: {result.message}",
                        f"Backup restoration succeeded: {backup_restored} file(s).",
                    ),
                    recommendations=(
                        "Verify working tree manually — backup restoration used.",
                        "Check git status before proceeding.",
                    ),
                    requires_approval=False,
                    data={
                        "sha":             snapshot_sha,
                        "strategy":        "backup_restoration",
                        "rollback_status": "partial",
                        "message":         f"Backup restored {backup_restored} file(s).",
                        "git_error":       result.message,
                    },
                ))

            # Both failed
            error = (
                f"ROLLBACK FAILED. "
                f"Git: {result.message}. "
                f"Backup: no backups found. "
                f"Manual intervention required."
            )
            logger.error("[ROLLBACK_WORKER] %s", error)
            return self._fail(task.task_id, error)

        except Exception as exc:
            logger.exception("[ROLLBACK_WORKER] Unexpected error.")
            return self._fail(task.task_id, str(exc))

    def _restore_from_backup(self, repo_root: str) -> int:
        """
        Attempt to restore files from the backup directory.
        Returns number of files restored, or 0 if no backups found.
        """
        backup_dir = os.path.join(repo_root, _BACKUP_DIR)
        if not os.path.isdir(backup_dir):
            return 0

        restored = 0
        for backup_name in os.listdir(backup_dir):
            # Filename format: YYYYMMDD_HHMMSS__core__agent.py
            parts = backup_name.split("__", 1)
            if len(parts) < 2:
                continue
            rel_path = parts[1].replace("__", os.sep)
            abs_path = os.path.join(repo_root, rel_path)
            backup_path = os.path.join(backup_dir, backup_name)
            try:
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                shutil.copy2(backup_path, abs_path)
                restored += 1
                logger.info("[ROLLBACK_WORKER] Restored: %s", rel_path)
            except Exception as e:
                logger.warning(
                    "[ROLLBACK_WORKER] Could not restore %s: %s", rel_path, e
                )

        return restored
