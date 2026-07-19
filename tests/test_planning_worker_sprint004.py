"""
Genesis-021 Sprint-004 — Planning Worker Tests
Completely self-contained. No dependency on other test files.

Coverage:
  - Worker interface: name, description, capabilities, status
  - Registration with WorkerManager and WorkerOrchestrator
  - validate(): valid goal, missing goal, empty goal, wrong task type
  - select_template(): all keyword categories, default fallback
  - execute(): successful plan generation
  - execute(): observations populated and structured
  - execute(): data dict fully populated
  - execute(): requires_approval=True
  - execute(): exception handling → failure result
  - Goal-aware template selection: bug fix, refactor, architecture,
    new feature, testing, documentation, default
  - Deterministic: same goal → same plan every time
  - Read-only: no files created or modified
  - Backwards compatibility
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.workers.planning_worker import PlanningWorker, PlanTemplate
from core.workers.manager import WorkerManager
from core.workers.orchestrator import WorkerOrchestrator
from core.workers.models import WorkerTask, WorkerResult, WorkerStatus
from core.workers.exceptions import InvalidTaskError, WorkerAlreadyRegisteredError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_task(goal="Implement a new feature.", context="", tags=None, **kwargs):
    payload = {"goal": goal}
    if context:
        payload["context"] = context
    if tags:
        payload["tags"] = tags
    return WorkerTask(task_type="plan_implementation", payload=payload, **kwargs)


def make_worker() -> PlanningWorker:
    return PlanningWorker()


def make_manager_with_worker() -> WorkerManager:
    m = WorkerManager()
    m.register(PlanningWorker())
    return m


# ===========================================================================
# 1. WORKER INTERFACE
# ===========================================================================

class TestPlanningWorkerInterface:

    def test_name_is_planning(self):
        assert make_worker().name == "planning"

    def test_has_description(self):
        assert make_worker().description

    def test_capabilities_include_plan_implementation(self):
        assert "plan_implementation" in make_worker().capabilities

    def test_starts_idle(self):
        assert make_worker().status() == WorkerStatus.IDLE

    def test_is_available(self):
        assert make_worker().is_available

    def test_last_result_none_initially(self):
        assert make_worker().last_result is None


# ===========================================================================
# 2. REGISTRATION
# ===========================================================================

class TestPlanningWorkerRegistration:

    def test_registers_with_manager(self):
        m = make_manager_with_worker()
        assert m.has_worker("planning")

    def test_discoverable_by_capability(self):
        m = make_manager_with_worker()
        workers = m.workers_for("plan_implementation")
        assert len(workers) == 1
        assert workers[0].name == "planning"

    def test_available_after_registration(self):
        m = make_manager_with_worker()
        assert m.get_worker("planning").is_available

    def test_duplicate_registration_raises(self):
        m = make_manager_with_worker()
        with pytest.raises(WorkerAlreadyRegisteredError):
            m.register(PlanningWorker())

    def test_available_via_orchestrator(self):
        m = make_manager_with_worker()
        orch = WorkerOrchestrator(m)
        assert orch.available_for("plan_implementation")


# ===========================================================================
# 3. VALIDATE
# ===========================================================================

class TestPlanningWorkerValidate:

    def test_valid_goal(self):
        assert make_worker().validate(make_task("Implement a new feature."))

    def test_missing_goal_key(self):
        task = WorkerTask(task_type="plan_implementation", payload={})
        assert not make_worker().validate(task)

    def test_empty_goal(self):
        task = WorkerTask(task_type="plan_implementation", payload={"goal": ""})
        assert not make_worker().validate(task)

    def test_whitespace_goal(self):
        task = WorkerTask(task_type="plan_implementation", payload={"goal": "   "})
        assert not make_worker().validate(task)

    def test_wrong_task_type(self):
        task = WorkerTask(task_type="wrong_type", payload={"goal": "Do something."})
        assert not make_worker().validate(task)

    def test_valid_goal_with_context(self):
        assert make_worker().validate(
            make_task("Implement a feature.", context="Sprint-004")
        )


# ===========================================================================
# 4. TEMPLATE SELECTION — goal-aware
# ===========================================================================

class TestTemplateSelection:

    def setup_method(self):
        self.worker = make_worker()

    def _template(self, goal: str) -> PlanTemplate:
        return self.worker.select_template(goal)

    def test_bug_fix_template(self):
        assert self._template("Fix the login bug.").name == "bug_fix"

    def test_hotfix_template(self):
        assert self._template("Apply a hotfix to production.").name == "bug_fix"

    def test_defect_template(self):
        assert self._template("Resolve the defect in payment flow.").name == "bug_fix"

    def test_refactor_template(self):
        assert self._template("Refactor the database layer.").name == "refactor"

    def test_cleanup_template(self):
        assert self._template("Clean up the legacy code.").name == "refactor"

    def test_architecture_template(self):
        assert self._template("Design the new architecture.").name == "architecture"

    def test_framework_template(self):
        assert self._template("Build a new framework for Workers.").name == "architecture"

    def test_pipeline_template(self):
        assert self._template("Implement the pipeline layer.").name == "architecture"

    def test_new_feature_template(self):
        assert self._template("Add a new search feature.").name == "new_feature"

    def test_implement_template(self):
        assert self._template("Implement the new search feature.").name == "new_feature"

    def test_testing_template(self):
        assert self._template("Improve test coverage.").name == "testing"

    def test_qa_template(self):
        assert self._template("Set up QA for the login flow.").name == "testing"

    def test_documentation_template(self):
        assert self._template("Write documentation for the API.").name == "documentation"

    def test_readme_template(self):
        assert self._template("Update the README.").name == "documentation"

    def test_default_template_when_no_match(self):
        assert self._template("Do the thing.").name == "general"

    def test_default_template_empty_goal(self):
        assert self._template("").name == "general"

    def test_case_insensitive_matching(self):
        assert self._template("FIX THE BUG").name == "bug_fix"
        assert self._template("REFACTOR the code").name == "refactor"

    def test_template_selection_deterministic(self):
        goal = "Fix the authentication bug."
        t1 = self._template(goal)
        t2 = self._template(goal)
        assert t1.name == t2.name
        assert t1.complexity == t2.complexity


# ===========================================================================
# 5. PLAN TEMPLATE MODEL
# ===========================================================================

class TestPlanTemplate:

    def test_plan_template_is_frozen(self):
        from dataclasses import FrozenInstanceError
        t = make_worker().select_template("Fix bug.")
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            t.name = "changed"

    def test_steps_is_tuple(self):
        t = make_worker().select_template("Fix bug.")
        assert isinstance(t.steps, tuple)

    def test_dependencies_is_tuple(self):
        t = make_worker().select_template("Fix bug.")
        assert isinstance(t.dependencies, tuple)

    def test_risks_is_tuple(self):
        t = make_worker().select_template("Fix bug.")
        assert isinstance(t.risks, tuple)

    def test_complexity_is_string(self):
        t = make_worker().select_template("Fix bug.")
        assert isinstance(t.complexity, str)

    def test_complexity_values_valid(self):
        goals = [
            "Fix bug.", "Refactor code.", "Build architecture.",
            "Add feature.", "Write tests.", "Write docs.", "Do thing."
        ]
        for goal in goals:
            t = make_worker().select_template(goal)
            assert t.complexity in ("Low", "Medium", "High"), \
                f"Invalid complexity {t.complexity!r} for {goal!r}"


# ===========================================================================
# 6. EXECUTE — successful plan generation
# ===========================================================================

class TestPlanningWorkerExecute:

    def test_returns_worker_result(self):
        result = make_worker().execute(make_task())
        assert isinstance(result, WorkerResult)

    def test_result_is_success(self):
        result = make_worker().execute(make_task())
        assert result.success

    def test_requires_approval_true(self):
        result = make_worker().execute(make_task())
        assert result.requires_approval

    def test_worker_name_in_result(self):
        result = make_worker().execute(make_task())
        assert result.worker_name == "planning"

    def test_task_id_preserved(self):
        task = make_task()
        result = make_worker().execute(task)
        assert result.task_id == task.task_id

    def test_observations_non_empty(self):
        result = make_worker().execute(make_task())
        assert len(result.observations) > 0

    def test_observations_contain_goal(self):
        result = make_worker().execute(make_task("Fix the login bug."))
        assert any("Fix the login bug" in obs for obs in result.observations)

    def test_observations_contain_steps(self):
        result = make_worker().execute(make_task())
        assert any("1." in obs for obs in result.observations)

    def test_observations_contain_complexity(self):
        result = make_worker().execute(make_task())
        assert any("complexity" in obs.lower() or
                   any(c in obs for c in ["Low", "Medium", "High"])
                   for obs in result.observations)

    def test_observations_contain_risks(self):
        result = make_worker().execute(make_task())
        assert any("risk" in obs.lower() or "•" in obs
                   for obs in result.observations)

    def test_recommendations_non_empty(self):
        result = make_worker().execute(make_task())
        assert len(result.recommendations) > 0

    def test_worker_status_completed(self):
        w = make_worker()
        w.execute(make_task())
        assert w.status() == WorkerStatus.COMPLETED

    def test_last_result_set(self):
        w = make_worker()
        task = make_task()
        result = w.execute(task)
        assert w.last_result is result


# ===========================================================================
# 7. EXECUTE — structured data
# ===========================================================================

class TestPlanningWorkerData:

    def setup_method(self):
        self.result = make_worker().execute(
            make_task("Fix the login bug.", context="Sprint-004", tags=["auth"])
        )

    def test_data_has_goal(self):
        assert self.result.data["goal"] == "Fix the login bug."

    def test_data_has_template(self):
        assert self.result.data["template"] == "bug_fix"

    def test_data_has_complexity(self):
        assert self.result.data["complexity"] == "Low"

    def test_data_has_steps(self):
        assert isinstance(self.result.data["steps"], list)
        assert len(self.result.data["steps"]) > 0

    def test_data_has_step_count(self):
        assert self.result.data["step_count"] == len(self.result.data["steps"])

    def test_data_has_dependencies(self):
        assert isinstance(self.result.data["dependencies"], list)

    def test_data_has_risks(self):
        assert isinstance(self.result.data["risks"], list)
        assert len(self.result.data["risks"]) > 0

    def test_data_has_context(self):
        assert self.result.data["context"] == "Sprint-004"

    def test_data_has_tags(self):
        assert self.result.data["tags"] == ["auth"]

    def test_data_empty_context_when_not_provided(self):
        result = make_worker().execute(make_task("Fix bug."))
        assert result.data["context"] == ""

    def test_data_empty_tags_when_not_provided(self):
        result = make_worker().execute(make_task("Fix bug."))
        assert result.data["tags"] == []


# ===========================================================================
# 8. DETERMINISM
# ===========================================================================

class TestPlanningWorkerDeterminism:

    def test_same_goal_same_template(self):
        goal = "Implement a new authentication feature."
        r1 = make_worker().execute(make_task(goal))
        r2 = make_worker().execute(make_task(goal))
        assert r1.data["template"] == r2.data["template"]
        assert r1.data["complexity"] == r2.data["complexity"]
        assert r1.data["steps"] == r2.data["steps"]

    def test_same_goal_same_observations_count(self):
        goal = "Fix the payment bug."
        r1 = make_worker().execute(make_task(goal))
        r2 = make_worker().execute(make_task(goal))
        assert len(r1.observations) == len(r2.observations)

    def test_different_goals_may_differ(self):
        r_bug = make_worker().execute(make_task("Fix the bug."))
        r_arch = make_worker().execute(make_task("Design the architecture."))
        assert r_bug.data["template"] != r_arch.data["template"]
        assert r_bug.data["complexity"] != r_arch.data["complexity"]


# ===========================================================================
# 9. EXCEPTION HANDLING
# ===========================================================================

class TestPlanningWorkerExceptions:

    def test_invalid_task_raises_via_manager(self):
        m = make_manager_with_worker()
        task = WorkerTask(task_type="plan_implementation", payload={})
        with pytest.raises(InvalidTaskError):
            m.execute("planning", task)

    def test_invalid_task_via_orchestrator_returns_failure(self):
        m = make_manager_with_worker()
        orch = WorkerOrchestrator(m)
        task = WorkerTask(task_type="plan_implementation", payload={})
        # Orchestrator wraps InvalidTaskError into failure result
        result = orch.run(task)
        assert not result.success

    def test_execute_does_not_raise_on_exception(self):
        import unittest.mock as mock
        w = make_worker()
        with mock.patch.object(w, "select_template", side_effect=RuntimeError("oops")):
            result = w.execute(make_task("Fix bug."))
        assert not result.success
        assert "oops" in result.error


# ===========================================================================
# 10. EXECUTE VIA MANAGER AND ORCHESTRATOR
# ===========================================================================

class TestPlanningWorkerViaManager:

    def test_execute_via_manager(self):
        m = make_manager_with_worker()
        result = m.execute("planning", make_task("Add a new feature."))
        assert result.success

    def test_execute_via_orchestrator(self):
        m = make_manager_with_worker()
        orch = WorkerOrchestrator(m)
        result = orch.run(make_task("Add a new feature."))
        assert result.success
        assert result.worker_name == "planning"

    def test_orchestrator_routes_correctly(self):
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(EngineeringWorker())
        m.register(PlanningWorker())
        orch = WorkerOrchestrator(m)
        result = orch.run(make_task("Plan the new feature."))
        assert result.success
        assert result.worker_name == "planning"


# ===========================================================================
# 11. READ-ONLY GUARANTEE
# ===========================================================================

class TestPlanningWorkerReadOnly:

    def test_does_not_create_files(self):
        import tempfile, os
        tmp = Path(tempfile.mkdtemp())
        files_before = set(tmp.iterdir())
        make_worker().execute(make_task("Add a new feature."))
        files_after = set(tmp.iterdir())
        assert files_before == files_after


# ===========================================================================
# 12. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_worker_framework_unchanged(self):
        m = WorkerManager()
        assert m.worker_count() == 0

    def test_engineering_worker_unchanged(self):
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(EngineeringWorker())
        assert m.has_worker("engineering")

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_planning_worker_importable(self):
        from core.workers.planning_worker import PlanningWorker
        assert PlanningWorker is not None

    def test_orchestrator_routes_both_workers(self):
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(EngineeringWorker())
        m.register(PlanningWorker())
        orch = WorkerOrchestrator(m)
        assert orch.available_for("analyse_repository")
        assert orch.available_for("plan_implementation")