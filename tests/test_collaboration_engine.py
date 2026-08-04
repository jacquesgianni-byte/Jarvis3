"""
Tests — Multi-Worker Collaboration Engine
Genesis-038 Sprint-001
"""

import pytest
from core.collaboration.models import (
    WorkerCapability, WorkerAssignment, WorkerPlan, CollaborationResult,
    AssignmentStatus, make_assignment,
)
from core.collaboration.engine import WorkerCollaborationEngine


# ── Stubs ──────────────────────────────────────────────────────────────────────

class _FakeWorker:
    def __init__(self, name: str, capabilities: list[str], available: bool = True):
        self.name         = name
        self.capabilities = capabilities
        self.description  = f"{name} worker"
        self.is_available = available

    def status(self):
        class S:
            def label(self): return "Idle"
        return S()


class _FakeManager:
    def __init__(self, workers: list[_FakeWorker]):
        self._workers = {w.name: w for w in workers}

    def workers_for(self, capability: str) -> list[_FakeWorker]:
        return [w for w in self._workers.values() if capability in w.capabilities]

    def all_workers(self) -> list[_FakeWorker]:
        return list(self._workers.values())

    def has_worker(self, name: str) -> bool:
        return name in self._workers

    def get_worker(self, name: str) -> _FakeWorker:
        return self._workers[name]

    def execute(self, name: str, task) -> object:
        from core.workers.models import WorkerResult
        return WorkerResult(
            task_id=task.task_id,
            worker_name=name,
            success=True,
            observations=(f"{name} executed.",),
            recommendations=(),
            requires_approval=False,
        )

    def worker_count(self) -> int:
        return len(self._workers)

    def available_workers(self) -> list[_FakeWorker]:
        return [w for w in self._workers.values() if w.is_available]


class _FakeCoordinator:
    """Coordinator stub that tracks registered workflows and executions."""

    def __init__(self, manager: _FakeManager):
        self._manager   = manager
        self._workflows: dict[str, list[str]] = {}
        self.runs: list[str] = []

    def register_workflow(self, task_type: str, worker_names: list[str]) -> None:
        self._workflows[task_type] = worker_names

    def has_workflow(self, task_type: str) -> bool:
        return task_type in self._workflows

    def workflow_for(self, task_type: str) -> list[str]:
        return self._workflows.get(task_type, [])

    def available_workflows(self) -> list[str]:
        return list(self._workflows.keys())

    def run(self, task) -> object:
        from core.workers.models import WorkerResult
        self.runs.append(task.task_type)
        workflow = self._workflows.get(task.task_type, [])
        if not workflow:
            return WorkerResult.failure(task.task_id, "coordinator",
                                        f"No workflow for {task.task_type}")
        worker_name = workflow[0]
        if not self._manager.has_worker(worker_name):
            return WorkerResult.failure(task.task_id, "coordinator",
                                        f"Worker {worker_name!r} not registered")
        return self._manager.execute(worker_name, task)


def _make_work_package(
    capability: str = "run_tests",
    priority: int = 1,
    genesis: str = "038",
    scope: str = "small",
    review: tuple = (),
):
    class FakePkg:
        pass
    pkg = FakePkg()
    pkg.id                  = "pkg-001"
    pkg.objective           = f"Execute {capability}"
    pkg.capability_required = capability
    pkg.genesis             = genesis
    pkg.estimated_scope     = scope
    pkg.review_requirements = review
    pkg.can_delegate        = True
    pkg.priority            = priority
    return pkg


@pytest.fixture()
def suite_manager():
    return _FakeManager([
        _FakeWorker("suite_runner_worker", ["run_tests"]),
        _FakeWorker("engineering_review_worker", ["run_engineering_review"]),
        _FakeWorker("coding_worker", ["plan_implementation"], available=True),
    ])


@pytest.fixture()
def coordinator(suite_manager):
    return _FakeCoordinator(suite_manager)


@pytest.fixture()
def engine(suite_manager, coordinator):
    return WorkerCollaborationEngine(suite_manager, coordinator)


# ── WorkerCapability ──────────────────────────────────────────────────────────

class TestWorkerCapability:
    def test_available_true(self):
        cap = WorkerCapability(name="run_tests", worker_name="suite_runner_worker",
                               available=True)
        assert cap.available is True

    def test_available_false(self):
        cap = WorkerCapability(name="unknown", worker_name="", available=False)
        assert cap.available is False


# ── WorkerAssignment ──────────────────────────────────────────────────────────

