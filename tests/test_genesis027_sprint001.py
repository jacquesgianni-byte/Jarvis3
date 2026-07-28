"""
Tests for Genesis-027 Sprint-001: Worker Operating System — Bring Online

Verifies that:
    - WorkerManager is instantiated in Agent
    - DebugWorker and TestWorker are registered
    - Worker contract is correctly implemented by both workers
    - WorkerOrchestrator routes tasks correctly
    - WorkerFactory stub is present
    - No regressions in existing pipeline
"""

import pytest
from unittest.mock import MagicMock

from core.workers.manager import WorkerManager
from core.workers.orchestrator import WorkerOrchestrator
from core.workers.registry import WorkerRegistry
from core.workers.models import WorkerTask, WorkerResult, WorkerStatus
from core.workers.debug_worker import DebugWorker
from core.workers.suite_worker import SuiteRunnerWorker as TestWorker
from core.workers.worker_factory import WorkerFactory, WorkerBlueprint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    m = WorkerManager()
    m.register(DebugWorker())
    m.register(TestWorker())
    return m

@pytest.fixture
def orchestrator(manager):
    return WorkerOrchestrator(manager)

@pytest.fixture
def debug_worker():
    return DebugWorker()

@pytest.fixture
def test_worker():
    return TestWorker()


# ---------------------------------------------------------------------------
# Agent integration — WOS online
# ---------------------------------------------------------------------------

