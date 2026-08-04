"""
Planning Intelligence — Rules
Genesis-037 Sprint-001

Data-driven planning rules. Each rule receives a DecisionResult
and a PlanningContext, and produces a WorkPackage or None.

Rules are evaluated in priority order.
Adding a new rule = one new class. No if/elif chains in the engine.

Genesis-040 note: can_delegate=True on a WorkPackage signals that
a future external AI worker could execute this without internal changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from core.planning.models import WorkPackage, make_work_package


class PlanningRule(ABC):
    """Abstract base for all planning rules."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def priority(self) -> int: ...

    @abstractmethod
    def plan(
        self,
        decision_result,          # DecisionResult
        genesis: str,
        context: dict,            # additional context from subsystems
    ) -> Optional[WorkPackage]: ...


# ── Rule implementations ───────────────────────────────────────────────────────

class FixTestsRule(PlanningRule):
    """Rule 1: Failing tests → plan a test fix work package."""

    name     = "fix_tests"
    priority = 10

    def plan(self, decision_result, genesis: str, context: dict) -> Optional[WorkPackage]:
        tests_failed = context.get("tests_failed", 0)
        if tests_failed == 0:
            return None
        return make_work_package(
            objective=f"Fix {tests_failed} failing test(s) to restore green suite.",
            capability_required="run_tests",
            priority=1,
            estimated_scope="small",
            affected_subsystems=("tests/",),
            constraints=(
                "Do not modify test assertions to make tests pass artificially.",
                "Do not skip failing tests.",
            ),
            dependencies=(),
            acceptance_tests=(
                "All tests pass: 0 failed.",
                "Test count does not decrease (no tests removed).",
            ),
            definition_of_done=(
                f"python -m pytest --tb=short -q shows 0 failed.",
                "Full regression suite green.",
            ),
            review_requirements=(
                "Engineering review required before closing.",
            ),
            can_delegate=True,   # future CodingWorker / external AI can fix tests
            source_decision=decision_result.recommendation,
            genesis=genesis,
        )


class ResolveBlockerRule(PlanningRule):
    """Rule 2: Active blockers → plan blocker resolution."""

    name     = "resolve_blocker"
    priority = 20

    def plan(self, decision_result, genesis: str, context: dict) -> Optional[WorkPackage]:
        blockers = decision_result.blockers
        if not blockers:
            return None
        primary_blocker = blockers[0]
        return make_work_package(
            objective=f"Resolve active blocker: {primary_blocker}",
            capability_required="resolve_blocker",
            priority=1,
            estimated_scope="small",
            affected_subsystems=(),
            constraints=(
                "Do not proceed to close Genesis until blocker is resolved.",
            ),
            dependencies=(),
            acceptance_tests=(
                f"Blocker '{primary_blocker}' is no longer reported.",
                "No new blockers introduced.",
            ),
            definition_of_done=(
                f"Blocker resolved: {primary_blocker}",
                "Progress state updated to unblocked.",
            ),
            review_requirements=(),
            can_delegate=False,
            source_decision=decision_result.recommendation,
            genesis=genesis,
        )


class DesktopValidationRule(PlanningRule):
    """Rule 3: Desktop validation pending → plan validation work package."""

    name     = "desktop_validation"
    priority = 30

    def plan(self, decision_result, genesis: str, context: dict) -> Optional[WorkPackage]:
        desktop_status = context.get("desktop_status", "")
        if desktop_status == "passed":
            return None
        if desktop_status == "failed":
            objective = f"Fix and re-run desktop validation for Genesis-{genesis}."
        else:
            objective = f"Complete desktop validation for Genesis-{genesis}."
        return make_work_package(
            objective=objective,
            capability_required="validate_desktop",
            priority=2,
            estimated_scope="small",
            affected_subsystems=("core/agent.py",),
            constraints=(
                "All validation scenarios must pass — no partial acceptance.",
                "Do not skip scenarios.",
            ),
            dependencies=(
                "All automated tests must pass first.",
            ),
            acceptance_tests=(
                "All desktop validation scenarios pass.",
                "desktop_validation.status == 'passed' in evidence.",
            ),
            definition_of_done=(
                "Desktop validation recorded as passed.",
                "Evidence updated via: evidence.record_desktop_validation()",
            ),
            review_requirements=(
                "Engineering review required after validation passes.",
            ),
            can_delegate=False,
            source_decision=decision_result.recommendation,
            genesis=genesis,
        )


