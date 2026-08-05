"""
Autonomous Engineering Execution — Safety Foundation
Genesis-041 Sprint-001

Three components — no execution, no git writes.
Safety abstractions that everything else depends on.

Components:
  ExecutionResult     — immutable record of what was done (or attempted)
  RollbackStrategy    — ABC with GitRollbackStrategy implementation
  PlanValidator       — validates an execution plan before any file is touched

Design principles:
  Data-first — all state in frozen dataclasses.
  Safety-first — validator must pass before executor runs.
  Rollback-first — snapshot before execution, rollback on any failure.
  Provider-agnostic — RollbackStrategy is an interface; git is one implementation.
"""

from __future__ import annotations

import logging
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExecutionStatus(Enum):
    PENDING    = "pending"
    EXECUTING  = "executing"
    COMPLETE   = "complete"
    FAILED     = "failed"
    ROLLED_BACK = "rolled_back"


class ValidationStatus(Enum):
    VALID   = "valid"
    INVALID = "invalid"


class RollbackStatus(Enum):
    NOT_NEEDED = "not_needed"
    SUCCEEDED  = "succeeded"
    FAILED     = "failed"


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileChange:
    """
    A single file operation recorded during execution.

    Immutable — produced by ExecutionWorker, consumed by RollbackWorker.
    """
    path:        str
    operation:   str   # "create" | "modify" | "delete"
    backup_path: str   # path to pre-execution backup, or "" if new file


@dataclass(frozen=True)
class ExecutionResult:
    """
    Immutable structured record of an execution attempt.

    Produced by ExecutionWorker after applying an approved plan.
    Consumed by RegressionGateWorker and RollbackWorker.

    This is the canonical data object for the execution phase.
    Markdown reports are derived from it, never the other way around.
    """
    result_id:       str
    session_id:      str
    status:          ExecutionStatus
    description:     str
    files_written:   tuple[FileChange, ...]   # all file operations attempted
    files_created:   tuple[str, ...]          # new files (for rollback cleanup)
    files_modified:  tuple[str, ...]          # modified files (backed up)
    snapshot_sha:    str                      # git HEAD SHA before execution
    error:           str                      # empty on success
    started_at:      str
    completed_at:    Optional[str]
    duration_seconds: Optional[float]

    @classmethod
    def pending(cls, session_id: str, description: str) -> "ExecutionResult":
        return cls(
            result_id=str(uuid4()),
            session_id=session_id,
            status=ExecutionStatus.PENDING,
            description=description,
            files_written=(),
            files_created=(),
            files_modified=(),
            snapshot_sha="",
            error="",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
            duration_seconds=None,
        )

    def with_success(
        self,
        files_written: tuple[FileChange, ...],
        files_created: tuple[str, ...],
        files_modified: tuple[str, ...],
        snapshot_sha: str,
    ) -> "ExecutionResult":
        now = datetime.now(timezone.utc).isoformat()
        started = datetime.fromisoformat(self.started_at)
        ended   = datetime.fromisoformat(now)
        return ExecutionResult(
            result_id=self.result_id,
            session_id=self.session_id,
            status=ExecutionStatus.COMPLETE,
            description=self.description,
            files_written=files_written,
            files_created=files_created,
            files_modified=files_modified,
            snapshot_sha=snapshot_sha,
            error="",
            started_at=self.started_at,
            completed_at=now,
            duration_seconds=(ended - started).total_seconds(),
        )

    def with_failure(self, error: str) -> "ExecutionResult":
        now = datetime.now(timezone.utc).isoformat()
        started = datetime.fromisoformat(self.started_at)
        ended   = datetime.fromisoformat(now)
        return ExecutionResult(
            result_id=self.result_id,
            session_id=self.session_id,
            status=ExecutionStatus.FAILED,
            description=self.description,
            files_written=self.files_written,
            files_created=self.files_created,
            files_modified=self.files_modified,
            snapshot_sha=self.snapshot_sha,
            error=error,
            started_at=self.started_at,
            completed_at=now,
            duration_seconds=(ended - started).total_seconds(),
        )

    def with_rollback(self) -> "ExecutionResult":
        return ExecutionResult(
            result_id=self.result_id,
            session_id=self.session_id,
            status=ExecutionStatus.ROLLED_BACK,
            description=self.description,
            files_written=self.files_written,
            files_created=self.files_created,
            files_modified=self.files_modified,
            snapshot_sha=self.snapshot_sha,
            error=self.error,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration_seconds=self.duration_seconds,
        )

    @property
    def is_complete(self) -> bool:
        return self.status == ExecutionStatus.COMPLETE

    @property
    def is_failed(self) -> bool:
        return self.status in (ExecutionStatus.FAILED, ExecutionStatus.ROLLED_BACK)

    def to_summary(self) -> str:
        lines = [
            f"Execution: {self.status.value.upper()}",
            f"Description: {self.description}",
        ]
        if self.files_created:
            lines.append(f"Files created ({len(self.files_created)}): "
                         + ", ".join(self.files_created[:3])
                         + ("..." if len(self.files_created) > 3 else ""))
        if self.files_modified:
            lines.append(f"Files modified ({len(self.files_modified)}): "
                         + ", ".join(self.files_modified[:3])
                         + ("..." if len(self.files_modified) > 3 else ""))
        if self.error:
            lines.append(f"Error: {self.error}")
        if self.duration_seconds is not None:
            lines.append(f"Duration: {self.duration_seconds:.1f}s")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# RollbackStrategy — ABC + GitRollbackStrategy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RollbackResult:
    """Immutable record of a rollback attempt."""
    status:  RollbackStatus
    message: str
    sha:     str   # the SHA that was restored to, or "" if N/A


