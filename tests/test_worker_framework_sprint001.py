"""
Genesis-021 Sprint-001 — Worker Framework Tests
Completely self-contained. No dependency on other test files.

Coverage:
  - WorkerStatus: all statuses, labels, is_busy, is_available
  - WorkerTask: immutable, fields, str, failure constructor
  - WorkerResult: immutable, fields, str, failure()
  - Worker (base): abstract interface, _begin/_succeed/_fail helpers
  - Worker: cancel(), reset(), status(), is_available, last_result
  - WorkerRegistry: register, unregister, get, find, has, count
  - WorkerRegistry: duplicate registration raises
  - WorkerRegistry: missing lookup raises / returns None
  - WorkerRegistry: workers_for(), all_workers(), names()
  - WorkerRegistry: summary(), clear()
  - WorkerManager: register, unregister, execute, execute_for_type
  - WorkerManager: cancel, status, get_worker, available_workers
  - WorkerManager: workers_for, all_workers, has_worker, worker_count
  - WorkerManager: duplicate registration raises
  - WorkerManager: missing worker raises
  - WorkerManager: busy worker raises on execute
  - WorkerManager: invalid task raises
  - WorkerManager: execution exception → failure result
  - WorkerManager: summary()
  - Isolation: no imports from routing, AI, memory, tools
  - Backwards compatibility: existing Jarvis files unaffected
"""

import sys
from datetime import UTC, datetime
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.workers.models import WorkerStatus, WorkerTask, WorkerResult
from core.workers.base import Worker
from core.workers.registry import WorkerRegistry
from core.workers.manager import WorkerManager
from core.workers.exceptions import (
    WorkerError,
    WorkerNotFoundError,
    WorkerAlreadyRegisteredError,
    WorkerNotReadyError,
    WorkerCancelledError,
    InvalidTaskError,
)


# ---------------------------------------------------------------------------
# Concrete Worker implementations for testing
# ---------------------------------------------------------------------------

