"""
Engineering Intelligence Engine — Genesis-045 Sprint-001 / Sprint-002 / Sprint-003

Orchestrates the observation → analysis → proposal loop.

Called by Agent after every N turns (configurable, default 10)
or when /engineering analyse is issued explicitly.

Pipeline:
  1. Drain SessionLogBuffer → log lines
  2. SessionAnalysisWorker.analyse_session(lines) → EngineeringReport
  3. Increment PatternStore frequency for all found issues
  4. Build SessionRecord, update PatternRecords (Sprint-002)
  5. Load existing proposal — if PENDING, check staleness
  6. ImprovementSelector.select() → ImprovementProposal | None
  7. Save proposal to PatternStore
  8. Return proposal (or None)

Sprint-003 additions to reject_proposal():
  - Load PatternRecord at rejection time; snapshot affected_components
  - Compute suppression_cycles from RejectionReasonCode via SUPPRESSION_BY_REASON
  - Store both in RejectionRecord (self-describing audit trail)

Does NOT call AI. Does NOT modify source code.
Does NOT create proposals autonomously — only surfaces them.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Default number of turns before an analysis cycle triggers
DEFAULT_CYCLE_TURNS: int = 10

# How many stale cycles before STALE → EXPIRED
STALE_EXPIRY_CYCLES: int = 3

# Open CFR entries for cross-reference (read-only, updated manually)
_OPEN_CFRS: dict[str, str] = {
    "CFR-001": "memory stale data KnowledgeEngine",
    "CFR-002": "entity resolution stale property",
    "CFR-003": "follow-up continuity followup_resolver",
}


class EngineeringIntelligenceEngine:
    """
    Orchestrates the engineering observation-to-proposal loop.

    One active proposal at a time. One analysis cycle per N turns.

    Public API:
        process_session(log_lines)  -> Optional[ImprovementProposal]
        get_pending_proposal()      -> Optional[ImprovementProposal]
        approve_proposal()          -> str
        reject_proposal(reason)     -> str
        defer_proposal()            -> str
        status_summary()            -> str
    """

    def __init__(self, knowledge_engine) -> None:
        from core.engineering.intelligence.pattern_store import PatternStore
        from core.engineering.intelligence.selector import ImprovementSelector
        self._pattern_store = PatternStore(knowledge_engine)
        self._selector      = ImprovementSelector()
        self._cycle_count   = self._pattern_store.get_last_cycle()

    # ------------------------------------------------------------------
    # Main loop entry point
    # ------------------------------------------------------------------

    def process_session(self, log_lines: list[str]) -> "Optional[ImprovementProposal]":
        """
        Run one analysis cycle on the provided log lines.

        Args:
            log_lines: Lines captured by SessionLogBuffer during this cycle.

        Returns:
            A new ImprovementProposal if one was formed, or None.
        """
        from core.workers.session_analysis_worker import SessionAnalysisWorker
        from core.engineering.intelligence.models import ProposalStatus

        self._cycle_count += 1
        logger.info(
            "[INTEL_ENGINE] Analysis cycle %d starting (%d lines).",
            self._cycle_count, len(log_lines),
        )

        if not log_lines:
            logger.info("[INTEL_ENGINE] No log lines — skipping cycle.")
            return None

        # Step 1: Analyse session
        worker = SessionAnalysisWorker()
        report = worker.analyse_session(log_lines)
        logger.info(
            "[INTEL_ENGINE] Report: health=%d, issues=%d, turns=%d",
            report.health_score, len(report.issues), report.session_turns,
        )

        # Step 2: Increment frequency for all found issues
        for issue in report.issues:
            cat = issue.category.value if hasattr(issue.category, "value") else str(issue.category)
            self._pattern_store.increment_frequency(cat, issue.title)

        # Step 2b: Build SessionRecord and update PatternRecords (Sprint-002)
        from core.engineering.intelligence.session_record import (
            SessionRecord as _SessionRecord, compute_drr_trend as _compute_drr,
        )
        from core.engineering.intelligence.pattern_record import PatternRecord as _PR
        import datetime as _dt

        _total = _det = _ai = _err = 0
        for _ln in log_lines:
            if "[TURN_TYPE] type=" not in _ln:
                continue
            if any(x in _ln for x in ("INTENTIONAL", "SYSTEM_CMD", "EMPTY_INPUT", "INTERRUPTED")):
                continue
            _total += 1
            if "CONVERSATION_AI" in _ln:
                _ai += 1
            elif "CONVERSATION_ERROR" in _ln:
                _err += 1
            elif "TOOL_EXTERNAL" not in _ln:
                _det += 1

        _issues_found = []
        for _iss in report.issues:
            _c   = _iss.category.value if hasattr(_iss.category, "value") else str(_iss.category)
            _sig = _PR.normalise_signature(_c, _iss.title)
            _issues_found.append({"signature": _sig, "category": _c, "confidence": _iss.confidence})

        _sess_rec = _SessionRecord(
            cycle=self._cycle_count,
            timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            total_turns=_total,
            deterministic_turns=_det,
            ai_called_turns=_ai,
            error_turns=_err,
            issues_found=_issues_found,
        )
        try:
            self._pattern_store.save_session_record(_sess_rec)
        except Exception as _se:
            logger.warning("[INTEL_ENGINE] SessionRecord save failed: %s", _se)

        _all_sess  = self._pattern_store.get_session_records(n=10)
        _drr_trend = _compute_drr(_all_sess)
        logger.info("[INTEL_ENGINE] DRR=%.2f trend=%s", _sess_rec.drr, _drr_trend.value)

        for _iss2 in _issues_found:
            _lf2 = []
            for _orig2 in report.issues:
                _c2 = _orig2.category.value if hasattr(_orig2.category, "value") else str(_orig2.category)
                if _PR.normalise_signature(_c2, _orig2.title) == _iss2["signature"]:
                    _lf2 = _orig2.likely_files or []
                    break
            self._pattern_store.update_pattern(
                signature=_iss2["signature"],
                category=_iss2["category"],
                display_title=_iss2["signature"].split(":", 1)[-1],
                cycle=self._cycle_count,
                likely_files=_lf2,
            )

        # Step 3: Check existing proposal staleness
        existing = self._pattern_store.load_proposal()
        if existing is not None and existing.is_pending():
            issue_titles   = {i.title for i in report.issues}
            proposal_title = existing.evidence[0].title if existing.evidence else ""
            if proposal_title not in issue_titles:
                new_stale = existing.stale_cycles + 1
                import dataclasses
                if new_stale >= STALE_EXPIRY_CYCLES:
                    updated = dataclasses.replace(
                        existing, status=ProposalStatus.EXPIRED, stale_cycles=new_stale,
                    )
                    logger.info("[INTEL_ENGINE] Proposal EXPIRED after %d stale cycles.", new_stale)
                else:
                    updated = dataclasses.replace(
                        existing, status=ProposalStatus.STALE, stale_cycles=new_stale,
                    )
                    logger.info(
                        "[INTEL_ENGINE] Proposal marked STALE (cycle %d/%d).",
                        new_stale, STALE_EXPIRY_CYCLES,
                    )
                self._pattern_store.save_proposal(updated)
            else:
                logger.info("[INTEL_ENGINE] Existing PENDING proposal still active — no new proposal.")
            return None

        # Step 4: If no pending proposal, try to select one
        if existing is not None and existing.is_pending():
            return None

        proposal = self._selector.select(
            report,
            self._pattern_store,
            current_cycle=self._cycle_count,
            cfr_register=_OPEN_CFRS,
            drr_trend=_drr_trend,
        )

        if proposal is not None:
            self._pattern_store.save_proposal(proposal)
            if proposal.pattern_signature:
                self._pattern_store.link_proposal_to_pattern(
                    proposal.pattern_signature, proposal.proposal_id,
                )
            logger.info("[INTEL_ENGINE] New proposal saved: %s", proposal.proposal_id)

        return proposal

    # ------------------------------------------------------------------
    # Proposal access
    # ------------------------------------------------------------------

    def get_pending_proposal(self) -> "Optional[ImprovementProposal]":
        """Return the current active proposal, or None."""
        from core.engineering.intelligence.models import ProposalStatus
        proposal = self._pattern_store.load_proposal()
        if proposal is None:
            return None
        if proposal.status in (ProposalStatus.PENDING, ProposalStatus.STALE):
            return proposal
        return None

    # ------------------------------------------------------------------
    # Human decisions
    # ------------------------------------------------------------------

    def approve_proposal(self) -> str:
        """
        Mark pending proposal as APPROVED. Returns response string.

        APPROVED means: the human authorised this proposal to proceed to
        the collaboration pipeline.

        It does NOT mean:
          - the diagnosis was correct
          - the recommendation will work
          - the problem is solved

        The pattern continues to be observed. The evidence continues to
        accumulate. The selector may produce a new proposal for the same
        pattern in future cycles if the issue recurs.
        """
        import dataclasses
        from core.engineering.intelligence.models import ProposalStatus
        from datetime import UTC, datetime

        proposal = self._pattern_store.load_proposal()
        if proposal is None or not proposal.is_pending():
            return "No pending proposal to approve."

        updated = dataclasses.replace(
            proposal,
            status     = ProposalStatus.APPROVED,
            decided_at = datetime.now(UTC),
        )
        self._pattern_store.save_proposal(updated)
        logger.info("[INTEL_ENGINE] Proposal APPROVED: %s", proposal.proposal_id)
        return (
            f"Proposal {proposal.proposal_id} approved. "
            "Routing to the engineering collaboration pipeline for implementation."
        )

    def reject_proposal(self, reason: str = "") -> str:
        """
        Mark pending proposal as REJECTED.

        Sprint-003:
          1. Parse RejectionReasonCode from the reason string first word.
          2. Snapshot PatternRecord.affected_components at this moment.
          3. Compute suppression_cycles from the reason code.
          4. Save RejectionRecord with snapshot + computed window.
          5. Also write the legacy suppression key (backward-compat).

        The pattern evidence is NOT modified. Recurrence of the same issue
        will continue to increment frequency, but will not override the
        suppression window unless evidence novelty is detected (new component).
        Frequency growth alone does not bypass a human rejection decision.
        """
        import dataclasses
        from core.engineering.intelligence.models import ProposalStatus
        from core.engineering.intelligence.pattern_record import (
            RejectionRecord, RejectionReasonCode,
        )
        from core.engineering.intelligence.selector import get_suppression_cycles
        from datetime import UTC, datetime

        proposal = self._pattern_store.load_proposal()
        if proposal is None or not proposal.is_pending():
            return "No pending proposal to reject."

        # Parse reason code
        _parts     = reason.strip().split(None, 1) if reason.strip() else []
        _code      = RejectionReasonCode.from_string(_parts[0]) if _parts else RejectionReasonCode.OTHER
        _rtext     = _parts[1] if len(_parts) > 1 else ""

        # Compute suppression window for this reason code
        _window    = get_suppression_cycles(_code)

        # Snapshot affected_components from PatternRecord at rejection time
        _components_snapshot: list = []
        if proposal.pattern_signature:
            _pat = self._pattern_store.get_pattern(proposal.pattern_signature)
            if _pat is not None:
                _components_snapshot = list(_pat.affected_components)

        # Build and save structured RejectionRecord (Sprint-003 path)
        _rej = RejectionRecord(
            proposal_id             = proposal.proposal_id,
            pattern_signature       = proposal.pattern_signature,
            reason_code             = _code,
            reason_text             = _rtext,
            cycle                   = self._cycle_count,
            components_at_rejection = _components_snapshot,
            suppression_cycles      = _window,
            recorded_genesis        = "Genesis-045",
        )
        try:
            self._pattern_store.save_rejection_record(_rej)
        except Exception as _re:
            logger.warning("[INTEL_ENGINE] RejectionRecord save failed: %s", _re)

        # Legacy suppression key (backward-compat for Sprint-002 selector path)
        cat   = proposal.evidence[0].category if proposal.evidence else ""
        title = proposal.evidence[0].title    if proposal.evidence else ""
        try:
            self._pattern_store.record_rejection(cat, title, self._cycle_count, reason)
        except Exception as _le:
            logger.warning("[INTEL_ENGINE] Legacy rejection record failed: %s", _le)

        # Update proposal status
        updated = dataclasses.replace(
            proposal,
            status           = ProposalStatus.REJECTED,
            decided_at       = datetime.now(UTC),
            rejection_reason = reason,
        )
        self._pattern_store.save_proposal(updated)
        logger.info(
            "[INTEL_ENGINE] Proposal REJECTED: %s reason=%r window=%d",
            proposal.proposal_id, reason, _window,
        )
        return (
            f"Proposal {proposal.proposal_id} rejected. "
            f"This pattern will be suppressed for {_window} analysis cycles. "
            f"Reason: {_code.label()}."
            + (f" Notes: {_rtext}" if _rtext else "")
        )

    def defer_proposal(self) -> str:
        """
        Keep proposal PENDING. Deferred means no change.

        DEFERRED semantics: the human chose not to decide yet.
        The proposal remains visible. No suppression occurs.
        The pattern continues to be observed normally.
        """
        proposal = self._pattern_store.load_proposal()
        if proposal is None or not proposal.is_pending():
            return "No pending proposal to defer."
        logger.info("[INTEL_ENGINE] Proposal DEFERRED: %s", proposal.proposal_id)
        return (
            f"Proposal {proposal.proposal_id} deferred. "
            "It will remain active until you decide. "
            "Type /engineering to review it again."
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status_summary(self) -> str:
        """Return status with DRR history and pending proposal."""
        from core.engineering.intelligence.session_record import compute_drr_trend
        proposal = self.get_pending_proposal()
        sessions = self._pattern_store.get_session_records(n=6)
        drr_parts = []
        for r in sessions[-3:]:
            drr_parts.append("cycle %d: %d%%" % (r.cycle, int(r.drr * 100)))
        trend = compute_drr_trend(sessions)
        drr_line = (
            "DRR (" + trend.label() + "): " + ", ".join(drr_parts)
            if drr_parts else "DRR: no data"
        )
        if proposal is None:
            return (
                "Engineering Intelligence: cycle %d — no pending proposal. %s"
                % (self._cycle_count, drr_line)
            )
        from core.engineering.intelligence.models import ProposalStatus
        if proposal.status == ProposalStatus.STALE:
            return (
                f"Engineering Intelligence: proposal {proposal.proposal_id} is STALE "
                f"(issue not reproduced in {proposal.stale_cycles} cycle(s)). "
                "Type /engineering to review."
            )
        return (
            f"Engineering Intelligence: proposal {proposal.proposal_id} is PENDING. "
            "Type /engineering to review."
        )
