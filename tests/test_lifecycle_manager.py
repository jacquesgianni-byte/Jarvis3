"""
Tests — Engineering Lifecycle Store and Manager
Genesis-034 Sprint-001
"""

import pytest
from core.engineering.lifecycle.models import GenesisLifecycleStatus
from core.engineering.lifecycle.store import LifecycleStore
from core.engineering.lifecycle.manager import LifecycleManager


# ── In-memory KE stub ─────────────────────────────────────────────────────────

class _MemoryStore:
    def __init__(self):
        self._records: dict = {}

    def store_memory(self, subject, category, attribute, value, tags=None, **kwargs):
        from datetime import datetime, timezone
        from uuid import uuid4

        class Rec:
            pass

        key = f"{subject}::{attribute}"
        r = Rec()
        r.id = str(uuid4())
        r.subject = subject
        r.category = category
        r.attribute = attribute
        r.value = value
        r.tags = list(tags or [])
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


# ── LifecycleStore ─────────────────────────────────────────────────────────────

class TestLifecycleStore:
    def test_open_genesis_returns_record(self, ke):
        store = LifecycleStore(ke)
        record = store.open_genesis("034")
        assert record.genesis == "034"
        assert record.status == GenesisLifecycleStatus.ACTIVE
        assert record.opened_at != ""

    def test_open_genesis_retrievable(self, ke):
        store = LifecycleStore(ke)
        store.open_genesis("034")
        retrieved = store.get("034")
        assert retrieved is not None
        assert retrieved.status == GenesisLifecycleStatus.ACTIVE

    def test_close_genesis_returns_record(self, ke):
        store = LifecycleStore(ke)
        store.open_genesis("034")
        record = store.close_genesis("034")
        assert record.status == GenesisLifecycleStatus.CLOSED
        assert record.closed_at != ""

    def test_close_genesis_retrievable(self, ke):
        store = LifecycleStore(ke)
        store.open_genesis("034")
        store.close_genesis("034")
        retrieved = store.get("034")
        assert retrieved.status == GenesisLifecycleStatus.CLOSED

    def test_active_genesis_returns_open(self, ke):
        store = LifecycleStore(ke)
        store.open_genesis("034")
        active = store.active_genesis()
        assert active is not None
        assert active.genesis == "034"

    def test_active_genesis_none_when_empty(self, ke):
        store = LifecycleStore(ke)
        assert store.active_genesis() is None

    def test_active_genesis_none_after_close(self, ke):
        store = LifecycleStore(ke)
        store.open_genesis("034")
        store.close_genesis("034")
        assert store.active_genesis() is None

    def test_get_returns_none_for_unknown(self, ke):
        store = LifecycleStore(ke)
        assert store.get("099") is None

    def test_open_preserves_opened_at_through_close(self, ke):
        store = LifecycleStore(ke)
        opened = store.open_genesis("034")
        closed = store.close_genesis("034")
        assert closed.opened_at == opened.opened_at


# ── LifecycleManager ──────────────────────────────────────────────────────────

class TestLifecycleManagerOpen:
    def test_can_handle_open(self, ke):
        mgr = LifecycleManager(ke)
        assert mgr.can_handle("Open Genesis-034.") is True

    def test_can_handle_close(self, ke):
        mgr = LifecycleManager(ke)
        assert mgr.can_handle("Close Genesis-034.") is True

    def test_cannot_handle_unrelated(self, ke):
        mgr = LifecycleManager(ke)
        assert mgr.can_handle("What is the weather?") is False

    def test_open_genesis_response_contains_number(self, ke):
        mgr = LifecycleManager(ke)
        response = mgr.handle("Open Genesis-034.")
        assert "034" in response

    def test_open_genesis_sets_active(self, ke):
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        active = mgr._store.active_genesis()
        assert active is not None
        assert active.genesis == "034"

    def test_open_already_active_returns_message(self, ke):
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        response = mgr.handle("Open Genesis-034.")
        assert "already active" in response.lower()

    def test_open_different_while_active_blocks(self, ke):
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        response = mgr.handle("Open Genesis-035.")
        assert "034" in response   # warns about active genesis
        assert "close" in response.lower()

    def test_unknown_utterance_returns_empty(self, ke):
        mgr = LifecycleManager(ke)
        response = mgr.handle("What is the weather?")
        assert response == ""


