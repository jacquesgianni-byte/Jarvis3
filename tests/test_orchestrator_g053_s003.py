"""
Genesis-053 Sprint-003 — Worker Bridge Tests
"""
from __future__ import annotations
import pathlib
import pytest
from unittest.mock import MagicMock


def _make_request(text="Implement Sprint-003 worker bridge"):
    from core.engineering.coordinator.models import EngineeringRequest
    return EngineeringRequest(request=text)

def _make_store(tmp_path):
    from core.engineering.coordinator.session_store import SessionStore
    return SessionStore(directory=tmp_path)

def _make_plan_dict(paths=None, action="modify"):
    paths = paths or ["core/test_file.py"]
    return {
        "plan_id": "test-plan-id", "capability": "implement_feature",
        "description": "Test plan",
        "operations": [{"action": action, "path": p, "content": "# test", "reason": "test"} for p in paths],
    }

def _make_claude_worker(plan_dict=None, fail=False):
    from core.workers.models import WorkerResult
    worker = MagicMock()
    if fail:
        worker.execute.return_value = WorkerResult(
            task_id="t1", worker_name="claude_ai_worker", success=False, error="AI unavailable")
    else:
        worker.execute.return_value = WorkerResult(
            task_id="t1", worker_name="claude_ai_worker", success=True,
            data={"execution_plan": plan_dict or _make_plan_dict()})
    return worker

def _make_execution_runner(success=True, tests_failed=0, tests_passed=4986):
    from core.engineering.execution.execution_runner import ExecutionOutcome, ApprovalLifecycleState
    runner = MagicMock()
    if success and tests_failed == 0:
        summary = MagicMock()
        summary.tests_passed = tests_passed
        summary.tests_skipped = 33
        summary.files_created = []
        summary.files_modified = ["core/test_file.py"]
        summary.to_text.return_value = "All tests passed."
        outcome = ExecutionOutcome(
            state=ApprovalLifecycleState.COMMIT_PENDING, description="test",
            summary=summary, markdown="ok", success=True)
    else:
        outcome = ExecutionOutcome(
            state=ApprovalLifecycleState.FAILED, description="test",
            summary=None, markdown="failed", success=False, error="Tests failed")
    runner.run.return_value = outcome
    return runner

def _make_coordinator(tmp_path, enable_gate=True, claude_worker=None, execution_runner=None, enable_guardrails=False):
    from core.engineering.coordinator.coordinator import CoordinatorConfig, EngineeringCoordinator
    store = _make_store(tmp_path)
    config = CoordinatorConfig(
        enable_planning=False, enable_guardrails=enable_guardrails,
        enable_approval_gate=enable_gate, enable_validation=False, enable_debugging=False)
    return EngineeringCoordinator(
        config=config, session_store=store,
        claude_worker=claude_worker, execution_runner=execution_runner), store


class TestNewStages:
    def test_executing_stage_exists(self):
        from core.engineering.coordinator.models import EngineeringStage
        assert hasattr(EngineeringStage, "EXECUTING")

    def test_testing_stage_exists(self):
        from core.engineering.coordinator.models import EngineeringStage
        assert hasattr(EngineeringStage, "TESTING")

    def test_executing_not_terminal(self):
        from core.engineering.coordinator.models import EngineeringStage
        assert not EngineeringStage.EXECUTING.is_terminal()

    def test_testing_not_terminal(self):
        from core.engineering.coordinator.models import EngineeringStage
        assert not EngineeringStage.TESTING.is_terminal()


