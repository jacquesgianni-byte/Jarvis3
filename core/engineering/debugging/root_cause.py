"""
Root Cause Models (Genesis-017 Sprint 003)

Immutable data carriers for root cause analysis.

Design philosophy:
    "Why did this happen?" — answered from evidence, never guessed.

RootCause is the output of RootCauseAnalyzer.
It is never produced by assumption.
If evidence is insufficient: category=UNKNOWN, confidence=0.0.
"""

from dataclasses import dataclass
from enum import Enum


class RootCauseCategory(Enum):
    """
    Deterministic classification of a failure's root cause.

    Each value maps to a specific, observable pattern in the evidence.
    UNKNOWN is the honest answer when no pattern matches.
    """
    SYNTAX_ERROR       = "Syntax Error"
    IMPORT_DEPENDENCY  = "Import Dependency"
    MISSING_MODULE     = "Missing Module"
    CONFIGURATION      = "Configuration Error"
    TEST_REGRESSION    = "Test Regression"
    INVALID_API        = "Invalid API Usage"
    MISSING_FILE       = "Missing File"
    PERMISSION         = "Permission Error"
    TIMEOUT            = "Timeout"
    UNKNOWN            = "Unknown"


@dataclass(frozen=True)
class RootCause:
    """
    Immutable root cause determination for an engineering failure.

    Produced by RootCauseAnalyzer. Never modified after creation.
    Contains only what can be determined from observed evidence —
    no speculation, no repair suggestions.

    Fields
    ------
    category             : RootCauseCategory — the most likely cause.
    description          : Human-readable explanation of the root cause.
    confidence           : 0.0 (unknown) → 1.0 (definitive).
    supporting_evidence  : Tuple of evidence lines that support this conclusion.
    contributing_factors : Tuple of additional observations that influenced
                           the determination (e.g. related files, error chain).
    """

    category:             RootCauseCategory
    description:          str
    confidence:           float           # 0.0 – 1.0
    supporting_evidence:  tuple           # lines from FailureEvidence
    contributing_factors: tuple           # additional context, may be empty

    def summary_line(self) -> str:
        """One-line summary suitable for report headers."""
        return (
            f"{self.category.value} "
            f"(confidence {self.confidence:.0%}): {self.description}"
        )