class TestLifecycleManagerClose:
    def _make_fake_coordinator(self, success=True):
        """Minimal WorkerCoordinator stub."""
        class FakeResult:
            def __init__(self, success):
                self.success = success
                self.error = "" if success else "Review failed"
                self.data = {
                    "results": {
                        "engineering_review_worker": {
                            "genesis": "034",
                            "json_path": "engineering_reviews/genesis_034_sprint_001_review.json",
                            "md_path":   "engineering_reviews/genesis_034_sprint_001_report.md",
                            "markdown":  "# Genesis 034 Review\n...",
                        }
                    }
                }

        class FakeCoordinator:
            def __init__(self, success):
                self._success = success
            def run(self, task):
                return FakeResult(self._success)

        class FakePlanner:
            def capabilities_for(self, request):
                return ["run_engineering_review"]

        return FakeCoordinator(success), FakePlanner()

    def test_close_genesis_success(self, ke):
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        coord, planner = self._make_fake_coordinator(success=True)
        response = mgr.handle("Close Genesis-034.", coord, planner)
        assert "034" in response
        assert "closed" in response.lower() or "successfully" in response.lower()

    def test_close_genesis_marks_closed(self, ke):
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        coord, planner = self._make_fake_coordinator(success=True)
        mgr.handle("Close Genesis-034.", coord, planner)
        record = mgr._store.get("034")
        assert record.status == GenesisLifecycleStatus.CLOSED

    def test_close_already_closed_returns_message(self, ke):
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        coord, planner = self._make_fake_coordinator(success=True)
        mgr.handle("Close Genesis-034.", coord, planner)
        response = mgr.handle("Close Genesis-034.", coord, planner)
        assert "already closed" in response.lower()

    def test_close_failed_review_keeps_open(self, ke):
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        coord, planner = self._make_fake_coordinator(success=False)
        response = mgr.handle("Close Genesis-034.", coord, planner)
        assert "failed" in response.lower()
        record = mgr._store.get("034")
        assert record is None or record.status == GenesisLifecycleStatus.ACTIVE

    def test_close_response_mentions_next_genesis(self, ke):
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        coord, planner = self._make_fake_coordinator(success=True)
        response = mgr.handle("Close Genesis-034.", coord, planner)
        assert "035" in response

    def test_close_response_mentions_report_paths(self, ke):
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        coord, planner = self._make_fake_coordinator(success=True)
        response = mgr.handle("Close Genesis-034.", coord, planner)
        assert "engineering_reviews" in response

    def test_no_active_genesis_can_still_close(self, ke):
        """Closing a genesis that was never explicitly opened still works."""
        mgr = LifecycleManager(ke)
        coord, planner = self._make_fake_coordinator(success=True)
        response = mgr.handle("Close Genesis-034.", coord, planner)
        assert "034" in response


# ── Desktop validation scenarios ──────────────────────────────────────────────

class TestDesktopScenarios:
    def _coord_and_planner(self, success=True):
        class FakeResult:
            def __init__(self, s):
                self.success = s
                self.error = "" if s else "error"
                self.data = {"results": {"engineering_review_worker": {
                    "genesis": "034", "json_path": "reviews/g034.json",
                    "md_path": "reviews/g034.md", "markdown": "# Review"}}}

        class FakeCoord:
            def __init__(self, s): self._s = s
            def run(self, t): return FakeResult(self._s)

        class FakePlanner:
            def capabilities_for(self, r): return ["run_engineering_review"]

        return FakeCoord(success), FakePlanner()

    def test_scenario_1_open_genesis(self):
        """Open Genesis-034 → Genesis becomes active."""
        ke = _MemoryStore()
        mgr = LifecycleManager(ke)
        response = mgr.handle("Open Genesis-034.")
        assert "034" in response
        assert mgr._store.active_genesis() is not None

    def test_scenario_2_close_genesis(self):
        """Close Genesis-034 → review runs, reports saved, Genesis marked CLOSED."""
        ke = _MemoryStore()
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        coord, planner = self._coord_and_planner(success=True)
        response = mgr.handle("Close Genesis-034.", coord, planner)
        assert "034" in response
        assert mgr._store.get("034").status == GenesisLifecycleStatus.CLOSED

    def test_scenario_3_already_closed(self):
        """Attempt to close an already closed Genesis → graceful message."""
        ke = _MemoryStore()
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        coord, planner = self._coord_and_planner(success=True)
        mgr.handle("Close Genesis-034.", coord, planner)
        response = mgr.handle("Close Genesis-034.", coord, planner)
        assert "already closed" in response.lower()

    def test_scenario_4_open_while_another_active(self):
        """Open a Genesis while another is active → request confirmation."""
        ke = _MemoryStore()
        mgr = LifecycleManager(ke)
        mgr.handle("Open Genesis-034.")
        response = mgr.handle("Open Genesis-035.")
        assert "034" in response
        assert "close" in response.lower()
