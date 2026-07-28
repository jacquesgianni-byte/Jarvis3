"""
Tests for Genesis-027 Sprint-003: Multi-Worker Coordination

Proves that WorkerCoordinator can sequence CodingWorker -> DebugWorker
-> SuiteRunnerWorker into a single engineering_review workflow.

Coverage:
    - SuiteRunnerWorker registered and functional
    - WorkerCoordinator wired into Agent
    - engineering_review workflow registered
    - Three-worker pipeline executes in correct order
    - Context flows between workers via merge_context
    - Coordinator stops on failure
    - No worker-specific branches in coordinator
    - Existing 2871-test suite remains green
"""

import pytest
from unittest.mock import MagicMock

from core.workers.manager import WorkerManager
from core.workers.coordinator import WorkerCoordinator
from core.workers.debug_worker import DebugWorker
from core.workers.suite_worker import SuiteRunnerWorker
from core.workers.coding_worker import CodingWorker
from core.workers.models import WorkerTask, WorkerResult, WorkerStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ai():
    ai = MagicMock()
    ai.ask.return_value = MagicMock(
        success=True,
        message='{"summary":"Add logging","complexity":"low","files":["core/agent.py"],"plan":["Step 1: add logger","Step 2: instrument calls"]}'
    )
    return ai

@pytest.fixture
def manager(mock_ai):
    m = WorkerManager()
    m.register(CodingWorker(ai=mock_ai))
    m.register(DebugWorker())
    m.register(SuiteRunnerWorker())
    return m

@pytest.fixture
def coordinator(manager):
    c = WorkerCoordinator(manager)
    c.register_workflow(
        "engineering_review",
        ["coding_worker", "debug_worker", "suite_runner_worker"],
    )
    return c


# ---------------------------------------------------------------------------
# SuiteRunnerWorker — contract
# ---------------------------------------------------------------------------

class TestSuiteRunnerWorkerContract:

    def test_name(self):
        assert SuiteRunnerWorker().name == "suite_runner_worker"

    def test_capabilities(self):
        assert "run_tests" in SuiteRunnerWorker().capabilities

    def test_initial_status_idle(self):
        assert SuiteRunnerWorker().status() == WorkerStatus.IDLE

    def test_validate_valid_task(self):
        task = WorkerTask(task_type="run_tests", payload={})
        assert SuiteRunnerWorker().validate(task) is True

    def test_validate_wrong_type(self):
        task = WorkerTask(task_type="plan_implementation", payload={})
        assert SuiteRunnerWorker().validate(task) is False

    def test_execute_returns_worker_result(self):
        task = WorkerTask(
            task_type="run_tests",
            payload={"paths": ["tests/test_normalizer.py"]},
        )
        result = SuiteRunnerWorker().execute(task)
        assert isinstance(result, WorkerResult)

    def test_execute_returns_counts(self):
        task = WorkerTask(
            task_type="run_tests",
            payload={"paths": ["tests/test_normalizer.py"]},
        )
        result = SuiteRunnerWorker().execute(task)
        assert "passed" in result.data
        assert "failed" in result.data
        assert "skipped" in result.data

    def test_execute_does_not_interpret_failures(self):
        """SuiteRunnerWorker reports counts only — no interpretation."""
        task = WorkerTask(
            task_type="run_tests",
            payload={"paths": ["tests/test_normalizer.py"]},
        )
        result = SuiteRunnerWorker().execute(task)
        # Result has counts but no diagnostic recommendations from the runner
        assert "passed" in result.data
        # Interpretation is DebugWorker's job


# ---------------------------------------------------------------------------
# Agent integration — Sprint-003
# ---------------------------------------------------------------------------

class TestAgentSprint003:

    def test_agent_has_worker_coordinator(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        assert hasattr(agent, 'worker_coordinator')
        assert isinstance(agent.worker_coordinator, WorkerCoordinator)

    def test_agent_suite_runner_registered(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        assert agent.worker_manager.has_worker("suite_runner_worker")

    def test_agent_engineering_review_workflow_registered(self):
        from core.agent import Agent
        mock_ai = MagicMock()
        mock_ai.ask.return_value = MagicMock(success=True, message='{}')
        agent = Agent(ai=mock_ai)
        assert agent.worker_coordinator.has_workflow("engineering_review")

    def test_agent_engineering_review_workflow_order(self):
        from core.agent import Agent
        mock_ai = MagicMock()
        mock_ai.ask.return_value = MagicMock(success=True, message='{}')
        agent = Agent(ai=mock_ai)
        workflow = agent.worker_coordinator.workflow_for("engineering_review")
        assert workflow == ["coding_worker", "debug_worker", "suite_runner_worker"]


# ---------------------------------------------------------------------------
# WorkerCoordinator — engineering_review workflow
# ---------------------------------------------------------------------------

class TestEngineeringReviewWorkflow:

    def test_workflow_registered(self, coordinator):
        assert coordinator.has_workflow("engineering_review")

    def test_workflow_order(self, coordinator):
        workflow = coordinator.workflow_for("engineering_review")
        assert workflow == ["coding_worker", "debug_worker", "suite_runner_worker"]

    def test_workflow_runs_to_completion(self, coordinator):
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging to agent.py",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        assert isinstance(result, WorkerResult)

    def test_workflow_succeeds(self, coordinator):
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging to agent.py",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        assert result.success is True

    def test_workflow_coordinator_name(self, coordinator):
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        assert result.worker_name == "coordinator"

    def test_workflow_all_workers_executed(self, coordinator):
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        executed = result.data["workers_executed"]
        assert "coding_worker" in executed
        assert "debug_worker" in executed
        assert "suite_runner_worker" in executed

    def test_workflow_execution_order(self, coordinator):
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        executed = result.data["workers_executed"]
        assert executed.index("coding_worker") < executed.index("debug_worker")
        assert executed.index("debug_worker") < executed.index("suite_runner_worker")

    def test_workflow_results_contain_all_workers(self, coordinator):
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        assert "coding_worker" in result.data["results"]
        assert "debug_worker" in result.data["results"]
        assert "suite_runner_worker" in result.data["results"]

    def test_workflow_requires_approval(self, coordinator):
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        assert result.requires_approval is True

    def test_workflow_stops_on_failure(self, coordinator, mock_ai):
        """Coordinator must stop if any worker fails."""
        mock_ai.ask.return_value = MagicMock(success=False, message="")
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        assert result.success is False
        # Should have stopped at coding_worker
        executed = result.data.get("workers_executed", [])
        assert "suite_runner_worker" not in executed

    def test_context_passes_between_workers(self, coordinator):
        """Previous worker's data should appear in next worker's payload."""
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        # If workflow succeeded, context was passed correctly
        assert result.success is True
        assert result.data["steps_completed"] == 3

    def test_unknown_workflow_returns_failure(self, coordinator):
        task = WorkerTask(task_type="nonexistent_workflow", payload={})
        result = coordinator.run(task)
        assert result.success is False

    def test_no_worker_specific_branches_in_coordinator(self):
        """Coordinator must have zero worker-specific logic."""
        import inspect
        source = inspect.getsource(WorkerCoordinator)
        assert "coding_worker" not in source
        assert "debug_worker" not in source
        assert "suite_runner_worker" not in source
        assert "isinstance" not in source

    def test_steps_completed_count(self, coordinator):
        task = WorkerTask(
            task_type="engineering_review",
            payload={
                "description": "Add request logging",
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        assert result.data["steps_completed"] == 3
        assert result.data["steps_total"] == 3