class CloseGenesisRule(PlanningRule):
    """Rule 4: Ready to close → plan engineering review and closure."""

    name     = "close_genesis"
    priority = 40

    def plan(self, decision_result, genesis: str, context: dict) -> Optional[WorkPackage]:
        if not decision_result.ready_to_close:
            return None
        return make_work_package(
            objective=f"Run engineering review and close Genesis-{genesis}.",
            capability_required="run_engineering_review",
            priority=1,
            estimated_scope="small",
            affected_subsystems=(
                "core/engineering/review/",
                "core/engineering/lifecycle/",
                "core/engineering/evidence/",
            ),
            constraints=(
                "Engineering review must complete before genesis is marked closed.",
                "No manual genesis closure without review.",
            ),
            dependencies=(
                "All tests passing.",
                "Desktop validation passed.",
                "No active blockers.",
            ),
            acceptance_tests=(
                "engineering_reviews/genesis_{N}_*_review.json written.",
                "engineering_reviews/genesis_{N}_*_report.md written.",
                f"Genesis-{genesis} lifecycle status = closed.",
            ),
            definition_of_done=(
                f"Say: 'Close Genesis-{genesis}.' to execute.",
                "JSON and Markdown reports persisted.",
                f"Genesis-{genesis} marked CLOSED in lifecycle store.",
            ),
            review_requirements=(
                "Automated engineering review via EngineeringReviewOSWorker.",
            ),
            can_delegate=False,   # closure requires lifecycle state change — human approved
            source_decision=decision_result.recommendation,
            genesis=genesis,
        )


class ContinueDevelopmentRule(PlanningRule):
    """Rule 5: Work in progress with no issues → plan continued development."""

    name     = "continue_development"
    priority = 50

    def plan(self, decision_result, genesis: str, context: dict) -> Optional[WorkPackage]:
        active_task = context.get("active_task", "")
        active_project = context.get("active_project", "")
        objective = (
            f"Continue development: {active_task}."
            if active_task
            else f"Continue Genesis-{genesis} development."
        )
        subsystems = (active_project,) if active_project else ()
        return make_work_package(
            objective=objective,
            capability_required="plan_implementation",
            priority=3,
            estimated_scope="medium",
            affected_subsystems=subsystems,
            constraints=(
                "No autonomous code changes without human approval.",
                "All changes must pass full regression suite.",
            ),
            dependencies=(),
            acceptance_tests=(
                "Full regression suite passes.",
                "Desktop validation passes.",
            ),
            definition_of_done=(
                "Implementation complete.",
                "Tests written and passing.",
                "Desktop validation scenarios documented.",
            ),
            review_requirements=(
                "Engineering review on genesis close.",
            ),
            can_delegate=True,   # future external AI could implement this
            source_decision=decision_result.recommendation,
            genesis=genesis,
        )


class DefaultPlanRule(PlanningRule):
    """Rule 99: Fallback — produce a generic planning work package."""

    name     = "default_plan"
    priority = 99

    def plan(self, decision_result, genesis: str, context: dict) -> Optional[WorkPackage]:
        return make_work_package(
            objective=f"Begin engineering work for Genesis-{genesis}.",
            capability_required="plan_implementation",
            priority=5,
            estimated_scope="medium",
            constraints=(
                "Open genesis first: 'Open Genesis-{N}.'",
            ),
            acceptance_tests=(
                "Genesis opened in lifecycle store.",
                "Progress state set to in_progress.",
            ),
            definition_of_done=(
                "Active genesis confirmed.",
                "Engineering objectives defined.",
            ),
            review_requirements=(),
            can_delegate=False,
            source_decision=decision_result.recommendation,
            genesis=genesis,
        )


# ── Rule registry ──────────────────────────────────────────────────────────────

ALL_PLANNING_RULES: list[PlanningRule] = sorted([
    FixTestsRule(),
    ResolveBlockerRule(),
    DesktopValidationRule(),
    CloseGenesisRule(),
    ContinueDevelopmentRule(),
    DefaultPlanRule(),
], key=lambda r: r.priority)
