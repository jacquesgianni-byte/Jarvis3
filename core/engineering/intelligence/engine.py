"""
Engineering Intelligence Engine — Genesis-045 Sprint-001 / Sprint-002 / Sprint-003 / Sprint-004

Orchestrates the observation → analysis → proposal loop.

Sprint-004 additions:
  approve_proposal() writes a pending-implementation entry after APPROVED.
  process_session() checks for COMMIT_PENDING via execution_runner reference
  and transitions proposals to IMPLEMENTED, then monitors for VALIDATED /
  FAILED_VALIDATION over subsequent cycles.

IMPLEMENTED detection:
  ExecutionRunner.has_pending_commit() returns True when _last_outcome has
  state=COMMIT_PENDING. This is an in-memory signal, not a log line.
  The engine holds an optional reference to the ExecutionRunner and checks
  it at the start of each process_session() call.

Epistemic boundaries (enforced, not assumed):
  IMPLEMENTED ≠ diagnosis correct ≠ problem solved
  VALIDATED = expected improvement observed; causation NOT established
  FAILED_VALIDATION = improvement not observed; cause uncertain; no auto-retry
  Every new engineering action requires human approval regardless of outcome

Does NOT call AI. Does NOT modify source code autonomously.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CYCLE_TURNS:  int = 10
STALE_EXPIRY_CYCLES:  int = 3
VALIDATION_CYCLES:    int = 2   # consecutive cycles without pattern recurrence → VALIDATED

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
        set_execution_runner(runner) -> None   (Sprint-004)
    """

    def __init__(self, knowledge_engine) -> None:
        from core.engineering.intelligence.pattern_store import PatternStore
        from core.engineering.intelligence.selector import ImprovementSelector
        self._pattern_store     = PatternStore(knowledge_engine)
        self._selector          = ImprovementSelector()
        self._cycle_count       = self._pattern_store.get_last_cycle()
        self._execution_runner  = None   # Sprint-004: set via set_execution_runner()

    def set_execution_runner(self, runner) -> None:
        """
        Provide a reference to the ExecutionRunner so the engine can check
        for COMMIT_PENDING without modifying the execution pipeline.
        Called by Agent after both are constructed.
        """
        self._execution_runner = runner
        logger.info("[INTEL_ENGINE] ExecutionRunner reference set.")

    # ------------------------------------------------------------------
    # Main loop entry point
    # ------------------------------------------------------------------

    def process_session(self, log_lines: list[str]) -> "Optional[ImprovementProposal]":
        """
        Run one analysis cycle on the provided log lines.
        """
        from core.workers.session_analysis_worker import SessionAnalysisWorker
        from core.engineering.intelligence.models import ProposalStatus

        self._cycle_count += 1
        logger.info(
            "[INTEL_ENGINE] Analysis cycle %d starting (%d lines).",
            self._cycle_count, len(log_lines),
        )

        # Sprint-004: check for pending implementation before anything else
        self._check_implementation_outcome()

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

        # Sprint-004: check VALIDATED / FAILED_VALIDATION for IMPLEMENTED proposals
        self._check_validation_outcome(_issues_found)

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
                logger.info("[INTEL_ENGINE] Existing PENDING proposal still active.")
            return None

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
    # Sprint-004: Implementation and validation monitoring
    # ------------------------------------------------------------------

    def _check_implementation_outcome(self) -> None:
        """
        Check whether the ExecutionRunner has reached COMMIT_PENDING for a
        session linked to the pending-implementation entry.

        If yes: transition proposal to IMPLEMENTED, write ProposalOutcomeRecord,
        clear the pending-implementation entry.

        This is called at the start of every process_session() call.
        No log-line scanning — uses ExecutionRunner.has_pending_commit() directly.
        """
        pending = self._pattern_store.get_pending_implementation()
        if pending is None:
            return

        proposal_id       = pending.get("proposal_id", "")
        pattern_signature = pending.get("pattern_signature", "")
        approved_at_cycle = pending.get("approved_at_cycle", 0)

        if not proposal_id:
            return

        # Check ExecutionRunner for COMMIT_PENDING signal
        runner = self._execution_runner
        if runner is None or not getattr(runner, "has_pending_commit", lambda: False)():
            logger.debug(
                "[INTEL_ENGINE] Pending implementation %s: no COMMIT_PENDING yet.",
                proposal_id,
            )
            return

        # COMMIT_PENDING confirmed — extract summary data if available
        tests_run     = 0
        files_changed = 0
        snapshot_sha  = ""
        try:
            last_outcome = getattr(runner, "_last_outcome", None)
            if last_outcome is not None:
                summary = getattr(last_outcome, "summary", None)
                if summary is not None:
                    tests_run     = getattr(summary, "tests_passed", 0)
                    files_changed = getattr(summary, "total_files_changed", 0)
                    snapshot_sha  = getattr(summary, "snapshot_sha", "")
        except Exception as _e:
            logger.debug("[INTEL_ENGINE] Could not extract summary data: %s", _e)

        # Write ProposalOutcomeRecord
        from core.engineering.intelligence.pattern_record import (
            OutcomeStatus, ProposalOutcomeRecord,
        )
        outcome_record = ProposalOutcomeRecord(
            proposal_id          = proposal_id,
            pattern_signature    = pattern_signature,
            status               = OutcomeStatus.IMPLEMENTED,
            approved_at_cycle    = approved_at_cycle,
            implemented_at_cycle = self._cycle_count,
            validated_at_cycle   = None,
            tests_run            = tests_run,
            files_changed        = files_changed,
            snapshot_sha         = snapshot_sha,
            recorded_genesis     = "Genesis-045",
        )
        try:
            self._pattern_store.save_outcome_record(outcome_record)
        except Exception as _oe:
            logger.warning("[INTEL_ENGINE] save_outcome_record failed: %s", _oe)
            return

        # Update proposal status to IMPLEMENTED
        import dataclasses
        from core.engineering.intelligence.models import ProposalStatus
        proposal = self._pattern_store.load_proposal()
        if proposal is not None and proposal.proposal_id == proposal_id:
            updated = dataclasses.replace(proposal, status=ProposalStatus.IMPLEMENTED)
            self._pattern_store.save_proposal(updated)

        # Clear the pending-implementation entry
        self._pattern_store.clear_pending_implementation()
        logger.info(
            "[INTEL_ENGINE] Proposal %s marked IMPLEMENTED (cycle=%d).",
            proposal_id, self._cycle_count,
        )

    def _check_validation_outcome(self, issues_found: list[dict]) -> None:
        """
        For any IMPLEMENTED proposal, check whether the pattern has improved.

        VALIDATED:        pattern not in issues_found for VALIDATION_CYCLES
                          consecutive cycles since implementation.
        FAILED_VALIDATION: pattern recurred within the observation window.

        Observation, not causation. Evidence is never erased.
        No autonomous action on either outcome.
        """
        proposal = self._pattern_store.load_proposal()
        if proposal is None:
            return
        from core.engineering.intelligence.models import ProposalStatus
        if proposal.status != ProposalStatus.IMPLEMENTED:
            return

        pat_sig = proposal.pattern_signature
        if not pat_sig:
            return

        outcome = self._pattern_store.get_outcome_record(proposal.proposal_id)
        if outcome is None:
            return

        # Check if pattern recurred this cycle
        current_sigs = {iss.get("signature", "") for iss in issues_found}
        pattern_recurred = pat_sig in current_sigs

        if pattern_recurred:
            # Pattern still present — FAILED_VALIDATION
            from core.engineering.intelligence.pattern_record import (
                OutcomeStatus, ProposalOutcomeRecord,
            )
            import dataclasses
            updated_outcome = ProposalOutcomeRecord(
                proposal_id          = outcome.proposal_id,
                pattern_signature    = outcome.pattern_signature,
                status               = OutcomeStatus.FAILED_VALIDATION,
                approved_at_cycle    = outcome.approved_at_cycle,
                implemented_at_cycle = outcome.implemented_at_cycle,
                validated_at_cycle   = self._cycle_count,
                tests_run            = outcome.tests_run,
                files_changed        = outcome.files_changed,
                snapshot_sha         = outcome.snapshot_sha,
                recorded_genesis     = outcome.recorded_genesis,
            )
            self._pattern_store.save_outcome_record(updated_outcome)
            updated_proposal = dataclasses.replace(
                proposal, status=ProposalStatus.FAILED_VALIDATION,
            )
            self._pattern_store.save_proposal(updated_proposal)
            logger.info(
                "[INTEL_ENGINE] Proposal %s: FAILED_VALIDATION — pattern recurred at cycle %d. "
                "Cause uncertain. Evidence intact. Pattern remains eligible.",
                proposal.proposal_id, self._cycle_count,
            )
            return

        # Pattern absent — check if we have enough consecutive clear cycles
        impl_cycle    = outcome.implemented_at_cycle
        cycles_clear  = self._cycle_count - impl_cycle
        if cycles_clear >= VALIDATION_CYCLES:
            from core.engineering.intelligence.pattern_record import (
                OutcomeStatus, ProposalOutcomeRecord,
            )
            import dataclasses
            updated_outcome = ProposalOutcomeRecord(
                proposal_id          = outcome.proposal_id,
                pattern_signature    = outcome.pattern_signature,
                status               = OutcomeStatus.VALIDATED,
                approved_at_cycle    = outcome.approved_at_cycle,
                implemented_at_cycle = outcome.implemented_at_cycle,
                validated_at_cycle   = self._cycle_count,
                tests_run            = outcome.tests_run,
                files_changed        = outcome.files_changed,
                snapshot_sha         = outcome.snapshot_sha,
                recorded_genesis     = outcome.recorded_genesis,
            )
            self._pattern_store.save_outcome_record(updated_outcome)
            updated_proposal = dataclasses.replace(
                proposal, status=ProposalStatus.VALIDATED,
            )
            self._pattern_store.save_proposal(updated_proposal)
            logger.info(
                "[INTEL_ENGINE] Proposal %s: VALIDATED — pattern absent for %d cycles. "
                "Outcome observation only; causation not established.",
                proposal.proposal_id, cycles_clear,
            )

    # ------------------------------------------------------------------
    # Proposal access
    # ------------------------------------------------------------------

    def get_pending_proposal(self) -> "Optional[ImprovementProposal]":
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
        Mark pending proposal as APPROVED.

        APPROVED means: the human authorised this proposal to proceed.
        It does NOT mean: diagnosis correct / recommendation will work /
        problem solved.

        Sprint-004: writes a pending-implementation entry so that
        process_session() can detect COMMIT_PENDING and transition to
        IMPLEMENTED without any changes to ExecutionRunner.
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

        # Sprint-004: record pending-implementation entry
        try:
            self._pattern_store.save_pending_implementation(
                proposal_id       = proposal.proposal_id,
                pattern_signature = proposal.pattern_signature,
                approved_at_cycle = self._cycle_count,
            )
        except Exception as _pe:
            logger.warning("[INTEL_ENGINE] save_pending_implementation failed: %s", _pe)

        logger.info("[INTEL_ENGINE] Proposal APPROVED: %s", proposal.proposal_id)
        return (
            f"Proposal {proposal.proposal_id} approved. "
            "Routing to the engineering collaboration pipeline for implementation."
        )

    def reject_proposal(self, reason: str = "") -> str:
        """
        Mark pending proposal as REJECTED. Differentiated suppression per reason code.

        Evidence is NOT modified. Frequency continues to accumulate.
        Rejection does not resolve the underlying issue.
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

        _parts  = reason.strip().split(None, 1) if reason.strip() else []
        _code   = RejectionReasonCode.from_string(_parts[0]) if _parts else RejectionReasonCode.OTHER
        _rtext  = _parts[1] if len(_parts) > 1 else ""
        _window = get_suppression_cycles(_code)

        _components_snapshot: list = []
        if proposal.pattern_signature:
            _pat = self._pattern_store.get_pattern(proposal.pattern_signature)
            if _pat is not None:
                _components_snapshot = list(_pat.affected_components)

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

        cat   = proposal.evidence[0].category if proposal.evidence else ""
        title = proposal.evidence[0].title    if proposal.evidence else ""
        try:
            self._pattern_store.record_rejection(cat, title, self._cycle_count, reason)
        except Exception as _le:
            logger.warning("[INTEL_ENGINE] Legacy rejection record failed: %s", _le)

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
        Keep proposal PENDING. No suppression. No evidence change.
        DEFERRED: human chose not to decide yet.
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
        from core.engineering.intelligence.session_record import compute_drr_trend
        proposal = self.get_pending_proposal()
        sessions = self._pattern_store.get_session_records(n=6)
        drr_parts = []
        for r in sessions[-3:]:
            drr_parts.append("cycle %d: %d%%" % (r.cycle, int(r.drr * 100)))
        trend    = compute_drr_trend(sessions)
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