class TestAgentWOS:

    def test_agent_has_worker_manager(self):
        """Agent must have a WorkerManager instance."""
        from core.agent import Agent
        agent = Agent(ai=None)
        assert hasattr(agent, 'worker_manager')
        assert isinstance(agent.worker_manager, WorkerManager)

    def test_agent_has_worker_orchestrator(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        assert hasattr(agent, 'worker_orchestrator')
        assert isinstance(agent.worker_orchestrator, WorkerOrchestrator)

    def test_agent_has_worker_factory(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        assert hasattr(agent, 'worker_factory')
        assert isinstance(agent.worker_factory, WorkerFactory)

    def test_agent_debug_worker_registered(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        assert agent.worker_manager.has_worker('debug_worker')

    def test_agent_test_worker_registered(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        assert agent.worker_manager.has_worker('suite_runner_worker')

    def test_agent_worker_count(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        assert agent.worker_manager.worker_count() >= 2


# ---------------------------------------------------------------------------
# DebugWorker — contract
# ---------------------------------------------------------------------------

class TestDebugWorkerContract:

    def test_name(self, debug_worker):
        assert debug_worker.name == "debug_worker"

    def test_description_non_empty(self, debug_worker):
        assert len(debug_worker.description) > 0

    def test_capabilities(self, debug_worker):
        assert "analyse_session" in debug_worker.capabilities

    def test_initial_status_idle(self, debug_worker):
        assert debug_worker.status() == WorkerStatus.IDLE

    def test_is_available(self, debug_worker):
        assert debug_worker.is_available is True

    def test_validate_valid_task(self, debug_worker):
        task = WorkerTask(
            task_type="analyse_session",
            payload={"log_lines": ["line1", "line2"]},
        )
        assert debug_worker.validate(task) is True

    def test_validate_wrong_type(self, debug_worker):
        task = WorkerTask(task_type="run_tests", payload={})
        assert debug_worker.validate(task) is False

    def test_validate_missing_log_lines(self, debug_worker):
        task = WorkerTask(task_type="analyse_session", payload={})
        assert debug_worker.validate(task) is False

    def test_validate_wrong_log_lines_type(self, debug_worker):
        task = WorkerTask(
            task_type="analyse_session",
            payload={"log_lines": "not a list"},
        )
        assert debug_worker.validate(task) is False

    def test_execute_returns_worker_result(self, debug_worker):
        task = WorkerTask(
            task_type="analyse_session",
            payload={"log_lines": [
                "2026-07-27 12:00:00 | INFO | Jarvis | Request received: hello",
                "2026-07-27 12:00:00 | INFO | [ROUTER] Intent=GREETING → DecisionType=Answer Directly",
            ]},
        )
        result = debug_worker.execute(task)
        assert isinstance(result, WorkerResult)

    def test_execute_success(self, debug_worker):
        task = WorkerTask(
            task_type="analyse_session",
            payload={"log_lines": [
                "2026-07-27 12:00:00 | INFO | Jarvis | Request received: hello",
            ]},
        )
        result = debug_worker.execute(task)
        assert result.success is True

    def test_execute_returns_health_score(self, debug_worker):
        task = WorkerTask(
            task_type="analyse_session",
            payload={"log_lines": [
                "2026-07-27 12:00:00 | INFO | Jarvis | Request received: hello",
            ]},
        )
        result = debug_worker.execute(task)
        assert "health_score" in result.data
        assert isinstance(result.data["health_score"], int)

    def test_execute_status_completed(self, debug_worker):
        task = WorkerTask(
            task_type="analyse_session",
            payload={"log_lines": []},
        )
        debug_worker.execute(task)
        assert debug_worker.status() == WorkerStatus.COMPLETED

    def test_reset_returns_to_idle(self, debug_worker):
        task = WorkerTask(
            task_type="analyse_session",
            payload={"log_lines": []},
        )
        debug_worker.execute(task)
        debug_worker.reset()
        assert debug_worker.status() == WorkerStatus.IDLE


# ---------------------------------------------------------------------------
# TestWorker — contract
# ---------------------------------------------------------------------------

class TestTestWorkerContract:

    def test_name(self, test_worker):
        assert test_worker.name == "suite_runner_worker"

    def test_description_non_empty(self, test_worker):
        assert len(test_worker.description) > 0

    def test_capabilities(self, test_worker):
        assert "run_tests" in test_worker.capabilities

    def test_initial_status_idle(self, test_worker):
        assert test_worker.status() == WorkerStatus.IDLE

    def test_is_available(self, test_worker):
        assert test_worker.is_available is True

    def test_validate_valid_task(self, test_worker):
        task = WorkerTask(task_type="run_tests", payload={})
        assert test_worker.validate(task) is True

    def test_validate_wrong_type(self, test_worker):
        task = WorkerTask(task_type="analyse_session", payload={})
        assert test_worker.validate(task) is False

    def test_execute_returns_worker_result(self, test_worker):
        """Run a minimal test subset to verify the worker returns a result."""
        task = WorkerTask(
            task_type="run_tests",
            payload={"paths": ["tests/test_normalizer.py"]},
        )
        result = test_worker.execute(task)
        assert isinstance(result, WorkerResult)

    def test_execute_returns_counts(self, test_worker):
        task = WorkerTask(
            task_type="run_tests",
            payload={"paths": ["tests/test_normalizer.py"]},
        )
        result = test_worker.execute(task)
        assert "passed" in result.data
        assert "failed" in result.data
        assert "skipped" in result.data

    def test_execute_passing_suite_success(self, test_worker):
        task = WorkerTask(
            task_type="run_tests",
            payload={"paths": ["tests/test_normalizer.py"]},
        )
        result = test_worker.execute(task)
        assert result.success is True
        assert result.data["failed"] == 0


# ---------------------------------------------------------------------------
# WorkerManager — registration and routing
# ---------------------------------------------------------------------------

class TestWorkerManagerIntegration:

    def test_debug_worker_registered(self, manager):
        assert manager.has_worker("debug_worker")

    def test_test_worker_registered(self, manager):
        assert manager.has_worker("suite_runner_worker")

    def test_workers_for_analyse_session(self, manager):
        workers = manager.workers_for("analyse_session")
        assert any(w.name == "debug_worker" for w in workers)

    def test_workers_for_run_tests(self, manager):
        workers = manager.workers_for("run_tests")
        assert any(w.name == "suite_runner_worker" for w in workers)

    def test_workers_for_unknown_type(self, manager):
        workers = manager.workers_for("unknown_task_type")
        assert workers == []

    def test_available_workers(self, manager):
        available = manager.available_workers()
        assert len(available) >= 2

    def test_execute_debug_worker(self, manager):
        task = WorkerTask(
            task_type="analyse_session",
            payload={"log_lines": ["INFO | Request received: hello"]},
        )
        result = manager.execute("debug_worker", task)
        assert isinstance(result, WorkerResult)
        assert result.success is True


# ---------------------------------------------------------------------------
# WorkerOrchestrator — routing
# ---------------------------------------------------------------------------

class TestWorkerOrchestratorIntegration:

    def test_available_for_analyse_session(self, orchestrator):
        assert orchestrator.available_for("analyse_session") is True

    def test_available_for_run_tests(self, orchestrator):
        assert orchestrator.available_for("run_tests") is True

    def test_available_for_unknown(self, orchestrator):
        assert orchestrator.available_for("unknown_type") is False

    def test_run_routes_to_debug_worker(self, orchestrator):
        task = WorkerTask(
            task_type="analyse_session",
            payload={"log_lines": []},
        )
        result = orchestrator.run(task)
        assert isinstance(result, WorkerResult)
        assert result.worker_name == "debug_worker"

    def test_run_unknown_type_returns_failure(self, orchestrator):
        task = WorkerTask(task_type="unknown_type", payload={})
        result = orchestrator.run(task)
        assert result.success is False

    def test_registered_task_types(self, orchestrator):
        types = orchestrator.registered_task_types()
        assert "analyse_session" in types
        assert "run_tests" in types


# ---------------------------------------------------------------------------
# WorkerFactory — stub
# ---------------------------------------------------------------------------

class TestWorkerFactoryStub:

    def test_factory_instantiates(self):
        factory = WorkerFactory()
        assert factory is not None

    def test_create_unknown_raises_key_error(self):
        """CV-002: WorkerFactory now active - unknown name raises KeyError."""
        factory = WorkerFactory()
        with pytest.raises(KeyError):
            factory.create("nonexistent_worker")

    def test_generate_scaffold_raises_not_implemented(self):
        factory = WorkerFactory()
        blueprint = WorkerBlueprint(name="x", description="x")
        with pytest.raises(NotImplementedError):
            factory.generate_scaffold(blueprint)

    def test_summary_returns_active_status(self):
        """Sprint-002: factory is now active, not stub."""
        factory = WorkerFactory()
        summary = factory.summary()
        assert summary["status"] == "active"