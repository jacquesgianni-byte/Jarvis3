"""
Recommendation Engine (Genesis-017 Sprint 005)

Produces deterministic, evidence-backed engineering recommendations
from the structured output of previous pipeline stages.

Responsibility: analyse evidence + root cause + correlation →
               produce a tuple of Recommendations.

Constitutional constraints — this module MUST NEVER:
    * Repair or modify files.
    * Generate code or patches.
    * Call AI or LLM providers.
    * Execute engineering actions.
    * Invent advice without supporting evidence.
    * Recommend fixing without evidence of the problem.

Design philosophy:
    A recommendation sounds like a senior engineer:
        "Review the recent commit — three failures correlate to it."
    NOT like a code generator:
        "Replace line 77 with: ..."

    Every recommendation references concrete evidence.
    Jarvis never invents advice.

Pipeline position:
    FailureEvidence + FailureType + RootCause + CorrelationRecord
    → RecommendationEngine
    → tuple[Recommendation]
    → DebugReport
"""

import logging
from core.engineering.debugging.models import FailureEvidence, FailureType
from core.engineering.debugging.root_cause import RootCause, RootCauseCategory
from core.engineering.debugging.correlation import CorrelationRecord, CorrelationType
from core.engineering.debugging.recommendation import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule tables — each maps an observable condition to a recommendation.
# Priority and confidence are determined by specificity of the evidence.
# ---------------------------------------------------------------------------

# Root cause → recommendation
_ROOT_CAUSE_RULES: dict[
    RootCauseCategory,
    tuple[RecommendationCategory, RecommendationPriority, float, str, str]
] = {
    # category, priority, confidence, title, description_template
    RootCauseCategory.SYNTAX_ERROR: (
        RecommendationCategory.INVESTIGATE_SYNTAX,
        RecommendationPriority.HIGH,
        0.95,
        "Investigate syntax error",
        "A syntax error was detected. Review the reported file and line number "
        "to correct the syntax before re-running validation.",
    ),
    RootCauseCategory.MISSING_MODULE: (
        RecommendationCategory.VERIFY_DEPENDENCIES,
        RecommendationPriority.HIGH,
        0.95,
        "Verify module dependencies",
        "A required module could not be found. Verify that all dependencies "
        "are installed and that the module path is correct.",
    ),
    RootCauseCategory.IMPORT_DEPENDENCY: (
        RecommendationCategory.VERIFY_IMPORTS,
        RecommendationPriority.HIGH,
        0.90,
        "Verify import paths",
        "An import failed. Check that the module exists at the expected path "
        "and that there are no circular import issues.",
    ),
    RootCauseCategory.CONFIGURATION: (
        RecommendationCategory.CHECK_CONFIGURATION,
        RecommendationPriority.HIGH,
        0.90,
        "Check configuration settings",
        "A configuration error was detected. Verify environment variables, "
        ".env file contents, and Settings fields are correctly set.",
    ),
    RootCauseCategory.TEST_REGRESSION: (
        RecommendationCategory.REVIEW_TEST_FAILURES,
        RecommendationPriority.MEDIUM,
        0.85,
        "Review failing tests",
        "One or more tests failed. Review the test output and determine "
        "whether behaviour has changed or the test expectations need updating.",
    ),
    RootCauseCategory.INVALID_API: (
        RecommendationCategory.REVIEW_API_USAGE,
        RecommendationPriority.MEDIUM,
        0.85,
        "Review API usage",
        "An object was accessed with an incorrect attribute or method. "
        "Verify that the API contract has not changed since the last freeze.",
    ),
    RootCauseCategory.MISSING_FILE: (
        RecommendationCategory.CHECK_FILE_EXISTENCE,
        RecommendationPriority.HIGH,
        0.92,
        "Verify required file exists",
        "A required file or path was not found. Confirm the file exists "
        "at the expected location and has not been renamed or deleted.",
    ),
    RootCauseCategory.PERMISSION: (
        RecommendationCategory.CHECK_FILE_EXISTENCE,
        RecommendationPriority.MEDIUM,
        0.85,
        "Check file permissions",
        "A permission error was encountered. Verify that the process has "
        "appropriate access rights to the affected file or directory.",
    ),
    RootCauseCategory.TIMEOUT: (
        RecommendationCategory.MONITOR_REPEATED_FAILURES,
        RecommendationPriority.MEDIUM,
        0.90,
        "Investigate timeout",
        "The process exceeded the time limit. Consider whether the timeout "
        "threshold is appropriate or if the process is hanging.",
    ),
}

