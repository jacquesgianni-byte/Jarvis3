"""
Tests for Genesis-027 Sprint-002: WorkerFactory + CodingWorker

Verifies that:
    - WorkerFactory creates workers via registered builders
    - WorkerFactory injects dependencies correctly
    - CodingWorker implements the Worker contract correctly
    - Workers are created via factory in Agent (single creation path)
    - No worker-specific branches in WorkerManager or WorkerFactory
    - All existing tests remain green
"""

import pytest
from unittest.mock import MagicMock

from core.workers.worker_factory import WorkerFactory
from core.workers.debug_worker import DebugWorker
from core.workers.suite_worker import SuiteRunnerWorker
from core.workers.coding_worker import CodingWorker
from core.workers.manager import WorkerManager
from core.workers.orchestrator import WorkerOrchestrator
from core.workers.models import WorkerTask, WorkerResult, WorkerStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def factory():
    f = WorkerFactory()
    f.register_builder("debug_worker",  lambda deps: DebugWorker())
    f.register_builder("test_worker",   lambda deps: SuiteRunnerWorker())
    f.register_builder("coding_worker", lambda deps: CodingWorker(deps["ai"]))
    return f

@pytest.fixture
def mock_ai():
    ai = MagicMock()
    ai.ask.return_value = MagicMock(
        success=True,
        message='{"summary":"Add X","complexity":"low","files":["core/agent.py"],"plan":["Step 1: do this","Step 2: do that"]}'
    )
    return ai

@pytest.fixture
def coding_worker(mock_ai):
    return CodingWorker(ai=mock_ai)


# ---------------------------------------------------------------------------
# WorkerFactory — builder registration
# ---------------------------------------------------------------------------

class TestWorkerFactoryBuilders:

    def test_factory_starts_empty(self):
        f = WorkerFactory()
        assert f.available_worker_names() == []

    def test_register_builder(self):
        f = WorkerFactory()
        f.register_builder("debug_worker", lambda deps: DebugWorker())
        assert f.can_create("debug_worker")

    def test_register_duplicate_raises(self):
        f = WorkerFactory()
        f.register_builder("debug_worker", lambda deps: DebugWorker())
        with pytest.raises(ValueError):
            f.register_builder("debug_worker", lambda deps: DebugWorker())

    def test_replace_builder(self):
        f = WorkerFactory()
        f.register_builder("debug_worker", lambda deps: DebugWorker())
        f.replace_builder("debug_worker", lambda deps: DebugWorker())
        assert f.can_create("debug_worker")

    def test_can_create_false_for_unknown(self):
        f = WorkerFactory()
        assert f.can_create("unknown_worker") is False

    def test_available_worker_names(self, factory):
        names = factory.available_worker_names()
        assert "debug_worker" in names
        assert "test_worker" in names
        assert "coding_worker" in names

    def test_summary_active(self, factory):
        s = factory.summary()
        assert s["status"] == "active"
        assert s["registered_builders"] == 3


# ---------------------------------------------------------------------------
# WorkerFactory — creation
# ---------------------------------------------------------------------------

class TestWorkerFactoryCreation:

    def test_create_debug_worker(self, factory):
        worker = factory.create("debug_worker")
        assert isinstance(worker, DebugWorker)
        assert worker.name == "debug_worker"

    def test_create_test_worker(self, factory):
        worker = factory.create("test_worker")
        assert isinstance(worker, SuiteRunnerWorker)
        assert worker.name == "test_worker"

    def test_create_coding_worker_with_deps(self, factory, mock_ai):
        worker = factory.create("coding_worker", deps={"ai": mock_ai})
        assert isinstance(worker, CodingWorker)
        assert worker.name == "coding_worker"

    def test_create_unknown_raises(self, factory):
        with pytest.raises(KeyError):
            factory.create("unknown_worker")

    def test_create_returns_idle_worker(self, factory):
        worker = factory.create("debug_worker")
        assert worker.status() == WorkerStatus.IDLE
        assert worker.is_available is True

    def test_create_multiple_independent_instances(self, factory):
        w1 = factory.create("debug_worker")
        w2 = factory.create("debug_worker")
        assert w1 is not w2

    def test_no_worker_specific_logic_in_factory(self, factory):
        """Factory core must not contain isinstance checks or name branches."""
        import inspect
        source = inspect.getsource(WorkerFactory)
        assert "isinstance" not in source
        assert "if name ==" not in source
        assert "DebugWorker" not in source
        assert "CodingWorker" not in source


# ---------------------------------------------------------------------------
# CodingWorker — contract
# ---------------------------------------------------------------------------

