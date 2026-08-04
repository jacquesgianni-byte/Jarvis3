"""
Tests — Planning Intelligence: Planning Engine
Genesis-037 Sprint-001
"""

import pytest
from core.planning.models import WorkPackage, PlanningResult, make_work_package
from core.planning.detector import PlanningDetector
from core.planning.rules import (
    ALL_PLANNING_RULES, FixTestsRule, ResolveBlockerRule,
    DesktopValidationRule, CloseGenesisRule, ContinueDevelopmentRule,
    DefaultPlanRule,
)
from core.planning.engine import PlanningEngine, _NullDecisionResult


# ── In-memory KE stub ─────────────────────────────────────────────────────────

class _MemoryStore:
    def __init__(self):
        self._records: dict = {}

    def store_memory(self, subject, category, attribute, value, tags=None, **kwargs):
        from datetime import datetime, timezone
        from uuid import uuid4
        class Rec: pass
        key = f"{subject}::{attribute}"
        r = Rec()
        r.id = str(uuid4()); r.subject = subject; r.category = category
        r.attribute = attribute; r.value = value; r.tags = list(tags or [])
        r.created_at = datetime.now(timezone.utc)
        r.updated_at = datetime.now(timezone.utc)
        r.expires_at = None
        self._records[key] = r
        return r

    def recall_memory(self, subject, attribute, category=None):
        return self._records.get(f"{subject}::{attribute}")

    def forget_memory(self, subject, attribute, permanent=False, **kwargs):
        key = f"{subject}::{attribute}"
        if key in self._records:
            del self._records[key]
            return True
        return False

    def update_memory(self, subject, attribute, value, **kwargs):
        key = f"{subject}::{attribute}"
        if key in self._records:
            self._records[key].value = value
        return self._records.get(key)

    def list_memories(self, subject=None, limit=100, **kwargs):
        results = list(self._records.values())
        if subject:
            results = [r for r in results if r.subject == subject]
        return results[:limit]


@pytest.fixture()
def ke():
    return _MemoryStore()


def _null_decision(**kwargs):
    """Build a minimal decision result for testing."""
    defaults = dict(
        recommendation="Continue.",
        confidence=0.8,
        reasons=(),
        blockers=(),
        prerequisites=(),
        next_action="Continue.",
        can_delegate=False,
        ready_to_close=False,
    )
    defaults.update(kwargs)

    class FakeDecision:
        pass

    d = FakeDecision()
    for k, v in defaults.items():
        setattr(d, k, v)
    return d


# ── WorkPackage ────────────────────────────────────────────────────────────────

class TestWorkPackage:
    def test_is_frozen(self):
        pkg = make_work_package(
            objective="Test",
            capability_required="run_tests",
        )
        with pytest.raises((AttributeError, TypeError)):
            pkg.objective = "Changed"  # type: ignore

    def test_to_text_contains_objective(self):
        pkg = make_work_package(
            objective="Fix 5 failing tests.",
            capability_required="run_tests",
        )
        assert "Fix 5 failing tests" in pkg.to_text()

    def test_to_text_contains_capability(self):
        pkg = make_work_package(
            objective="Run tests.",
            capability_required="run_tests",
        )
        assert "run_tests" in pkg.to_text()

    def test_to_text_contains_acceptance_tests(self):
        pkg = make_work_package(
            objective="Fix tests.",
            capability_required="run_tests",
            acceptance_tests=("All tests pass.",),
        )
        assert "All tests pass" in pkg.to_text()

    def test_to_text_contains_definition_of_done(self):
        pkg = make_work_package(
            objective="Fix tests.",
            capability_required="run_tests",
            definition_of_done=("Zero failed tests.",),
        )
        assert "Zero failed tests" in pkg.to_text()

    def test_can_delegate_field(self):
        pkg = make_work_package(
            objective="Implement feature.",
            capability_required="plan_implementation",
            can_delegate=True,
        )
        assert pkg.can_delegate is True

    def test_id_is_set(self):
        pkg = make_work_package(objective="Test", capability_required="run_tests")
        assert len(pkg.id) == 36   # UUID format


# ── PlanningResult ─────────────────────────────────────────────────────────────

