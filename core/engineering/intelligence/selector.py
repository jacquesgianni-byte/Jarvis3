"""
Improvement Selector — Genesis-045 Sprint-001 / Sprint-002 / Sprint-003 / Sprint-004

Sprint-004 additions:
  Outcome-aware scoring: reads ProposalOutcomeRecord for each candidate pattern.
  Recently VALIDATED: score * VALIDATED_SCORE_FACTOR (deprioritise, not suppress).
  FAILED_VALIDATION: normal score (issue was not resolved; full priority restored).

Epistemic boundaries:
  VALIDATED reduces priority but does not eliminate the pattern.
  FAILED_VALIDATION restores normal priority; cause remains uncertain.
  No outcome triggers autonomous action.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.engineering.intelligence.session_record import DRRTrend

logger = logging.getLogger(__name__)

MIN_CONFIDENCE: float = 0.50

from core.engineering.intelligence.pattern_record import RejectionReasonCode

SUPPRESSION_BY_REASON: dict[RejectionReasonCode, int] = {
    RejectionReasonCode.NOT_A_PROBLEM:        10,
    RejectionReasonCode.WRONG_DIAGNOSIS:       5,
    RejectionReasonCode.WRONG_RECOMMENDATION:  3,
    RejectionReasonCode.TOO_RISKY:             3,
    RejectionReasonCode.NOT_NOW:               3,
    RejectionReasonCode.ACCEPTABLE_TRADEOFF:  15,
    RejectionReasonCode.OTHER:                 5,
}

_DEFAULT_SUPPRESSION_CYCLES: int = 5

# Backward-compatibility alias — Sprint-001/002 tests import this name
REJECTION_SUPPRESSION_CYCLES: int = _DEFAULT_SUPPRESSION_CYCLES

# Sprint-004: VALIDATED pattern score multiplier
# Reduces priority without eliminating the pattern from future proposals.
# The improvement may not have been caused by the fix, or may not be permanent.
VALIDATED_SCORE_FACTOR: float = 0.5

# How many cycles after VALIDATED before full priority is restored
VALIDATED_GRACE_CYCLES: int = 5


def get_suppression_cycles(reason_code: RejectionReasonCode) -> int:
    return SUPPRESSION_BY_REASON.get(reason_code, _DEFAULT_SUPPRESSION_CYCLES)


def _build_inference(issue, frequency: int) -> str:
    freq_note = f" (seen {frequency} time(s) this session)" if frequency > 1 else ""
    return (
        f"The {issue.category.value if hasattr(issue.category, 'value') else issue.category} "
        f"pattern '{issue.title}' suggests a recurring architectural gap{freq_note}. "
        f"This is an inference — it may reflect a transient condition rather than "
        f"a structural problem."
    )


def _build_uncertainty(issue) -> str:
    return (
        f"This finding is based on a single analysis cycle. "
        f"The issue may be transient or context-specific. "
        f"Confidence: {issue.confidence * 100:.0f}%."
    )


def _build_recommendation(issue) -> tuple[str, str, str]:
    cat = issue.category.value if hasattr(issue.category, "value") else str(issue.category)
    if cat == "ROUTING":
        return (
            "Investigate the intent routing path for utterances that fall back to AI. "
            "Consider whether new intent patterns or slot types would reduce AI_FALLBACK rate.",
            "Fewer AI fallbacks means faster, more deterministic responses.",
            "Run a session with the same utterance types. "
            "Verify AI_FALLBACK rate drops in the next EngineeringReport.",
        )
    elif cat == "MEMORY":
        return (
            "Investigate the memory retrieval path for misses or stale data. "
            "Consider whether entity registration or knowledge recency ranking needs improvement.",
            "Correct memory recall means users get accurate answers from stored knowledge.",
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
            "Fewer unhandled exceptions means more reliable responses.",
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
    Deterministic. No AI.
    """

    def select(
        self,
        report,
        pattern_store,
        current_cycle: int = 0,
        cfr_register: dict = None,
        drr_trend: "DRRTrend" = None,
    ) -> "Optional[ImprovementProposal]":
        from core.workers.engineering_models import Severity

        if cfr_register is None:
            cfr_register = {}

        if not report.has_issues():
            logger.info("[SELECTOR] No issues in report — no proposal.")
            return None

        high_issues = report.issues_by_severity(Severity.HIGH)
        if not high_issues:
            logger.info("[SELECTOR] No HIGH severity issues — no proposal.")
            return None

        candidates = []

        for issue in high_issues:
            cat   = issue.category.value if hasattr(issue.category, "value") else str(issue.category)
            title = issue.title

            from core.engineering.intelligence.pattern_record import PatternRecord
            pat_sig = PatternRecord.normalise_signature(cat, title)

            # Suppression check (Sprint-003)
            suppressed = self._check_suppression(
                pattern_store=pattern_store,
                pat_sig=pat_sig,
                cat=cat,
                title=title,
                current_cycle=current_cycle,
            )
            if suppressed:
                continue

            if issue.confidence < MIN_CONFIDENCE:
                logger.info(
                    "[SELECTOR] Skipping %r — confidence %.2f below threshold.",
                    title, issue.confidence,
                )
                continue

            frequency  = pattern_store.get_frequency(cat, title)
            freq_boost = 1.0 + min(frequency * 0.1, 0.5)
            score      = issue.confidence * freq_boost

            if drr_trend == DRRTrend.DECLINING and cat in ("ROUTING", "MEMORY"):
                score *= 1.10

            # Sprint-004: outcome-aware scoring
            score = self._apply_outcome_scoring(
                score=score,
                pat_sig=pat_sig,
                pattern_store=pattern_store,
                current_cycle=current_cycle,
            )

            candidates.append((score, issue, frequency, pat_sig))

        if not candidates:
            logger.info("[SELECTOR] All HIGH issues filtered — no proposal.")
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        score, top_issue, frequency, pat_sig = candidates[0]
        cat   = top_issue.category.value if hasattr(top_issue.category, "value") else str(top_issue.category)
        title = top_issue.title

        logger.info(
            "[SELECTOR] Selected: %r (score=%.2f, conf=%.2f, freq=%d)",
            title, score, top_issue.confidence, frequency,
        )

        from core.engineering.intelligence.models import Observation
        observation = Observation.from_issue(top_issue)

        cfr_ref = ""
        for cfr_code, cfr_desc in cfr_register.items():
            if cat.lower() in cfr_desc.lower() or title.lower() in cfr_desc.lower():
                cfr_ref = cfr_code
                break

        from core.engineering.intelligence.models import Diagnosis
        diagnosis = Diagnosis(
            inference         = _build_inference(top_issue, frequency),
            confidence        = top_issue.confidence * 0.85,
            uncertainty       = _build_uncertainty(top_issue),
            likely_components = tuple(top_issue.likely_files or []),
            cfr_reference     = cfr_ref,
        )

        from core.engineering.intelligence.models import Recommendation
        proposed, benefit, validation = _build_recommendation(top_issue)
        recommendation = Recommendation(
            proposed_change     = proposed,
            expected_benefit    = benefit,
            affected_components = tuple(top_issue.likely_files or []),
            validation_plan     = validation,
        )

        import uuid
        from datetime import UTC, datetime
        from core.engineering.intelligence.models import ImprovementProposal, ProposalStatus

        proposal = ImprovementProposal(
            proposal_id       = f"G045-{cat[:3]}-{uuid.uuid4().hex[:6].upper()}",
            status            = ProposalStatus.PENDING,
            evidence          = [observation],
            diagnosis         = diagnosis,
            recommendation    = recommendation,
            confidence        = score / 1.5,
            session_id        = f"cycle-{current_cycle}",
            pattern_signature = pat_sig,
        )

        logger.info("[SELECTOR] Proposal formed: %s", proposal.proposal_id)
        return proposal

    # ------------------------------------------------------------------
    # Sprint-003: suppression check
    # ------------------------------------------------------------------

    def _check_suppression(
        self,
        pattern_store,
        pat_sig: str,
        cat: str,
        title: str,
        current_cycle: int,
    ) -> bool:
        rej_record = pattern_store.get_rejection_record_by_signature(pat_sig)
        if rej_record is not None:
            cycles_elapsed = current_cycle - rej_record.cycle
            window         = rej_record.suppression_cycles

            if cycles_elapsed >= window:
                return False

            if not rej_record.reason_code.is_novelty_exempt():
                current_pattern = pattern_store.get_pattern(pat_sig)
                if current_pattern is not None:
                    snapshot_comps = set(rej_record.components_at_rejection)
                    current_comps  = set(current_pattern.affected_components)
                    new_components = current_comps - snapshot_comps
                    if new_components:
                        logger.info(
                            "[SELECTOR] %r has new components %s — evidence novelty, eligible.",
                            pat_sig, new_components,
                        )
                        return False

            logger.info(
                "[SELECTOR] Skipping %r — rejected %d cycle(s) ago (window=%d, reason=%s).",
                pat_sig, cycles_elapsed, window, rej_record.reason_code.value,
            )
            return True

        rejected_at = pattern_store.get_rejection_cycle(cat, title)
        if rejected_at != -1:
            cycles_since = current_cycle - rejected_at
            if cycles_since < _DEFAULT_SUPPRESSION_CYCLES:
                return True

        return False

    # ------------------------------------------------------------------
    # Sprint-004: outcome-aware scoring
    # ------------------------------------------------------------------

    def _apply_outcome_scoring(
        self,
        score: float,
        pat_sig: str,
        pattern_store,
        current_cycle: int,
    ) -> float:
        """
        Adjust score based on the most recent ProposalOutcomeRecord for this pattern.

        VALIDATED (within grace period):
            score * VALIDATED_SCORE_FACTOR
            Rationale: improvement was observed; deprioritise but don't eliminate.
            Causation is NOT established — the pattern may recur or the improvement
            may not have been caused by the fix.

        FAILED_VALIDATION:
            score unchanged (normal priority)
            Rationale: the expected improvement was NOT observed. The issue remains
            active. Full priority is correct. Cause is uncertain.

        No outcome record / IMPLEMENTED (still observing):
            score unchanged
        """
        from core.engineering.intelligence.pattern_record import OutcomeStatus
        try:
            outcome = pattern_store.get_latest_outcome_for_pattern(pat_sig)
            if outcome is None:
                return score

            if outcome.status == OutcomeStatus.VALIDATED:
                # Only apply grace period if validated_at_cycle is set
                if outcome.validated_at_cycle is not None:
                    cycles_since_validated = current_cycle - outcome.validated_at_cycle
                    if cycles_since_validated < VALIDATED_GRACE_CYCLES:
                        logger.debug(
                            "[SELECTOR] %r recently VALIDATED — applying score factor %.1f.",
                            pat_sig, VALIDATED_SCORE_FACTOR,
                        )
                        return score * VALIDATED_SCORE_FACTOR

            # FAILED_VALIDATION or IMPLEMENTED: normal score
            return score

        except Exception as _e:
            logger.debug("[SELECTOR] outcome scoring failed for %r: %s", pat_sig, _e)
            return score