class TestCodingWorkerContract:

    def test_name(self, coding_worker):
        assert coding_worker.name == "coding_worker"

    def test_description_non_empty(self, coding_worker):
        assert len(coding_worker.description) > 0

    def test_capabilities(self, coding_worker):
        assert "plan_implementation" in coding_worker.capabilities

    def test_initial_status_idle(self, coding_worker):
        assert coding_worker.status() == WorkerStatus.IDLE

    def test_validate_valid_task(self, coding_worker):
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "Add X feature to agent.py"},
        )
        assert coding_worker.validate(task) is True

    def test_validate_wrong_type(self, coding_worker):
        task = WorkerTask(task_type="analyse_session", payload={})
        assert coding_worker.validate(task) is False

    def test_validate_missing_description(self, coding_worker):
        task = WorkerTask(task_type="plan_implementation", payload={})
        assert coding_worker.validate(task) is False

    def test_validate_empty_description(self, coding_worker):
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "   "},
        )
        assert coding_worker.validate(task) is False

    def test_execute_returns_worker_result(self, coding_worker):
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "Add logging to agent.py"},
        )
        result = coding_worker.execute(task)
        assert isinstance(result, WorkerResult)

    def test_execute_success(self, coding_worker):
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "Add logging to agent.py"},
        )
        result = coding_worker.execute(task)
        assert result.success is True

    def test_execute_requires_approval(self, coding_worker):
        """CodingWorker plans must require human approval."""
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "Add logging to agent.py"},
        )
        result = coding_worker.execute(task)
        assert result.requires_approval is True

    def test_execute_returns_plan_data(self, coding_worker):
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "Add logging to agent.py"},
        )
        result = coding_worker.execute(task)
        assert "plan" in result.data
        assert "files" in result.data
        assert "complexity" in result.data
        assert "summary" in result.data

    def test_execute_plan_is_list(self, coding_worker):
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "Add logging to agent.py"},
        )
        result = coding_worker.execute(task)
        assert isinstance(result.data["plan"], list)

    def test_execute_status_completed(self, coding_worker):
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "Add logging to agent.py"},
        )
        coding_worker.execute(task)
        assert coding_worker.status() == WorkerStatus.COMPLETED

    def test_execute_ai_failure_returns_failure(self, mock_ai):
        mock_ai.ask.return_value = MagicMock(success=False, message="")
        worker = CodingWorker(ai=mock_ai)
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "Add logging to agent.py"},
        )
        result = worker.execute(task)
        assert result.success is False


# ---------------------------------------------------------------------------
# Agent integration — Sprint-002
# ---------------------------------------------------------------------------

class TestAgentSprint002:

    def test_agent_coding_worker_registered_with_ai(self):
        """CodingWorker should be registered when AI provider is present."""
        from core.agent import Agent
        mock_ai = MagicMock()
        mock_ai.ask.return_value = MagicMock(success=True, message='{}')
        agent = Agent(ai=mock_ai)
        assert agent.worker_manager.has_worker("coding_worker")

    def test_agent_coding_worker_not_registered_without_ai(self):
        """CodingWorker should not be registered when no AI provider."""
        from core.agent import Agent
        agent = Agent(ai=None)
        assert not agent.worker_manager.has_worker("coding_worker")

    def test_agent_factory_has_builders(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        assert agent.worker_factory.can_create("debug_worker")
        assert agent.worker_factory.can_create("test_worker")
        assert agent.worker_factory.can_create("coding_worker")

    def test_workers_created_via_factory(self):
        """All workers in manager should have been created by factory."""
        from core.agent import Agent
        agent = Agent(ai=None)
        # Factory must know how to create everything that's registered
        for worker in agent.worker_manager.all_workers():
            assert agent.worker_factory.can_create(worker.name), \
                f"Worker {worker.name!r} not creatable via factory"


# ---------------------------------------------------------------------------
# End-to-end: orchestrator routes to CodingWorker
# ---------------------------------------------------------------------------

class TestCodingWorkerOrchestration:

    def test_orchestrator_routes_plan_task(self, mock_ai):
        manager = WorkerManager()
        factory = WorkerFactory()
        factory.register_builder("coding_worker", lambda deps: CodingWorker(deps["ai"]))
        manager.register(factory.create("coding_worker", deps={"ai": mock_ai}))
        orchestrator = WorkerOrchestrator(manager)

        task = WorkerTask(
            task_type="plan_implementation",
            payload={"description": "Refactor the memory detector"},
        )
        result = orchestrator.run(task)
        assert isinstance(result, WorkerResult)
        assert result.worker_name == "coding_worker"
        assert result.success is True

    def test_manager_never_checks_worker_type(self, mock_ai):
        """WorkerManager dispatches all workers identically - no isinstance checks."""
        import inspect
        source = inspect.getsource(WorkerManager)
        assert "isinstance" not in source
        assert "CodingWorker" not in source
        assert "DebugWorker" not in source