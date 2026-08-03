"""
Tests — Executive Intelligence: Progress Engine
Genesis-035 Sprint-001
"""

import pytest
from core.progress.models import ProgressState, ProgressSummary, ProgressRecord
from core.progress.detector import ProgressDetector, ProgressCommandKind
from core.progress.store import ProgressStore
from core.progress.engine import ProgressEngine


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
        r.created_at = datetime.now(timezone.utc); r.updated_at = datetime.now(timezone.utc)
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
        if key in self._records: self._records[key].value = value
        return self._records.get(key)

    def list_memories(self, subject=None, limit=100, **kwargs):
        results = list(self._records.values())
        if subject: results = [r for r in results if r.subject == subject]
        return results[:limit]


@pytest.fixture()
def ke():
    return _MemoryStore()


# ── ProgressState ──────────────────────────────────────────────────────────────

class TestProgressState:
    def test_values(self):
        assert ProgressState.IN_PROGRESS.value == "in_progress"
        assert ProgressState.COMPLETED.value   == "completed"
        assert ProgressState.BLOCKED.value     == "blocked"
        assert ProgressState.WAITING.value     == "waiting"
        assert ProgressState.NOT_STARTED.value == "not_started"
        assert ProgressState.CANCELLED.value   == "cancelled"

    def test_is_terminal(self):
        assert ProgressState.COMPLETED.is_terminal is True
        assert ProgressState.CANCELLED.is_terminal is True
        assert ProgressState.IN_PROGRESS.is_terminal is False
        assert ProgressState.BLOCKED.is_terminal is False

    def test_is_open(self):
        assert ProgressState.IN_PROGRESS.is_open is True
        assert ProgressState.COMPLETED.is_open is False

    def test_label(self):
        assert ProgressState.IN_PROGRESS.label() == "In Progress"
        assert ProgressState.NOT_STARTED.label() == "Not Started"


# ── ProgressSummary ───────────────────────────────────────────────────────────

class TestProgressSummary:
    def test_to_text_contains_entity_name(self):
        s = ProgressSummary(
            entity_name="Genesis-035",
            entity_type="genesis",
            state=ProgressState.IN_PROGRESS,
        )
        assert "Genesis-035" in s.to_text()

    def test_to_text_contains_state(self):
        s = ProgressSummary(
            entity_name="Genesis-035",
            entity_type="genesis",
            state=ProgressState.BLOCKED,
            blocker="desktop validation",
        )
        text = s.to_text()
        assert "Blocked" in text
        assert "desktop validation" in text

    def test_to_text_contains_tasks(self):
        s = ProgressSummary(
            entity_name="Genesis-035",
            entity_type="genesis",
            state=ProgressState.IN_PROGRESS,
            completed_tasks=["Parser task", "Tests"],
            open_tasks=["Desktop validation"],
        )
        text = s.to_text()
        assert "Parser task" in text
        assert "Desktop validation" in text

    def test_to_text_contains_test_results(self):
        s = ProgressSummary(
            entity_name="Genesis-035",
            entity_type="genesis",
            state=ProgressState.IN_PROGRESS,
            test_passed=3641,
            test_failed=0,
        )
        assert "3641" in s.to_text()


# ── ProgressDetector ──────────────────────────────────────────────────────────

class TestProgressDetector:
    def setup_method(self):
        self.d = ProgressDetector()

    def test_genesis_in_progress(self):
        r = self.d.detect("Genesis-035 is in progress.")
        assert r is not None
        assert r.kind == ProgressCommandKind.UPDATE_STATE
        assert r.state == ProgressState.IN_PROGRESS
        assert "035" in r.subject

    def test_genesis_now_in_progress(self):
        r = self.d.detect("Genesis-035 is now in progress.")
        assert r is not None
        assert r.state == ProgressState.IN_PROGRESS

    def test_task_complete(self):
        r = self.d.detect("The parser task is complete.")
        assert r is not None
        assert r.kind == ProgressCommandKind.UPDATE_STATE
        assert r.state == ProgressState.COMPLETED
        assert "parser" in r.subject.lower()

    def test_genesis_blocked(self):
        r = self.d.detect("Genesis-035 is blocked waiting for desktop validation.")
        assert r is not None
        assert r.kind == ProgressCommandKind.UPDATE_STATE
        assert r.state == ProgressState.BLOCKED
        assert "desktop validation" in r.blocker.lower()

    def test_genesis_blocked_on(self):
        r = self.d.detect("Genesis-035 is blocked on CI pipeline.")
        assert r is not None
        assert r.state == ProgressState.BLOCKED

    def test_mark_as_complete(self):
        r = self.d.detect("Mark genesis-035 as complete.")
        assert r is not None
        assert r.state == ProgressState.COMPLETED

    def test_query_how_is_progressing(self):
        r = self.d.detect("How is Genesis-035 progressing?")
        assert r is not None
        assert r.kind == ProgressCommandKind.QUERY_PROGRESS
        assert "035" in r.subject

    def test_query_what_is_progress(self):
        r = self.d.detect("What is the progress on Genesis-035?")
        assert r is not None
        assert r.kind == ProgressCommandKind.QUERY_PROGRESS

    def test_query_status_of(self):
        r = self.d.detect("Status of Genesis-035?")
        assert r is not None
        assert r.kind == ProgressCommandKind.QUERY_PROGRESS

    def test_no_detection_for_unrelated(self):
        assert self.d.detect("What is the weather?") is None
        assert self.d.detect("Hello Jarvis") is None
        assert self.d.detect("My goal is to release Jarvis") is None

    def test_genesis_completed(self):
        r = self.d.detect("Genesis-035 is completed.")
        assert r is not None
        assert r.state == ProgressState.COMPLETED

    def test_genesis_cancelled(self):
        r = self.d.detect("Genesis-035 is cancelled.")
        assert r is not None
        assert r.state == ProgressState.CANCELLED


