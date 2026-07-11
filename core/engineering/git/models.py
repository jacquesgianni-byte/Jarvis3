"""
Git Status Models (Genesis-016 Sprint 002)

Pure data carriers for Git repository state.
No behaviour, no subprocess calls, no file modification.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommitInfo:
    """The most recent commit."""

    short_hash: str
    message: str


@dataclass(frozen=True)
class GitStatus:
    """
    A point-in-time snapshot of the Git repository state.

    All fields are read from the repository at query time and
    never written back. This object is immutable once created.
    """

    available: bool          # is git installed and repo detected?
    root: str                # absolute path to the repository root
    branch: str              # current branch name
    clean: bool              # True when working tree has no changes
    modified: tuple          # tracked files with uncommitted changes
    untracked: tuple         # files not yet added to git
    last_commit: CommitInfo  # most recent commit (hash + message)
    error: str = ""          # non-empty if git command failed

    @property
    def dirty(self) -> bool:
        return not self.clean

    @property
    def summary(self) -> str:
        """One-line human-readable status."""
        if not self.available:
            return f"Git unavailable: {self.error}"
        state = "clean" if self.clean else "dirty"
        parts = [f"branch={self.branch}", f"status={state}"]
        if self.modified:
            parts.append(f"modified={len(self.modified)}")
        if self.untracked:
            parts.append(f"untracked={len(self.untracked)}")
        parts.append(f"commit={self.last_commit.short_hash}")
        return " | ".join(parts)