"""
Failure Correlation Models (Genesis-017 Sprint 004)

Immutable data carriers for failure correlation.

Design philosophy:
    "Has this happened before, and is it related to previous activity?"
    Answered from evidence. Never guessed.

CorrelationRecord is the output of FailureCorrelationEngine.
It connects the current failure to previously observed patterns.
If evidence is insufficient: correlation_type=UNKNOWN, confidence=0.0.
"""

from dataclasses import dataclass
from enum import Enum


class CorrelationType(Enum):
    """
    Deterministic classification of a failure correlation.

    Each value represents a specific, observable relationship between
    the current failure and previous engineering activity.
    UNKNOWN is the honest answer when no relationship is detected.
    """
    SAME_FILE       = "Same File"        # same source file(s) affected
    SAME_MODULE     = "Same Module"      # same module/package affected
    SAME_EXCEPTION  = "Same Exception"   # identical exception type
    SAME_ROOT_CAUSE = "Same Root Cause"  # identical root cause category
    SAME_COMMIT     = "Same Commit"      # same commit hash in context
    REPEATED_FAILURE = "Repeated Failure" # same failure seen multiple times
    UNKNOWN         = "Unknown"          # no correlation detected


@dataclass(frozen=True)
class CorrelationRecord:
    """
    Immutable record of failure correlation analysis.

    Produced by FailureCorrelationEngine. Never modified after creation.
    Answers: "Has this failure happened before, and how is it related
    to previous engineering activity?"

    Fields
    ------
    correlation_type    : The strongest detected correlation.
    confidence          : 0.0 (no correlation) → 1.0 (definitive).
    description         : Human-readable explanation of the correlation.
    related_failures    : Tuple of descriptions of related past failures.
    related_files       : Tuple of file paths appearing in multiple failures.
    related_modules     : Tuple of module names appearing in multiple failures.
    related_commits     : Tuple of commit hashes associated with failures.
    timeline            : Tuple of chronological observations (oldest first).
    """

    correlation_type:  CorrelationType
    confidence:        float            # 0.0 – 1.0
    description:       str
    related_failures:  tuple            # descriptions of correlated failures
    related_files:     tuple            # files appearing across failures
    related_modules:   tuple            # modules appearing across failures
    related_commits:   tuple            # commits associated with failures
    timeline:          tuple            # chronological observations

    @property
    def is_correlated(self) -> bool:
        """True when a meaningful correlation was detected."""
        return self.correlation_type != CorrelationType.UNKNOWN

    def summary_line(self) -> str:
        """One-line summary suitable for report headers."""
        if not self.is_correlated:
            return "No correlation detected with previous failures."
        return (
            f"{self.correlation_type.value} "
            f"(confidence {self.confidence:.0%}): {self.description}"
        )