# ── ProgressStore ─────────────────────────────────────────────────────────────

class TestProgressStore:
    def test_set_and_get_state(self, ke):
        store = ProgressStore(ke)
        store.set_state("genesis", "035", "Genesis-035", ProgressState.IN_PROGRESS)
        rec = store.get_state("genesis", "035")
        assert rec is not None
        assert rec.state == ProgressState.IN_PROGRESS

    def test_update_state(self, ke):
        store = ProgressStore(ke)
        store.set_state("genesis", "035", "Genesis-035", ProgressState.IN_PROGRESS)
        store.set_state("genesis", "035", "Genesis-035", ProgressState.COMPLETED)
        rec = store.get_state("genesis", "035")
        assert rec.state == ProgressState.COMPLETED

    def test_blocker_stored(self, ke):
        store = ProgressStore(ke)
        store.set_state("genesis", "035", "Genesis-035", ProgressState.BLOCKED,
                        blocker="desktop validation")
        rec = store.get_state("genesis", "035")
        assert "desktop validation" in rec.blocker

    def test_get_state_none_for_unknown(self, ke):
        store = ProgressStore(ke)
        assert store.get_state("genesis", "099") is None

    def test_all_records(self, ke):
        store = ProgressStore(ke)
        store.set_state("genesis", "035", "Genesis-035", ProgressState.IN_PROGRESS)
        store.set_state("task", "parser", "Parser", ProgressState.COMPLETED)
        all_r = store.all_records()
        assert len(all_r) == 2

    def test_records_by_state(self, ke):
        store = ProgressStore(ke)
        store.set_state("genesis", "035", "Genesis-035", ProgressState.IN_PROGRESS)
        store.set_state("genesis", "034", "Genesis-034", ProgressState.COMPLETED)
        in_progress = store.records_by_state(ProgressState.IN_PROGRESS)
        assert len(in_progress) == 1
        assert "035" in in_progress[0].entity_id


# ── ProgressEngine ────────────────────────────────────────────────────────────

class TestProgressEngine:
    def test_can_handle_update(self, ke):
        eng = ProgressEngine(ke)
        assert eng.can_handle("Genesis-035 is in progress.") is True

    def test_can_handle_query(self, ke):
        eng = ProgressEngine(ke)
        assert eng.can_handle("How is Genesis-035 progressing?") is True

    def test_cannot_handle_unrelated(self, ke):
        eng = ProgressEngine(ke)
        assert eng.can_handle("What is the weather?") is False

    def test_scenario_1_genesis_in_progress(self, ke):
        """Genesis-035 is in progress → state updated."""
        eng = ProgressEngine(ke)
        response = eng.handle("Genesis-035 is in progress.")
        assert "035" in response or "in progress" in response.lower()
        rec = eng._store.get_state("genesis", "035")
        assert rec.state == ProgressState.IN_PROGRESS

    def test_scenario_2_task_complete(self, ke):
        """The parser task is complete → task marked completed."""
        eng = ProgressEngine(ke)
        response = eng.handle("The parser task is complete.")
        assert "complete" in response.lower() or "parser" in response.lower()
        rec = eng._store.get_state("task", "parser")
        assert rec is not None
        assert rec.state == ProgressState.COMPLETED

    def test_scenario_3_genesis_blocked(self, ke):
        """Genesis-035 is blocked waiting for desktop validation."""
        eng = ProgressEngine(ke)
        response = eng.handle("Genesis-035 is blocked waiting for desktop validation.")
        assert "blocked" in response.lower()
        rec = eng._store.get_state("genesis", "035")
        assert rec.state == ProgressState.BLOCKED
        assert "desktop validation" in rec.blocker.lower()

    def test_scenario_4_progress_query(self, ke):
        """How is Genesis-035 progressing? → deterministic summary."""
        eng = ProgressEngine(ke)
        eng.handle("Genesis-035 is in progress.")
        response = eng.handle("How is Genesis-035 progressing?")
        assert "Genesis-035" in response
        assert "In Progress" in response or "in progress" in response.lower()

    def test_query_includes_blocker(self, ke):
        eng = ProgressEngine(ke)
        eng.handle("Genesis-035 is blocked waiting for desktop validation.")
        response = eng.handle("How is Genesis-035 progressing?")
        assert "desktop validation" in response.lower()

    def test_no_ai_calls(self, ke):
        eng = ProgressEngine(ke)
        assert not hasattr(eng, "_ai")
        assert not hasattr(eng, "ai")
