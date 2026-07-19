"""
Genesis-021 Sprint-005 — Worker Coordinator Tests
Completely self-contained. No dependency on other test files.

Coverage:
  - run(): successful single-worker workflow
  - run(): successful multi-worker workflow
  - run(): no workflow registered → failure result
  - run(): worker not registered → failure result
  - run(): worker returns failure → stops, returns failure
  - run(): exception in worker → failure result, never raises
  - run(): partial results preserved in failure data
  - merge_context(): previous data merged into next task payload
  - merge_context(): original payload fields preserved
  - _aggregate(): observations from all workers combined
  - _aggregate(): data contains workflow metadata
  - _aggregate(): requires_approval=True always
  - register_workflow(): adds new workflow
  - register_workflow(): replaces existing workflow
  - register_workflow(): empty args raise ValueError
  - has_workflow(), workflow_for(), available_workflows()
  - summary() dict structure
  - Default workflows present
  - Integration: PlanningWorker + EngineeringWorker real workflow
  - Never raises guarantee
  - Backwards compatibility
"""

import sys
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.workers.coordinator import WorkerCoordinator
from core.workers.manager import WorkerManager
from core.workers.base import Worker
from core.workers.models import WorkerTask, WorkerResult, WorkerStatus
from core.workers.exceptions import WorkerAlreadyRegisteredError


# ---------------------------------------------------------------------------
# Concrete test workers
# ---------------------------------------------------------------------------

class EchoWorker(Worker):
    @property
    def name(self) -> str: return "echo"
    @property
    def description(self) -> str: return "Echoes."
    @property
    def capabilities(self) -> list[str]: return ["echo_task"]
    def validate(self, task): return True
    def execute(self, task):
        self._begin(task)
        return self._succeed(WorkerResult(
            task_id=task.task_id, worker_name=self.name,
            success=True,
            observations=("Echo observation.",),
            recommendations=("Echo recommendation.",),
            requires_approval=False,
            data={"echo": "done", "payload_keys": list(task.payload.keys())},
        ))


class SecondWorker(Worker):
    @property
    def name(self) -> str: return "second"
    @property
    def description(self) -> str: return "Second step."
    @property
    def capabilities(self) -> list[str]: return ["second_task"]
    def validate(self, task): return True
    def execute(self, task):
        self._begin(task)
        has_context = "previous_result_data" in task.payload
        return self._succeed(WorkerResult(
            task_id=task.task_id, worker_name=self.name,
            success=True,
            observations=(f"Second observation. Has context: {has_context}",),
            requires_approval=False,
            data={"second": "done", "received_context": has_context},
        ))


class FailingWorker(Worker):
    @property
    def name(self) -> str: return "failing"
    @property
    def description(self) -> str: return "Always fails."
    @property
    def capabilities(self) -> list[str]: return ["fail_task"]
    def validate(self, task): return True
    def execute(self, task):
        self._begin(task)
        return self._fail(task.task_id, "Intentional failure.")


class RaisingWorker(Worker):
    @property
    def name(self) -> str: return "raising"
    @property
    def description(self) -> str: return "Always raises."
    @property
    def capabilities(self) -> list[str]: return ["raise_task"]
    def validate(self, task): return True
    def execute(self, task):
        self._begin(task)
        raise RuntimeError("Deliberate exception.")


def make_task(task_type="echo_task", payload=None, **kwargs):
    return WorkerTask(task_type=task_type, payload=payload or {}, **kwargs)


def make_manager(*workers) -> WorkerManager:
    m = WorkerManager()
    for w in workers:
        m.register(w)
    return m


def make_coordinator(*workers, extra_workflows=None) -> WorkerCoordinator:
    m = make_manager(*workers)
    c = WorkerCoordinator(m)
    if extra_workflows:
        for task_type, names in extra_workflows.items():
            c.register_workflow(task_type, names)
    return c


# ===========================================================================
# 1. WORKFLOW REGISTRY
# ===========================================================================

