"""
Git Worker — Autonomous Engineering Execution
Genesis-041 Sprint-002

GitWorker is the first worker with write access to the repository.

Capabilities:
  git_snapshot   — record HEAD SHA (non-destructive, no approval needed)
  git_checkout   — restore to a SHA (rollback only, no approval needed)
  git_commit     — create a commit (requires_approval=True always)
  git_push       — push to remote  (requires_approval=True always)

Design principles:
  - git_snapshot and git_checkout are used internally by the execution
    pipeline. They do not require human approval (they are safety
    operations, not engineering decisions).
  - git_commit and git_push always require human approval. No code path
    ever calls them autonomously.
  - GitWorker never calls AI. All decisions are deterministic.
  - Never raises — always returns WorkerResult.
  - Commit messages are structured and deterministic.
  - Push target is always the current branch (no force push ever).

Constitutional note:
  GitReader (Genesis-016) is read-only by its own constitution.
  GitWorker earns write authority by demonstrating reliable behaviour
  in isolated sprint validation before being wired into the execution
  pipeline. This follows the Earned Authority principle.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask

logger = logging.getLogger(__name__)

_GIT_TIMEOUT = 30   # seconds per git operation


class GitWorker(Worker):
    """
    Worker with write access to the Git repository.

    Registered as "git_worker" with four capabilities:
      git_snapshot  — record HEAD SHA before execution
      git_checkout  — restore to SHA (rollback)
      git_commit    — commit staged/tracked changes
      git_push      — push current branch to origin

    git_commit and git_push always set requires_approval=True.
    git_snapshot and git_checkout set requires_approval=False
    (they are safety operations, not engineering decisions).
    """

    def __init__(self, repo_root: Optional[str] = None) -> None:
        super().__init__()
        self._repo_root = repo_root or os.getcwd()

    # -- Worker contract ---------------------------------------------------

    @property
    def name(self) -> str:
        return "git_worker"

    @property
    def description(self) -> str:
        return (
            "Git worker for snapshot, rollback, commit, and push. "
            "commit and push always require human approval."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "git_snapshot",
            "git_checkout",
            "git_commit",
            "git_push",
        ]

    def validate(self, task: WorkerTask) -> bool:
        return task.task_type in self.capabilities

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        try:
            if task.task_type == "git_snapshot":
                return self._snapshot(task)
            if task.task_type == "git_checkout":
                return self._checkout(task)
            if task.task_type == "git_commit":
                return self._commit(task)
            if task.task_type == "git_push":
                return self._push(task)
            return self._fail(task.task_id, f"Unknown capability: {task.task_type}")
        except Exception as exc:
            logger.exception("[GIT_WORKER] Unexpected error in execute().")
            return self._fail(task.task_id, str(exc))

    # -- Capabilities ------------------------------------------------------

    def _snapshot(self, task: WorkerTask) -> WorkerResult:
        """
        Record the current HEAD SHA.

        Returns WorkerResult.data["sha"] — the rollback anchor.
        requires_approval=False — this is a safety operation.
        """
        sha = self._run(["git", "rev-parse", "HEAD"])
        if sha is None:
            return self._fail(task.task_id, "git rev-parse HEAD failed.")

        sha = sha.strip()
        logger.info("[GIT_WORKER] Snapshot: HEAD=%s", sha[:8])

        return self._succeed(WorkerResult(
            task_id=task.task_id,
            worker_name=self.name,
            success=True,
            observations=(f"Snapshot recorded: {sha[:8]}",),
            recommendations=(),
            requires_approval=False,
            data={"sha": sha, "capability": "git_snapshot"},
        ))

    def _checkout(self, task: WorkerTask) -> WorkerResult:
        """
        Restore working tree to a given SHA.

        Expects task.payload["sha"] — the anchor from snapshot.
        Expects task.payload["files_created"] — new files to delete.
        requires_approval=False — this is an automatic rollback operation.
        """
        sha = task.payload.get("sha", "").strip()
        if not sha:
            return self._fail(task.task_id, "No SHA provided for git_checkout.")

        files_created = task.payload.get("files_created", [])

        # Restore tracked files to snapshot SHA
        output = self._run(["git", "checkout", sha, "--", "."])
        if output is None:
            return self._fail(
                task.task_id,
                f"git checkout {sha[:8]} failed.",
            )

        # Delete new untracked files that didn't exist at snapshot time
        deleted = []
        for rel_path in files_created:
            abs_path = os.path.join(self._repo_root, rel_path)
            if os.path.exists(abs_path):
                try:
                    os.remove(abs_path)
                    deleted.append(rel_path)
                except Exception as e:
                    logger.warning("[GIT_WORKER] Could not delete %s: %s", rel_path, e)

        msg = f"Rolled back to {sha[:8]}."
        if deleted:
            msg += f" Deleted {len(deleted)} new file(s)."

        logger.info("[GIT_WORKER] %s", msg)

        return self._succeed(WorkerResult(
            task_id=task.task_id,
            worker_name=self.name,
            success=True,
            observations=(msg,),
            recommendations=(),
            requires_approval=False,
            data={
                "sha": sha,
                "files_deleted": deleted,
                "capability": "git_checkout",
            },
        ))

    def _commit(self, task: WorkerTask) -> WorkerResult:
        """
        Stage all tracked changes and create a commit.

        Expects task.payload["message"] — commit message (optional).
        Expects task.payload["session_id"] — for structured message.
        Expects task.payload["description"] — for structured message.
        requires_approval=True — ALWAYS. Never call autonomously.
        """
        session_id = task.payload.get("session_id", "unknown")[:8]
        description = task.payload.get("description", "Engineering change")
        custom_message = task.payload.get("message", "")

        if custom_message:
            message = custom_message
        else:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            message = (
                f"[Jarvis] {description}\n\n"
                f"Approved by: human\n"
                f"Session: {session_id}\n"
                f"Date: {now}"
            )

        # Stage all tracked changes (git add -u — never adds untracked files)
        add_output = self._run(["git", "add", "-u"])
        if add_output is None:
            return self._fail(task.task_id, "git add -u failed.")

        # Create commit
        commit_output = self._run(["git", "commit", "-m", message])
        if commit_output is None:
            return self._fail(task.task_id, "git commit failed.")

        # Get the new commit SHA
        sha = self._run(["git", "rev-parse", "HEAD"])
        sha = sha.strip() if sha else "unknown"

        logger.info("[GIT_WORKER] Committed: %s", sha[:8])

        return self._succeed(WorkerResult(
            task_id=task.task_id,
            worker_name=self.name,
            success=True,
            observations=(
                f"Committed: {sha[:8]}",
                f"Message: {message.splitlines()[0]}",
            ),
            recommendations=("Review commit before pushing.",),
            requires_approval=True,   # always — permanent principle
            data={
                "sha": sha,
                "message": message,
                "capability": "git_commit",
            },
        ))

    def _push(self, task: WorkerTask) -> WorkerResult:
        """
        Push the current branch to origin.

        Never force-pushes. Always pushes to current branch.
        requires_approval=True — ALWAYS. Never call autonomously.
        """
        # Get current branch
        branch = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if branch is None:
            return self._fail(task.task_id, "Could not determine current branch.")
        branch = branch.strip()

        if branch in ("HEAD", "unknown", ""):
            return self._fail(
                task.task_id,
                f"Cannot push: detached HEAD or unknown branch ({branch!r}).",
            )

        # Push — never force
        push_output = self._run(["git", "push", "origin", branch])
        if push_output is None:
            return self._fail(
                task.task_id,
                f"git push origin {branch} failed.",
            )

        logger.info("[GIT_WORKER] Pushed to origin/%s", branch)

        return self._succeed(WorkerResult(
            task_id=task.task_id,
            worker_name=self.name,
            success=True,
            observations=(f"Pushed to origin/{branch}.",),
            recommendations=(),
            requires_approval=True,   # always — permanent principle
            data={
                "branch": branch,
                "capability": "git_push",
            },
        ))

    # -- Internal ----------------------------------------------------------

    def _run(self, cmd: list[str]) -> Optional[str]:
        """
        Run a git command. Returns stdout on success, None on failure.
        Never raises.
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
            )
            if result.returncode != 0:
                logger.warning(
                    "[GIT_WORKER] %s failed (rc=%d): %s",
                    " ".join(cmd[:3]),
                    result.returncode,
                    result.stderr.strip()[:200],
                )
                return None
            return result.stdout
        except subprocess.TimeoutExpired:
            logger.error("[GIT_WORKER] %s timed out.", " ".join(cmd[:3]))
            return None
        except Exception as exc:
            logger.exception("[GIT_WORKER] %s raised.", " ".join(cmd[:3]))
            return None