class RollbackStrategy(ABC):
    """
    Abstract rollback strategy.

    Abstracts the rollback mechanism so future implementations
    (filesystem backup, cloud snapshot) can replace git without
    changing ExecutionWorker or RollbackWorker.

    Subclasses must implement:
        snapshot(repo_path)              — record current state, return anchor
        rollback(repo_path, anchor, ...) — restore to anchor
        name                             — human-readable strategy name
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    @abstractmethod
    def snapshot(self, repo_path: str) -> str:
        """
        Record the current state and return an anchor string.

        For git: returns HEAD SHA.
        For filesystem: returns backup directory path.
        Never raises — returns empty string on failure.
        """
        ...

    @abstractmethod
    def rollback(
        self,
        repo_path: str,
        anchor: str,
        files_created: tuple[str, ...] = (),
    ) -> RollbackResult:
        """
        Restore the repository to the state captured by snapshot().

        Args:
            repo_path:     Absolute path to the repository root.
            anchor:        The value returned by snapshot().
            files_created: New files to delete (not tracked by git checkout).

        Returns:
            RollbackResult — never raises.
        """
        ...


class GitRollbackStrategy(RollbackStrategy):
    """
    Git-based rollback strategy.

    snapshot() → records HEAD SHA.
    rollback()  → git checkout <SHA> -- . then deletes untracked new files.

    This is the primary rollback mechanism. A filesystem backup layer
    is provided by ExecutionWorker as a secondary safety net.
    """

    @property
    def name(self) -> str:
        return "git_rollback"

    def snapshot(self, repo_path: str) -> str:
        """Return the current HEAD SHA. Returns '' on failure."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                sha = result.stdout.strip()
                logger.info("[GIT_ROLLBACK] Snapshot: HEAD=%s", sha[:8])
                return sha
            logger.warning(
                "[GIT_ROLLBACK] snapshot failed: %s", result.stderr.strip()
            )
            return ""
        except Exception as exc:
            logger.exception("[GIT_ROLLBACK] snapshot raised.")
            return ""

    def rollback(
        self,
        repo_path: str,
        anchor: str,
        files_created: tuple[str, ...] = (),
    ) -> RollbackResult:
        """
        Restore tracked files to anchor SHA, then delete new untracked files.
        Never raises.
        """
        if not anchor:
            return RollbackResult(
                status=RollbackStatus.FAILED,
                message="No anchor SHA available — cannot rollback.",
                sha="",
            )

        try:
            # Restore all tracked files to the snapshot SHA
            result = subprocess.run(
                ["git", "checkout", anchor, "--", "."],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return RollbackResult(
                    status=RollbackStatus.FAILED,
                    message=f"git checkout failed: {result.stderr.strip()}",
                    sha=anchor,
                )

            # Delete new files that weren't tracked before execution
            deleted = []
            for path in files_created:
                abs_path = os.path.join(repo_path, path)
                if os.path.exists(abs_path):
                    try:
                        os.remove(abs_path)
                        deleted.append(path)
                    except Exception as e:
                        logger.warning(
                            "[GIT_ROLLBACK] Could not delete %s: %s", path, e
                        )

            msg = f"Rolled back to {anchor[:8]}."
            if deleted:
                msg += f" Deleted {len(deleted)} new file(s)."

            logger.info("[GIT_ROLLBACK] %s", msg)
            return RollbackResult(
                status=RollbackStatus.SUCCEEDED,
                message=msg,
                sha=anchor,
            )

        except Exception as exc:
            logger.exception("[GIT_ROLLBACK] rollback raised.")
            return RollbackResult(
                status=RollbackStatus.FAILED,
                message=str(exc),
                sha=anchor,
            )


# ---------------------------------------------------------------------------
# PlanValidator
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationError:
    """A single validation failure."""
    field:   str   # what was checked
    message: str   # why it failed


@dataclass(frozen=True)
class ValidationResult:
    """
    Immutable result of plan validation.

    ExecutionWorker must check is_valid before writing any file.
    """
    status:           ValidationStatus
    errors:           tuple[ValidationError, ...]
    validated_paths:  tuple[str, ...]   # paths that passed validation
    repo_root:        str

    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.VALID

    def to_text(self) -> str:
        if self.is_valid:
            return (
                f"Plan valid. {len(self.validated_paths)} path(s) verified "
                f"within repo root: {self.repo_root}"
            )
        lines = [f"Plan invalid. {len(self.errors)} error(s):"]
        for err in self.errors:
            lines.append(f"  [{err.field}] {err.message}")
        return "\n".join(lines)


class PlanValidator:
    """
    Validates an execution plan before any file is touched.

    Responsibilities:
      - Every referenced path must be inside the project root.
      - No path traversal (../ etc.).
      - Files marked as existing must actually exist.
      - Files marked as new must not already exist (warns, does not block).
      - Plan must contain at least one file operation.

    ExecutionWorker must call validate() and check result.is_valid
    before proceeding. If not valid, execution must not start.

    Public API:
        validate(plan, repo_root) -> ValidationResult
    """

    def validate(
        self,
        plan: dict[str, Any],
        repo_root: str,
    ) -> ValidationResult:
        """
        Validate an execution plan against the repository root.

        Args:
            plan:      Dict with keys:
                         "files_to_create": list of relative paths
                         "files_to_modify": list of relative paths
                         "files_to_delete": list of relative paths
            repo_root: Absolute path to the repository root.

        Returns:
            ValidationResult — never raises.
        """
        errors: list[ValidationError] = []
        validated_paths: list[str] = []

        repo_root = os.path.abspath(repo_root)

        files_to_create = plan.get("files_to_create", [])
        files_to_modify = plan.get("files_to_modify", [])
        files_to_delete = plan.get("files_to_delete", [])

        all_paths = (
            [("create", p) for p in files_to_create]
            + [("modify", p) for p in files_to_modify]
            + [("delete", p) for p in files_to_delete]
        )

        # Must have at least one operation
        if not all_paths:
            errors.append(ValidationError(
                field="plan",
                message="Plan contains no file operations.",
            ))

        for operation, rel_path in all_paths:
            # Check for path traversal
            if ".." in rel_path or rel_path.startswith("/") or rel_path.startswith("\\"):
                errors.append(ValidationError(
                    field=rel_path,
                    message=f"Path traversal detected in {operation!r} operation.",
                ))
                continue

            # Resolve and verify inside repo root
            abs_path = os.path.normpath(os.path.join(repo_root, rel_path))
            if not abs_path.startswith(repo_root + os.sep) and abs_path != repo_root:
                errors.append(ValidationError(
                    field=rel_path,
                    message=(
                        f"{operation!r} path resolves outside repo root: "
                        f"{abs_path}"
                    ),
                ))
                continue

            # Existing files must exist for modify/delete
            if operation in ("modify", "delete"):
                if not os.path.exists(abs_path):
                    errors.append(ValidationError(
                        field=rel_path,
                        message=(
                            f"File does not exist for {operation!r} operation."
                        ),
                    ))
                    continue

            # New files should not already exist (warning, not error)
            if operation == "create" and os.path.exists(abs_path):
                logger.warning(
                    "[PLAN_VALIDATOR] File already exists for 'create': %s",
                    rel_path,
                )

            validated_paths.append(rel_path)

        status = (
            ValidationStatus.VALID
            if not errors
            else ValidationStatus.INVALID
        )

        logger.info(
            "[PLAN_VALIDATOR] %s — %d path(s) valid, %d error(s)",
            status.value, len(validated_paths), len(errors),
        )

        return ValidationResult(
            status=status,
            errors=tuple(errors),
            validated_paths=tuple(validated_paths),
            repo_root=repo_root,
        )