class TestPlanningResult:
    def test_to_text_contains_header(self):
        pkg = make_work_package(objective="Fix tests.", capability_required="run_tests")
        result = PlanningResult(
            packages=(pkg,),
            total=1,
            genesis="037",
            planned_at="2026-08-04T12:00:00+00:00",
        )
        text = result.to_text()
        assert "ENGINEERING WORK PLAN" in text

    def test_to_text_contains_genesis(self):
        result = PlanningResult(packages=(), total=0, genesis="037", planned_at="2026-08-04T12:00:00")
        assert "037" in result.to_text()

    def test_to_text_contains_package(self):
        pkg = make_work_package(objective="Fix tests.", capability_required="run_tests")
        result = PlanningResult(packages=(pkg,), total=1, genesis="037", planned_at="2026-08-04T12:00:00")
        assert "Fix tests" in result.to_text()


# ── PlanningDetector ──────────────────────────────────────────────────────────

class TestPlanningDetector:
    def setup_method(self):
        self.d = PlanningDetector()

    def test_what_needs_to_happen_next(self):
        assert self.d.can_handle("What needs to happen next?") is True

    def test_create_a_work_plan(self):
        assert self.d.can_handle("Create a work plan.") is True

    def test_plan_the_next_sprint(self):
        assert self.d.can_handle("Plan the next sprint.") is True

    def test_plan(self):
        assert self.d.can_handle("Plan") is True

    def test_what_should_happen_next(self):
        assert self.d.can_handle("What should happen next?") is True

    def test_generate_a_plan(self):
        assert self.d.can_handle("Generate a plan.") is True

    def test_unrelated(self):
        assert self.d.can_handle("What is the weather?") is False
        assert self.d.can_handle("Engineering briefing.") is False
        assert self.d.can_handle("What should we do next?") is False


# ── Planning Rules ─────────────────────────────────────────────────────────────

class TestPlanningRules:
    def test_fix_tests_rule_fires_when_failing(self):
        d = _null_decision()
        pkg = FixTestsRule().plan(d, "037", {"tests_failed": 5})
        assert pkg is not None
        assert "run_tests" == pkg.capability_required
        assert pkg.can_delegate is True
        assert "5" in pkg.objective

    def test_fix_tests_rule_silent_when_green(self):
        d = _null_decision()
        assert FixTestsRule().plan(d, "037", {"tests_failed": 0}) is None

    def test_resolve_blocker_fires_when_blocked(self):
        d = _null_decision(blockers=("desktop validation",))
        pkg = ResolveBlockerRule().plan(d, "037", {})
        assert pkg is not None
        assert "desktop validation" in pkg.objective

    def test_resolve_blocker_silent_when_clear(self):
        d = _null_decision(blockers=())
        assert ResolveBlockerRule().plan(d, "037", {}) is None

    def test_desktop_validation_fires_when_pending(self):
        d = _null_decision()
        pkg = DesktopValidationRule().plan(d, "037", {"desktop_status": ""})
        assert pkg is not None
        assert "validate_desktop" == pkg.capability_required

    def test_desktop_validation_silent_when_passed(self):
        d = _null_decision()
        assert DesktopValidationRule().plan(d, "037", {"desktop_status": "passed"}) is None

    def test_close_genesis_fires_when_ready(self):
        d = _null_decision(ready_to_close=True)
        pkg = CloseGenesisRule().plan(d, "037", {})
        assert pkg is not None
        assert "run_engineering_review" == pkg.capability_required
        assert pkg.can_delegate is False  # closure needs human approval

    def test_close_genesis_silent_when_not_ready(self):
        d = _null_decision(ready_to_close=False)
        assert CloseGenesisRule().plan(d, "037", {}) is None

    def test_continue_development_fires(self):
        d = _null_decision()
        pkg = ContinueDevelopmentRule().plan(d, "037", {"active_task": "Write tests"})
        assert pkg is not None
        assert "plan_implementation" == pkg.capability_required
        assert pkg.can_delegate is True  # external AI eligible
        assert "Write tests" in pkg.objective

    def test_default_rule_always_fires(self):
        d = _null_decision()
        pkg = DefaultPlanRule().plan(d, "037", {})
        assert pkg is not None

    def test_rules_ordered_by_priority(self):
        priorities = [r.priority for r in ALL_PLANNING_RULES]
        assert priorities == sorted(priorities)

    def test_fix_tests_beats_desktop_validation(self):
        """Fix tests has higher priority than desktop validation."""
        fix = FixTestsRule()
        dv  = DesktopValidationRule()
        assert fix.priority < dv.priority

    def test_close_genesis_package_has_correct_dod(self):
        d = _null_decision(ready_to_close=True)
        pkg = CloseGenesisRule().plan(d, "037", {})
        dod_text = " ".join(pkg.definition_of_done)
        assert "Close Genesis-037" in dod_text


