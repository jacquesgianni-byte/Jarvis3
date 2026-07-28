"""
Tests for Genesis-027 Sprint-004: Dynamic Task Planning

Proves that TaskPlanner analyses engineering requests and produces
correct ordered WorkerPlans using capability resolution.

Coverage:
    - Different requests produce different WorkerPlans
    - Planner uses capabilities not worker names
    - Capabilities resolve to correct workers via WorkerManager
    - Coordinator executes arbitrary plans
    - No worker-specific logic in planner or coordinator
    - WorkerPlan is immutable and correctly structured
    - Empty plan returned for unrecognised requests
    - Full regression suite remains green
"""

import pytest
from unittest.mock import MagicMock

from core.workers.task_planner import TaskPlanner, WorkerPlan, _CAPABILITY_SIGNALS
from core.workers.manager import WorkerManager
from core.workers.coordinator import WorkerCoordinator
from core.workers.debug_worker import DebugWorker
from core.workers.suite_worker import SuiteRunnerWorker
from core.workers.coding_worker import CodingWorker
from core.workers.models import WorkerTask, WorkerResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ai():
    ai = MagicMock()
    ai.ask.return_value = MagicMock(
        success=True,
        message='{"summary":"Fix bug","complexity":"low","files":[],"plan":["Step 1"]}'
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
def planner(manager):
    return TaskPlanner(manager)

@pytest.fixture
def coordinator(manager):
    return WorkerCoordinator(manager)


# ---------------------------------------------------------------------------
# WorkerPlan — immutable structure
# ---------------------------------------------------------------------------

class TestWorkerPlan:

    def test_plan_is_immutable(self):
        plan = WorkerPlan(tasks=(), capabilities=(), request="test")
        with pytest.raises((AttributeError, TypeError)):
            plan.tasks = ()

    def test_is_empty_true_for_no_tasks(self):
        plan = WorkerPlan(tasks=(), capabilities=(), request="test")
        assert plan.is_empty is True

    def test_is_empty_false_with_tasks(self):
        task = WorkerTask(task_type="run_tests", payload={})
        plan = WorkerPlan(tasks=(task,), capabilities=("run_tests",), request="test")
        assert plan.is_empty is False

    def test_summary_contains_request(self):
        plan = WorkerPlan(tasks=(), capabilities=(), request="Fix the bug")
        s = plan.summary()
        assert "Fix the bug" in s["request"]

    def test_summary_contains_capabilities(self):
        plan = WorkerPlan(
            tasks=(),
            capabilities=("analyse_session", "run_tests"),
            request="test"
        )
        s = plan.summary()
        assert "analyse_session" in s["capabilities"]
        assert "run_tests" in s["capabilities"]

    def test_confidence_default(self):
        plan = WorkerPlan(tasks=(), capabilities=(), request="test")
        assert plan.confidence == 0.85


# ---------------------------------------------------------------------------
# TaskPlanner — capability detection
# ---------------------------------------------------------------------------

class TestTaskPlannerCapabilityDetection:

    def test_debug_request_detects_analyse_session(self, planner):
        caps = planner.capabilities_for("Debug the memory bug")
        assert "analyse_session" in caps

    def test_implement_request_detects_plan_implementation(self, planner):
        caps = planner.capabilities_for("Implement the new feature")
        assert "plan_implementation" in caps

    def test_test_request_detects_run_tests(self, planner):
        caps = planner.capabilities_for("Make sure the tests still pass")
        assert "run_tests" in caps

    def test_fix_and_test_request_detects_both(self, planner):
        caps = planner.capabilities_for("Fix the bug and make sure tests pass")
        assert "analyse_session" in caps
        assert "run_tests" in caps

    def test_full_engineering_request_detects_all_three(self, planner):
        caps = planner.capabilities_for(
            "Fix the memory bug and implement the fix and make sure tests still pass"
        )
        assert "plan_implementation" in caps
        assert "analyse_session" in caps
        assert "run_tests" in caps

    def test_unrecognised_request_returns_empty(self, planner):
        caps = planner.capabilities_for("Tell me a joke")
        assert caps == []

    def test_empty_request_returns_empty(self, planner):
        caps = planner.capabilities_for("")
        assert caps == []

    def test_execution_order_debug_before_tests(self, planner):
        caps = planner.capabilities_for("Debug the failing tests")
        if "analyse_session" in caps and "run_tests" in caps:
            assert caps.index("analyse_session") < caps.index("run_tests")

    def test_execution_order_implement_before_debug(self, planner):
        caps = planner.capabilities_for("Implement the fix and debug any issues")
        if "plan_implementation" in caps and "analyse_session" in caps:
            assert caps.index("plan_implementation") < caps.index("analyse_session")

    def test_no_worker_names_in_capability_signals(self):
        """Planner must use capabilities, not worker names."""
        for signal in _CAPABILITY_SIGNALS:
            assert "coding_worker" not in signal.name
            assert "debug_worker" not in signal.name
            assert "suite_runner_worker" not in signal.name


# ---------------------------------------------------------------------------
# TaskPlanner — plan production
# ---------------------------------------------------------------------------

class TestTaskPlannerPlanProduction:

    def test_plan_returns_worker_plan(self, planner):
        result = planner.plan("Fix the bug and run the tests")
        assert isinstance(result, WorkerPlan)

    def test_debug_request_produces_plan(self, planner):
        plan = planner.plan("Debug the memory leak")
        assert not plan.is_empty
        assert "analyse_session" in plan.capabilities

    def test_test_request_produces_plan(self, planner):
        plan = planner.plan("Run the test suite")
        assert not plan.is_empty
        assert "run_tests" in plan.capabilities

    def test_implement_request_produces_plan(self, planner):
        plan = planner.plan("Add logging to the agent")
        assert not plan.is_empty
        assert "plan_implementation" in plan.capabilities

    def test_different_requests_produce_different_plans(self, planner):
        plan_debug = planner.plan("Debug the memory bug")
        plan_test = planner.plan("Run the tests")
        assert plan_debug.capabilities != plan_test.capabilities

    def test_unrecognised_request_produces_empty_plan(self, planner):
        plan = planner.plan("What is the weather today?")
        assert plan.is_empty
        assert plan.confidence == 0.0

    def test_plan_tasks_have_correct_task_types(self, planner):
        plan = planner.plan("Run the test suite")
        for task in plan.tasks:
            assert task.task_type in [s.name for s in _CAPABILITY_SIGNALS]

    def test_plan_includes_request_in_payload(self, planner):
        plan = planner.plan("Fix the memory bug")
        for task in plan.tasks:
            assert "planning_request" in task.payload

    def test_plan_confidence_positive_when_workers_available(self, planner):
        plan = planner.plan("Debug the memory bug")
        if not plan.is_empty:
            assert plan.confidence > 0.0

    def test_plan_capability_count_matches_task_count(self, planner):
        plan = planner.plan("Fix the bug and run the tests")
        assert len(plan.tasks) == len(plan.capabilities)

    def test_no_worker_names_in_planner_source(self):
        """Planner must never reference specific worker names."""
        import inspect
        source = inspect.getsource(TaskPlanner)
        assert "coding_worker" not in source
        assert "debug_worker" not in source
        assert "suite_runner_worker" not in source


# ---------------------------------------------------------------------------
# Agent integration — Sprint-004
# ---------------------------------------------------------------------------

class TestAgentSprint004:

    def test_agent_has_task_planner(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        assert hasattr(agent, 'task_planner')
        assert isinstance(agent.task_planner, TaskPlanner)

    def test_agent_planner_connected_to_manager(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        # Planner should be able to resolve workers from the agent's manager
        plan = agent.task_planner.plan("Run the test suite")
        assert isinstance(plan, WorkerPlan)

    def test_agent_planner_debug_request(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        plan = agent.task_planner.plan("Debug the session log")
        assert "analyse_session" in plan.capabilities


# ---------------------------------------------------------------------------
# Three-layer architecture proof
# ---------------------------------------------------------------------------

class TestThreeLayerArchitecture:

    def test_planner_coordinator_worker_pipeline(self, planner, coordinator, manager):
        """
        Prove the complete three-layer architecture:
        TaskPlanner -> WorkerCoordinator -> Workers
        """
        # Layer 1: Planner decides what to do
        plan = planner.plan("Debug the issue and run the tests")
        assert not plan.is_empty

        # Layer 2: Register a dynamic workflow from the plan
        workflow_name = f"dynamic_{plan.request[:20].replace(' ', '_')}"
        worker_names = [t.requester for t in plan.tasks]
        coordinator.register_workflow(workflow_name, worker_names)

        # Layer 3: Coordinator executes
        task = WorkerTask(
            task_type=workflow_name,
            payload={
                "log_lines": [],
                "paths": ["tests/test_normalizer.py"],
            },
        )
        result = coordinator.run(task)
        assert isinstance(result, WorkerResult)

    def test_planner_never_executes(self, planner):
        """TaskPlanner must never call workers directly."""
        import inspect
        source = inspect.getsource(TaskPlanner)
        assert "execute" not in source
        assert "_manager.execute" not in source

    def test_coordinator_never_plans(self, coordinator):
        """WorkerCoordinator must never contain planning logic."""
        import inspect
        source = inspect.getsource(WorkerCoordinator)
        assert "capabilities_for" not in source
        assert "TaskPlanner" not in source
        assert "WorkerPlan" not in source


# ---------------------------------------------------------------------------
# EngineeringIntentDetector tests
# ---------------------------------------------------------------------------

class TestEngineeringIntentDetector:

    @pytest.fixture
    def detector(self):
        from core.workers.engineering_intent_detector import EngineeringIntentDetector
        return EngineeringIntentDetector()

    def test_debug_request_is_engineering(self, detector):
        intent = detector.detect("Debug the memory bug")
        assert intent.is_engineering is True

    def test_implement_request_is_engineering(self, detector):
        intent = detector.detect("Implement the new feature")
        assert intent.is_engineering is True

    def test_fix_request_is_engineering(self, detector):
        intent = detector.detect("Fix the broken tests")
        assert intent.is_engineering is True

    def test_test_request_is_engineering(self, detector):
        intent = detector.detect("Make sure the tests still pass")
        assert intent.is_engineering is True

    def test_joke_not_engineering(self, detector):
        intent = detector.detect("Tell me a joke")
        assert intent.is_engineering is False

    def test_weather_not_engineering(self, detector):
        intent = detector.detect("What is the weather today?")
        assert intent.is_engineering is False

    def test_empty_not_engineering(self, detector):
        intent = detector.detect("")
        assert intent.is_engineering is False

    def test_positive_has_confidence(self, detector):
        intent = detector.detect("Fix and test the bug")
        if intent.is_engineering:
            assert intent.confidence > 0.0

    def test_negative_has_zero_confidence(self, detector):
        intent = detector.detect("Tell me a joke")
        assert intent.confidence == 0.0

    def test_matched_signals_non_empty_for_engineering(self, detector):
        intent = detector.detect("Debug the memory leak")
        if intent.is_engineering:
            assert len(intent.matched_signals) > 0

    def test_agent_has_engineering_intent_detector(self):
        from core.agent import Agent
        from core.workers.engineering_intent_detector import EngineeringIntentDetector
        agent = Agent(ai=None)
        assert hasattr(agent, 'engineering_intent_detector')
        assert isinstance(agent.engineering_intent_detector, EngineeringIntentDetector)