class TestWorkflowRegistry:

    def test_default_workflows_present(self):
        c = WorkerCoordinator(make_manager())
        assert c.has_workflow("engineering_plan")
        assert c.has_workflow("analyse_repository")
        assert c.has_workflow("plan_implementation")

    def test_register_new_workflow(self):
        c = WorkerCoordinator(make_manager())
        c.register_workflow("custom_task", ["echo", "second"])
        assert c.has_workflow("custom_task")

    def test_register_replaces_existing(self):
        c = WorkerCoordinator(make_manager())
        c.register_workflow("engineering_plan", ["echo"])
        assert c.workflow_for("engineering_plan") == ["echo"]

    def test_register_empty_task_type_raises(self):
        c = WorkerCoordinator(make_manager())
        with pytest.raises(ValueError):
            c.register_workflow("", ["echo"])

    def test_register_empty_workers_raises(self):
        c = WorkerCoordinator(make_manager())
        with pytest.raises(ValueError):
            c.register_workflow("custom", [])

    def test_has_workflow_false_for_unknown(self):
        c = WorkerCoordinator(make_manager())
        assert not c.has_workflow("nonexistent_task")

    def test_workflow_for_returns_copy(self):
        c = WorkerCoordinator(make_manager())
        names = c.workflow_for("engineering_plan")
        names.clear()
        assert len(c.workflow_for("engineering_plan")) > 0

    def test_workflow_for_unknown_returns_empty(self):
        c = WorkerCoordinator(make_manager())
        assert c.workflow_for("unknown") == []

    def test_available_workflows_includes_defaults(self):
        c = WorkerCoordinator(make_manager())
        workflows = c.available_workflows()
        assert "engineering_plan" in workflows
        assert "plan_implementation" in workflows


# ===========================================================================
# 2. run() — successful single-worker workflow
# ===========================================================================

class TestCoordinatorRunSingle:

    def test_single_worker_success(self):
        c = make_coordinator(EchoWorker(), extra_workflows={"echo_task": ["echo"]})
        result = c.run(make_task("echo_task"))
        assert result.success

    def test_result_worker_name_is_coordinator(self):
        c = make_coordinator(EchoWorker(), extra_workflows={"echo_task": ["echo"]})
        result = c.run(make_task("echo_task"))
        assert result.worker_name == "coordinator"

    def test_task_id_preserved(self):
        c = make_coordinator(EchoWorker(), extra_workflows={"echo_task": ["echo"]})
        task = make_task("echo_task")
        result = c.run(task)
        assert result.task_id == task.task_id

    def test_requires_approval_true(self):
        c = make_coordinator(EchoWorker(), extra_workflows={"echo_task": ["echo"]})
        result = c.run(make_task("echo_task"))
        assert result.requires_approval

    def test_observations_contain_worker_header(self):
        c = make_coordinator(EchoWorker(), extra_workflows={"echo_task": ["echo"]})
        result = c.run(make_task("echo_task"))
        assert any("Echo" in obs and "Worker" in obs for obs in result.observations)

    def test_observations_contain_worker_output(self):
        c = make_coordinator(EchoWorker(), extra_workflows={"echo_task": ["echo"]})
        result = c.run(make_task("echo_task"))
        assert any("Echo observation" in obs for obs in result.observations)

    def test_data_has_workflow_metadata(self):
        c = make_coordinator(EchoWorker(), extra_workflows={"echo_task": ["echo"]})
        result = c.run(make_task("echo_task"))
        assert result.data["workflow"] == "echo_task"
        assert result.data["steps_completed"] == 1
        assert result.data["steps_total"] == 1
        assert "echo" in result.data["workers_executed"]

    def test_data_has_worker_results(self):
        c = make_coordinator(EchoWorker(), extra_workflows={"echo_task": ["echo"]})
        result = c.run(make_task("echo_task"))
        assert "echo" in result.data["results"]


# ===========================================================================
# 3. run() — successful multi-worker workflow
# ===========================================================================

class TestCoordinatorRunMulti:

    def setup_method(self):
        self.c = make_coordinator(
            EchoWorker(), SecondWorker(),
            extra_workflows={"two_step": ["echo", "second"]}
        )
        self.result = self.c.run(make_task("two_step"))

    def test_both_workers_succeed(self):
        assert self.result.success

    def test_steps_completed_is_two(self):
        assert self.result.data["steps_completed"] == 2

    def test_both_workers_in_executed_list(self):
        executed = self.result.data["workers_executed"]
        assert "echo" in executed
        assert "second" in executed

    def test_both_results_in_data(self):
        assert "echo" in self.result.data["results"]
        assert "second" in self.result.data["results"]

    def test_observations_from_both_workers(self):
        obs_text = " ".join(self.result.observations)
        assert "Echo observation" in obs_text
        assert "Second observation" in obs_text

    def test_recommendations_from_both_workers(self):
        recs_text = " ".join(self.result.recommendations)
        assert "Echo recommendation" in recs_text

    def test_headers_for_both_workers(self):
        obs_text = " ".join(self.result.observations)
        assert "Echo Worker" in obs_text
        assert "Second Worker" in obs_text

    def test_requires_approval_true(self):
        assert self.result.requires_approval