# ── PlanningEngine end-to-end ─────────────────────────────────────────────────

class TestPlanningEngine:
    def test_can_handle_work_plan(self, ke):
        eng = PlanningEngine(ke)
        assert eng.can_handle("Create a work plan.") is True

    def test_can_handle_plan_next_sprint(self, ke):
        eng = PlanningEngine(ke)
        assert eng.can_handle("Plan the next sprint.") is True

    def test_cannot_handle_engineering_briefing(self, ke):
        eng = PlanningEngine(ke)
        assert eng.can_handle("Engineering briefing.") is False

    def test_cannot_handle_what_should_we_do_next(self, ke):
        """Decision engine handles this, not planning engine."""
        eng = PlanningEngine(ke)
        assert eng.can_handle("What should we do next?") is False

    def test_handle_returns_string(self, ke):
        eng = PlanningEngine(ke)
        result = eng.handle("Create a work plan.")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_handle_contains_header(self, ke):
        eng = PlanningEngine(ke)
        result = eng.handle("Plan the next sprint.")
        assert "ENGINEERING WORK PLAN" in result

    def test_plan_returns_planning_result(self, ke):
        eng = PlanningEngine(ke)
        d   = _null_decision()
        result = eng.plan(d, "037")
        assert isinstance(result, PlanningResult)

    def test_plan_has_packages(self, ke):
        eng = PlanningEngine(ke)
        d   = _null_decision()
        result = eng.plan(d, "037")
        assert result.total >= 1

    def test_plan_with_failing_tests(self, ke):
        """Scenario: failing tests → FixTests package."""
        from core.engineering.evidence.store import EvidenceStore
        ev = EvidenceStore(ke)
        ev.initialise("037")
        ev.set_test_results("037", passed=100, skipped=0, failed=5)

        eng = PlanningEngine(ke)
        d   = _null_decision()
        result = eng.plan(d, "037")
        assert result.total >= 1
        assert result.packages[0].capability_required == "run_tests"

    def test_plan_with_blocker(self, ke):
        """Scenario 4: blocked project → includes dependencies."""
        d = _null_decision(blockers=("desktop validation",))
        eng = PlanningEngine(ke)
        result = eng.plan(d, "037")
        assert result.total >= 1
        pkg = result.packages[0]
        assert "resolve_blocker" == pkg.capability_required or \
               "desktop validation" in pkg.objective.lower()

    def test_plan_ready_to_close(self, ke):
        """Scenario: ready to close → engineering review package."""
        from core.engineering.evidence.store import EvidenceStore
        ev = EvidenceStore(ke)
        ev.initialise("037")
        ev.set_test_results("037", passed=3750, skipped=33, failed=0)
        ev.set_desktop_validation("037", "passed", ["All scenarios passed"])

        d = _null_decision(ready_to_close=True)
        eng = PlanningEngine(ke)
        result = eng.plan(d, "037")
        assert result.packages[0].capability_required == "run_engineering_review"

    def test_no_ai_calls(self, ke):
        eng = PlanningEngine(ke)
        assert not hasattr(eng, "_ai")
        assert not hasattr(eng, "ai")


# ── Desktop Validation Scenarios ──────────────────────────────────────────────

class TestDesktopScenarios:
    def test_scenario_1_what_should_happen_next(self, ke):
        """What should happen next? → WorkPackage produced."""
        eng = PlanningEngine(ke)
        text = eng.handle("What should happen next?")
        assert "ENGINEERING WORK PLAN" in text
        assert "Work Package" in text

    def test_scenario_2_create_work_plan(self, ke):
        """Create a work plan. → Structured WorkPackage."""
        eng = PlanningEngine(ke)
        text = eng.handle("Create a work plan.")
        assert "ENGINEERING WORK PLAN" in text

    def test_scenario_3_plan_next_sprint(self, ke):
        """Plan the next sprint. → Prioritised WorkPackage."""
        eng = PlanningEngine(ke)
        text = eng.handle("Plan the next sprint.")
        assert "ENGINEERING WORK PLAN" in text
        assert "Priority" in text

    def test_scenario_4_blocked_includes_dependencies(self, ke):
        """Blocked project → WorkPackage includes dependencies."""
        d = _null_decision(blockers=("desktop validation",))
        eng = PlanningEngine(ke)
        result = eng.plan(d, "037")
        pkg = result.packages[0]
        text = pkg.to_text()
        # Should mention the blocker or have dependencies
        assert "desktop validation" in text.lower() or len(pkg.constraints) > 0