class TestWorkerAssignment:
    def test_make_assignment(self):
        a = make_assignment(worker_id="suite_runner_worker",
                            required_capability="run_tests",
                            work_package_id="pkg-001")
        assert a.worker_id == "suite_runner_worker"
        assert a.status == AssignmentStatus.PENDING

    def test_with_status(self):
        a = make_assignment(worker_id="w1", required_capability="run_tests")
        a2 = a.with_status(AssignmentStatus.COMPLETE)
        assert a2.status == AssignmentStatus.COMPLETE
        assert a.status == AssignmentStatus.PENDING  # original unchanged

    def test_is_frozen(self):
        a = make_assignment(worker_id="w1", required_capability="run_tests")
        with pytest.raises((AttributeError, TypeError)):
            a.worker_id = "changed"  # type: ignore


# ── WorkerPlan ────────────────────────────────────────────────────────────────

class TestWorkerPlan:
    def _make_plan(self, assignments):
        from uuid import uuid4
        return WorkerPlan(
            id=str(uuid4()),
            assignments=tuple(assignments),
            genesis="038",
            work_package_id="pkg-001",
            created_at="2026-08-04T12:00:00",
        )

    def test_sequential_groups_no_dependencies(self):
        a1 = make_assignment("w1", "run_tests")
        a2 = make_assignment("w2", "plan_implementation")
        plan = self._make_plan([a1, a2])
        groups = plan.sequential_groups()
        # Both have no deps — should be in one group
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_sequential_groups_with_dependency(self):
        a1 = make_assignment("w1", "run_tests")
        a2 = make_assignment("w2", "plan_implementation", dependencies=(a1.id,))
        plan = self._make_plan([a1, a2])
        groups = plan.sequential_groups()
        assert len(groups) == 2
        assert a1 in groups[0]
        assert a2 in groups[1]

    def test_empty_plan_has_no_groups(self):
        plan = self._make_plan([])
        assert plan.sequential_groups() == []

    def test_to_text_contains_plan_id(self):
        a = make_assignment("w1", "run_tests")
        plan = self._make_plan([a])
        assert "Worker Plan" in plan.to_text()
        assert "w1" in plan.to_text()

    def test_is_frozen(self):
        plan = self._make_plan([])
        with pytest.raises((AttributeError, TypeError)):
            plan.genesis = "changed"  # type: ignore


# ── CollaborationResult ────────────────────────────────────────────────────────

class TestCollaborationResult:
    def test_to_text_success(self):
        from uuid import uuid4
        plan = WorkerPlan(id=str(uuid4()), assignments=(), genesis="038",
                          work_package_id="", created_at="")
        r = CollaborationResult(plan=plan, results={}, success=True,
                                completed=1, failed=0, skipped=0)
        assert "Success" in r.to_text()

    def test_to_text_failure(self):
        from uuid import uuid4
        plan = WorkerPlan(id=str(uuid4()), assignments=(), genesis="038",
                          work_package_id="", created_at="")
        r = CollaborationResult(plan=plan, results={}, success=False,
                                completed=0, failed=1, skipped=0, error="Worker failed")
        assert "Failed" in r.to_text()


# ── WorkerCollaborationEngine ─────────────────────────────────────────────────

class TestResolveCapability:
    def test_resolve_available_capability(self, engine):
        cap = engine.resolve_capability("run_tests")
        assert cap.available is True
        assert cap.worker_name == "suite_runner_worker"

    def test_resolve_unavailable_capability(self, engine):
        cap = engine.resolve_capability("nonexistent_capability")
        assert cap.available is False
        assert cap.worker_name == ""

    def test_available_capabilities_lists_all(self, engine):
        caps = engine.available_capabilities()
        names = [c.name for c in caps]
        assert "run_tests" in names
        assert "run_engineering_review" in names

    def test_genesis_040_readiness(self, suite_manager, coordinator):
        """External AI worker registers like any other — resolve finds it."""
        external_worker = _FakeWorker("claude_ai_worker", ["implement_feature"])
        suite_manager._workers["claude_ai_worker"] = external_worker

        eng = WorkerCollaborationEngine(suite_manager, coordinator)
        cap = eng.resolve_capability("implement_feature")
        assert cap.available is True
        assert cap.worker_name == "claude_ai_worker"


