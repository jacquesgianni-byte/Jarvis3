"""
Genesis-021 Sprint-006 — Worker Context Tests
Completely self-contained. No dependency on other test files.

Coverage:
  - ContextEntry: valid, expired, age_seconds, TTL=0 never expires
  - WorkerContext: store, get, has — basic operations
  - WorkerContext: TTL expiry — expired entries removed on get/has
  - WorkerContext: TTL=0 never expires
  - WorkerContext: deterministic key generation (same payload → same key)
  - WorkerContext: invalidate(worker_name) removes correct entries
  - WorkerContext: invalidate_all() clears everything
  - WorkerContext: set_shared, get_shared, has_shared
  - WorkerContext: get_data with and without payload
  - WorkerContext: entry_count, valid_entry_count
  - WorkerContext: summary() dict
  - WorkerCoordinator: context attribute exposed
  - WorkerCoordinator: context hit skips re-execution
  - WorkerCoordinator: result stored in context on success
  - WorkerCoordinator: failed result NOT stored in context
  - WorkerCoordinator: shared data accessible after workflow
  - Integration: real workflow uses context
  - Workers remain unaware of context
  - Backwards compatibility
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.workers.worker_context import WorkerContext, ContextEntry, DEFAULT_TTL
from core.workers.coordinator import WorkerCoordinator
from core.workers.manager import WorkerManager
from core.workers.base import Worker
from core.workers.models import WorkerTask, WorkerResult, WorkerStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(worker_name="echo", success=True, data=None) -> WorkerResult:
    return WorkerResult(
        task_id="t-1",
        worker_name=worker_name,
        success=success,
        observations=("Obs.",),
        data=data or {"key": "value"},
        error="" if success else "Error.",
    )


def make_context(ttl=DEFAULT_TTL) -> WorkerContext:
    return WorkerContext(default_ttl=ttl)


def make_payload(**kwargs) -> dict:
    return dict(kwargs) if kwargs else {"goal": "test"}


class EchoWorker(Worker):
    call_count = 0

    @property
    def name(self): return "echo"
    @property
    def description(self): return "Echoes."
    @property
    def capabilities(self): return ["echo_task"]
    def validate(self, task): return True
    def execute(self, task):
        EchoWorker.call_count += 1
        self._begin(task)
        return self._succeed(WorkerResult(
            task_id=task.task_id, worker_name=self.name,
            success=True, observations=("Echo.",),
            data={"executed": True},
        ))


class FailingWorker(Worker):
    @property
    def name(self): return "failing"
    @property
    def description(self): return "Fails."
    @property
    def capabilities(self): return ["fail_task"]
    def validate(self, task): return True
    def execute(self, task):
        self._begin(task)
        return self._fail(task.task_id, "Failure.")


def make_coordinator(*workers, **workflow_kwargs) -> WorkerCoordinator:
    m = WorkerManager()
    for w in workers:
        m.register(w)
    c = WorkerCoordinator(m)
    for task_type, names in workflow_kwargs.items():
        c.register_workflow(task_type, names)
    return c


# ===========================================================================
# 1. CONTEXT ENTRY
# ===========================================================================

class TestContextEntry:

    def test_fresh_entry_is_valid(self):
        entry = ContextEntry(result=make_result(), ttl_seconds=300)
        assert entry.is_valid()

    def test_zero_ttl_never_expires(self):
        entry = ContextEntry(
            result=make_result(),
            stored_at=datetime.now(UTC) - timedelta(days=365),
            ttl_seconds=0,
        )
        assert entry.is_valid()

    def test_expired_entry_invalid(self):
        entry = ContextEntry(
            result=make_result(),
            stored_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
        )
        assert not entry.is_valid()

    def test_expiry_with_injected_time(self):
        now = datetime.now(UTC)
        entry = ContextEntry(result=make_result(), stored_at=now, ttl_seconds=60)
        assert not entry.is_valid(now=now + timedelta(seconds=61))
        assert entry.is_valid(now=now + timedelta(seconds=59))

    def test_age_seconds(self):
        now = datetime.now(UTC)
        past = now - timedelta(seconds=30)
        entry = ContextEntry(result=make_result(), stored_at=past, ttl_seconds=300)
        assert entry.age_seconds(now=now) == pytest.approx(30.0, abs=1.0)

    def test_hits_starts_at_zero(self):
        assert ContextEntry(result=make_result()).hits == 0


# ===========================================================================
# 2. WORKER CONTEXT — basic store/get/has
# ===========================================================================

class TestWorkerContextBasic:

    def test_store_and_get(self):
        ctx = make_context()
        result = make_result("echo")
        ctx.store("echo", make_payload(), result)
        retrieved = ctx.get("echo", make_payload())
        assert retrieved is result

    def test_has_true_after_store(self):
        ctx = make_context()
        ctx.store("echo", make_payload(), make_result())
        assert ctx.has("echo", make_payload())

    def test_has_false_when_not_stored(self):
        ctx = make_context()
        assert not ctx.has("echo", make_payload())

    def test_get_returns_none_when_not_stored(self):
        ctx = make_context()
        assert ctx.get("echo", make_payload()) is None

    def test_different_payloads_different_entries(self):
        ctx = make_context()
        r1 = make_result("echo", data={"v": 1})
        r2 = make_result("echo", data={"v": 2})
        ctx.store("echo", {"goal": "A"}, r1)
        ctx.store("echo", {"goal": "B"}, r2)
        assert ctx.get("echo", {"goal": "A"}).data["v"] == 1
        assert ctx.get("echo", {"goal": "B"}).data["v"] == 2

    def test_different_workers_different_entries(self):
        ctx = make_context()
        payload = make_payload()
        r1 = make_result("echo")
        r2 = make_result("planning")
        ctx.store("echo", payload, r1)
        ctx.store("planning", payload, r2)
        assert ctx.get("echo", payload).worker_name == "echo"
        assert ctx.get("planning", payload).worker_name == "planning"

    def test_entry_count(self):
        ctx = make_context()
        ctx.store("echo", {"a": 1}, make_result())
        ctx.store("echo", {"b": 2}, make_result())
        ctx.store("planning", {"a": 1}, make_result())
        assert ctx.entry_count() == 3

    def test_hits_incremented_on_get(self):
        ctx = make_context()
        ctx.store("echo", make_payload(), make_result())
        ctx.get("echo", make_payload())
        ctx.get("echo", make_payload())
        entry = list(ctx._entries.values())[0]
        assert entry.hits == 2


# ===========================================================================
# 3. WORKER CONTEXT — TTL expiry
# ===========================================================================

class TestWorkerContextExpiry:

    def test_expired_entry_get_returns_none(self):
        ctx = make_context()
        result = make_result()
        # Store with past timestamp via direct entry manipulation
        from core.workers.worker_context import ContextEntry
        key = ctx._make_key("echo", make_payload())
        ctx._entries[key] = ContextEntry(
            result=result,
            stored_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
        )
        assert ctx.get("echo", make_payload()) is None

    def test_expired_entry_removed_on_get(self):
        ctx = make_context()
        from core.workers.worker_context import ContextEntry
        key = ctx._make_key("echo", make_payload())
        ctx._entries[key] = ContextEntry(
            result=make_result(),
            stored_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
        )
        ctx.get("echo", make_payload())
        assert ctx.entry_count() == 0

    def test_has_false_for_expired(self):
        ctx = make_context()
        from core.workers.worker_context import ContextEntry
        key = ctx._make_key("echo", make_payload())
        ctx._entries[key] = ContextEntry(
            result=make_result(),
            stored_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
        )
        assert not ctx.has("echo", make_payload())

    def test_zero_ttl_never_expires(self):
        ctx = WorkerContext(default_ttl=0)
        ctx.store("echo", make_payload(), make_result())
        assert ctx.has("echo", make_payload())

    def test_custom_ttl_per_store(self):
        ctx = make_context()
        ctx.store("echo", make_payload(), make_result(), ttl_seconds=0)
        # Should never expire
        assert ctx.has("echo", make_payload())

    def test_valid_entry_count(self):
        ctx = make_context()
        from core.workers.worker_context import ContextEntry
        ctx.store("echo", {"a": 1}, make_result())  # valid
        key = ctx._make_key("echo", {"b": 2})
        ctx._entries[key] = ContextEntry(
            result=make_result(),
            stored_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
        )  # expired
        assert ctx.valid_entry_count() == 1


# ===========================================================================
# 4. WORKER CONTEXT — deterministic key generation
# ===========================================================================

class TestWorkerContextKeys:

    def test_same_payload_same_key(self):
        k1 = WorkerContext._make_key("echo", {"goal": "test", "path": "/tmp"})
        k2 = WorkerContext._make_key("echo", {"path": "/tmp", "goal": "test"})
        assert k1 == k2  # order-independent

    def test_different_payload_different_key(self):
        k1 = WorkerContext._make_key("echo", {"goal": "A"})
        k2 = WorkerContext._make_key("echo", {"goal": "B"})
        assert k1 != k2

    def test_different_worker_different_key(self):
        k1 = WorkerContext._make_key("echo", {"goal": "test"})
        k2 = WorkerContext._make_key("planning", {"goal": "test"})
        assert k1 != k2

    def test_empty_payload_produces_key(self):
        k = WorkerContext._make_key("echo", {})
        assert k and len(k) > 0

    def test_key_starts_with_worker_name(self):
        k = WorkerContext._make_key("planning", {"goal": "test"})
        assert k.startswith("planning:")


# ===========================================================================
# 5. WORKER CONTEXT — invalidation
# ===========================================================================

class TestWorkerContextInvalidation:

    def test_invalidate_removes_worker_entries(self):
        ctx = make_context()
        ctx.store("echo", {"a": 1}, make_result())
        ctx.store("echo", {"b": 2}, make_result())
        ctx.store("planning", {"a": 1}, make_result())
        count = ctx.invalidate("echo")
        assert count == 2
        assert not ctx.has("echo", {"a": 1})
        assert ctx.has("planning", {"a": 1})

    def test_invalidate_unknown_worker_returns_zero(self):
        ctx = make_context()
        assert ctx.invalidate("nonexistent") == 0

    def test_invalidate_all_clears_entries(self):
        ctx = make_context()
        ctx.store("echo", make_payload(), make_result())
        ctx.store("planning", make_payload(), make_result())
        count = ctx.invalidate_all()
        assert count == 2
        assert ctx.entry_count() == 0

    def test_invalidate_all_clears_shared(self):
        ctx = make_context()
        ctx.set_shared("foo", "bar")
        ctx.invalidate_all()
        assert not ctx.has_shared("foo")


# ===========================================================================
# 6. WORKER CONTEXT — shared data
# ===========================================================================

class TestWorkerContextShared:

    def test_set_and_get_shared(self):
        ctx = make_context()
        ctx.set_shared("root_path", "/tmp/repo")
        assert ctx.get_shared("root_path") == "/tmp/repo"

    def test_get_shared_default(self):
        ctx = make_context()
        assert ctx.get_shared("missing", default="fallback") == "fallback"

    def test_get_shared_none_default(self):
        ctx = make_context()
        assert ctx.get_shared("missing") is None

    def test_has_shared_true(self):
        ctx = make_context()
        ctx.set_shared("key", "value")
        assert ctx.has_shared("key")

    def test_has_shared_false(self):
        ctx = make_context()
        assert not ctx.has_shared("nonexistent")

    def test_shared_data_persists(self):
        ctx = make_context()
        ctx.set_shared("count", 42)
        ctx.set_shared("name", "Jarvis")
        assert ctx.get_shared("count") == 42
        assert ctx.get_shared("name") == "Jarvis"


# ===========================================================================
# 7. WORKER CONTEXT — get_data
# ===========================================================================

class TestWorkerContextGetData:

    def test_get_data_with_payload(self):
        ctx = make_context()
        ctx.store("echo", make_payload(), make_result(data={"answer": 42}))
        data = ctx.get_data("echo", make_payload())
        assert data["answer"] == 42

    def test_get_data_without_payload(self):
        ctx = make_context()
        ctx.store("echo", {"a": 1}, make_result(data={"x": 99}))
        data = ctx.get_data("echo")
        assert data["x"] == 99

    def test_get_data_returns_empty_when_missing(self):
        ctx = make_context()
        assert ctx.get_data("echo") == {}

    def test_get_data_returns_empty_for_expired(self):
        ctx = make_context()
        from core.workers.worker_context import ContextEntry
        key = ctx._make_key("echo", make_payload())
        ctx._entries[key] = ContextEntry(
            result=make_result(data={"v": 1}),
            stored_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
        )
        assert ctx.get_data("echo", make_payload()) == {}


# ===========================================================================
# 8. WORKER CONTEXT — summary
# ===========================================================================

class TestWorkerContextSummary:

    def test_summary_is_dict(self):
        assert isinstance(make_context().summary(), dict)

    def test_summary_has_counts(self):
        ctx = make_context()
        ctx.store("echo", make_payload(), make_result())
        s = ctx.summary()
        assert s["total_entries"] == 1
        assert s["valid_entries"] == 1

    def test_summary_has_shared_keys(self):
        ctx = make_context()
        ctx.set_shared("foo", "bar")
        assert "foo" in ctx.summary()["shared_keys"]

    def test_summary_has_default_ttl(self):
        ctx = WorkerContext(default_ttl=120)
        assert ctx.summary()["default_ttl"] == 120


# ===========================================================================
# 9. COORDINATOR — context integration
# ===========================================================================

class TestCoordinatorContextIntegration:

    def setup_method(self):
        EchoWorker.call_count = 0

    def test_coordinator_has_context_attribute(self):
        c = WorkerCoordinator(WorkerManager())
        assert hasattr(c, "context")
        assert isinstance(c.context, WorkerContext)

    def test_successful_result_stored_in_context(self):
        c = make_coordinator(EchoWorker(), echo_task=["echo"])
        task = WorkerTask(task_type="echo_task", payload=make_payload())
        c.run(task)
        assert c.context.has("echo", make_payload())

    def test_context_hit_skips_execution(self):
        c = make_coordinator(EchoWorker(), echo_task=["echo"])
        task = WorkerTask(task_type="echo_task", payload=make_payload())

        # First run — executes worker
        c.run(task)
        count_after_first = EchoWorker.call_count

        # Second run — should use context, not re-execute
        c.run(task)
        assert EchoWorker.call_count == count_after_first

    def test_failed_result_not_stored_in_context(self):
        c = make_coordinator(FailingWorker(), fail_task=["failing"])
        task = WorkerTask(task_type="fail_task", payload=make_payload())
        c.run(task)
        assert not c.context.has("failing", make_payload())

    def test_context_invalidation_forces_re_execution(self):
        c = make_coordinator(EchoWorker(), echo_task=["echo"])
        task = WorkerTask(task_type="echo_task", payload=make_payload())
        c.run(task)
        count_after_first = EchoWorker.call_count

        c.context.invalidate("echo")
        c.run(task)
        assert EchoWorker.call_count > count_after_first

    def test_workers_unaware_of_context(self):
        """Worker.execute() receives a plain WorkerTask — no context reference."""
        import inspect
        sig = inspect.signature(EchoWorker.execute)
        params = list(sig.parameters.keys())
        assert "context" not in params
        assert "worker_context" not in params


# ===========================================================================
# 10. INTEGRATION — real workflow with context
# ===========================================================================

class TestWorkerContextRealWorkflow:

    def test_engineering_plan_stores_results_in_context(self):
        from core.workers.planning_worker import PlanningWorker
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(PlanningWorker())
        m.register(EngineeringWorker())
        c = WorkerCoordinator(m)
        task = WorkerTask(
            task_type="engineering_plan",
            payload={"goal": "Add a new feature.", "root_path": str(REPO_ROOT)}
        )
        result = c.run(task)
        assert result.success
        assert c.context.get_data("planning")
        assert c.context.get_data("engineering")

    def test_shared_data_accessible_after_workflow(self):
        from core.workers.planning_worker import PlanningWorker
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(PlanningWorker())
        m.register(EngineeringWorker())
        c = WorkerCoordinator(m)
        c.context.set_shared("session_id", "test-session-001")
        task = WorkerTask(
            task_type="engineering_plan",
            payload={"goal": "Fix the bug.", "root_path": str(REPO_ROOT)}
        )
        c.run(task)
        assert c.context.get_shared("session_id") == "test-session-001"


# ===========================================================================
# 11. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_coordinator_sprint005_tests_still_pass(self):
        """Coordinator public API unchanged."""
        m = WorkerManager()
        c = WorkerCoordinator(m)
        assert c.has_workflow("engineering_plan")
        assert c.has_workflow("plan_implementation")

    def test_worker_framework_unchanged(self):
        m = WorkerManager()
        assert m.worker_count() == 0

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_worker_context_importable(self):
        from core.workers.worker_context import WorkerContext
        assert WorkerContext is not None

    def test_default_ttl_is_300(self):
        assert DEFAULT_TTL == 300