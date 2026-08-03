"""
Tests — Executive Intelligence: Dashboard Engine
Genesis-035 Sprint-002
"""

import pytest
from core.executive.models import ExecutiveSection, ExecutiveDashboard
from core.executive.engine import ExecutiveDashboardEngine


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


# ── ExecutiveSection ──────────────────────────────────────────────────────────

class TestExecutiveSection:
    def test_to_text_with_lines(self):
        s = ExecutiveSection(title="GOAL", lines=["Goal: Jarvis 1.0", "Status: Active"])
        text = s.to_text()
        assert "GOAL" in text
        assert "Jarvis 1.0" in text

    def test_to_text_empty(self):
        s = ExecutiveSection(title="GOAL", empty=True)
        text = s.to_text()
        assert "GOAL" in text
        assert "none" in text.lower()


# ── ExecutiveDashboard ────────────────────────────────────────────────────────

class TestExecutiveDashboard:
    def test_to_text_contains_header(self):
        d = ExecutiveDashboard(sections=[], recommendation="Continue.")
        text = d.to_text()
        assert "ENGINEERING BRIEFING" in text

    def test_to_text_contains_recommendation(self):
        d = ExecutiveDashboard(sections=[], recommendation="Fix failing tests.")
        text = d.to_text()
        assert "Fix failing tests" in text

    def test_to_text_contains_all_sections(self):
        sections = [
            ExecutiveSection(title="GOAL",     lines=["Goal: Jarvis 1.0"]),
            ExecutiveSection(title="PROJECT",  lines=["Project: Genesis-035"]),
            ExecutiveSection(title="QUALITY",  lines=["Tests: ✅ 3676 passed"]),
        ]
        d = ExecutiveDashboard(sections=sections, recommendation="Continue.")
        text = d.to_text()
        assert "GOAL" in text
        assert "PROJECT" in text
        assert "QUALITY" in text

    def test_to_text_contains_generated_at(self):
        d = ExecutiveDashboard(
            sections=[],
            recommendation="Continue.",
            generated_at="2026-08-03T12:00:00+00:00",
        )
        text = d.to_text()
        assert "2026-08-03" in text


# ── ExecutiveDashboardEngine ──────────────────────────────────────────────────

class TestCanHandle:
    def test_engineering_briefing(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        assert eng.can_handle("Engineering briefing.") is True
        assert eng.can_handle("engineering briefing") is True

    def test_executive_dashboard(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        assert eng.can_handle("Executive dashboard.") is True

    def test_project_status(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        assert eng.can_handle("Project status.") is True

    def test_dashboard(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        assert eng.can_handle("Dashboard") is True

    def test_briefing(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        assert eng.can_handle("Briefing") is True

    def test_unrelated(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        assert eng.can_handle("What is the weather?") is False
        assert eng.can_handle("My goal is to release Jarvis") is False


class TestBuild:
    def test_returns_executive_dashboard(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        d = eng.build()
        assert isinstance(d, ExecutiveDashboard)

    def test_has_six_sections(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        d = eng.build()
        assert len(d.sections) == 6

    def test_has_recommendation(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        d = eng.build()
        assert d.recommendation != ""

    def test_has_generated_at(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        d = eng.build()
        assert d.generated_at != ""

    def test_handle_returns_non_empty_string(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        text = eng.handle("Engineering briefing.")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_handle_contains_header(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        text = eng.handle("Engineering briefing.")
        assert "ENGINEERING BRIEFING" in text

    def test_all_three_triggers_same_output_shape(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        t1 = eng.handle("Engineering briefing.")
        t2 = eng.handle("Executive dashboard.")
        t3 = eng.handle("Project status.")
        # All should contain the header
        for t in [t1, t2, t3]:
            assert "ENGINEERING BRIEFING" in t


class TestRecommendations:
    def _setup_blocker(self, ke):
        from core.progress.store import ProgressStore
        from core.progress.models import ProgressState
        store = ProgressStore(ke)
        store.set_state("genesis", "035", "Genesis-035",
                        ProgressState.BLOCKED, blocker="desktop validation")

    def _setup_in_progress(self, ke):
        from core.progress.store import ProgressStore
        from core.progress.models import ProgressState
        store = ProgressStore(ke)
        store.set_state("genesis", "035", "Genesis-035", ProgressState.IN_PROGRESS)

    def test_blocker_appears_in_recommendation(self, ke):
        self._setup_blocker(ke)
        eng = ExecutiveDashboardEngine(ke)
        d = eng.build()
        assert "desktop validation" in d.recommendation.lower() or \
               "blocker" in d.recommendation.lower()

    def test_blocker_appears_in_dashboard_text(self, ke):
        """Scenario 4: blocker introduced → appears in briefing."""
        self._setup_blocker(ke)
        eng = ExecutiveDashboardEngine(ke)
        text = eng.handle("Engineering briefing.")
        assert "desktop validation" in text.lower()
        assert "Blocked" in text or "blocker" in text.lower()

    def test_in_progress_recommendation(self, ke):
        self._setup_in_progress(ke)
        eng = ExecutiveDashboardEngine(ke)
        d = eng.build()
        assert "Continue" in d.recommendation or "Genesis" in d.recommendation

    def test_empty_state_recommendation(self, ke):
        eng = ExecutiveDashboardEngine(ke)
        d = eng.build()
        # Should suggest setting status
        assert d.recommendation != ""


# ── Desktop validation scenarios ──────────────────────────────────────────────

class TestDesktopScenarios:
    def test_scenario_1_engineering_briefing(self, ke):
        """Engineering briefing. → complete dashboard."""
        eng  = ExecutiveDashboardEngine(ke)
        text = eng.handle("Engineering briefing.")
        assert "ENGINEERING BRIEFING" in text
        assert len(text) > 100

    def test_scenario_2_executive_dashboard(self, ke):
        """Executive dashboard. → same dashboard."""
        eng  = ExecutiveDashboardEngine(ke)
        text = eng.handle("Executive dashboard.")
        assert "ENGINEERING BRIEFING" in text

    def test_scenario_3_project_status(self, ke):
        """Project status. → same dashboard."""
        eng  = ExecutiveDashboardEngine(ke)
        text = eng.handle("Project status.")
        assert "ENGINEERING BRIEFING" in text

    def test_scenario_4_blocker_in_briefing(self, ke):
        """Blocker introduced → appears in dashboard + recommendation updates."""
        from core.progress.store import ProgressStore
        from core.progress.models import ProgressState
        store = ProgressStore(ke)
        store.set_state("genesis", "035", "Genesis-035",
                        ProgressState.BLOCKED, blocker="desktop validation")

        eng  = ExecutiveDashboardEngine(ke)
        text = eng.handle("Engineering briefing.")

        assert "desktop validation" in text.lower()
        # Recommendation should mention the blocker
        d = eng.build()
        assert "desktop validation" in d.recommendation.lower() or \
               "blocker" in d.recommendation.lower()
