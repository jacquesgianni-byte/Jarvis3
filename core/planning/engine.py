"""
Planning Intelligence — Engine
Genesis-037 Sprint-001

PlanningEngine consumes DecisionResult and engineering context,
evaluates PlanningRules, and produces immutable WorkPackages.

No AI. No storage. One-way dependency direction.

Reads from:
  - DecisionEngine (primary — gets decision result)
  - ProgressStore  (active blockers/state)
  - LifecycleStore (active genesis)
  - EvidenceStore  (test results, desktop status)
  - GoalTracker, TaskTracker (active task/project)

Genesis-040: WorkPackages are designed to be consumed by external
AI workers without modification.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.planning.detector import PlanningDetector
from core.planning.models import PlanningResult, WorkPackage
from core.planning.rules import ALL_PLANNING_RULES

logger = logging.getLogger(__name__)


class PlanningEngine:
    """
    Transforms DecisionResults into structured WorkPackages.

    Public API (called by Agent):
        can_handle(utterance) -> bool
        handle(utterance)     -> str
        plan(decision_result, genesis) -> PlanningResult
        build_context(genesis)         -> dict
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke       = knowledge_engine
        self._detector = PlanningDetector()
        self._rules    = ALL_PLANNING_RULES

    # ── Public ─────────────────────────────────────────────────────────────────

    def can_handle(self, utterance: str) -> bool:
        return self._detector.can_handle(utterance)

    def handle(self, utterance: str) -> str:
        """Handle a planning request and return rendered text."""
        genesis = self._active_genesis() or "036"
        decision = self._get_decision(genesis)
        result   = self.plan(decision, genesis)
        return result.to_text()

    def plan(self, decision_result, genesis: str) -> PlanningResult:
        """
        Produce a PlanningResult from a DecisionResult.
        Evaluates all rules and returns matching WorkPackages.
        """
        context  = self.build_context(genesis)
        packages = self._evaluate_rules(decision_result, genesis, context)

        return PlanningResult(
            packages=tuple(packages),
            total=len(packages),
            genesis=genesis,
            planned_at=datetime.now(timezone.utc).isoformat(),
        )

    def build_context(self, genesis: str) -> dict:
        """
        Assemble planning context from all subsystems.
        Tolerant of missing subsystems — uses empty defaults.
        """
        ctx: dict = {
            "genesis":       genesis,
            "tests_passed":  0,
            "tests_failed":  0,
            "desktop_status": "",
            "active_task":   "",
            "active_project": "",
            "active_goal":   "",
            "blockers":      [],
        }

        # Evidence
        try:
            from core.engineering.evidence.store import EvidenceStore
            ev   = EvidenceStore(self._ke)
            snap = ev.snapshot(genesis)
            ctx["tests_passed"]   = snap.test_results.get("passed", 0)
            ctx["tests_failed"]   = snap.test_results.get("failed", 0)
            ctx["desktop_status"] = snap.desktop_validation.get("status", "")
        except Exception:
            logger.debug("[PLANNING] EvidenceStore unavailable.")

        # Progress / blockers
        try:
            from core.progress.store import ProgressStore
            from core.progress.models import ProgressState
            ps      = ProgressStore(self._ke)
            blocked = ps.records_by_state(ProgressState.BLOCKED)
            ctx["blockers"] = [r.blocker for r in blocked if r.blocker]
        except Exception:
            logger.debug("[PLANNING] ProgressStore unavailable.")

        # Goal Intelligence
        try:
            from core.goal_intelligence.goal_tracker import GoalTracker
            from core.goal_intelligence.project_tracker import ProjectTracker
            from core.goal_intelligence.task_tracker import TaskTracker
            gt = GoalTracker(self._ke)
            pt = ProjectTracker(self._ke)
            tt = TaskTracker(self._ke)
            goal    = gt.active_goal()
            project = pt.active_project()
            task    = tt.active_task()
            if goal:    ctx["active_goal"]    = goal.title
            if project: ctx["active_project"] = project.title
            if task:    ctx["active_task"]    = task.title
        except Exception:
            logger.debug("[PLANNING] Goal Intelligence unavailable.")

        return ctx

    # ── Internal ───────────────────────────────────────────────────────────────

    def _evaluate_rules(
        self,
        decision_result,
        genesis: str,
        context: dict,
    ) -> list[WorkPackage]:
        """Evaluate all rules and collect matching WorkPackages."""
        packages: list[WorkPackage] = []

        for rule in self._rules:
            try:
                pkg = rule.plan(decision_result, genesis, context)
                if pkg is not None:
                    packages.append(pkg)
                    logger.info(
                        "[PLANNING] Rule %r produced package: %s",
                        rule.name, pkg.objective[:60],
                    )
                    # Stop at first match unless it's a compound plan
                    # For now: return first matching package (single work item)
                    break
            except Exception:
                logger.exception("[PLANNING] Rule %r raised.", rule.name)

        return packages

    def _get_decision(self, genesis: str):
        """Get a DecisionResult for the given genesis."""
        try:
            from core.decision.engine import DecisionEngine
            de = DecisionEngine(self._ke)
            return de.evaluate(genesis)
        except Exception:
            logger.debug("[PLANNING] DecisionEngine unavailable.")
            return _NullDecisionResult()

    def _active_genesis(self) -> Optional[str]:
        """Return the active genesis number, or None."""
        try:
            from core.engineering.lifecycle.store import LifecycleStore
            lc     = LifecycleStore(self._ke)
            active = lc.active_genesis()
            return active.genesis if active else None
        except Exception:
            return None


class _NullDecisionResult:
    """Minimal stub used when DecisionEngine is unavailable."""
    recommendation = ""
    confidence     = 0.0
    reasons:       tuple = ()
    blockers:      tuple = ()
    prerequisites: tuple = ()
    next_action    = ""
    can_delegate   = False
    ready_to_close = False
