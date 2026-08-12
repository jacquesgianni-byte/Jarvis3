"""
Improvement Selector â€” Genesis-045 Sprint-001 / Sprint-002 / Sprint-003

Deterministic selection of the single highest-priority improvement
from an EngineeringReport. No AI. Fully testable.

Selection algorithm:
  1. Filter to HIGH severity issues only
  2. Build pattern_signature for each issue
  3. Check suppression via get_rejection_record_by_signature() (Sprint-003 path)
     or legacy get_rejection_cycle() fallback (Sprint-002 data)
  4. Sprint-003 suppression rules:
       a. If suppression window has not elapsed AND no evidence novelty â†’ skip
       b. Evidence novelty = new component in affected_components not present
          in components_at_rejection snapshot
       c. ACCEPTABLE_TRADEOFF: window-only; evidence novelty does NOT apply
  5. Skip issues below MIN_CONFIDENCE threshold
  6. Score remaining: confidence Ã— frequency_boost
  7. Apply DRR declining boost for ROUTING / MEMORY patterns
  8. Return top scorer as ImprovementProposal, or None

One proposal at a time. Returns None if one is already PENDING.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.engineering.intelligence.session_record import DRRTrend

logger = logging.getLogger(__name__)

# Minimum confidence to form a proposal
MIN_CONFIDENCE: float = 0.50

# ---------------------------------------------------------------------------
# Sprint-003: differentiated suppression windows per rejection reason code.
# Defined here as the single authoritative source.
# ---------------------------------------------------------------------------
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

# Default used when no RejectionRecord exists and the legacy key is absent
_DEFAULT_SUPPRESSION_CYCLES: int = 5


def get_suppression_cycles(reason_code: RejectionReasonCode) -> int:
    """Return the suppression window for the given reason code."""
    return SUPPRESSION_BY_REASON.get(reason_code, _DEFAULT_SUPPRESSION_CYCLES)


def _build_inference(issue, frequency: int) -> str:
    freq_note = f" (seen {frequency} time(s) this session)" if frequency > 1 else ""
    return (
        f"The {issue.category.value if hasattr(issue.category, 'value') else issue.category} "
        f"pattern '{issue.title}' suggests a recurring architectural gap{freq_note}. "
        f"This is an inference â€” it may reflect a transient condition rather than "
        f"a structural problem."
    )


def _build_uncertainty(issue) -> str:
    return (
        f"This finding is based on a single analysis cycle. "
        f"The issue may be transient or context-specific. "
        f"Confidence: {issue.confidence * 100:.0f}%."
    )


def _build_recommendation(issue) -> tuple[str, str, str]:
    """Return (proposed_change, expected_benefit, validation_plan)."""
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
        select(report, pattern_store, current_cycle, cfr_register) ->
            Optional[ImprovementProposal]
    """

    def select(
        self,
        report,
        pattern_store,
        current_cycle: int = 0,
        cfr_register: dict = None,
        drr_trend: "DRRTrend" = None,
    ) -> "Optional[ImprovementProposal]":
        """
        Select the single highest-priority improvement from an EngineeringReport.

        Args:
            report:          EngineeringReport from SessionAnalysisWorker
            pattern_store:   PatternStore for frequency and rejection history
            current_cycle:   Current analysis cycle number
            cfr_register:    Dict of open CFR entries {code: description}
            drr_trend:       Current DRR trend (Sprint-002)

        Returns:
            ImprovementProposal or None if no qualifying issue found.
        """
        from core.workers.engineering_models import Severity

        if cfr_register is None:
            cfr_register = {}

        if not report.has_issues():
            logger.info("[SELECTOR] No issues in report â€” no proposal.")
            return None

        high_issues = report.issues_by_severity(Severity.HIGH)
        if not high_issues:
            logger.info("[SELECTOR] No HIGH severity issues â€” no proposal.")
            return None

        candidates = []

        for issue in high_issues:
            cat   = issue.category.value if hasattr(issue.category, "value") else str(issue.category)
            title = issue.title

            # Build pattern signature for this issue
            from core.engineering.intelligence.pattern_record import PatternRecord
            pat_sig = PatternRecord.normalise_signature(cat, title)

            # ------------------------------------------------------------------
            # Sprint-003 suppression check
            # Primary path: structured RejectionRecord keyed by pattern_signature
            # Fallback:     legacy rejected_at_cycle integer
            # ------------------------------------------------------------------
            suppressed = self._check_suppression(
                pattern_store=pattern_store,
                pat_sig=pat_sig,
                cat=cat,
                title=title,
                current_cycle=current_cycle,
            )
            if suppressed:
                continue

            # Skip below confidence threshold
            if issue.confidence < MIN_CONFIDENCE:
                logger.info(
                    "[SELECTOR] Skipping %r â€” confidence %.2f below threshold %.2f.",
                    title, issue.confidence, MIN_CONFIDENCE,
                )
                continue

            # Score: confidence Ã— frequency_boost
            frequency  = pattern_store.get_frequency(cat, title)
            freq_boost = 1.0 + min(frequency * 0.1, 0.5)  # cap at 1.5Ã—
            score      = issue.confidence * freq_boost

            # Sprint-002: DRR declining boosts ROUTING and MEMORY patterns
            if drr_trend == DRRTrend.DECLINING and cat in ("ROUTING", "MEMORY"):
                score *= 1.10
                logger.debug("[SELECTOR] DRR declining boost applied to %r", title)

            candidates.append((score, issue, frequency, pat_sig))

        if not candidates:
            logger.info("[SELECTOR] All HIGH issues filtered â€” no proposal.")
            return None

        # Select top scorer
        candidates.sort(key=lambda x: x[0], reverse=True)
        score, top_issue, frequency, pat_sig = candidates[0]
        cat   = top_issue.category.value if hasattr(top_issue.category, "value") else str(top_issue.category)
        title = top_issue.title

        logger.info(
            "[SELECTOR] Selected: %r (score=%.2f, conf=%.2f, freq=%d)",
            title, score, top_issue.confidence, frequency,
        )

        # Build observation layer â€” facts only
        from core.engineering.intelligence.models import Observation
        observation = Observation.from_issue(top_issue)

        # CFR cross-reference (read-only)
        cfr_ref = ""
        for cfr_code, cfr_desc in cfr_register.items():
            if cat.lower() in cfr_desc.lower() or title.lower() in cfr_desc.lower():
                cfr_ref = cfr_code
                break

        # Build diagnosis layer â€” inference, explicitly labelled
        from core.engineering.intelligence.models import Diagnosis
        diagnosis = Diagnosis(
            inference         = _build_inference(top_issue, frequency),
            confidence        = top_issue.confidence * 0.85,
            uncertainty       = _build_uncertainty(top_issue),
            likely_components = tuple(top_issue.likely_files or []),
            cfr_reference     = cfr_ref,
        )

        # Build recommendation layer â€” proposal, not decision
        from core.engineering.intelligence.models import Recommendation
        proposed, benefit, validation = _build_recommendation(top_issue)
        recommendation = Recommendation(
            proposed_change     = proposed,
            expected_benefit    = benefit,
            affected_components = tuple(top_issue.likely_files or []),
            validation_plan     = validation,
        )

        # Assemble proposal
        import uuid
        from datetime import UTC, datetime
        from core.engineering.intelligence.models import ImprovementProposal, ProposalStatus

        proposal = ImprovementProposal(
            proposal_id       = f"G045-{cat[:3]}-{uuid.uuid4().hex[:6].upper()}",
            status            = ProposalStatus.PENDING,
            evidence          = [observation],
            diagnosis         = diagnosis,
            recommendation    = recommendation,
            confidence        = score / 1.5,  # normalise back to 0â€“1
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
        """
        Return True if this pattern is currently suppressed.

        Primary path: load RejectionRecord by pattern_signature.
          - Apply suppression_cycles (pre-computed at rejection time).
          - If window not elapsed, check evidence novelty.
          - Evidence novelty = new component in affected_components vs snapshot.
          - ACCEPTABLE_TRADEOFF: window-only; novelty does NOT apply.

        Fallback path: legacy rejected_at_cycle integer with default 5-cycle window.
        """
        # Primary path (Sprint-003)
        rej_record = pattern_store.get_rejection_record_by_signature(pat_sig)
        if rej_record is not None:
            cycles_elapsed = current_cycle - rej_record.cycle
            window         = rej_record.suppression_cycles

            if cycles_elapsed >= window:
                # Window has expired â€” eligible
                logger.debug(
                    "[SELECTOR] %r window expired (elapsed=%d, window=%d) â€” eligible.",
                    pat_sig, cycles_elapsed, window,
                )
                return False

            # Window has not elapsed â€” check evidence novelty
            # ACCEPTABLE_TRADEOFF is window-only; no novelty bypass
            if not rej_record.reason_code.is_novelty_exempt():
                current_pattern = pattern_store.get_pattern(pat_sig)
                if current_pattern is not None:
                    snapshot_comps = set(rej_record.components_at_rejection)
                    current_comps  = set(current_pattern.affected_components)
                    new_components = current_comps - snapshot_comps
                    if new_components:
                        logger.info(
                            "[SELECTOR] %r has new components %s â€” evidence novelty, eligible.",
                            pat_sig, new_components,
                        )
                        return False  # new evidence â€” not suppressed

            # Still within window, no novelty (or ACCEPTABLE_TRADEOFF)
            logger.info(
                "[SELECTOR] Skipping %r â€” rejected %d cycle(s) ago (window=%d, reason=%s).",
                pat_sig, cycles_elapsed, window, rej_record.reason_code.value,
            )
            return True

        # Fallback path (Sprint-002 legacy data)
        rejected_at = pattern_store.get_rejection_cycle(cat, title)
        if rejected_at != -1:
            cycles_since = current_cycle - rejected_at
            if cycles_since < _DEFAULT_SUPPRESSION_CYCLES:
                logger.info(
                    "[SELECTOR] Skipping %r â€” legacy rejection %d cycle(s) ago (window=%d).",
                    title, cycles_since, _DEFAULT_SUPPRESSION_CYCLES,
                )
                return True

        return False


# Backward-compatibility alias — Sprint-001/002 tests import this name
REJECTION_SUPPRESSION_CYCLES: int = _DEFAULT_SUPPRESSION_CYCLES