class TestExecutionPlanPersistence:
    def test_execution_plan_field_exists(self):
        from core.engineering.coordinator.models import EngineeringRequest, EngineeringSession
        session = EngineeringSession.create(EngineeringRequest(request="test"))
        assert hasattr(session, "execution_plan")
        assert session.execution_plan is None

    def test_execution_plan_in_to_dict(self):
        from core.engineering.coordinator.models import EngineeringRequest, EngineeringSession
        session = EngineeringSession.create(EngineeringRequest(request="test"))
        session.execution_plan = _make_plan_dict()
        d = session.to_dict()
        assert "execution_plan" in d
        assert d["execution_plan"]["plan_id"] == "test-plan-id"

    def test_execution_plan_round_trips(self):
        from core.engineering.coordinator.models import EngineeringRequest, EngineeringSession, EngineeringStatus, EngineeringStage
        session = EngineeringSession.create(EngineeringRequest(request="test"))
        session.suspend()
        session.execution_plan = _make_plan_dict(["core/a.py", "core/b.py"])
        restored = EngineeringSession.from_dict(session.to_dict())
        assert restored.execution_plan is not None
        assert len(restored.execution_plan["operations"]) == 2

    def test_execution_outcome_persists(self):
        from core.engineering.coordinator.models import EngineeringRequest, EngineeringSession
        session = EngineeringSession.create(EngineeringRequest(request="test"))
        session.execution_outcome = "passed"
        restored = EngineeringSession.from_dict(session.to_dict())
        assert restored.execution_outcome == "passed"