# Correlation → additional recommendation
_CORRELATION_RULES: dict[
    CorrelationType,
    tuple[RecommendationCategory, RecommendationPriority, float, str, str]
] = {
    CorrelationType.REPEATED_FAILURE: (
        RecommendationCategory.MONITOR_REPEATED_FAILURES,
        RecommendationPriority.CRITICAL,
        0.97,
        "Address recurring failure pattern",
        "This failure has been seen multiple times. It represents a systemic "
        "issue rather than an isolated event — prioritise investigation before "
        "making further engineering changes.",
    ),
    CorrelationType.SAME_COMMIT: (
        RecommendationCategory.REVIEW_RECENT_COMMITS,
        RecommendationPriority.HIGH,
        0.95,
        "Review associated commit",
        "Multiple failures correlate to the same commit. Review the changes "
        "introduced by that commit to identify the regression source.",
    ),
    CorrelationType.SAME_ROOT_CAUSE: (
        RecommendationCategory.MONITOR_REPEATED_FAILURES,
        RecommendationPriority.HIGH,
        0.90,
        "Investigate shared root cause",
        "Multiple failures share the same root cause. A single underlying "
        "issue may be responsible — investigate the common cause.",
    ),
    CorrelationType.SAME_EXCEPTION: (
        RecommendationCategory.REVIEW_API_USAGE,
        RecommendationPriority.MEDIUM,
        0.85,
        "Review recurring exception type",
        "The same exception type has appeared in multiple failures. "
        "Review all usage of the relevant API or module.",
    ),
    CorrelationType.SAME_FILE: (
        RecommendationCategory.INVESTIGATE_SYNTAX,
        RecommendationPriority.MEDIUM,
        0.82,
        "Review repeatedly failing file",
        "The same file has appeared in multiple failures. "
        "This file may require closer inspection or additional tests.",
    ),
    CorrelationType.SAME_MODULE: (
        RecommendationCategory.VERIFY_IMPORTS,
        RecommendationPriority.LOW,
        0.78,
        "Review affected module",
        "The same module has appeared across multiple failures. "
        "Consider whether the module interface has changed.",
    ),
}


class RecommendationEngine:
    """
    Produces deterministic, evidence-backed engineering recommendations.

    Read-only. No files modified. No code generated. No repairs suggested.
    Returns an empty tuple when no evidence supports a recommendation.
    """

    def recommend(
        self,
        evidence: FailureEvidence,
        failure_type: FailureType,
        root_cause: RootCause,
        correlation: CorrelationRecord,
    ) -> tuple:
        """
        Produce a tuple of Recommendations from the available evidence.

        Args:
            evidence:     FailureEvidence from EvidenceExtractor.
            failure_type: FailureType from FailureClassifier.
            root_cause:   RootCause from RootCauseAnalyzer.
            correlation:  CorrelationRecord from FailureCorrelationEngine.

        Returns:
            Immutable tuple of Recommendation objects, ordered by
            priority (CRITICAL first, LOW last).
            Empty tuple when no recommendations are warranted.
            Never raises.
        """
        # Success — no recommendations
        if evidence.exit_code == 0:
            return ()

        recs: list[Recommendation] = []

        # Layer 1: root cause recommendations (primary source)
        rc_rec = self._from_root_cause(root_cause, evidence)
        if rc_rec:
            recs.append(rc_rec)

        # Layer 2: correlation recommendations (secondary source)
        corr_rec = self._from_correlation(correlation, root_cause)
        if corr_rec and not self._is_duplicate(corr_rec, recs):
            recs.append(corr_rec)

        # Sort by priority (CRITICAL=0, HIGH=1, MEDIUM=2, LOW=3)
        priority_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH:     1,
            RecommendationPriority.MEDIUM:   2,
            RecommendationPriority.LOW:      3,
        }
        recs.sort(key=lambda r: priority_order[r.priority])

        logger.info(
            "RecommendationEngine: %d recommendation(s) produced for %s",
            len(recs), failure_type.value,
        )
        return tuple(recs)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _from_root_cause(
        self,
        root_cause: RootCause,
        evidence: FailureEvidence,
    ) -> Recommendation | None:
        """Produce a recommendation from the root cause."""
        if root_cause.category == RootCauseCategory.UNKNOWN:
            return None

        rule = _ROOT_CAUSE_RULES.get(root_cause.category)
        if not rule:
            return None

        category, priority, confidence, title, description = rule

        # Enrich description with specific evidence
        enriched = self._enrich_description(
            description, root_cause, evidence
        )

        return Recommendation(
            category=category,
            priority=priority,
            confidence=confidence,
            title=title,
            description=enriched,
            supporting_evidence=root_cause.supporting_evidence[:5],
            related_root_cause=root_cause.category.value,
            related_correlation="",
        )

    def _from_correlation(
        self,
        correlation: CorrelationRecord,
        root_cause: RootCause,
    ) -> Recommendation | None:
        """Produce a recommendation from correlation findings."""
        if not correlation.is_correlated:
            return None

        rule = _CORRELATION_RULES.get(correlation.correlation_type)
        if not rule:
            return None

        category, priority, confidence, title, description = rule

        # Include related files/commits in supporting evidence
        supporting: list[str] = []
        if correlation.related_files:
            supporting.extend(
                f"Related file: {f}" for f in correlation.related_files[:3]
            )
        if correlation.related_commits:
            supporting.extend(
                f"Related commit: {c}" for c in correlation.related_commits[:2]
            )
        supporting.extend(
            str(f) for f in correlation.related_failures[:2]
        )

        return Recommendation(
            category=category,
            priority=priority,
            confidence=confidence,
            title=title,
            description=description,
            supporting_evidence=tuple(supporting[:5]),
            related_root_cause=root_cause.category.value,
            related_correlation=correlation.correlation_type.value,
        )

    def _enrich_description(
        self,
        base: str,
        root_cause: RootCause,
        evidence: FailureEvidence,
    ) -> str:
        """Add specific file/line context to a description."""
        if evidence.failing_files:
            base += f" Affected: {evidence.failing_files[0]}."
        if evidence.line_numbers:
            base += f" Line: {evidence.line_numbers[0]}."
        return base

    def _is_duplicate(
        self,
        candidate: Recommendation,
        existing: list[Recommendation],
    ) -> bool:
        """Avoid recommending the same category twice."""
        return any(r.category == candidate.category for r in existing)