# ===========================================================================
# 4. run() — failure cases
# ===========================================================================

class TestCoordinatorRunFailure:

    def test_no_workflow_returns_failure(self):
        c = WorkerCoordinator(make_manager())
        result = c.run(make_task("unknown_workflow_xyz"))
        assert not result.success
        assert result.error

    def test_no_workflow_does_not_raise(self):
        c = WorkerCoordinator(make_manager())
        try:
            c.run(make_task("unknown_workflow"))
        except Exception as e:
            pytest.fail(f"run() raised: {e}")

    def test_missing_worker_returns_failure(self):
        c = WorkerCoordinator(make_manager())
        c.register_workflow("missing_step", ["nonexistent_worker"])
        result = c.run(make_task("missing_step"))
        assert not result.success
        assert "not registered" in result.error.lower()

    def test_worker_failure_stops_workflow(self):
        c = make_coordinator(
            FailingWorker(), SecondWorker(),
            extra_workflows={"fail_then_second": ["failing", "second"]}
        )
        result = c.run(make_task("fail_then_second"))
        assert not result.success
        assert "second" not in result.data.get("workers_executed", [])

    def test_worker_failure_preserves_partial_results(self):
        c = make_coordinator(
            EchoWorker(), FailingWorker(),
            extra_workflows={"echo_then_fail": ["echo", "failing"]}
        )
        result = c.run(make_task("echo_then_fail"))
        assert not result.success
        assert "echo" in result.data.get("partial_results", {})

    def test_worker_exception_returns_failure(self):
        c = make_coordinator(
            RaisingWorker(),
            extra_workflows={"raise_task": ["raising"]}
        )
        result = c.run(make_task("raise_task"))
        assert not result.success
        assert result.error

    def test_worker_exception_does_not_propagate(self):
        c = make_coordinator(
            RaisingWorker(),
            extra_workflows={"raise_task": ["raising"]}
        )
        try:
            c.run(make_task("raise_task"))
        except Exception as e:
            pytest.fail(f"run() propagated exception: {e}")

    def test_failure_result_task_id_preserved(self):
        c = WorkerCoordinator(make_manager())
        task = make_task("unknown")
        result = c.run(task)
        assert result.task_id == task.task_id

    def test_failure_requires_approval_false(self):
        c = WorkerCoordinator(make_manager())
        result = c.run(make_task("unknown"))
        assert not result.requires_approval


# ===========================================================================
# 5. merge_context()
# ===========================================================================

class TestMergeContext:

    def setup_method(self):
        self.c = WorkerCoordinator(make_manager())

    def _make_result(self, data=None, worker_name="echo"):
        return WorkerResult(
            task_id="t-1", worker_name=worker_name,
            success=True, data=data or {"key": "value"},
        )

    def test_previous_data_in_next_payload(self):
        result = self._make_result({"answer": 42})
        task = make_task("next_task", payload={"goal": "Do something."})
        next_task = self.c.merge_context(result, task)
        assert "previous_result_data" in next_task.payload
        assert next_task.payload["previous_result_data"]["answer"] == 42

    def test_previous_worker_name_in_next_payload(self):
        result = self._make_result(worker_name="planning")
        task = make_task("next_task")
        next_task = self.c.merge_context(result, task)
        assert next_task.payload["previous_worker"] == "planning"

    def test_original_payload_preserved(self):
        result = self._make_result()
        task = make_task("next_task", payload={"goal": "Keep me.", "root_path": "/tmp"})
        next_task = self.c.merge_context(result, task)
        assert next_task.payload["goal"] == "Keep me."
        assert next_task.payload["root_path"] == "/tmp"

    def test_task_type_preserved(self):
        result = self._make_result()
        task = make_task("original_type")
        next_task = self.c.merge_context(result, task)
        assert next_task.task_type == "original_type"

    def test_task_id_preserved(self):
        result = self._make_result()
        task = make_task()
        next_task = self.c.merge_context(result, task)
        assert next_task.task_id == task.task_id

    def test_second_worker_receives_context(self):
        """SecondWorker checks for previous_result_data in payload."""
        c = make_coordinator(
            EchoWorker(), SecondWorker(),
            extra_workflows={"two_step": ["echo", "second"]}
        )
        result = c.run(make_task("two_step"))
        assert result.success
        second_data = result.data["results"]["second"]
        assert second_data["received_context"] is True


