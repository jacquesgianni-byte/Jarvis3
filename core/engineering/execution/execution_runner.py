"""
Autonomous Engineering Execution — ExecutionRunner
Genesis-041 Sprint-004

ExecutionRunner orchestrates the full post-approval pipeline:

  1. Git snapshot (rollback anchor)
  2. Execute approved plan (file writes)
  3. Regression gate (full test suite)
  4a. Tests fail → automatic rollback → failure report
  4b. Tests pass → ChangeSummary → present to human

Design principles:
  - Mirrors CollaborationRunner (same pattern, different domain)
  - No AI calls — deterministic throughout
  - Rollback is automatic on test failure
  - Commit and push always require separate human approval
  - Never raises — always returns ExecutionOutcome

ApprovalLifecycleState:
  AWAITING_APPROVAL → SNAPSHOTTING → EXECUTING → TESTING
  → ROLLED_BACK (on failure) | COMMIT_PENDING (on success)
  → COMMITTED → PUSH_PENDING → PUSHED
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from core.workers.models import WorkerTask, WorkerResult

logger = logging.getLogger(__name__)

# Approval trigger phrases (same as process() early check)
_EXECUTION_TRIGGERS: frozenset[str] = frozenset({
    "approve", "approved", "yes", "yes.",
    "apply", "apply the changes",
    "apply recommended changes",
    "apply the recommended changes",
    "apply the recommended changes automatically",
    "proceed", "proceed with changes",
    "confirm", "go ahead",
    "yes proceed", "yes, proceed",
    "implement it", "implement the changes",
    "make the changes", "i approve",
    "execute", "execute the plan",
    "run it", "do it",
})


# ---------------------------------------------------------------------------
# ApprovalLifecycleState
# ---------------------------------------------------------------------------

class ApprovalLifecycleState(Enum):
    AWAITING_APPROVAL = "awaiting_approval"
    SNAPSHOTTING      = "snapshotting"
    EXECUTING         = "executing"
    TESTING           = "testing"
    ROLLED_BACK       = "rolled_back"
    COMMIT_PENDING    = "commit_pending"
    COMMITTED         = "committed"
    PUSH_PENDING      = "push_pending"
    PUSHED            = "pushed"
    FAILED            = "failed"


# ---------------------------------------------------------------------------
# ChangeSummary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChangeSummary:
    """
    Immutable record of a successful execution.

    Presented to the human before requesting commit approval.
    Data-first — Markdown is derived from this, never the other way.
    """
    summary_id:       str
    session_id:       str
    description:      str
    files_created:    tuple[str, ...]
    files_modified:   tuple[str, ...]
    files_deleted:    tuple[str, ...]
    tests_passed:     int
    tests_skipped:    int
    snapshot_sha:     str
    duration_seconds: Optional[float]
    generated_at:     str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def create(
        cls,
        session_id: str,
        description: str,
        execution_data: dict,
        test_data: dict,
        snapshot_sha: str,
        duration_seconds: Optional[float] = None,
    ) -> "ChangeSummary":
        return cls(
            summary_id=str(uuid4()),
            session_id=session_id,
            description=description,
            files_created=tuple(execution_data.get("files_created", [])),
            files_modified=tuple(execution_data.get("files_modified", [])),
            files_deleted=tuple(execution_data.get("files_deleted", [])),
            tests_passed=test_data.get("passed", 0),
            tests_skipped=test_data.get("skipped", 0),
            snapshot_sha=snapshot_sha,
            duration_seconds=duration_seconds,
        )

    @property
    def total_files_changed(self) -> int:
        return (
            len(self.files_created)
            + len(self.files_modified)
            + len(self.files_deleted)
        )

    def to_text(self) -> str:
        sep = "─" * 56
        lines = [
            sep,
            "CHANGE SUMMARY",
            sep,
            f"Description: {self.description}",
            f"Session:     {self.session_id[:8]}",
            "",
            f"Files changed: {self.total_files_changed}",
        ]
        if self.files_created:
            lines.append(f"  Created ({len(self.files_created)}):")
            for f in self.files_created:
                lines.append(f"    + {f}")
        if self.files_modified:
            lines.append(f"  Modified ({len(self.files_modified)}):")
            for f in self.files_modified:
                lines.append(f"    ~ {f}")
        if self.files_deleted:
            lines.append(f"  Deleted ({len(self.files_deleted)}):")
            for f in self.files_deleted:
                lines.append(f"    - {f}")
        lines += [
            "",
            f"Tests: {self.tests_passed} passed, {self.tests_skipped} skipped, 0 failed",
            f"Snapshot: {self.snapshot_sha[:8] if self.snapshot_sha else 'none'}",
            "",
            "✅ All engineering gates passed.",
            "Ready for commit. Type 'Commit changes.' to proceed.",
            sep,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ExecutionOutcome
# ---------------------------------------------------------------------------

@dataclass
class ExecutionOutcome:
    """
    The result of a full execution run.
    Analogous to CollaborationOutcome.
    """
    state:        ApprovalLifecycleState
    description:  str
    summary:      Optional[ChangeSummary]
    markdown:     str
    success:      bool
    error:        str = ""
    snapshot_sha: str = ""
    session_id:   str = ""


# ---------------------------------------------------------------------------
# ExecutionRunner
# ---------------------------------------------------------------------------

class ExecutionRunner:
    """
    Orchestrates the complete post-approval execution pipeline.

    Mirrors CollaborationRunner — thin orchestrator, workers do the work.

    Public API:
        can_execute(utterance)       -> bool
        run(collaboration_outcome)   -> ExecutionOutcome
        has_pending_commit()         -> bool
        get_commit_summary_text()    -> str
        clear_pending_commit()       -> None
    """

    def __init__(
        self,
        worker_coordinator,
        worker_manager,
        worker_intelligence=None,
        repo_root: str = ".",
    ) -> None:
        self._coordinator  = worker_coordinator
        self._manager      = worker_manager
        self._intelligence = worker_intelligence
        self._repo_root    = repo_root
        self._last_outcome: Optional[ExecutionOutcome] = None

    def can_execute(self, utterance: str) -> bool:
        """True if the utterance is an execution trigger."""
        return utterance.strip().lower().rstrip("?!.") in _EXECUTION_TRIGGERS

    def run(
        self,
        description: str,
        plan: dict,
        session_id: str = "",
    ) -> ExecutionOutcome:
        """
        Run the full execution pipeline.

        Steps:
          1. Git snapshot
          2. Execute approved plan
          3. Regression gate
          4a. Fail → rollback → failure outcome
          4b. Pass → change summary → commit pending

        Never raises.
        """
        import time as _time
        _start = _time.perf_counter()
        session_id = session_id or str(uuid4())[:8]

        # ── Step 1: Git snapshot ─────────────────────────────────────────
        snapshot_sha = self._git_snapshot()
        if not snapshot_sha:
            return self._failure_outcome(
                description, session_id,
                "Git snapshot failed — cannot proceed without rollback anchor.",
            )

        # ── Step 2: Execute approved plan ────────────────────────────────
        exec_result = self._execute_plan(description, plan, session_id, snapshot_sha)
        if not exec_result.success:
            # Execution failed — attempt rollback
            self._rollback(snapshot_sha, [], session_id)
            return self._failure_outcome(
                description, session_id,
                f"Execution failed: {exec_result.error}",
                snapshot_sha=snapshot_sha,
            )

        # Unwrap coordinator envelope for execution data
        _exec_data = (
            exec_result.data.get("results", {}).get("execution_worker", {})
            or exec_result.data
        )
        files_created  = _exec_data.get("files_created", [])
        files_modified = _exec_data.get("files_modified", [])
        exec_data      = _exec_data

        # ── Step 3: Regression gate ──────────────────────────────────────
        test_result = self._run_tests()
        # Unwrap coordinator envelope for test data
        _test_data = (
            test_result.data.get("results", {}).get("suite_runner_worker", {})
            or test_result.data
        )
        tests_failed = _test_data.get("failed", 0) if test_result.success else 1

        if tests_failed > 0 or not test_result.success:
            # Tests failed — automatic rollback
            self._rollback(snapshot_sha, files_created, session_id)
            failures = _test_data.get("failures", [])[:5]
            error = (
                f"Regression tests failed ({tests_failed} failure(s)). "
                f"Rolled back to {snapshot_sha[:8]}. "
                + (f"Failing: {', '.join(failures)}" if failures else "")
            )
            return self._failure_outcome(
                description, session_id, error, snapshot_sha=snapshot_sha
            )

        # ── Step 4: Change summary ───────────────────────────────────────
        duration = _time.perf_counter() - _start
        summary = ChangeSummary.create(
            session_id=session_id,
            description=description,
            execution_data=exec_data,
            test_data=_test_data,
            snapshot_sha=snapshot_sha,
            duration_seconds=round(duration, 1),
        )

        outcome = ExecutionOutcome(
            state=ApprovalLifecycleState.COMMIT_PENDING,
            description=description,
            summary=summary,
            markdown=summary.to_text(),
            success=True,
            snapshot_sha=snapshot_sha,
            session_id=session_id,
        )
        self._last_outcome = outcome
        return outcome

    # ── Commit / push API ────────────────────────────────────────────────

    def has_pending_commit(self) -> bool:
        return (
            self._last_outcome is not None
            and self._last_outcome.success
            and self._last_outcome.state == ApprovalLifecycleState.COMMIT_PENDING
        )

    def get_commit_summary_text(self) -> str:
        if self._last_outcome and self._last_outcome.summary:
            return self._last_outcome.summary.to_text()
        return ""

    def clear_pending_commit(self) -> None:
        self._pending_push = True   # commit done → push now available
        self._last_outcome = None

    def has_pending_push(self) -> bool:
        return getattr(self, "_pending_push", False)

    def get_push_summary_text(self) -> str:
        return "Changes committed. Ready to push to GitHub."

    def clear_pending_push(self) -> None:
        self._pending_push = False

    # ── Internal ─────────────────────────────────────────────────────────

    def _git_snapshot(self) -> str:
        """Run git_snapshot, return SHA or empty string on failure."""
        self._ensure_workflow("git_snapshot", ["git_worker"])
        task = WorkerTask(
            task_type="git_snapshot",
            payload={"repo_root": self._repo_root},
            requester="execution_runner",
        )
        try:
            result = self._coordinator.run(task)
            if self._intelligence:
                self._intelligence.observe(result, "git_snapshot")
            if result.success:
                worker_data = (
                    result.data.get("results", {}).get("git_worker", {})
                    or result.data
                )
                return worker_data.get("sha", "")
        except Exception:
            logger.exception("[EXEC_RUNNER] git_snapshot raised.")
        return ""

    def _execute_plan(
        self,
        description: str,
        plan: dict,
        session_id: str,
        snapshot_sha: str,
    ) -> WorkerResult:
        """Run ExecutionWorker."""
        self._ensure_workflow("execute_approved_plan", ["execution_worker"])
        task = WorkerTask(
            task_type="execute_approved_plan",
            payload={
                "description": description,
                "plan": plan,
                "session_id": session_id,
                "snapshot_sha": snapshot_sha,
                "repo_root": self._repo_root,
            },
            requester="execution_runner",
        )
        try:
            result = self._coordinator.run(task)
            if self._intelligence:
                self._intelligence.observe(result, "execute_approved_plan")
            return result
        except Exception as exc:
            logger.exception("[EXEC_RUNNER] execute_plan raised.")
            return WorkerResult.failure("exec", "execution_runner", str(exc))

    def _run_tests(self) -> WorkerResult:
        """Run SuiteRunnerWorker regression gate."""
        self._ensure_workflow("run_tests", ["suite_runner_worker"])
        task = WorkerTask(
            task_type="run_tests",
            payload={"paths": ["tests/"], "verbose": False},
            requester="execution_runner",
        )
        try:
            result = self._coordinator.run(task)
            if self._intelligence:
                self._intelligence.observe(result, "run_tests")
            return result
        except Exception as exc:
            logger.exception("[EXEC_RUNNER] run_tests raised.")
            return WorkerResult.failure("tests", "execution_runner", str(exc))

    def _rollback(
        self,
        snapshot_sha: str,
        files_created: list[str],
        session_id: str,
    ) -> None:
        """Trigger RollbackWorker — automatic, no approval needed."""
        self._ensure_workflow("rollback_execution", ["rollback_worker"])
        task = WorkerTask(
            task_type="rollback_execution",
            payload={
                "snapshot_sha": snapshot_sha,
                "files_created": files_created,
                "repo_root": self._repo_root,
                "session_id": session_id,
            },
            requester="execution_runner",
        )
        try:
            result = self._coordinator.run(task)
            if self._intelligence:
                self._intelligence.observe(result, "rollback_execution")
            if not result.success:
                logger.error(
                    "[EXEC_RUNNER] Rollback failed: %s", result.error
                )
        except Exception:
            logger.exception("[EXEC_RUNNER] rollback raised.")

    def _ensure_workflow(self, name: str, workers: list[str]) -> None:
        try:
            self._coordinator.register_workflow(name, workers)
        except Exception:
            pass  # already registered

    def _failure_outcome(
        self,
        description: str,
        session_id: str,
        error: str,
        snapshot_sha: str = "",
    ) -> ExecutionOutcome:
        sep = "─" * 56
        markdown = "\n".join([
            sep,
            "EXECUTION FAILED",
            sep,
            f"Description: {description}",
            f"Error: {error}",
            "",
            "🚫 Changes have been rolled back." if snapshot_sha else "⚠️  No rollback anchor available.",
            sep,
        ])
        outcome = ExecutionOutcome(
            state=ApprovalLifecycleState.FAILED,
            description=description,
            summary=None,
            markdown=markdown,
            success=False,
            error=error,
            snapshot_sha=snapshot_sha,
            session_id=session_id,
        )
        self._last_outcome = outcome
        return outcome