class EchoWorker(Worker):
    """Simple worker that echoes task payload as an observation."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes the task payload as an observation."

    @property
    def capabilities(self) -> list[str]:
        return ["echo", "test"]

    def validate(self, task: WorkerTask) -> bool:
        return bool(task.task_type)

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        observation = f"Received task: {task.task_type}"
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=self.name,
            success=True,
            observations=(observation,),
            recommendations=("No action required.",),
            requires_approval=False,
        )
        return self._succeed(result)


class FailingWorker(Worker):
    """Worker that always fails."""

    @property
    def name(self) -> str:
        return "failing"

    @property
    def description(self) -> str:
        return "Always fails."

    @property
    def capabilities(self) -> list[str]:
        return ["fail_task"]

    def validate(self, task: WorkerTask) -> bool:
        return True

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        return self._fail(task.task_id, "Intentional failure.")


class RaisingWorker(Worker):
    """Worker that raises an exception during execute."""

    @property
    def name(self) -> str:
        return "raising"

    @property
    def description(self) -> str:
        return "Raises an exception."

    @property
    def capabilities(self) -> list[str]:
        return ["raise_task"]

    def validate(self, task: WorkerTask) -> bool:
        return True

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        raise RuntimeError("Unexpected error in worker.")


class StrictWorker(Worker):
    """Worker that rejects tasks without 'required_key' in payload."""

    @property
    def name(self) -> str:
        return "strict"

    @property
    def description(self) -> str:
        return "Requires required_key in payload."

    @property
    def capabilities(self) -> list[str]:
        return ["strict_task"]

    def validate(self, task: WorkerTask) -> bool:
        return "required_key" in task.payload

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=self.name,
            success=True,
            observations=("Key found.",),
            requires_approval=True,
        )
        return self._succeed(result)


class SlowCancellableWorker(Worker):
    """Worker that checks _cancelled flag during execution."""

    @property
    def name(self) -> str:
        return "cancellable"

    @property
    def description(self) -> str:
        return "Can be cancelled."

    @property
    def capabilities(self) -> list[str]:
        return ["long_task"]

    def validate(self, task: WorkerTask) -> bool:
        return True

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        # Simulate checking cancellation
        if self._cancelled:
            return self._fail(task.task_id, "Cancelled before start.")
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=self.name,
            success=True,
            observations=("Completed.",),
        )
        return self._succeed(result)


def make_task(task_type="echo", payload=None, **kwargs) -> WorkerTask:
    return WorkerTask(task_type=task_type, payload=payload or {}, **kwargs)


def make_manager() -> WorkerManager:
    return WorkerManager()


# ===========================================================================
# 1. EXCEPTIONS
# ===========================================================================

class TestExceptions:

    def test_worker_error_is_base(self):
        assert issubclass(WorkerNotFoundError, WorkerError)
        assert issubclass(WorkerAlreadyRegisteredError, WorkerError)
        assert issubclass(WorkerNotReadyError, WorkerError)
        assert issubclass(WorkerCancelledError, WorkerError)
        assert issubclass(InvalidTaskError, WorkerError)

    def test_catch_by_base_class(self):
        with pytest.raises(WorkerError):
            raise WorkerNotFoundError("test")

    def test_all_exceptions_are_exceptions(self):
        for exc_class in [WorkerNotFoundError, WorkerAlreadyRegisteredError,
                          WorkerNotReadyError, WorkerCancelledError, InvalidTaskError]:
            with pytest.raises(exc_class):
                raise exc_class("test")


# ===========================================================================
# 2. WORKER STATUS
# ===========================================================================

class TestWorkerStatus:

    def test_all_statuses_exist(self):
        for name in ["IDLE", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]:
            assert hasattr(WorkerStatus, name)

    def test_values_unique(self):
        values = [s.value for s in WorkerStatus]
        assert len(values) == len(set(values))

    def test_label_human_readable(self):
        assert WorkerStatus.IDLE.label() == "Idle"
        assert WorkerStatus.RUNNING.label() == "Running"
        assert WorkerStatus.COMPLETED.label() == "Completed"

    def test_is_busy_only_running(self):
        assert WorkerStatus.RUNNING.is_busy
        assert not WorkerStatus.IDLE.is_busy
        assert not WorkerStatus.COMPLETED.is_busy

    def test_is_available(self):
        assert WorkerStatus.IDLE.is_available
        assert WorkerStatus.COMPLETED.is_available
        assert WorkerStatus.FAILED.is_available
        assert WorkerStatus.CANCELLED.is_available
        assert not WorkerStatus.RUNNING.is_available


# ===========================================================================
# 3. WORKER TASK
# ===========================================================================

class TestWorkerTask:

    def test_is_frozen(self):
        t = make_task()
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            t.task_type = "changed"

    def test_has_auto_id(self):
        t = make_task()
        assert t.task_id and len(t.task_id) > 0

    def test_two_tasks_different_ids(self):
        assert make_task().task_id != make_task().task_id

    def test_has_timestamp(self):
        assert isinstance(make_task().created_at, datetime)

    def test_default_requester(self):
        assert make_task().requester == "system"

    def test_default_priority(self):
        assert make_task().priority == 5

    def test_custom_payload(self):
        t = WorkerTask(task_type="test", payload={"key": "value"})
        assert t.payload["key"] == "value"

    def test_str_includes_task_type(self):
        t = make_task(task_type="analyse_code")
        assert "analyse_code" in str(t)

    def test_empty_payload_default(self):
        assert make_task().payload == {}


# ===========================================================================
# 4. WORKER RESULT
# ===========================================================================

class TestWorkerResult:

    def test_is_frozen(self):
        r = WorkerResult(task_id="t", worker_name="w", success=True)
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            r.success = False

    def test_has_timestamp(self):
        r = WorkerResult(task_id="t", worker_name="w", success=True)
        assert isinstance(r.completed_at, datetime)

    def test_default_requires_approval(self):
        r = WorkerResult(task_id="t", worker_name="w", success=True)
        assert r.requires_approval is True

    def test_observations_stored_as_tuple(self):
        r = WorkerResult(task_id="t", worker_name="w", success=True,
                         observations=("obs1", "obs2"))
        assert isinstance(r.observations, tuple)

    def test_recommendations_stored_as_tuple(self):
        r = WorkerResult(task_id="t", worker_name="w", success=True,
                         recommendations=("rec1",))
        assert isinstance(r.recommendations, tuple)

    def test_str_includes_worker_name(self):
        r = WorkerResult(task_id="t", worker_name="echo", success=True)
        assert "echo" in str(r)

    def test_str_shows_failed(self):
        r = WorkerResult(task_id="t", worker_name="w", success=False,
                         error="Something went wrong")
        assert "FAILED" in str(r)

    def test_failure_classmethod(self):
        r = WorkerResult.failure("t-id", "my_worker", "Error message")
        assert not r.success
        assert r.error == "Error message"
        assert r.task_id == "t-id"
        assert r.worker_name == "my_worker"
        assert r.requires_approval is False

    def test_empty_error_on_success(self):
        r = WorkerResult(task_id="t", worker_name="w", success=True)
        assert r.error == ""


# ===========================================================================
# 5. WORKER BASE — interface and lifecycle
# ===========================================================================

class TestWorkerBase:

    def test_worker_is_abstract(self):
        with pytest.raises(TypeError):
            Worker()  # cannot instantiate ABC

    def test_echo_worker_name(self):
        assert EchoWorker().name == "echo"

    def test_echo_worker_description(self):
        assert EchoWorker().description

    def test_echo_worker_capabilities(self):
        assert "echo" in EchoWorker().capabilities

    def test_echo_worker_starts_idle(self):
        assert EchoWorker().status() == WorkerStatus.IDLE

    def test_echo_worker_is_available(self):
        assert EchoWorker().is_available

    def test_echo_worker_last_result_none_initially(self):
        assert EchoWorker().last_result is None

    def test_echo_worker_execute(self):
        w = EchoWorker()
        task = make_task("echo")
        result = w.execute(task)
        assert result.success
        assert result.worker_name == "echo"
        assert result.task_id == task.task_id

    def test_echo_worker_status_completed_after_execute(self):
        w = EchoWorker()
        w.execute(make_task("echo"))
        assert w.status() == WorkerStatus.COMPLETED

    def test_echo_worker_last_result_after_execute(self):
        w = EchoWorker()
        task = make_task("echo")
        result = w.execute(task)
        assert w.last_result is result

    def test_echo_worker_validate_true(self):
        assert EchoWorker().validate(make_task("echo"))

    def test_failing_worker_returns_failure(self):
        w = FailingWorker()
        result = w.execute(make_task("fail_task"))
        assert not result.success
        assert result.error

    def test_failing_worker_status_failed(self):
        w = FailingWorker()
        w.execute(make_task("fail_task"))
        assert w.status() == WorkerStatus.FAILED

    def test_cancel_running_worker(self):
        w = EchoWorker()
        # Simulate RUNNING state
        w._status = WorkerStatus.RUNNING
        w.cancel()
        assert w.status() == WorkerStatus.CANCELLED

    def test_cancel_idle_worker_no_error(self):
        w = EchoWorker()
        w.cancel()  # should not raise
        assert w.status() == WorkerStatus.IDLE

    def test_reset_returns_to_idle(self):
        w = EchoWorker()
        w.execute(make_task("echo"))
        assert w.status() == WorkerStatus.COMPLETED
        w.reset()
        assert w.status() == WorkerStatus.IDLE

    def test_reset_clears_task(self):
        w = EchoWorker()
        w.execute(make_task("echo"))
        w.reset()
        assert w._current_task is None

    def test_begin_raises_when_running(self):
        w = EchoWorker()
        w._status = WorkerStatus.RUNNING
        with pytest.raises(WorkerNotReadyError):
            w._begin(make_task("echo"))

    def test_str_includes_name_and_status(self):
        w = EchoWorker()
        s = str(w)
        assert "echo" in s
        assert "Idle" in s


# ===========================================================================
# 6. WORKER REGISTRY
# ===========================================================================

class TestWorkerRegistry:

    def test_starts_empty(self):
        r = WorkerRegistry()
        assert r.count() == 0

    def test_register_worker(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        assert r.count() == 1

    def test_has_after_register(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        assert r.has("echo")

    def test_has_false_when_not_registered(self):
        assert not WorkerRegistry().has("echo")

    def test_get_returns_worker(self):
        r = WorkerRegistry()
        w = EchoWorker()
        r.register(w)
        assert r.get("echo") is w

    def test_get_raises_when_missing(self):
        with pytest.raises(WorkerNotFoundError):
            WorkerRegistry().get("nonexistent")

    def test_find_returns_worker(self):
        r = WorkerRegistry()
        w = EchoWorker()
        r.register(w)
        assert r.find("echo") is w

    def test_find_returns_none_when_missing(self):
        assert WorkerRegistry().find("nonexistent") is None

    def test_duplicate_registration_raises(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        with pytest.raises(WorkerAlreadyRegisteredError):
            r.register(EchoWorker())

    def test_unregister_removes_worker(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        r.unregister("echo")
        assert not r.has("echo")
        assert r.count() == 0

    def test_unregister_missing_raises(self):
        with pytest.raises(WorkerNotFoundError):
            WorkerRegistry().unregister("nonexistent")

    def test_workers_for_task_type(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        r.register(FailingWorker())
        workers = r.workers_for("echo")
        assert len(workers) == 1
        assert workers[0].name == "echo"

    def test_workers_for_unknown_type_empty(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        assert r.workers_for("nonexistent_type") == []

    def test_all_workers_returns_list(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        r.register(FailingWorker())
        assert len(r.all_workers()) == 2

    def test_names_returns_list(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        assert "echo" in r.names()

    def test_clear_removes_all(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        r.register(FailingWorker())
        r.clear()
        assert r.count() == 0

    def test_summary_dict(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        s = r.summary()
        assert s["count"] == 1
        assert len(s["workers"]) == 1
        assert s["workers"][0]["name"] == "echo"

    def test_register_after_unregister(self):
        r = WorkerRegistry()
        r.register(EchoWorker())
        r.unregister("echo")
        r.register(EchoWorker())  # should not raise
        assert r.has("echo")


# ===========================================================================
# 7. WORKER MANAGER
# ===========================================================================

class TestWorkerManager:

    def test_starts_empty(self):
        assert make_manager().worker_count() == 0

    def test_register_worker(self):
        m = make_manager()
        m.register(EchoWorker())
        assert m.worker_count() == 1

    def test_has_worker_true(self):
        m = make_manager()
        m.register(EchoWorker())
        assert m.has_worker("echo")

    def test_has_worker_false(self):
        assert not make_manager().has_worker("echo")

    def test_duplicate_registration_raises(self):
        m = make_manager()
        m.register(EchoWorker())
        with pytest.raises(WorkerAlreadyRegisteredError):
            m.register(EchoWorker())

    def test_unregister_removes_worker(self):
        m = make_manager()
        m.register(EchoWorker())
        m.unregister("echo")
        assert not m.has_worker("echo")

    def test_unregister_missing_raises(self):
        with pytest.raises(WorkerNotFoundError):
            make_manager().unregister("nonexistent")

    def test_get_worker_returns_instance(self):
        m = make_manager()
        w = EchoWorker()
        m.register(w)
        assert m.get_worker("echo") is w

    def test_get_worker_missing_raises(self):
        with pytest.raises(WorkerNotFoundError):
            make_manager().get_worker("nonexistent")

    def test_execute_returns_result(self):
        m = make_manager()
        m.register(EchoWorker())
        result = m.execute("echo", make_task("echo"))
        assert result.success
        assert result.worker_name == "echo"

    def test_execute_missing_worker_raises(self):
        with pytest.raises(WorkerNotFoundError):
            make_manager().execute("nonexistent", make_task("echo"))

    def test_execute_busy_worker_raises(self):
        m = make_manager()
        w = EchoWorker()
        w._status = WorkerStatus.RUNNING
        m.register(w)
        with pytest.raises(WorkerNotReadyError):
            m.execute("echo", make_task("echo"))

    def test_execute_invalid_task_raises(self):
        m = make_manager()
        m.register(StrictWorker())
        task = make_task("strict_task", payload={})  # missing required_key
        with pytest.raises(InvalidTaskError):
            m.execute("strict", task)

    def test_execute_valid_strict_task(self):
        m = make_manager()
        m.register(StrictWorker())
        task = make_task("strict_task", payload={"required_key": "value"})
        result = m.execute("strict", task)
        assert result.success

    def test_execute_exception_returns_failure(self):
        m = make_manager()
        m.register(RaisingWorker())
        result = m.execute("raising", make_task("raise_task"))
        assert not result.success
        assert result.error

    def test_execute_for_type(self):
        m = make_manager()
        m.register(EchoWorker())
        result = m.execute_for_type("echo", make_task("echo"))
        assert result.success

    def test_execute_for_type_no_worker_raises(self):
        with pytest.raises(WorkerNotFoundError):
            make_manager().execute_for_type("unknown_type", make_task("x"))

    def test_execute_for_type_all_busy_raises(self):
        m = make_manager()
        w = EchoWorker()
        w._status = WorkerStatus.RUNNING
        m.register(w)
        with pytest.raises(WorkerNotReadyError):
            m.execute_for_type("echo", make_task("echo"))

    def test_cancel_worker(self):
        m = make_manager()
        w = EchoWorker()
        w._status = WorkerStatus.RUNNING
        m.register(w)
        m.cancel("echo")
        assert m.status("echo") == WorkerStatus.CANCELLED

    def test_cancel_missing_raises(self):
        with pytest.raises(WorkerNotFoundError):
            make_manager().cancel("nonexistent")

    def test_status_returns_worker_status(self):
        m = make_manager()
        m.register(EchoWorker())
        assert m.status("echo") == WorkerStatus.IDLE

    def test_status_missing_raises(self):
        with pytest.raises(WorkerNotFoundError):
            make_manager().status("nonexistent")

    def test_available_workers_empty_initially(self):
        assert make_manager().available_workers() == []

    def test_available_workers_after_register(self):
        m = make_manager()
        m.register(EchoWorker())
        assert len(m.available_workers()) == 1

    def test_available_workers_excludes_running(self):
        m = make_manager()
        w = EchoWorker()
        w._status = WorkerStatus.RUNNING
        m.register(w)
        assert len(m.available_workers()) == 0

    def test_workers_for_task_type(self):
        m = make_manager()
        m.register(EchoWorker())
        m.register(FailingWorker())
        workers = m.workers_for("echo")
        assert len(workers) == 1
        assert workers[0].name == "echo"

    def test_all_workers_returns_all(self):
        m = make_manager()
        m.register(EchoWorker())
        m.register(FailingWorker())
        assert len(m.all_workers()) == 2

    def test_summary_dict(self):
        m = make_manager()
        m.register(EchoWorker())
        s = m.summary()
        assert s["worker_count"] == 1
        assert s["available"] == 1

    def test_worker_reset_after_completion_allows_reuse(self):
        m = make_manager()
        m.register(EchoWorker())
        m.execute("echo", make_task("echo"))
        # Worker is COMPLETED — still available
        result2 = m.execute("echo", make_task("echo"))
        assert result2.success


# ===========================================================================
# 8. ISOLATION
# ===========================================================================

class TestIsolation:

    def test_manager_does_not_import_router(self):
        import core.workers.manager as mod
        src = open(mod.__file__).read()
        assert "IntentRouter" not in src

    def test_manager_does_not_import_knowledge_engine(self):
        import core.workers.manager as mod
        src = open(mod.__file__).read()
        assert "KnowledgeEngine" not in src

    def test_base_does_not_import_ai(self):
        import core.workers.base as mod
        src = open(mod.__file__).read()
        assert "openai" not in src.lower()
        assert "anthropic" not in src.lower()

    def test_models_do_not_import_routing(self):
        import core.workers.models as mod
        src = open(mod.__file__).read()
        assert "from core.router" not in src

    def test_registry_does_not_import_tools(self):
        import core.workers.registry as mod
        src = open(mod.__file__).read()
        assert "ToolManager" not in src


# ===========================================================================
# 9. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        router = IntentRouter()
        assert router.detect("Hello Jarvis.") == Intent.GREETING

    def test_existing_session_context_unchanged(self):
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_project("Jarvis OS")
        assert s.active_project.value == "Jarvis OS"

    def test_existing_timeline_unchanged(self):
        from core.conversation.conversation_timeline import ConversationTimeline
        from core.conversation.timeline_event import EventType, TimelineEvent
        tl = ConversationTimeline()
        tl.record(TimelineEvent(EventType.START_PROJECT, "Jarvis", turn=1))
        assert tl.count() == 1

    def test_workers_package_importable(self):
        from core.workers.manager import WorkerManager
        from core.workers.base import Worker
        from core.workers.registry import WorkerRegistry
        from core.workers.models import WorkerTask, WorkerResult, WorkerStatus
        from core.workers.exceptions import WorkerError
        assert WorkerManager is not None

    def test_plug_and_play_new_worker(self):
        """A new worker type plugs in without any framework changes."""
        class ResearchWorker(Worker):
            @property
            def name(self): return "research"
            @property
            def description(self): return "Researches topics."
            @property
            def capabilities(self): return ["research_task"]
            def validate(self, task): return True
            def execute(self, task):
                self._begin(task)
                return self._succeed(WorkerResult(
                    task_id=task.task_id, worker_name=self.name,
                    success=True, observations=("Research complete.",),
                    requires_approval=True,
                ))

        m = make_manager()
        m.register(ResearchWorker())
        result = m.execute("research", make_task("research_task"))
        assert result.success
        assert result.requires_approval