class TestClaudeBeforeApprovalGate:
    def test_plan_attached_to_suspended_session(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        claude = _make_claude_worker()
        coord, _ = _make_coordinator(tmp_path, claude_worker=claude)
        result = coord.coordinate(_make_request())
        assert result.status == EngineeringStatus.AWAITING_APPROVAL
        session = coord._suspended_sessions[result.session_id]
        assert session.execution_plan is not None
        assert len(session.execution_plan["operations"]) > 0

    def test_empty_plan_fails_before_gate(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        empty = {"plan_id": "x", "capability": "implement_feature", "description": "", "operations": []}
        claude = _make_claude_worker(plan_dict=empty)
        coord, _ = _make_coordinator(tmp_path, claude_worker=claude)
        assert coord.coordinate(_make_request()).status == EngineeringStatus.FAILED

    def test_claude_failure_fails_before_gate(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        coord, _ = _make_coordinator(tmp_path, claude_worker=_make_claude_worker(fail=True))
        assert coord.coordinate(_make_request()).status == EngineeringStatus.FAILED

    def test_no_approval_card_on_claude_failure(self, tmp_path):
        coord, _ = _make_coordinator(tmp_path, claude_worker=_make_claude_worker(fail=True))
        coord.coordinate(_make_request())
        assert len(coord._suspended_sessions) == 0

    def test_plan_persisted_to_disk(self, tmp_path):
        claude = _make_claude_worker()
        coord, store = _make_coordinator(tmp_path, claude_worker=claude)
        result = coord.coordinate(_make_request())
        loaded = store.load(result.session_id)
        assert loaded is not None
        assert loaded.execution_plan is not None


class TestGuardrailsOnPlan:
    def test_guardrails_reject_too_many_files(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        from core.engineering.coordinator.coordinator import CoordinatorConfig, EngineeringCoordinator
        from core.engineering.guardrails.guardrails import EngineeringGuardrails
        plan = _make_plan_dict([f"core/file_{i}.py" for i in range(10)])
        claude = _make_claude_worker(plan_dict=plan)
        store = _make_store(tmp_path)
        config = CoordinatorConfig(enable_planning=False, enable_guardrails=True,
            enable_approval_gate=True, enable_validation=False)
        coord = EngineeringCoordinator(config=config, session_store=store,
            claude_worker=claude, guardrails=EngineeringGuardrails(max_files=5))
        assert coord.coordinate(_make_request()).status == EngineeringStatus.FAILED

    def test_guardrails_pass_within_limit(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        from core.engineering.coordinator.coordinator import CoordinatorConfig, EngineeringCoordinator
        from core.engineering.guardrails.guardrails import EngineeringGuardrails
        plan = _make_plan_dict(["core/a.py", "core/b.py"])
        claude = _make_claude_worker(plan_dict=plan)
        store = _make_store(tmp_path)
        config = CoordinatorConfig(enable_planning=False, enable_guardrails=True,
            enable_approval_gate=True, enable_validation=False)
        coord = EngineeringCoordinator(config=config, session_store=store,
            claude_worker=claude, guardrails=EngineeringGuardrails(max_files=5))
        assert coord.coordinate(_make_request()).status == EngineeringStatus.AWAITING_APPROVAL


class TestExecutionPostApproval:
    def test_approve_triggers_execution(self, tmp_path):
        claude = _make_claude_worker()
        runner = _make_execution_runner(success=True)
        coord, _ = _make_coordinator(tmp_path, claude_worker=claude, execution_runner=runner)
        r1 = coord.coordinate(_make_request())
        coord.resume_session(r1.session_id, "approve", "ludovic")
        runner.run.assert_called_once()

    def test_passing_tests_returns_complete(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        claude = _make_claude_worker()
        runner = _make_execution_runner(success=True, tests_failed=0)
        coord, _ = _make_coordinator(tmp_path, claude_worker=claude, execution_runner=runner)
        r1 = coord.coordinate(_make_request())
        r2 = coord.resume_session(r1.session_id, "approve", "ludovic")
        assert r2.status == EngineeringStatus.COMPLETE

    def test_execution_failure_returns_failed(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        claude = _make_claude_worker()
        runner = _make_execution_runner(success=False)
        coord, _ = _make_coordinator(tmp_path, claude_worker=claude, execution_runner=runner)
        r1 = coord.coordinate(_make_request())
        r2 = coord.resume_session(r1.session_id, "approve", "ludovic")
        assert r2.status == EngineeringStatus.FAILED

    def test_execution_outcome_persisted(self, tmp_path):
        claude = _make_claude_worker()
        runner = _make_execution_runner(success=True)
        coord, store = _make_coordinator(tmp_path, claude_worker=claude, execution_runner=runner)
        r1 = coord.coordinate(_make_request())
        coord.resume_session(r1.session_id, "approve", "ludovic")
        loaded = store.load(r1.session_id)
        assert loaded is not None
        assert loaded.execution_outcome == "passed"

    def test_no_execution_runner_still_completes(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        claude = _make_claude_worker()
        coord, _ = _make_coordinator(tmp_path, claude_worker=claude, execution_runner=None)
        r1 = coord.coordinate(_make_request())
        r2 = coord.resume_session(r1.session_id, "approve", "ludovic")
        assert r2.status == EngineeringStatus.COMPLETE


class TestPlanSummaryInStatus:
    def test_plan_summary_in_suspended_sessions(self, tmp_path):
        plan = _make_plan_dict(["core/a.py", "core/b.py"], action="modify")
        claude = _make_claude_worker(plan_dict=plan)
        coord, _ = _make_coordinator(tmp_path, claude_worker=claude)
        coord.coordinate(_make_request())
        sessions = coord.suspended_sessions()
        assert len(sessions) == 1
        ps = sessions[0]["plan_summary"]
        assert ps["available"] is True
        assert ps["operations"] == 2
        assert ps["modifies"] == 2
        assert "core/a.py" in ps["files"]

    def test_summarise_plan_counts(self):
        from core.engineering.coordinator.coordinator import EngineeringCoordinator
        plan = {"plan_id": "x", "capability": "implement_feature", "description": "",
            "operations": [
                {"action": "create", "path": "core/new.py", "content": "", "reason": ""},
                {"action": "modify", "path": "core/old.py", "content": "", "reason": ""},
                {"action": "delete", "path": "core/dead.py", "content": "", "reason": ""},
            ]}
        s = EngineeringCoordinator._summarise_plan(plan)
        assert s["creates"] == 1 and s["modifies"] == 1 and s["deletes"] == 1

    def test_summarise_plan_none(self):
        from core.engineering.coordinator.coordinator import EngineeringCoordinator
        s = EngineeringCoordinator._summarise_plan(None)
        assert s["available"] is False


class TestStartupRestorationWithPlan:
    def test_execution_plan_survives_restart(self, tmp_path):
        plan = _make_plan_dict(["core/survivor.py"])
        claude = _make_claude_worker(plan_dict=plan)
        coord, store = _make_coordinator(tmp_path, claude_worker=claude)
        r1 = coord.coordinate(_make_request())
        sid = r1.session_id
        from core.engineering.coordinator.coordinator import CoordinatorConfig, EngineeringCoordinator
        config = CoordinatorConfig(enable_planning=False, enable_guardrails=False,
            enable_approval_gate=True, enable_validation=False)
        coord2 = EngineeringCoordinator(config=config, session_store=store)
        assert sid in coord2._suspended_sessions
        restored = coord2._suspended_sessions[sid]
        assert restored.execution_plan is not None
        assert restored.execution_plan["operations"][0]["path"] == "core/survivor.py"
