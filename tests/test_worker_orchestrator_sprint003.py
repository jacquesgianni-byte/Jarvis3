"""
Genesis-021 Sprint-003 — Worker Orchestrator Tests
Completely self-contained. No dependency on other test files.

Coverage:
  - run(): successful routing and execution
  - run(): no worker registered → failure result
  - run(): all workers busy → failure result
  - run(): worker raises → failure result (never re-raises)
  - run_named(): successful named execution
  - run_named(): worker not registered → failure result
  - run_named(): worker raises → failure result
  - available_for(): True when worker available
  - available_for(): False when no worker registered
  - available_for(): False when all workers busy
  - select_worker(): returns first available
  - select_worker(): returns None when none available
  - select_worker(): returns None when none registered
  - registered_task_types(): correct capability list
  - summary(): dict structure
  - Never raises — always returns WorkerResult
  - Backwards compatibility
"""

import sys
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.workers.orchestrator import WorkerOrchestrator
from core.workers.manager import WorkerManager
from core.workers.base import Worker
from core.workers.models import WorkerTask, WorkerResult, WorkerStatus
from core.workers.exceptions import WorkerAlreadyRegisteredError


# ---------------------------------------------------------------------------
# Concrete workers for testing
# ---------------------------------------------------------------------------

class EchoWorker(Worker):
    @property
    def name(self) -> str: return "echo"
    @property
    def description(self) -> str: return "Echoes."
    @property
    def capabilities(self) -> list[str]: return ["echo_task", "shared_task"]
    def validate(self, task: WorkerTask) -> bool: return True
    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        return self._succeed(WorkerResult(
            task_id=task.task_id, worker_name=self.name,
            success=True, observations=("Echo.",),
            requires_approval=False,
        ))


class SecondEchoWorker(Worker):
    """Second worker with overlapping capabilities — for priority testing."""
    @property
    def name(self) -> str: return "echo2"
    @property
    def description(self) -> str: return "Second echo."
    @property
    def capabilities(self) -> list[str]: return ["shared_task"]
    def validate(self, task: WorkerTask) -> bool: return True
    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        return self._succeed(WorkerResult(
            task_id=task.task_id, worker_name=self.name,
            success=True, observations=("Echo2.",),
            requires_approval=False,
        ))


class RaisingWorker(Worker):
    @property
    def name(self) -> str: return "raising"
    @property
    def description(self) -> str: return "Always raises."
    @property
    def capabilities(self) -> list[str]: return ["raise_task"]
    def validate(self, task: WorkerTask) -> bool: return True
    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        raise RuntimeError("Deliberate error.")


def make_task(task_type="echo_task", **kwargs) -> WorkerTask:
    return WorkerTask(task_type=task_type, **kwargs)


def make_orchestrator(*workers) -> WorkerOrchestrator:
    m = WorkerManager()
    for w in workers:
        m.register(w)
    return WorkerOrchestrator(m)


# ===========================================================================
# 1. run() — successful routing
# ===========================================================================

class TestOrchestratorRunSuccess:

    def test_routes_to_correct_worker(self):
        orch = make_orchestrator(EchoWorker())
        result = orch.run(make_task("echo_task"))
        assert result.success
        assert result.worker_name == "echo"

    def test_returns_worker_result(self):
        orch = make_orchestrator(EchoWorker())
        result = orch.run(make_task("echo_task"))
        assert isinstance(result, WorkerResult)

    def test_task_id_preserved(self):
        orch = make_orchestrator(EchoWorker())
        task = make_task("echo_task")
        result = orch.run(task)
        assert result.task_id == task.task_id

    def test_observations_populated(self):
        orch = make_orchestrator(EchoWorker())
        result = orch.run(make_task("echo_task"))
        assert len(result.observations) > 0

    def test_multiple_workers_routes_to_capable_one(self):
        orch = make_orchestrator(EchoWorker(), RaisingWorker())
        result = orch.run(make_task("raise_task"))
        # RaisingWorker raises — orchestrator wraps in failure
        assert not result.success
        assert result.worker_name == "raising"

    def test_first_available_selected_for_shared_task(self):
        """When two workers share a task type, first registered is selected."""
        orch = make_orchestrator(EchoWorker(), SecondEchoWorker())
        result = orch.run(make_task("shared_task"))
        assert result.success
        assert result.worker_name == "echo"  # registered first


