"""
Decision Intelligence — Rules
Genesis-036 Sprint-001

Data-driven decision rules. Each rule evaluates a DecisionContext
and returns a DecisionResult or None (no match → try next rule).

Adding a new rule = one new class. No if/elif chains in the engine.
Rules are evaluated in priority order (lower number = higher priority).

Genesis-040 readiness:
  can_delegate=True signals that a future AI worker could execute
  this recommendation autonomously after human approval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.decision.models import DecisionContext, DecisionResult, DecisionSeverity


class DecisionRule(ABC):
    """Abstract base for all decision rules."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def priority(self) -> int: ...

    @abstractmethod
    def evaluate(self, ctx: DecisionContext) -> Optional[DecisionResult]: ...


# ── Rule implementations ───────────────────────────────────────────────────────

class BlockerRule(DecisionRule):
    """Rule 1: Active blockers prevent any forward progress."""

    name     = "blocker_check"
    priority = 10

    def evaluate(self, ctx: DecisionContext) -> Optional[DecisionResult]:
        if not ctx.has_blockers:
            return None
        blocker_list = tuple(ctx.blockers)
        return DecisionResult(
            recommendation="Resolve active blockers before proceeding.",
            confidence=1.0,
            reasons=(
                f"{len(blocker_list)} active blocker(s) detected.",
            ),
            blockers=blocker_list,
            prerequisites=tuple(f"Resolve: {b}" for b in blocker_list),
            severity=DecisionSeverity.CRITICAL,
            next_action=f"Resolve: {blocker_list[0]}",
            can_delegate=False,
            ready_to_close=False,
        )


class NoActiveGenesisRule(DecisionRule):
    """Rule 2: No active genesis — nothing to evaluate."""

    name     = "no_active_genesis"
    priority = 20

    def evaluate(self, ctx: DecisionContext) -> Optional[DecisionResult]:
        if ctx.has_active_genesis:
            return None
        return DecisionResult(
            recommendation="Open a Genesis to begin engineering work.",
            confidence=1.0,
            reasons=("No active Genesis found.",),
            blockers=(),
            prerequisites=("Say: 'Open Genesis-0XX.' to begin.",),
            severity=DecisionSeverity.WARNING,
            next_action="Open Genesis-0XX.",
            can_delegate=False,
            ready_to_close=False,
        )


class FailingTestsRule(DecisionRule):
    """Rule 3: Failing tests block closure."""

    name     = "failing_tests"
    priority = 30

    def evaluate(self, ctx: DecisionContext) -> Optional[DecisionResult]:
        if ctx.tests_failed == 0:
            return None
        return DecisionResult(
            recommendation=f"Fix {ctx.tests_failed} failing test(s).",
            confidence=1.0,
            reasons=(
                f"{ctx.tests_failed} test(s) are currently failing.",
                "Genesis cannot be closed with failing tests.",
            ),
            blockers=(f"{ctx.tests_failed} failing test(s)",),
            prerequisites=("All tests must pass before closure.",),
            severity=DecisionSeverity.CRITICAL,
            next_action="Run the test suite and fix all failures.",
            can_delegate=True,   # a future CodingWorker could fix tests
            ready_to_close=False,
        )


class NoTestsRule(DecisionRule):
    """Rule 4: No test data recorded yet."""

    name     = "no_tests_recorded"
    priority = 35

    def evaluate(self, ctx: DecisionContext) -> Optional[DecisionResult]:
        if ctx.tests_passed > 0 or ctx.tests_failed > 0:
            return None
        if not ctx.has_evidence:
            return None
        return DecisionResult(
            recommendation="Record test results before closing.",
            confidence=0.9,
            reasons=("No test results recorded in evidence.",),
            blockers=(),
            prerequisites=("Run the test suite and record results.",),
            severity=DecisionSeverity.WARNING,
            next_action="Run: python -m pytest --tb=short -q",
            can_delegate=True,
            ready_to_close=False,
        )


