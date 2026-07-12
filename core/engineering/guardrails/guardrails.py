"""
Engineering Guardrails (Genesis-016 Sprint 003)

Validates proposed engineering tasks against configurable safety rules
before any action is taken.

Constitutional constraints — this module MUST NEVER:
    * Modify any file.
    * Execute any Git command.
    * Apply any patch or change.
    * Approve its own tasks automatically.

Sprint 003 earns authority only over planning and validation.
Write operations, backups, and automatic execution belong to future
sprints that will earn them by building on this trusted foundation.
(Earned Authority — Jarvis Constitution Principle 1)

Rules evaluated (in order):
    1. Protected path check  — any match → REQUIRES_APPROVAL
    2. File count limit      — exceeds max → REJECTED
    3. Otherwise             → APPROVED
"""

import logging
from pathlib import Path

from core.engineering.guardrails.models import (
    ApprovalStatus,
    EngineeringPlan,
)
from core.settings.settings import Settings

logger = logging.getLogger(__name__)

# Default protected path prefixes. Any proposed file whose path starts
# with one of these strings will trigger REQUIRES_APPROVAL regardless
# of file count. Paths are matched case-insensitively on Windows.
_DEFAULT_PROTECTED = (
    ".git/",
    ".env",
    "docs/",
)

# Default maximum number of files a single task may modify before the
# guardrail rejects it outright.
_DEFAULT_MAX_FILES = 5


class EngineeringGuardrails:
    """
    Validates proposed engineering tasks against safety rules.

    Instantiate with optional configuration overrides; call evaluate()
    to produce an EngineeringPlan. The plan records what was proposed
    and what was decided — nothing is ever executed.
    """

    def __init__(
        self,
        max_files: int = None,
        protected_paths: tuple = _DEFAULT_PROTECTED,
    ):
        """
        Args:
            max_files:        Hard limit on files per task. A task
                              proposing more than this is REJECTED.
                              Defaults to Settings.engineering_max_files
                              (env: ENGINEERING_MAX_FILES, default 5).
            protected_paths:  Path prefixes that trigger
                              REQUIRES_APPROVAL. Tuple so it is
                              immutable and auditable.
        """
        if max_files is None:
            max_files = Settings().engineering_max_files
        self.max_files = max_files
        self.protected_paths = tuple(protected_paths)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, task: str, files: list[str]) -> EngineeringPlan:
        """
        Evaluate a proposed engineering task against the guardrail rules.

        Args:
            task:   Human-readable description of what the task does.
            files:  List of file paths the task intends to modify.

        Returns:
            An EngineeringPlan with the evaluation result. Never raises.
            Nothing is written or executed.
        """
        # Deduplicate while preserving first-occurrence order.
        # A task listing the same file twice is a planning error,
        # not two changes. dict.fromkeys() is the idiomatic
        # order-preserving deduplicate in Python 3.7+.
        files = list(dict.fromkeys(files))
        total = len(files)
        protected = self._find_protected(files)

        # Rule 1: file count limit (hard reject — Chief cannot override
        # without revising scope)
        if total > self.max_files:
            reason = (
                f"Task proposes {total} file(s) but the limit is "
                f"{self.max_files}. Reduce scope before proceeding."
            )
            plan = EngineeringPlan(
                task=task,
                files_to_modify=tuple(files),
                protected_files_encountered=tuple(protected),
                total_files=total,
                max_files_allowed=self.max_files,
                status=ApprovalStatus.REJECTED,
                reason=reason,
            )
            logger.warning("Guardrails REJECTED: %s", reason)
            return plan

        # Rule 2: protected path encountered (soft block — Chief can
        # approve explicitly)
        if protected:
            reason = (
                f"{len(protected)} protected path(s) encountered: "
                f"{', '.join(protected)}. Chief approval required."
            )
            plan = EngineeringPlan(
                task=task,
                files_to_modify=tuple(files),
                protected_files_encountered=tuple(protected),
                total_files=total,
                max_files_allowed=self.max_files,
                status=ApprovalStatus.REQUIRES_APPROVAL,
                reason=reason,
            )
            logger.info("Guardrails REQUIRES_APPROVAL: %s", reason)
            return plan

        # Rule 3: all clear
        reason = (
            f"{total} file(s) within limit ({self.max_files}), "
            "no protected paths."
        )
        plan = EngineeringPlan(
            task=task,
            files_to_modify=tuple(files),
            protected_files_encountered=(),
            total_files=total,
            max_files_allowed=self.max_files,
            status=ApprovalStatus.APPROVED,
            reason=reason,
        )
        logger.info("Guardrails APPROVED: %s", reason)
        return plan

    def is_protected(self, filepath: str) -> bool:
        """Return True if the path matches any protected prefix."""
        return bool(self._find_protected([filepath]))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_protected(self, files: list[str]) -> list[str]:
        """Return the subset of files that match a protected prefix."""
        result = []
        for f in files:
            f_lower = f.replace("\\", "/").lower()
            for prefix in self.protected_paths:
                if f_lower.startswith(prefix.lower()):
                    result.append(f)
                    break
        return result