# ===========================================================================
# 2. run() — failure cases — never raises
# ===========================================================================

class TestOrchestratorRunFailure:

    def test_no_worker_returns_failure_result(self):
        orch = make_orchestrator()
        result = orch.run(make_task("unknown_task"))
        assert not result.success
        assert result.error
        assert result.worker_name == "orchestrator"

    def test_no_worker_does_not_raise(self):
        orch = make_orchestrator()
        result = orch.run(make_task("unknown_task"))  # must not raise
        assert isinstance(result, WorkerResult)

    def test_all_busy_returns_failure_result(self):
        m = WorkerManager()
        w = EchoWorker()
        w._status = WorkerStatus.RUNNING
        m.register(w)
        orch = WorkerOrchestrator(m)
        result = orch.run(make_task("echo_task"))
        assert not result.success
        assert "busy" in result.error.lower()

    def test_worker_raises_returns_failure_result(self):
        orch = make_orchestrator(RaisingWorker())
        result = orch.run(make_task("raise_task"))
        assert not result.success
        assert result.error

    def test_worker_raises_does_not_propagate(self):
        orch = make_orchestrator(RaisingWorker())
        result = orch.run(make_task("raise_task"))  # must not raise
        assert isinstance(result, WorkerResult)

    def test_failure_result_has_task_id(self):
        orch = make_orchestrator()
        task = make_task("unknown")
        result = orch.run(task)
        assert result.task_id == task.task_id


# ===========================================================================
# 3. run_named() — specific worker
# ===========================================================================

class TestOrchestratorRunNamed:

    def test_run_named_success(self):
        orch = make_orchestrator(EchoWorker())
        result = orch.run_named("echo", make_task("echo_task"))
        assert result.success
        assert result.worker_name == "echo"

    def test_run_named_missing_worker_returns_failure(self):
        orch = make_orchestrator()
        result = orch.run_named("nonexistent", make_task("echo_task"))
        assert not result.success
        assert "not registered" in result.error.lower()

    def test_run_named_missing_does_not_raise(self):
        orch = make_orchestrator()
        result = orch.run_named("nonexistent", make_task("x"))
        assert isinstance(result, WorkerResult)

    def test_run_named_raising_worker_returns_failure(self):
        orch = make_orchestrator(RaisingWorker())
        result = orch.run_named("raising", make_task("raise_task"))
        assert not result.success

    def test_run_named_raising_does_not_raise(self):
        orch = make_orchestrator(RaisingWorker())
        result = orch.run_named("raising", make_task("raise_task"))
        assert isinstance(result, WorkerResult)

    def test_run_named_task_id_preserved(self):
        orch = make_orchestrator(EchoWorker())
        task = make_task("echo_task")
        result = orch.run_named("echo", task)
        assert result.task_id == task.task_id


# ===========================================================================
# 4. available_for()
# ===========================================================================

class TestOrchestratorAvailableFor:

    def test_true_when_worker_registered_and_idle(self):
        orch = make_orchestrator(EchoWorker())
        assert orch.available_for("echo_task")

    def test_false_when_no_worker_registered(self):
        orch = make_orchestrator()
        assert not orch.available_for("echo_task")

    def test_false_when_all_workers_busy(self):
        m = WorkerManager()
        w = EchoWorker()
        w._status = WorkerStatus.RUNNING
        m.register(w)
        orch = WorkerOrchestrator(m)
        assert not orch.available_for("echo_task")

    def test_true_when_one_of_two_available(self):
        m = WorkerManager()
        w1 = EchoWorker()
        w1._status = WorkerStatus.RUNNING
        w2 = SecondEchoWorker()
        m.register(w1); m.register(w2)
        orch = WorkerOrchestrator(m)
        assert orch.available_for("shared_task")


# ===========================================================================
# 5. select_worker()
# ===========================================================================

