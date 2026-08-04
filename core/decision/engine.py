"""
Decision Intelligence — Engine
Genesis-036 Sprint-001

DecisionEngine assembles DecisionContext from all subsystems,
evaluates ordered DecisionRules, and returns a DecisionResult.

No AI. No storage. One-way dependency direction.
Reads from: ProgressStore, LifecycleStore, EvidenceStore, review files.

Genesis-040 readiness:
  DecisionResult.can_delegate signals whether future AI workers
  could execute the recommendation autonomously.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from core.decision.detector import DecisionDetector, DecisionQueryKind
from core.decision.models import DecisionContext, DecisionResult, DecisionSeverity
from core.decision.rules import ALL_RULES

logger = logging.getLogger(__name__)

_GENESIS_RE = re.compile(r"genesis[-\s]?(\d+)", re.IGNORECASE)


class DecisionEngine:
    """
    Evaluates engineering state and produces structured DecisionResults.

    Public API (called by Agent):
        can_handle(utterance) -> bool
        handle(utterance)     -> str
        evaluate(genesis)     -> DecisionResult
        build_context(genesis)-> DecisionContext
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke       = knowledge_engine
        self._detector = DecisionDetector()
        self._rules    = ALL_RULES

    # ── Public ─────────────────────────────────────────────────────────────────

    def can_handle(self, utterance: str) -> bool:
        return self._detector.detect(utterance) is not None

    def handle(self, utterance: str) -> str:
        query = self._detector.detect(utterance)
        if query is None:
            return ""

        # Resolve genesis number
        genesis = query.genesis
        if not genesis:
            genesis = self._active_genesis() or "036"

        if query.kind == DecisionQueryKind.WHAT_NEXT:
            result = self.evaluate(genesis)
            return result.to_text()

        if query.kind == DecisionQueryKind.CAN_CLOSE:
            result = self.evaluate(genesis)
            if result.ready_to_close:
                return (
                    f"Yes — Genesis-{genesis} is ready to close, sir.\n\n"
                    + result.to_text()
                )
            return (
                f"Not yet, sir. Genesis-{genesis} is not ready to close.\n\n"
                + result.to_text()
            )

        if query.kind == DecisionQueryKind.WHY_CANT_CLOSE:
            result = self.evaluate(genesis)
            if result.ready_to_close:
                return f"Genesis-{genesis} can actually be closed, sir.\n\n" + result.to_text()
            return (
                f"Genesis-{genesis} cannot be closed because:\n\n"
                + result.to_text()
            )

        if query.kind == DecisionQueryKind.BLOCKERS:
            result = self.evaluate(genesis)
            if not result.blockers:
                return f"No active blockers for Genesis-{genesis}, sir."
            lines = [f"Active blockers for Genesis-{genesis}:"]
            for b in result.blockers:
                lines.append(f"  ✗ {b}")
            lines.append("")
            lines.append(f"Next action: {result.next_action}")
            return "\n".join(lines)

        return self.evaluate(genesis).to_text()

    def evaluate(self, genesis: str) -> DecisionResult:
        """
        Assemble context and evaluate rules for the given genesis.
        Never raises — always returns a DecisionResult.
        """
        ctx = self.build_context(genesis)
        return self._evaluate_rules(ctx)

    def build_context(self, genesis: str) -> DecisionContext:
        """
        Assemble DecisionContext from all subsystems.
        Tolerant of missing subsystems — uses defaults.
        """
        ctx = DecisionContext(genesis=genesis)

        # Lifecycle
        try:
            from core.engineering.lifecycle.store import LifecycleStore
            lc    = LifecycleStore(self._ke)
            rec   = lc.get(genesis)
            active = lc.active_genesis()
            if rec:
                ctx.lifecycle_status = rec.status.value
            ctx.has_active_genesis = (
                active is not None and active.genesis == genesis
            )
        except Exception:
            logger.debug("[DECISION] LifecycleStore unavailable.")

        # Progress / blockers
        try:
            from core.progress.store import ProgressStore
            from core.progress.models import ProgressState
            ps  = ProgressStore(self._ke)
            rec = ps.get_state("genesis", genesis)
            if rec:
                ctx.progress_state = rec.state.value
                if rec.blocker:
                    ctx.blockers.append(rec.blocker)
            # All blocked records
            blocked = ps.records_by_state(ProgressState.BLOCKED)
            for b in blocked:
                if b.blocker and b.blocker not in ctx.blockers:
                    ctx.blockers.append(b.blocker)
        except Exception:
            logger.debug("[DECISION] ProgressStore unavailable.")

        # Evidence
        try:
            from core.engineering.evidence.store import EvidenceStore
            ev   = EvidenceStore(self._ke)
            snap = ev.snapshot(genesis)
            ctx.has_evidence       = ev.has_evidence(genesis)
            ctx.tests_passed       = snap.test_results.get("passed", 0)
            ctx.tests_failed       = snap.test_results.get("failed", 0)
            ctx.tests_skipped      = snap.test_results.get("skipped", 0)
            ctx.desktop_status     = snap.desktop_validation.get("status", "")
        except Exception:
            logger.debug("[DECISION] EvidenceStore unavailable.")

        # Latest review recommendation
        try:
            review_dir = "engineering_reviews"
            pattern    = f"genesis_{genesis}_"
            if os.path.isdir(review_dir):
                matching = sorted(
                    [f for f in os.listdir(review_dir)
                     if f.startswith(pattern) and f.endswith("_review.json")],
                    reverse=True,
                )
                if matching:
                    with open(os.path.join(review_dir, matching[0]), encoding="utf-8") as f:
                        data = json.load(f)
                    ctx.review_recommendation = (
                        data.get("review", {}).get("recommendation", "")
                    )
        except Exception:
            logger.debug("[DECISION] Review files unavailable.")

        return ctx

    # ── Internal ───────────────────────────────────────────────────────────────

    def _evaluate_rules(self, ctx: DecisionContext) -> DecisionResult:
        """Evaluate rules in priority order. Return first match."""
        for rule in self._rules:
            try:
                result = rule.evaluate(ctx)
                if result is not None:
                    logger.info(
                        "[DECISION] Rule %r fired for Genesis-%s: %s",
                        rule.name, ctx.genesis, result.recommendation,
                    )
                    return result
            except Exception:
                logger.exception("[DECISION] Rule %r raised.", rule.name)
        # Should never reach here — DefaultRule always fires
        return DecisionResult(
            recommendation="Unable to evaluate engineering state.",
            confidence=0.0,
            reasons=(),
            blockers=(),
            prerequisites=(),
            severity=DecisionSeverity.WARNING,
            next_action="Check system state.",
        )

    def _active_genesis(self) -> Optional[str]:
        """Return the active genesis number, or None."""
        try:
            from core.engineering.lifecycle.store import LifecycleStore
            lc     = LifecycleStore(self._ke)
            active = lc.active_genesis()
            return active.genesis if active else None
        except Exception:
            return None
