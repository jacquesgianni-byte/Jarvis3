"""
Tests — Decision Intelligence: Decision Engine
Genesis-036 Sprint-001
"""

import pytest
from core.decision.models import DecisionContext, DecisionResult, DecisionSeverity
from core.decision.detector import DecisionDetector, DecisionQueryKind
from core.decision.rules import (
    ALL_RULES, BlockerRule, FailingTestsRule, DesktopValidationRule,
    ReadyToCloseRule, NoActiveGenesisRule, InProgressRule, DefaultRule,
)
from core.decision.engine import DecisionEngine


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


# ── DecisionContext ────────────────────────────────────────────────────────────

class TestDecisionContext:
    def test_tests_green_true(self):
        ctx = DecisionContext(genesis="036", tests_passed=100, tests_failed=0)
        assert ctx.tests_green is True

    def test_tests_green_false_when_failures(self):
        ctx = DecisionContext(genesis="036", tests_passed=100, tests_failed=5)
        assert ctx.tests_green is False

    def test_tests_green_false_when_no_tests(self):
        ctx = DecisionContext(genesis="036", tests_passed=0, tests_failed=0)
        assert ctx.tests_green is False

    def test_desktop_passed(self):
        ctx = DecisionContext(genesis="036", desktop_status="passed")
        assert ctx.desktop_passed is True

    def test_has_blockers(self):
        ctx = DecisionContext(genesis="036", blockers=["desktop validation"])
        assert ctx.has_blockers is True

    def test_is_closeable_true(self):
        ctx = DecisionContext(
            genesis="036",
            tests_passed=100, tests_failed=0,
            desktop_status="passed",
            has_active_genesis=True,
        )
        assert ctx.is_closeable is True

    def test_is_closeable_false_with_blocker(self):
        ctx = DecisionContext(
            genesis="036",
            tests_passed=100, tests_failed=0,
            desktop_status="passed",
            has_active_genesis=True,
            blockers=["something"],
        )
        assert ctx.is_closeable is False


# ── DecisionResult ─────────────────────────────────────────────────────────────

class TestDecisionResult:
    def test_to_text_contains_recommendation(self):
        r = DecisionResult(
            recommendation="Close Genesis-036.",
            confidence=0.95,
            reasons=("All tests passing.",),
            blockers=(),
            prerequisites=(),
            severity=DecisionSeverity.INFO,
            next_action="Say: 'Close Genesis-036.'",
            ready_to_close=True,
        )
        text = r.to_text()
        assert "Close Genesis-036" in text
        assert "95%" in text

    def test_to_text_contains_blockers(self):
        r = DecisionResult(
            recommendation="Resolve blockers.",
            confidence=1.0,
            reasons=("Blocked.",),
            blockers=("desktop validation",),
            prerequisites=(),
            severity=DecisionSeverity.CRITICAL,
            next_action="Fix desktop validation.",
        )
        assert "desktop validation" in r.to_text()

    def test_to_text_ready_to_close(self):
        r = DecisionResult(
            recommendation="Close.",
            confidence=1.0,
            reasons=(),
            blockers=(),
            prerequisites=(),
            severity=DecisionSeverity.INFO,
            next_action="Close.",
            ready_to_close=True,
        )
        assert "Ready to close" in r.to_text()


# ── DecisionDetector ──────────────────────────────────────────────────────────