# ===========================================================================
# 6. summary()
# ===========================================================================

class TestCoordinatorSummary:

    def test_summary_is_dict(self):
        c = WorkerCoordinator(make_manager())
        assert isinstance(c.summary(), dict)

    def test_summary_has_workflows(self):
        c = WorkerCoordinator(make_manager())
        s = c.summary()
        assert "registered_workflows" in s
        assert "engineering_plan" in s["registered_workflows"]

    def test_summary_worker_count(self):
        c = make_coordinator(EchoWorker())
        assert c.summary()["worker_count"] == 1

    def test_summary_available_workers(self):
        c = make_coordinator(EchoWorker())
        assert "echo" in c.summary()["available_workers"]


# ===========================================================================
# 7. Never raises guarantee
# ===========================================================================

class TestCoordinatorNeverRaises:

    def test_unknown_workflow_no_exception(self):
        c = WorkerCoordinator(make_manager())
        try:
            c.run(make_task("totally_unknown_xyz"))
        except Exception as e:
            pytest.fail(f"run() raised: {e}")

    def test_missing_worker_no_exception(self):
        c = WorkerCoordinator(make_manager())
        c.register_workflow("missing", ["nonexistent"])
        try:
            c.run(make_task("missing"))
        except Exception as e:
            pytest.fail(f"run() raised: {e}")

    def test_raising_worker_no_propagation(self):
        c = make_coordinator(
            RaisingWorker(), extra_workflows={"raise_task": ["raising"]}
        )
        try:
            c.run(make_task("raise_task"))
        except Exception as e:
            pytest.fail(f"run() propagated: {e}")


# ===========================================================================
# 8. Integration — real workers
# ===========================================================================

class TestCoordinatorIntegration:

    def test_engineering_plan_workflow(self):
        """PlanningWorker → EngineeringWorker → aggregated result."""
        from core.workers.planning_worker import PlanningWorker
        from core.workers.engineering_worker import EngineeringWorker

        m = WorkerManager()
        m.register(PlanningWorker())
        m.register(EngineeringWorker())
        c = WorkerCoordinator(m)

        task = WorkerTask(
            task_type="engineering_plan",
            payload={
                "goal": "Add a new feature to Jarvis.",
                "root_path": str(REPO_ROOT),
            }
        )
        result = c.run(task)

        assert result.success
        assert result.worker_name == "coordinator"
        assert result.requires_approval
        assert result.data["steps_completed"] == 2
        assert "planning" in result.data["workers_executed"]
        assert "engineering" in result.data["workers_executed"]
        assert "planning" in result.data["results"]
        assert "engineering" in result.data["results"]

    def test_plan_only_workflow(self):
        from core.workers.planning_worker import PlanningWorker
        m = WorkerManager()
        m.register(PlanningWorker())
        c = WorkerCoordinator(m)
        task = WorkerTask(
            task_type="plan_implementation",
            payload={"goal": "Fix the authentication bug."}
        )
        result = c.run(task)
        assert result.success
        assert result.data["steps_completed"] == 1

    def test_analyse_only_workflow(self):
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(EngineeringWorker())
        c = WorkerCoordinator(m)
        task = WorkerTask(
            task_type="analyse_repository",
            payload={"root_path": str(REPO_ROOT)}
        )
        result = c.run(task)
        assert result.success
        assert result.data["steps_completed"] == 1

    def test_engineering_plan_observations_from_both(self):
        from core.workers.planning_worker import PlanningWorker
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(PlanningWorker())
        m.register(EngineeringWorker())
        c = WorkerCoordinator(m)
        task = WorkerTask(
            task_type="engineering_plan",
            payload={"goal": "Refactor the codebase.", "root_path": str(REPO_ROOT)}
        )
        result = c.run(task)
        obs = " ".join(result.observations)
        assert "Planning Worker" in obs
        assert "Engineering Worker" in obs


# ===========================================================================
# 9. Backwards compatibility
# ===========================================================================

class TestBackwardsCompatibility:

    def test_worker_framework_unchanged(self):
        m = WorkerManager()
        assert m.worker_count() == 0

    def test_orchestrator_unchanged(self):
        from core.workers.orchestrator import WorkerOrchestrator
        m = make_manager(EchoWorker())
        orch = WorkerOrchestrator(m)
        assert orch.available_for("echo_task")

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_coordinator_importable(self):
        from core.workers.coordinator import WorkerCoordinator
        assert WorkerCoordinator is not None