"""
Git Reader (Genesis-016 Sprint 002)

Read-only access to Git repository state via subprocess.

Constitutional constraints — this module MUST NEVER call:
    git add, git commit, git checkout, git merge,
    git push, git reset, git restore, git rm,
    or any other write operation.

Those capabilities belong to future sprints that will earn them
by demonstrating reliable read-only behaviour first.
(Earned Authority — Jarvis Constitution Principle 1)

Every method returns a plain value or raises nothing — the reader
always produces a result, even when Git is unavailable.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from core.engineering.git.models import CommitInfo, GitStatus

logger = logging.getLogger(__name__)

# Timeout for every git subprocess call (seconds).
# Keeps the reader responsive even on slow filesystems.
_GIT_TIMEOUT = 5


class GitReader:
    """
    Read-only interface to a Git repository.

    Uses subprocess to call git with a strict whitelist of safe,
    non-destructive commands. Any attempt to add write commands
    here violates the Constitutional constraints above.
    """

    def __init__(self, repo_root: str | Path | None = None):
        if repo_root is None:
            # Default: locate the repo root relative to this file.
            # core/engineering/git/status.py → ../../.. = project root
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
        self.repo_root = Path(repo_root).resolve()

    # ------------------------------------------------------------------
    # Public read-only API
    # ------------------------------------------------------------------

    def status(self) -> GitStatus:
        """
        Return a complete snapshot of the current repository state.

        Never raises. Returns a GitStatus with available=False and
        an error message if Git is not installed or this is not a
        Git repository.
        """
        if not self._git_available():
            return self._unavailable("git is not installed or not on PATH")

        if not self._is_git_repo():
            return self._unavailable(
                f"{self.repo_root} is not a Git repository"
            )

        branch = self._current_branch()
        modified, untracked = self._working_tree_changes()
        last_commit = self._last_commit()

        return GitStatus(
            available=True,
            root=str(self.repo_root),
            branch=branch,
            clean=not modified and not untracked,
            modified=tuple(modified),
            untracked=tuple(untracked),
            last_commit=last_commit,
        )

    def current_branch(self) -> str:
        """Return the current branch name, or 'unknown' on failure."""
        if not self._git_available() or not self._is_git_repo():
            return "unknown"
        return self._current_branch()

    def modified_files(self) -> list[str]:
        """Return a list of tracked files with uncommitted changes."""
        if not self._git_available() or not self._is_git_repo():
            return []
        modified, _ = self._working_tree_changes()
        return modified

    def untracked_files(self) -> list[str]:
        """Return a list of files not yet added to Git."""
        if not self._git_available() or not self._is_git_repo():
            return []
        _, untracked = self._working_tree_changes()
        return untracked

    def is_clean(self) -> bool:
        """Return True when the working tree has no uncommitted changes."""
        modified, untracked = self._working_tree_changes()
        return not modified and not untracked

    def last_commit(self) -> CommitInfo:
        """Return the most recent commit hash and message."""
        if not self._git_available() or not self._is_git_repo():
            return CommitInfo(short_hash="unknown", message="unknown")
        return self._last_commit()

    # ------------------------------------------------------------------
    # Internal helpers — all use _run() which is read-only by design
    # ------------------------------------------------------------------

    def _git_available(self) -> bool:
        try:
            self._run(["git", "--version"])
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _is_git_repo(self) -> bool:
        result = self._run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            check=False,
        )
        return result.returncode == 0

    def _current_branch(self) -> str:
        result = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip() or "unknown"

    def _working_tree_changes(self) -> tuple[list[str], list[str]]:
        """
        Parse `git status --porcelain` into (modified, untracked) lists.

        Porcelain format: two-character status code + space + filename.
            M  → modified (tracked)
            ?? → untracked
        """
        result = self._run(["git", "status", "--porcelain"])
        modified = []
        untracked = []
        for line in result.stdout.splitlines():
            if len(line) < 3:
                continue
            code = line[:2]
            filepath = line[3:]
            if code == "??":
                untracked.append(filepath)
            else:
                modified.append(filepath)
        return modified, untracked

    def _last_commit(self) -> CommitInfo:
        result = self._run(
            ["git", "log", "-1", "--pretty=format:%h|%s"],
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return CommitInfo(short_hash="none", message="no commits yet")
        parts = result.stdout.strip().split("|", 1)
        return CommitInfo(
            short_hash=parts[0] if parts else "unknown",
            message=parts[1] if len(parts) > 1 else "",
        )

    def _run(
        self,
        cmd: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run a git command in the repository root.

        SAFETY: this method only ever calls read-only git commands.
        The caller is responsible for ensuring only safe commands
        are passed. Write commands (add, commit, push, etc.) are
        never passed from this module.
        """
        return subprocess.run(
            cmd,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,    # we handle errors manually — never raises
        )

    def _unavailable(self, reason: str) -> GitStatus:
        logger.warning("GitReader: %s", reason)
        return GitStatus(
            available=False,
            root=str(self.repo_root),
            branch="unknown",
            clean=True,
            modified=(),
            untracked=(),
            last_commit=CommitInfo(short_hash="unknown", message="unknown"),
            error=reason,
        )