class TestDecisionDetector:
    def setup_method(self):
        self.d = DecisionDetector()

    def test_what_should_we_do_next(self):
        r = self.d.detect("What should we do next?")
        assert r is not None
        assert r.kind == DecisionQueryKind.WHAT_NEXT

    def test_whats_next(self):
        r = self.d.detect("What's next?")
        assert r is not None
        assert r.kind == DecisionQueryKind.WHAT_NEXT

    def test_can_we_close_genesis(self):
        r = self.d.detect("Can we close Genesis-036?")
        assert r is not None
        assert r.kind == DecisionQueryKind.CAN_CLOSE
        assert r.genesis == "036"

    def test_can_we_close_this(self):
        r = self.d.detect("Can we close this?")
        assert r is not None
        assert r.kind == DecisionQueryKind.CAN_CLOSE

    def test_why_cant_we_close_it(self):
        r = self.d.detect("Why can't we close it?")
        assert r is not None
        assert r.kind == DecisionQueryKind.WHY_CANT_CLOSE

    def test_why_cant_we_close_genesis(self):
        r = self.d.detect("Why can't we close Genesis-036?")
        assert r is not None
        assert r.kind == DecisionQueryKind.WHY_CANT_CLOSE
        assert r.genesis == "036"

    def test_is_anything_blocking_us(self):
        r = self.d.detect("Is anything blocking us?")
        assert r is not None
        assert r.kind == DecisionQueryKind.BLOCKERS

    def test_blockers(self):
        r = self.d.detect("Blockers")
        assert r is not None
        assert r.kind == DecisionQueryKind.BLOCKERS

    def test_no_detection_for_unrelated(self):
        assert self.d.detect("What is the weather?") is None
        assert self.d.detect("My goal is Jarvis 1.0") is None
        assert self.d.detect("Engineering briefing.") is None


# ── Decision Rules ─────────────────────────────────────────────────────────────

class TestDecisionRules:
    def _green_ctx(self, genesis="036") -> DecisionContext:
        return DecisionContext(
            genesis=genesis,
            has_active_genesis=True,
            tests_passed=3703, tests_failed=0,
            desktop_status="passed",
            progress_state="in_progress",
        )

    def test_blocker_rule_fires_when_blocked(self):
        ctx = DecisionContext(genesis="036", blockers=["desktop validation"])
        r = BlockerRule().evaluate(ctx)
        assert r is not None
        assert r.severity == DecisionSeverity.CRITICAL
        assert "desktop validation" in r.blockers

    def test_blocker_rule_silent_when_clear(self):
        ctx = DecisionContext(genesis="036", blockers=[])
        assert BlockerRule().evaluate(ctx) is None

    def test_failing_tests_rule_fires(self):
        ctx = DecisionContext(genesis="036", tests_failed=5)
        r = FailingTestsRule().evaluate(ctx)
        assert r is not None
        assert "5" in r.recommendation
        assert r.can_delegate is True

    def test_failing_tests_rule_silent_when_green(self):
        ctx = DecisionContext(genesis="036", tests_failed=0)
        assert FailingTestsRule().evaluate(ctx) is None

    def test_desktop_validation_rule_fires_when_pending(self):
        ctx = DecisionContext(genesis="036", desktop_status="")
        r = DesktopValidationRule().evaluate(ctx)
        assert r is not None
        assert r.severity == DecisionSeverity.WARNING

    def test_desktop_validation_rule_fires_when_failed(self):
        ctx = DecisionContext(genesis="036", desktop_status="failed")
        r = DesktopValidationRule().evaluate(ctx)
        assert r is not None
        assert r.severity == DecisionSeverity.CRITICAL

    def test_desktop_validation_rule_silent_when_passed(self):
        ctx = DecisionContext(genesis="036", desktop_status="passed")
        assert DesktopValidationRule().evaluate(ctx) is None

    def test_ready_to_close_fires_when_all_green(self):
        ctx = self._green_ctx()
        r = ReadyToCloseRule().evaluate(ctx)
        assert r is not None
        assert r.ready_to_close is True
        assert r.severity == DecisionSeverity.INFO

    def test_no_active_genesis_rule_fires(self):
        ctx = DecisionContext(genesis="036", has_active_genesis=False)
        r = NoActiveGenesisRule().evaluate(ctx)
        assert r is not None

    def test_in_progress_rule_fires(self):
        ctx = DecisionContext(genesis="036", progress_state="in_progress")
        r = InProgressRule().evaluate(ctx)
        assert r is not None
        assert "Continue" in r.recommendation

    def test_rules_ordered_by_priority(self):
        priorities = [r.priority for r in ALL_RULES]
        assert priorities == sorted(priorities)

    def test_default_rule_always_fires(self):
        ctx = DecisionContext(genesis="036")
        r = DefaultRule().evaluate(ctx)
        assert r is not None


# ── DecisionEngine end-to-end ─────────────────────────────────────────────────

