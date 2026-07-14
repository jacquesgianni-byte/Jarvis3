"""
Engineering Recommendation Models (Genesis-017 Sprint 005)

Immutable data carriers for engineering recommendations.

Design philosophy:
    "Based on the evidence, what engineering actions should be considered?"

    Recommendations are advisory only. They explain WHY they are being
    made by referencing concrete evidence. They never generate code,
    modify files, or execute actions.

    Every recommendation must answer:
    "Why are you recommending this?" with evidence from the investigation.
"""

from dataclasses import dataclass
from enum import Enum


class RecommendationCategory(Enum):
    """
    Deterministic category of an engineering recommendation.

    Each value maps to a specific, observable pattern in the evidence.
    NO_RECOMMENDATION is returned when the evidence yields no actionable
    advisory — honest silence is better than invented advice.
    """
    INVESTIGATE_SYNTAX        = "Investigate Syntax"
    VERIFY_IMPORTS            = "Verify Imports"
    CHECK_CONFIGURATION       = "Check Configuration"
    REVIEW_RECENT_COMMITS     = "Review Recent Commits"
    REVIEW_TEST_FAILURES      = "Review Test Failures"
    VERIFY_DEPENDENCIES       = "Verify Dependencies"
    CHECK_FILE_EXISTENCE      = "Check File Existence"
    REVIEW_API_USAGE          = "Review API Usage"
    MONITOR_REPEATED_FAILURES = "Monitor Repeated Failures"
    NO_RECOMMENDATION         = "No Recommendation"


class RecommendationPriority(Enum):
    """
    Deterministic priority level for an engineering recommendation.

    Derived purely from evidence — never AI-generated or guessed.
    """
    LOW      = "Low"
    MEDIUM   = "Medium"
    HIGH     = "High"
    CRITICAL = "Critical"


@dataclass(frozen=True)
class Recommendation:
    """
    Immutable advisory produced by RecommendationEngine.

    Never modified after creation. Contains only evidence-backed
    guidance — no code generation, no patch suggestions, no repairs.

    Every recommendation references the evidence that supports it
    so the Chief can evaluate the reasoning independently.

    Fields
    ------
    category            : What type of action is recommended.
    priority            : How urgently this should be considered.
    confidence          : 0.0 (speculative) → 1.0 (highly supported).
    title               : Short action title (verb phrase).
    description         : Why this is recommended, with evidence.
    supporting_evidence : Tuple of evidence lines that justify this.
    related_root_cause  : Root cause category that triggered this, or "".
    related_correlation : Correlation type that triggered this, or "".
    """

    category:            RecommendationCategory
    priority:            RecommendationPriority
    confidence:          float           # 0.0 – 1.0
    title:               str
    description:         str
    supporting_evidence: tuple           # evidence lines
    related_root_cause:  str             # root cause category value or ""
    related_correlation: str             # correlation type value or ""

    def summary_line(self) -> str:
        """One-line summary for report headers."""
        return (
            f"[{self.priority.value.upper()}] "
            f"{self.title} — {self.description[:80]}"
        )