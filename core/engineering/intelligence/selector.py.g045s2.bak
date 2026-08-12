"""
Improvement Selector — Genesis-045 Sprint-001

Deterministic selection of the single highest-priority improvement
from an EngineeringReport. No AI. Fully testable.

Selection algorithm:
  1. Filter to HIGH severity issues only (Sprint-001 threshold)
  2. Skip issues rejected within the last REJECTION_SUPPRESSION_CYCLES
  3. Score remaining: severity_weight × confidence × frequency_boost
  4. Return top scorer as ImprovementProposal, or None

One proposal at a time. Returns None if one is already PENDING.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Cycle suppression after rejection
REJECTION_SUPPRESSION_CYCLES: int = 5

# Minimum confidence to form a proposal
MIN_CONFIDENCE: float = 0.50


def _build_inference(issue, frequency: int) -> str:
    """Build an explicit inference string from an issue."""
    freq_note = f" (seen {frequency} time(s) this session)" if frequency > 1 else ""
    return (
        f"The {issue.category.value if hasattr(issue.category, 'value') else issue.category} "
        f"pattern '{issue.title}' suggests a recurring architectural gap{freq_note}. "
        f"This is an inference — it may reflect a transient condition rather than "
        f"a structural problem."
    )


def _build_uncertainty(issue) -> str:
    """Build an uncertainty statement for a finding."""
    return (
        f"This finding is based on a single analysis cycle. "
        f"The issue may be transient or context-specific. "
        f"Confidence: {issue.confidence * 100:.0f}%."
    )


def _build_recommendation(issue) -> tuple[str, str, str]:
    """Return (proposed_change, expected_benefit, validation_plan) for an issue."""
    cat = issue.category.value if hasattr(issue.category, "value") else str(issue.category)

    if cat == "ROUTING":
        return (
            "Investigate the intent routing path for utterances that fall back to AI. "
            "Consider whether new intent patterns or slot types would reduce AI_FALLBACK rate.",
            "Fewer AI fallbacks means faster, more deterministic responses. "
            "Users receive answers without AI latency.",
            "Run a session with the same utterance types. "
            "Verify AI_FALLBACK rate drops in the next EngineeringReport.",
        )
    elif cat == "MEMORY":
        return (
            "Investigate the memory retrieval path for misses or stale data. "
            "Consider whether entity registration or knowledge recency ranking needs improvement.",
            "Correct memory recall means users get accurate answers from stored knowledge "
            "without needing to repeat themselves.",
            "Run a session repeating the failing memory query. "
            "Verify memory hit rate improves in the next EngineeringReport.",
        )
    elif cat == "PERFORMANCE":
        return (
            "Investigate the latency outlier identified in the report. "
            "Consider whether caching, early exit, or async handling would help.",
            "Lower latency means faster responses and a more responsive experience.",
            "Run a session with similar request types. "
            "Verify stage timing in the next EngineeringReport.",
        )
    elif cat == "EXCEPTION":
        return (
            "Investigate the exception source identified in likely_files. "
            "Add defensive handling or better error boundaries.",
            "Fewer unhandled exceptions means more reliable responses "
            "and better error recovery.",
            "Run a session that reproduces the error condition. "
            "Verify no exception appears in the next EngineeringReport.",
        )
    else:
        return (
            f"Investigate the {cat} issue: {issue.title}.",
            "Resolving this issue should improve overall session health score.",
            "Verify the issue does not recur in the next EngineeringReport.",
        )


class ImprovementSelector:
    """
    Selects one ImprovementProposal from an EngineeringReport.

    Deterministic. No AI. Testable in isolation.

    Public API:
        select(report, pattern_store, current_cycle, cfr_register) -> Optional[ImprovementProposal]
    """

    def select(
        self,
        report,
        pattern_store,
        current_cycle: int = 0,
        cfr_register: dict = None,
    ) -> "Optional[ImprovementProposal]":
        """
        Select the single highest-priority improvement from an EngineeringReport.

        Args:
            report:         EngineeringReport from SessionAnalysisWorker
            pattern_store:  PatternStore for frequency and rejection history
            current_cycle:  Current analysis cycle number (for rejection suppression)
            cfr_register:   Dict of open CFR entries {code: description} for cross-reference

        Returns:
            ImprovementProposal or None if no qualifying issue found.
        """
        from core.workers.engineering_models import Severity

        if cfr_register is None:
            cfr_register = {}

        if not report.has_issues():
            logger.info("[SELECTOR] No issues in report — no proposal.")
            return None

        # Filter to HIGH severity only (Sprint-001 threshold)
        high_issues = report.issues_by_severity(Severity.HIGH)
        if not high_issues:
            logger.info("[SELECTOR] No HIGH severity issues — no proposal.")
            return None

        # Score each issue
        candidates = []
        for issue in high_issues:
            cat   = issue.category.value if hasattr(issue.category, "value") else str(issue.category)
            title = issue.title

            # Skip if rejected too recently
            rejected_at = pattern_store.get_rejection_cycle(cat, title)
            if rejected_at > 0:
                cycles_since = current_cycle - rejected_at
                if cycles_since < REJECTION_SUPPRESSION_CYCLES:
                    logger.info(
                        "[SELECTOR] Skipping %r — rejected %d cycles ago (suppressed for %d).",
                        title, cycles_since, REJECTION_SUPPRESSION_CYCLES,
                    )
                    continue

            # Skip below confidence threshold
            if issue.confidence < MIN_CONFIDENCE:
                logger.info(
                    "[SELECTOR] Skipping %r — confidence %.2f below threshold %.2f.",
                    title, issue.confidence, MIN_CONFIDENCE,
                )
                continue

            # Score: confidence × frequency_boost
            frequency = pattern_store.get_frequency(cat, title)
            freq_boost = 1.0 + min(frequency * 0.1, 0.5)  # cap at 1.5x
            score = issue.confidence * freq_boost

            candidates.append((score, issue, frequency))

        if not candidates:
            logger.info("[SELECTOR] All HIGH issues filtered — no proposal.")
            return None

        # Select top scorer
        candidates.sort(key=lambda x: x[0], reverse=True)
        score, top_issue, frequency = candidates[0]
        cat   = top_issue.category.value if hasattr(top_issue.category, "value") else str(top_issue.category)
        title = top_issue.title

        logger.info(
            "[SELECTOR] Selected: %r (score=%.2f, conf=%.2f, freq=%d)",
            title, score, top_issue.confidence, frequency,
        )

        # Build observation layer — facts only
        from core.engineering.intelligence.models import Observation
        observation = Observation.from_issue(top_issue)

        # Check CFR cross-reference (read-only)
        cfr_ref = ""
        for cfr_code, cfr_desc in cfr_register.items():
            if cat.lower() in cfr_desc.lower() or title.lower() in cfr_desc.lower():
                cfr_ref = cfr_code
                break

        # Build diagnosis layer — inference, explicitly labelled
        from core.engineering.intelligence.models import Diagnosis
        diagnosis = Diagnosis(
            inference         = _build_inference(top_issue, frequency),
            confidence        = top_issue.confidence * 0.85,  # slightly lower than raw
            uncertainty       = _build_uncertainty(top_issue),
            likely_components = tuple(top_issue.likely_files or []),
            cfr_reference     = cfr_ref,
        )

        # Build recommendation layer — proposal, not decision
        from core.engineering.intelligence.models import Recommendation
        proposed, benefit, validation = _build_recommendation(top_issue)
        recommendation = Recommendation(
            proposed_change      = proposed,
            expected_benefit     = benefit,
            affected_components  = tuple(top_issue.likely_files or []),
            validation_plan      = validation,
        )

        # Assemble proposal
        import uuid
        from datetime import UTC, datetime
        from core.engineering.intelligence.models import ImprovementProposal, ProposalStatus

        proposal = ImprovementProposal(
            proposal_id    = f"G045-{cat[:3]}-{uuid.uuid4().hex[:6].upper()}",
            status         = ProposalStatus.PENDING,
            evidence       = [observation],
            diagnosis      = diagnosis,
            recommendation = recommendation,
            confidence     = score / 1.5,  # normalise back to 0-1
            session_id     = f"cycle-{current_cycle}",
        )

        logger.info("[SELECTOR] Proposal formed: %s", proposal.proposal_id)
        return proposal
