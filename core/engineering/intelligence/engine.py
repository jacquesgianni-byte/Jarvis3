"""
Engineering Intelligence Engine — Genesis-045 Sprint-001

Orchestrates the observation → analysis → proposal loop.

Called by Agent after every N turns (configurable, default 10)
or when /engineering analyse is issued explicitly.

Pipeline:
  1. Drain SessionLogBuffer → log lines
  2. SessionAnalysisWorker.analyse_session(lines) → EngineeringReport
  3. Increment PatternStore frequency for all found issues
  4. Load existing proposal — if PENDING, check staleness
  5. ImprovementSelector.select() → ImprovementProposal | None
  6. Save proposal to PatternStore
  7. Return proposal (or None)

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
# Maps CFR code → brief description for matching
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
        self._cycle_count   = 0

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
        logger.info("[INTEL_ENGINE] Analysis cycle %d starting (%d lines).",
                    self._cycle_count, len(log_lines))

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
            cat   = issue.category.value if hasattr(issue.category, "value") else str(issue.category)
            self._pattern_store.increment_frequency(cat, issue.title)

        # Step 3: Check existing proposal staleness
        existing = self._pattern_store.load_proposal()
        if existing is not None and existing.is_pending():
            # Check if the issue is still present
            issue_titles = {i.title for i in report.issues}
            proposal_title = existing.evidence[0].title if existing.evidence else ""
            if proposal_title not in issue_titles:
                # Issue not reproduced — mark STALE
                new_stale = existing.stale_cycles + 1
                if new_stale >= STALE_EXPIRY_CYCLES:
                    import dataclasses
                    updated = dataclasses.replace(
                        existing, status=ProposalStatus.EXPIRED, stale_cycles=new_stale
                    )
                    logger.info("[INTEL_ENGINE] Proposal EXPIRED after %d stale cycles.", new_stale)
                else:
                    import dataclasses
                    updated = dataclasses.replace(
                        existing, status=ProposalStatus.STALE, stale_cycles=new_stale
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
            return None  # already handled above

        proposal = self._selector.select(
            report,
            self._pattern_store,
            current_cycle=self._cycle_count,
            cfr_register=_OPEN_CFRS,
        )

        if proposal is not None:
            self._pattern_store.save_proposal(proposal)
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
        """Mark pending proposal as APPROVED. Returns response string."""
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
        """Mark pending proposal as REJECTED. Suppresses for N cycles."""
        import dataclasses
        from core.engineering.intelligence.models import ProposalStatus
        from datetime import UTC, datetime

        proposal = self._pattern_store.load_proposal()
        if proposal is None or not proposal.is_pending():
            return "No pending proposal to reject."

        cat   = proposal.evidence[0].category if proposal.evidence else ""
        title = proposal.evidence[0].title    if proposal.evidence else ""
        self._pattern_store.record_rejection(cat, title, self._cycle_count, reason)

        updated = dataclasses.replace(
            proposal,
            status           = ProposalStatus.REJECTED,
            decided_at       = datetime.now(UTC),
            rejection_reason = reason,
        )
        self._pattern_store.save_proposal(updated)
        logger.info("[INTEL_ENGINE] Proposal REJECTED: %s reason=%r", proposal.proposal_id, reason)
        return (
            f"Proposal {proposal.proposal_id} rejected. "
            f"This finding will be suppressed for {5} analysis cycles."
            + (f" Reason recorded: {reason}" if reason else "")
        )

    def defer_proposal(self) -> str:
        """Keep proposal PENDING. Deferred means no change."""
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
        """Return a one-line status string for display."""
        proposal = self.get_pending_proposal()
        if proposal is None:
            return f"Engineering Intelligence: cycle {self._cycle_count} — no pending proposal."
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