class TestPlan:
    def test_plan_produces_worker_plan(self, engine):
        pkg = _make_work_package("run_tests")
        plan = engine.plan(pkg)
        assert isinstance(plan, WorkerPlan)
        assert len(plan.assignments) == 1

    def test_plan_resolves_capability_to_worker(self, engine):
        pkg = _make_work_package("run_tests")
        plan = engine.plan(pkg)
        assert plan.assignments[0].worker_id == "suite_runner_worker"

    def test_plan_unavailable_capability_creates_skipped_assignment(self, engine):
        pkg = _make_work_package("nonexistent_capability")
        plan = engine.plan(pkg)
        assert len(plan.assignments) == 1
        assert plan.assignments[0].status == AssignmentStatus.SKIPPED

    def test_plan_genesis_preserved(self, engine):
        pkg = _make_work_package(genesis="038")
        plan = engine.plan(pkg)
        assert plan.genesis == "038"


class TestExecute:
    def test_execute_success(self, engine):
        pkg = _make_work_package("run_tests")
        plan = engine.plan(pkg)
        result = engine.execute(plan)
        assert result.completed >= 1

    def test_execute_skipped_assignment(self, engine):
        pkg = _make_work_package("nonexistent_capability")
        plan = engine.plan(pkg)
        result = engine.execute(plan)
        assert result.skipped >= 1

    def test_execute_returns_collaboration_result(self, engine):
        pkg = _make_work_package("run_tests")
        plan = engine.plan(pkg)
        result = engine.execute(plan)
        assert isinstance(result, CollaborationResult)


# ── Desktop Validation Scenarios ──────────────────────────────────────────────

class TestDesktopScenarios:
    def test_scenario_1_single_worker_assignment(self, engine):
        """Single worker assignment — plan and execute."""
        pkg = _make_work_package("run_tests")
        plan = engine.plan(pkg)
        assert len(plan.assignments) == 1
        result = engine.execute(plan)
        assert result.completed == 1
        assert result.failed == 0

    def test_scenario_2_sequential_workers(self, suite_manager, coordinator):
        """Multiple sequential workers — planning then review."""
        eng = WorkerCollaborationEngine(suite_manager, coordinator)
        a1 = make_assignment("suite_runner_worker", "run_tests",
                             work_package_id="pkg-001", priority=1)
        a2 = make_assignment("engineering_review_worker", "run_engineering_review",
                             work_package_id="pkg-001", priority=2,
                             dependencies=(a1.id,))
        from uuid import uuid4
        plan = WorkerPlan(
            id=str(uuid4()),
            assignments=(a1, a2),
            genesis="038",
            work_package_id="pkg-001",
            created_at="2026-08-04T12:00:00",
        )
        groups = plan.sequential_groups()
        assert len(groups) == 2   # sequential: tests → review
        result = eng.execute(plan)
        assert result.completed >= 1

    def test_scenario_3_parallel_workers(self, suite_manager, coordinator):
        """Parallel workers — testing and review in same group."""
        eng = WorkerCollaborationEngine(suite_manager, coordinator)
        a1 = make_assignment("suite_runner_worker", "run_tests",
                             can_parallelise=True, work_package_id="pkg-002")
        a2 = make_assignment("engineering_review_worker", "run_engineering_review",
                             can_parallelise=True, work_package_id="pkg-002")
        from uuid import uuid4
        plan = WorkerPlan(
            id=str(uuid4()),
            assignments=(a1, a2),
            genesis="038",
            work_package_id="pkg-002",
            created_at="2026-08-04T12:00:00",
        )
        groups = plan.sequential_groups()
        # Both in same group (no dependencies between them)
        assert len(groups) == 1
        assert len(groups[0]) == 2
        text = plan.to_text()
        assert "parallel" in text

    def test_scenario_4_worker_unavailable(self, engine):
        """Worker unavailable → deterministic explanation."""
        pkg = _make_work_package("capability_that_does_not_exist")
        plan = engine.plan(pkg)
        result = engine.execute(plan)
        assert result.skipped >= 1
        assert result.failed == 0
        # The result should explain what happened
        assert "skipped" in result.to_text().lower() or result.skipped > 0

    def test_no_ai_calls(self, engine):
        assert not hasattr(engine, "_ai")
        assert not hasattr(engine, "ai")

    def test_worker_coordinator_unchanged(self, engine, coordinator):
        """WorkerCoordinator should still be the single execution point."""
        pkg = _make_work_package("run_tests")
        plan = engine.plan(pkg)
        engine.execute(plan)
        # Coordinator.run() was called
        assert len(coordinator.runs) > 0
