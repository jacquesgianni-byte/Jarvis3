"""
Jarvis ShiftController — Failure Containment (Sprint A)

Maps failure classes to their prescribed responses.
All failure responses are deterministic — no LLM involvement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class FailureClass(Enum):
    """Exhaustive enumeration of failure classes ShiftController can encounter."""
    TEST_REGRESSION_POST_REPAIR         = auto()
    DESKTOP_VALIDATION_FAILED           = auto()
    COMMIT_BOUNDARY_VIOLATION           = auto()
    ROLLBACK_FAILED                     = auto()
    SERVER_UNRESPONSIVE                 = auto()
    FINDING_ATTEMPTS_EXHAUSTED          = auto()
    CONSECUTIVE_DEGRADED_LIMIT          = auto()
    PROTECTED_COMPONENT_TOUCHED         = auto()
    RUNTIME_PATH_EXPANSION_ATTEMPTED    = auto()
    SOURCE_DIRTY_OUTSIDE_RUNTIME        = auto()
    PATH_TRAVERSAL_DETECTED             = auto()
    MANIFEST_WRITE_FAILED               = auto()
    REMOTE_STOP_RECEIVED                = auto()
    CYCLE_LIMIT_REACHED                 = auto()

    def label(self) -> str:
        return self.name


class FailureResponse(Enum):
    """Prescribed response to a failure class."""
    ROLLBACK            = auto()   # revert repair commit, re-validate, continue
    ABANDON_FINDING     = auto()   # mark finding ABANDONED, continue shift
    SERVER_RECOVERY     = auto()   # attempt controlled server restart
    HARD_STOP           = auto()   # freeze all repo activity, write manifest, notify Chief
    DEFER_FINDING       = auto()   # mark finding DEFERRED, continue shift
    COMPLETE_SHIFT      = auto()   # natural shift completion

    def label(self) -> str:
        return self.name

    @property
    def is_hard_stop(self) -> bool:
        return self == FailureResponse.HARD_STOP


@dataclass(frozen=True)
class ContainmentDecision:
    failure_class: FailureClass
    response: FailureResponse
    reason: str

    @property
    def is_hard_stop(self) -> bool:
        return self.response.is_hard_stop


# ---------------------------------------------------------------------------
# Failure → response mapping (exhaustive, deterministic)
# ---------------------------------------------------------------------------

_CONTAINMENT_TABLE: dict[FailureClass, tuple[FailureResponse, str]] = {
    FailureClass.TEST_REGRESSION_POST_REPAIR: (
        FailureResponse.ROLLBACK,
        "Suite regressed after repair commit — rolling back exact repair SHA.",
    ),
    FailureClass.DESKTOP_VALIDATION_FAILED: (
        FailureResponse.ROLLBACK,
        "Desktop validation failed after repair commit — rolling back exact repair SHA.",
    ),
    FailureClass.COMMIT_BOUNDARY_VIOLATION: (
        FailureResponse.HARD_STOP,
        "Commit boundary violation — unexpected files in staged area. HARD STOP.",
    ),
    FailureClass.ROLLBACK_FAILED: (
        FailureResponse.HARD_STOP,
        "Rollback failed — suite not restored after revert. HARD STOP.",
    ),
    FailureClass.SERVER_UNRESPONSIVE: (
        FailureResponse.SERVER_RECOVERY,
        "Server unresponsive — initiating controlled recovery sequence.",
    ),
    FailureClass.FINDING_ATTEMPTS_EXHAUSTED: (
        FailureResponse.ABANDON_FINDING,
        "Maximum repair attempts reached for finding — marking ABANDONED, continuing.",
    ),
    FailureClass.CONSECUTIVE_DEGRADED_LIMIT: (
        FailureResponse.HARD_STOP,
        "Two consecutive DEGRADED trajectory states — HARD STOP.",
    ),
    FailureClass.PROTECTED_COMPONENT_TOUCHED: (
        FailureResponse.HARD_STOP,
        "Proposed repair targets an autonomously protected component — HARD STOP.",
    ),
    FailureClass.RUNTIME_PATH_EXPANSION_ATTEMPTED: (
        FailureResponse.HARD_STOP,
        "Attempted to expand RUNTIME_DATA_PATHS — HARD STOP.",
    ),
    FailureClass.SOURCE_DIRTY_OUTSIDE_RUNTIME: (
        FailureResponse.HARD_STOP,
        "Source-dirty file detected outside RUNTIME_DATA_PATHS — HARD STOP.",
    ),
    FailureClass.PATH_TRAVERSAL_DETECTED: (
        FailureResponse.HARD_STOP,
        "Path traversal ('..' in dirty file path) detected — HARD STOP.",
    ),
    FailureClass.MANIFEST_WRITE_FAILED: (
        FailureResponse.HARD_STOP,
        "ShiftManifest write failed — cannot record state safely. HARD STOP.",
    ),
    FailureClass.REMOTE_STOP_RECEIVED: (
        FailureResponse.HARD_STOP,
        "Remote STOP command received from Chief. HARD STOP.",
    ),
    FailureClass.CYCLE_LIMIT_REACHED: (
        FailureResponse.COMPLETE_SHIFT,
        "Maximum repair cycle limit reached — completing shift normally.",
    ),
}


class FailureContainment:
    """
    Maps a FailureClass to a ContainmentDecision.
    All decisions are deterministic — no LLM involvement.
    """

    def decide(self, failure_class: FailureClass) -> ContainmentDecision:
        """
        Return the prescribed containment decision for a failure class.

        Raises:
            KeyError: If an unknown FailureClass is passed (defensive — all
                      known classes are in the table; a missing key indicates
                      a code defect, not a runtime condition).
        """
        if failure_class not in _CONTAINMENT_TABLE:
            # Unknown failure class is itself a HARD STOP condition
            return ContainmentDecision(
                failure_class=failure_class,
                response=FailureResponse.HARD_STOP,
                reason=f"Unknown failure class {failure_class!r} — HARD STOP.",
            )

        response, reason = _CONTAINMENT_TABLE[failure_class]
        return ContainmentDecision(
            failure_class=failure_class,
            response=response,
            reason=reason,
        )