class DesktopValidationRule(DecisionRule):
    """Rule 5: Desktop validation must pass before closure."""

    name     = "desktop_validation"
    priority = 40

    def evaluate(self, ctx: DecisionContext) -> Optional[DecisionResult]:
        if ctx.desktop_passed:
            return None
        if ctx.desktop_status == "failed":
            return DecisionResult(
                recommendation="Desktop validation failed — fix issues before closing.",
                confidence=1.0,
                reasons=("Desktop validation did not pass.",),
                blockers=("Desktop validation: failed",),
                prerequisites=("Desktop validation must pass.",),
                severity=DecisionSeverity.CRITICAL,
                next_action="Re-run desktop validation scenarios.",
                can_delegate=False,
                ready_to_close=False,
            )
        # Pending or unknown
        return DecisionResult(
            recommendation="Complete desktop validation before closing.",
            confidence=0.95,
            reasons=("Desktop validation has not been completed.",),
            blockers=(),
            prerequisites=("Desktop validation must be completed and pass.",),
            severity=DecisionSeverity.WARNING,
            next_action="Run all desktop validation scenarios.",
            can_delegate=False,
            ready_to_close=False,
        )


class ReadyToCloseRule(DecisionRule):
    """Rule 6: All checks pass — Genesis is ready to close."""

    name     = "ready_to_close"
    priority = 50

    def evaluate(self, ctx: DecisionContext) -> Optional[DecisionResult]:
        if not ctx.is_closeable:
            return None
        reasons = [
            f"Tests: {ctx.tests_passed} passing, 0 failing.",
            "Desktop validation: passed.",
            "No active blockers.",
        ]
        if ctx.review_recommendation:
            reasons.append(f"Latest review: {ctx.review_recommendation}")

        return DecisionResult(
            recommendation=f"Close Genesis-{ctx.genesis}.",
            confidence=0.95,
            reasons=tuple(reasons),
            blockers=(),
            prerequisites=(),
            severity=DecisionSeverity.INFO,
            next_action=f"Say: 'Close Genesis-{ctx.genesis}.'",
            can_delegate=False,
            ready_to_close=True,
        )


class InProgressRule(DecisionRule):
    """Rule 7: Work is in progress with no issues — continue."""

    name     = "in_progress"
    priority = 60

    def evaluate(self, ctx: DecisionContext) -> Optional[DecisionResult]:
        if ctx.progress_state != "in_progress":
            return None
        return DecisionResult(
            recommendation=f"Continue Genesis-{ctx.genesis}.",
            confidence=0.8,
            reasons=(f"Genesis-{ctx.genesis} is in progress.",),
            blockers=(),
            prerequisites=(),
            severity=DecisionSeverity.INFO,
            next_action="Continue development work.",
            can_delegate=False,
            ready_to_close=False,
        )


class DefaultRule(DecisionRule):
    """Rule 99: Fallback when no other rule fires."""

    name     = "default"
    priority = 99

    def evaluate(self, ctx: DecisionContext) -> Optional[DecisionResult]:
        return DecisionResult(
            recommendation="Set Genesis status to begin decision tracking.",
            confidence=0.5,
            reasons=("Insufficient engineering state to make a specific recommendation.",),
            blockers=(),
            prerequisites=(
                f"Say: 'Genesis-{ctx.genesis} is in progress.' to begin tracking.",
            ),
            severity=DecisionSeverity.INFO,
            next_action=f"Say: 'Genesis-{ctx.genesis} is in progress.'",
            can_delegate=False,
            ready_to_close=False,
        )


# ── Rule registry — ordered by priority ───────────────────────────────────────

ALL_RULES: list[DecisionRule] = sorted([
    BlockerRule(),
    NoActiveGenesisRule(),
    FailingTestsRule(),
    NoTestsRule(),
    DesktopValidationRule(),
    ReadyToCloseRule(),
    InProgressRule(),
    DefaultRule(),
], key=lambda r: r.priority)
