"""
Jarvis ShiftController — Source-Clean Enforcement (Sprint A)

Single source of truth for:
    RUNTIME_DATA_PATHS      — paths allowed to be dirty without blocking repair
    AUTONOMOUSLY_PROTECTED  — files ShiftController may NEVER modify
    GOVERNED_HIGH_RISK      — files requiring a separate manual governed sprint

GOVERNANCE CONSTRAINTS
    - RUNTIME_DATA_PATHS is a frozenset. It cannot be expanded by any
      LOW-risk autonomous repair. Any proposed change is classified HIGH.
    - AUTONOMOUSLY_PROTECTED is a frozenset. Chief approval does NOT
      unlock these for autonomous repair. Findings touching them are
      logged and surfaced to Chief as information only.
    - GOVERNED_HIGH_RISK is a frozenset. ShiftController surfaces findings
      to Chief but does not execute repairs autonomously.
    - Both sets are module-level constants. They are not parameters,
      not config files, not injectable at runtime.

MATCHING SEMANTICS
    - Repository-relative paths only.
    - Prefix matching: a path matches if it starts with an approved prefix.
    - Case-sensitive.
    - No wildcards.
    - No fuzzy matching.
    - Any path containing '..' triggers HARD ABORT regardless of other rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Runtime data paths — allowed dirty, never enter engineering commits
# ---------------------------------------------------------------------------

RUNTIME_DATA_PATHS: frozenset[str] = frozenset([
    "data/genesis_contributions/",
    "data/situational_memory/",
    "data/sprint_states/",
    "data/orchestrator/sessions/",
    "data/orchestrator/investigations/",
    "data/logs/",
    "data/shift_manifests/",
])


# ---------------------------------------------------------------------------
# Autonomously protected — ShiftController may never modify these
# Chief approval does NOT unlock them for autonomous repair
# ---------------------------------------------------------------------------

AUTONOMOUSLY_PROTECTED: frozenset[str] = frozenset([
    "core/shift/shift_controller.py",
    "core/shift/risk_classifier.py",
    "core/shift/failure_containment.py",
    "core/shift/source_clean.py",
    "core/shift/server_recovery.py",
    "apps/server/sprint_routes.py",
    "core/knowledge/genesis_contributions.py",
    "core/mission/intent/",
    "core/mission/engineering_intent/",
    "core/mission/authority/",
    "core/mission/approval/",
    "core/mission/risk/",
    "core/mission/routing/",
    "core/mission/safety/",
])


# ---------------------------------------------------------------------------
# Governed high-risk — surface to Chief, separate manual sprint required
# ShiftController does not execute repairs on these autonomously
# ---------------------------------------------------------------------------

GOVERNED_HIGH_RISK: frozenset[str] = frozenset([
    "core/workers/registry.py",
    "core/workers/coordinator.py",
    "core/workers/manager.py",
    "core/workers/base.py",
    "core/workers/models.py",
    "apps/server/app.py",
    "apps/server/server_main.py",
    "core/mission/pipeline.py",
    "core/mission/context/context_build_stage.py",
    "core/mission/dispatch/dispatch_stage.py",
    "apps/desktop/main.py",
])


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class CleanResult(Enum):
    CLEAN               = auto()   # source is clean, repair may proceed
    HARD_ABORT          = auto()   # source dirty or path traversal detected


@dataclass(frozen=True)
class SourceCleanAssertion:
    result: CleanResult
    reason: str
    offending_path: str = ""

    @property
    def is_clean(self) -> bool:
        return self.result == CleanResult.CLEAN

    @classmethod
    def clean(cls) -> "SourceCleanAssertion":
        return cls(result=CleanResult.CLEAN, reason="Source is clean.")

    @classmethod
    def hard_abort(cls, reason: str, path: str = "") -> "SourceCleanAssertion":
        return cls(result=CleanResult.HARD_ABORT, reason=reason, offending_path=path)


# ---------------------------------------------------------------------------
# Core assertion
# ---------------------------------------------------------------------------

def assert_source_clean(dirty_files: list[str]) -> SourceCleanAssertion:
    """
    Assert that the working tree is source-clean.

    A source-clean tree may have runtime-dirty files (RUNTIME_DATA_PATHS).
    Any file outside RUNTIME_DATA_PATHS that is dirty → HARD_ABORT.
    Any path containing '..' → HARD_ABORT regardless of other rules.

    Args:
        dirty_files: Repository-relative paths of all dirty files,
                     as returned by 'git status --porcelain'.

    Returns:
        SourceCleanAssertion — .is_clean is True if repair may proceed.
    """
    for path in dirty_files:
        # Path traversal guard — absolute first, no exceptions
        if ".." in path:
            return SourceCleanAssertion.hard_abort(
                reason="Path traversal detected — '..' found in dirty file path.",
                path=path,
            )

        # Check against runtime exclusions
        if not any(path.startswith(prefix) for prefix in RUNTIME_DATA_PATHS):
            return SourceCleanAssertion.hard_abort(
                reason=f"Unexpected source-dirty file outside runtime paths.",
                path=path,
            )

    return SourceCleanAssertion.clean()


# ---------------------------------------------------------------------------
# Component classification helpers
# ---------------------------------------------------------------------------

def classify_file(repo_relative_path: str) -> str:
    """
    Classify a file path against the three protection tiers.

    Returns:
        'AUTONOMOUSLY_PROTECTED'
        'GOVERNED_HIGH_RISK'
        'STANDARD'
    """
    for protected in AUTONOMOUSLY_PROTECTED:
        if repo_relative_path.startswith(protected):
            return "AUTONOMOUSLY_PROTECTED"
    for high_risk in GOVERNED_HIGH_RISK:
        if repo_relative_path.startswith(high_risk):
            return "GOVERNED_HIGH_RISK"
    return "STANDARD"


def is_runtime_path_expansion_attempt(proposed_paths: list[str]) -> bool:
    """
    Return True if proposed_paths contains any path not already in
    RUNTIME_DATA_PATHS. Used to detect attempted runtime expansion.
    """
    for path in proposed_paths:
        if path not in RUNTIME_DATA_PATHS:
            return True
    return False
