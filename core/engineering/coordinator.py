"""
Engineering Coordinator (Genesis-016 Sprint 001)

The single entry point for Jarvis engineering capabilities.

Sprint 001 provides repository awareness only: Jarvis can locate
files, list layers, and filter by role. No code analysis, no commits,
no autonomous changes.

Capability ladder (Earned Authority — Constitution Principle 1):
    Sprint 001 (this) — Repository Catalogue: find, layer, role
    Sprint 002        — Git Reader: status, log, diff, branch
    Sprint 003        — Guardrails: protected files, change limits
    Sprint 004        — Code Planner: spec to implementation plan
    Sprint 005        — Test Runner: pytest, regression detection
    Sprint 006        — Debug Loop: analyse, fix, retest
"""

import logging
import time
from pathlib import Path
from typing import Optional

from core.engineering.repository.catalogue import RepositoryCatalogue

logger = logging.getLogger(__name__)


class EngineeringCoordinator:
    """Central coordinator for Jarvis engineering capabilities."""

    def __init__(self, project_root=None):
        self._root = project_root
        self._catalogue = None
        self._ready = False
        self._init_ms = 0.0

    def initialise(self):
        """Build the catalogue. Call once at startup."""
        started = time.perf_counter()
        self._catalogue = RepositoryCatalogue(self._root).build()
        self._ready = True
        self._init_ms = (time.perf_counter() - started) * 1000.0
        stats = self._catalogue.stats()
        logger.info(
            "EngineeringCoordinator ready in %.1f ms — %d files across %d layers.",
            self._init_ms, stats["files"], stats["layers"],
        )
        return self

    def find(self, query: str) -> list:
        """Find files whose path contains the query string."""
        self._require_ready()
        return self._catalogue.find(query)

    def find_by_role(self, role: str) -> list:
        """Find files by architectural role keyword."""
        self._require_ready()
        return self._catalogue.find_by_role(role)

    def layer(self, name: str) -> list:
        """Return all files in a named architectural layer."""
        self._require_ready()
        return self._catalogue.layer(name)

    def status(self) -> str:
        """Return a human-readable status and capability summary."""
        if not self._ready:
            return "EngineeringCoordinator: not initialised. Call initialise() first."
        stats = self._catalogue.stats()
        return (
            f"EngineeringCoordinator - Sprint 001 (Repository Catalogue)\n"
            f"  Files catalogued: {stats['files']}\n"
            f"  Layers mapped:    {stats['layers']}\n"
            f"  Build time:       {stats['build_ms']} ms\n"
            f"  Capabilities:     find | find_by_role | layer\n"
            f"  Deferred:         symbol lookup, AST analysis (Sprint 002+)\n"
            f"  Next sprint:      Git awareness (status, log, diff, branch)"
        )

    def summary(self) -> str:
        """Return the catalogue project overview."""
        self._require_ready()
        return self._catalogue.summary()

    def _require_ready(self) -> None:
        if not self._ready:
            raise RuntimeError(
                "EngineeringCoordinator not initialised. Call initialise() first."
            )


    # ------------------------------------------------------------------
    # Sprint 002 -- Git Repository Awareness (read-only)
    # ------------------------------------------------------------------

    def git_status(self):
        """
        Return a GitStatus snapshot of the current repository state.

        Includes: branch, clean/dirty, modified files, untracked files,
        last commit hash and message, repository root.
        Read-only — no git write operations are ever performed.
        """
        from core.engineering.git.reader import GitReader
        return GitReader(self._root).status()

    def current_branch(self) -> str:
        """Return the current Git branch name."""
        from core.engineering.git.reader import GitReader
        return GitReader(self._root).current_branch()

    def modified_files(self) -> list:
        """Return tracked files with uncommitted changes."""
        from core.engineering.git.reader import GitReader
        return GitReader(self._root).modified_files()

    def repository_clean(self) -> bool:
        """Return True when the working tree has no uncommitted changes."""
        from core.engineering.git.reader import GitReader
        return GitReader(self._root).is_clean()