class TestOrchestratorSelectWorker:

    def test_returns_worker_when_available(self):
        orch = make_orchestrator(EchoWorker())
        worker = orch.select_worker(make_task("echo_task"))
        assert worker is not None
        assert worker.name == "echo"

    def test_returns_none_when_no_worker(self):
        orch = make_orchestrator()
        assert orch.select_worker(make_task("unknown")) is None

    def test_returns_none_when_all_busy(self):
        m = WorkerManager()
        w = EchoWorker()
        w._status = WorkerStatus.RUNNING
        m.register(w)
        orch = WorkerOrchestrator(m)
        assert orch.select_worker(make_task("echo_task")) is None

    def test_returns_first_available_when_multiple(self):
        orch = make_orchestrator(EchoWorker(), SecondEchoWorker())
        worker = orch.select_worker(make_task("shared_task"))
        assert worker.name == "echo"  # registered first

    def test_skips_busy_returns_next(self):
        m = WorkerManager()
        w1 = EchoWorker()
        w1._status = WorkerStatus.RUNNING
        w2 = SecondEchoWorker()
        m.register(w1); m.register(w2)
        orch = WorkerOrchestrator(m)
        worker = orch.select_worker(make_task("shared_task"))
        assert worker is not None
        assert worker.name == "echo2"


# ===========================================================================
# 6. registered_task_types() and summary()
# ===========================================================================

class TestOrchestratorIntrospection:

    def test_registered_task_types_empty_when_no_workers(self):
        orch = make_orchestrator()
        assert orch.registered_task_types() == []

    def test_registered_task_types_includes_capabilities(self):
        orch = make_orchestrator(EchoWorker())
        types = orch.registered_task_types()
        assert "echo_task" in types
        assert "shared_task" in types

    def test_registered_task_types_no_duplicates(self):
        orch = make_orchestrator(EchoWorker(), SecondEchoWorker())
        types = orch.registered_task_types()
        assert len(types) == len(set(types))

    def test_summary_is_dict(self):
        orch = make_orchestrator(EchoWorker())
        assert isinstance(orch.summary(), dict)

    def test_summary_worker_count(self):
        orch = make_orchestrator(EchoWorker(), RaisingWorker())
        assert orch.summary()["worker_count"] == 2

    def test_summary_available_workers(self):
        orch = make_orchestrator(EchoWorker())
        assert orch.summary()["available_workers"] == 1

    def test_summary_covered_task_types(self):
        orch = make_orchestrator(EchoWorker())
        assert "echo_task" in orch.summary()["covered_task_types"]


# ===========================================================================
# 7. Never raises guarantee
# ===========================================================================

class TestOrchestratorNeverRaises:

    def test_run_unknown_type_no_exception(self):
        orch = make_orchestrator()
        try:
            orch.run(make_task("totally_unknown_type_xyz"))
        except Exception as e:
            pytest.fail(f"run() raised unexpectedly: {e}")

    def test_run_named_missing_no_exception(self):
        orch = make_orchestrator()
        try:
            orch.run_named("nonexistent_worker", make_task("x"))
        except Exception as e:
            pytest.fail(f"run_named() raised unexpectedly: {e}")

    def test_run_exception_in_worker_no_propagation(self):
        orch = make_orchestrator(RaisingWorker())
        try:
            orch.run(make_task("raise_task"))
        except Exception as e:
            pytest.fail(f"run() propagated worker exception: {e}")

    def test_all_failure_results_have_error_text(self):
        orch = make_orchestrator()
        result = orch.run(make_task("unknown"))
        assert result.error
        assert len(result.error) > 0


# ===========================================================================
# 8. Integration with EngineeringWorker
# ===========================================================================

class TestOrchestratorWithEngineeringWorker:

    def test_routes_analyse_repository_to_engineering_worker(self):
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(EngineeringWorker())
        orch = WorkerOrchestrator(m)
        task = WorkerTask(
            task_type="analyse_repository",
            payload={"root_path": str(REPO_ROOT)}
        )
        result = orch.run(task)
        assert result.success
        assert result.worker_name == "engineering"
        assert result.requires_approval

    def test_engineering_worker_discoverable(self):
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(EngineeringWorker())
        orch = WorkerOrchestrator(m)
        assert orch.available_for("analyse_repository")


# ===========================================================================
# 9. Backwards compatibility
# ===========================================================================

class TestBackwardsCompatibility:

    def test_worker_framework_unchanged(self):
        m = WorkerManager()
        m.register(EchoWorker())
        assert m.worker_count() == 1

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_orchestrator_importable(self):
        from core.workers.orchestrator import WorkerOrchestrator
        assert WorkerOrchestrator is not None