class TestDecisionEngine:
    def test_can_handle_what_next(self, ke):
        eng = DecisionEngine(ke)
        assert eng.can_handle("What should we do next?") is True

    def test_can_handle_can_close(self, ke):
        eng = DecisionEngine(ke)
        assert eng.can_handle("Can we close Genesis-036?") is True

    def test_can_handle_why_cant_close(self, ke):
        eng = DecisionEngine(ke)
        assert eng.can_handle("Why can't we close it?") is True

    def test_can_handle_blockers(self, ke):
        eng = DecisionEngine(ke)
        assert eng.can_handle("Is anything blocking us?") is True

    def test_cannot_handle_unrelated(self, ke):
        eng = DecisionEngine(ke)
        assert eng.can_handle("Engineering briefing.") is False
        assert eng.can_handle("What is the weather?") is False

    def test_handle_returns_string(self, ke):
        eng = DecisionEngine(ke)
        result = eng.handle("What should we do next?")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_evaluate_returns_decision_result(self, ke):
        eng = DecisionEngine(ke)
        result = eng.evaluate("036")
        assert isinstance(result, DecisionResult)

    def test_build_context_returns_decision_context(self, ke):
        eng = DecisionEngine(ke)
        ctx = eng.build_context("036")
        assert isinstance(ctx, DecisionContext)
        assert ctx.genesis == "036"


# ── Desktop validation scenarios ──────────────────────────────────────────────

class TestDesktopScenarios:
    def test_scenario_1_what_should_we_do_next(self, ke):
        """What should we do next? → deterministic recommendation."""
        eng = DecisionEngine(ke)
        response = eng.handle("What should we do next?")
        assert "Recommendation" in response
        assert len(response) > 0

    def test_scenario_2_can_we_close(self, ke):
        """Can we close Genesis-036? → yes/no with reasons."""
        eng = DecisionEngine(ke)
        response = eng.handle("Can we close Genesis-036?")
        assert "036" in response
        assert "Recommendation" in response

    def test_scenario_3_why_cant_we_close(self, ke):
        """Why can't we close it? → explains blockers/prerequisites."""
        eng = DecisionEngine(ke)
        response = eng.handle("Why can't we close it?")
        assert "Recommendation" in response

    def test_scenario_4_is_anything_blocking(self, ke):
        """Is anything blocking us? → reports blockers."""
        eng = DecisionEngine(ke)
        response = eng.handle("Is anything blocking us?")
        assert response  # non-empty

    def test_scenario_4_with_blocker(self, ke):
        """With an active blocker → blocker appears in response."""
        from core.progress.store import ProgressStore
        from core.progress.models import ProgressState
        ps = ProgressStore(ke)
        ps.set_state("genesis", "036", "Genesis-036",
                     ProgressState.BLOCKED, blocker="desktop validation")

        eng = DecisionEngine(ke)
        response = eng.handle("Is anything blocking us?")
        assert "desktop validation" in response.lower()

    def test_can_we_close_yes_when_all_green(self, ke):
        """When all checks pass → can close."""
        from core.engineering.lifecycle.store import LifecycleStore
        from core.engineering.evidence.store import EvidenceStore
        import json

        # Set up lifecycle
        lc = LifecycleStore(ke)
        lc.open_genesis("036")

        # Set up evidence
        ev = EvidenceStore(ke)
        ev.initialise("036")
        ev.set_test_results("036", passed=3703, skipped=33, failed=0)
        ev.set_desktop_validation("036", "passed", ["All scenarios passed"])

        eng = DecisionEngine(ke)
        result = eng.evaluate("036")
        assert result.ready_to_close is True

    def test_cannot_close_with_failing_tests(self, ke):
        """Failing tests → cannot close."""
        from core.engineering.lifecycle.store import LifecycleStore
        from core.engineering.evidence.store import EvidenceStore

        lc = LifecycleStore(ke)
        lc.open_genesis("036")
        ev = EvidenceStore(ke)
        ev.initialise("036")
        ev.set_test_results("036", passed=100, skipped=0, failed=5)
        ev.set_desktop_validation("036", "passed", [])

        eng = DecisionEngine(ke)
        result = eng.evaluate("036")
        assert result.ready_to_close is False
        assert result.severity == DecisionSeverity.CRITICAL

    def test_no_ai_calls(self, ke):
        eng = DecisionEngine(ke)
        assert not hasattr(eng, "_ai")
        assert not hasattr(eng, "ai")
