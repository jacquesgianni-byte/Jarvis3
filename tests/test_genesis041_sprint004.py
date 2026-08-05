"""
Tests — ExecutionRunner
Genesis-041 Sprint-004

Covers the full pipeline:
  Success path:   snapshot → execute → tests pass → ChangeSummary
  Failure paths:  snapshot fail, execute fail, tests fail → rollback
  ChangeSummary:  structure, immutability, to_text()
  Commit API:     has_pending_commit, get_commit_summary_text, clear
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call


def make_worker_result(success: bool, data: dict = None, error: str = ""):
    result = MagicMock()
    result.success = success
    result.data = data or {}
    result.error = error
    result.observations = ()
    result.recommendations = ()
    return result


def make_coordinator(
    snapshot_sha: str = "abc1234",
    exec_success: bool = True,
    tests_passed: int = 100,
    tests_failed: int = 0,
    rollback_success: bool = True,
):
    """Build a mock coordinator that returns results in pipeline order."""
    coordinator = MagicMock()

    snapshot_result = make_worker_result(
        success=bool(snapshot_sha),
        data={"sha": snapshot_sha, "results": {"git_worker": {"sha": snapshot_sha}}},
    )

    exec_result = make_worker_result(
        success=exec_success,
        data={
            "files_created": ["core/new.py"],
            "files_modified": ["core/agent.py"],
            "files_deleted": [],
            "files_written": 2,
            "snapshot_sha": snapshot_sha,
            "results": {
                "execution_worker": {
                    "files_created": ["core/new.py"],
                    "files_modified": ["core/agent.py"],
                }
            },
        },
        error="" if exec_success else "Permission denied",
    )

    test_result = make_worker_result(
        success=tests_failed == 0,
        data={
            "passed": tests_passed,
            "failed": tests_failed,
            "skipped": 5,
            "failures": [f"tests/test_x.py::test_{i}" for i in range(tests_failed)],
            "results": {
                "suite_runner_worker": {
                    "passed": tests_passed,
                    "failed": tests_failed,
                }
            },
        },
    )

    rollback_result = make_worker_result(
        success=rollback_success,
        data={"sha": snapshot_sha, "strategy": "git_rollback"},
        error="" if rollback_success else "rollback failed",
    )

    # Pipeline order: snapshot, execute, tests, (rollback if needed)
    coordinator.run.side_effect = [
        snapshot_result,
        exec_result,
        test_result,
        rollback_result,
    ]
    return coordinator


def make_runner(coordinator=None, manager=None):
    from core.engineering.execution.execution_runner import ExecutionRunner
    return ExecutionRunner(
        worker_coordinator=coordinator or MagicMock(),
        worker_manager=manager or MagicMock(),
        repo_root="/repo",
    )


PLAN = {
    "files_to_create": [{"path": "core/new.py", "content": "# new\n"}],
    "files_to_modify": [{"path": "core/agent.py", "content": "# modified\n"}],
}


# ---------------------------------------------------------------------------
# ChangeSummary tests
# ---------------------------------------------------------------------------

class TestChangeSummary:

    def _make_summary(self):
        from core.engineering.execution.execution_runner import ChangeSummary
        return ChangeSummary.create(
            session_id="sess001",
            description="Add OAuth login",
            execution_data={
                "files_created": ["core/auth.py"],
                "files_modified": ["core/agent.py"],
                "files_deleted": [],
            },
            test_data={"passed": 100, "skipped": 5},
            snapshot_sha="abc1234xyz",
            duration_seconds=12.5,
        )

    def test_create(self):
        s = self._make_summary()
        assert s.session_id == "sess001"
        assert s.description == "Add OAuth login"
        assert "core/auth.py" in s.files_created
        assert "core/agent.py" in s.files_modified
        assert s.tests_passed == 100
        assert s.tests_skipped == 5
        assert s.snapshot_sha == "abc1234xyz"
        assert s.total_files_changed == 2

    def test_is_immutable(self):
        s = self._make_summary()
        with pytest.raises((AttributeError, TypeError)):
            s.tests_passed = 0  # type: ignore[misc]

    def test_to_text_contains_key_fields(self):
        s = self._make_summary()
        text = s.to_text()
        assert "CHANGE SUMMARY" in text
        assert "Add OAuth login" in text
        assert "core/auth.py" in text
        assert "core/agent.py" in text
        assert "100 passed" in text
        assert "abc1234" in text
        assert "Commit" in text

    def test_summary_id_is_unique(self):
        from core.engineering.execution.execution_runner import ChangeSummary
        s1 = ChangeSummary.create("s1", "d", {}, {}, "sha")
        s2 = ChangeSummary.create("s2", "d", {}, {}, "sha")
        assert s1.summary_id != s2.summary_id

    def test_total_files_changed(self):
        from core.engineering.execution.execution_runner import ChangeSummary
        s = ChangeSummary.create(
            "s", "d",
            {"files_created": ["a", "b"], "files_modified": ["c"], "files_deleted": ["d"]},
            {}, "sha",
        )
        assert s.total_files_changed == 4


# ---------------------------------------------------------------------------
# ApprovalLifecycleState
# ---------------------------------------------------------------------------

class TestApprovalLifecycleState:

    def test_all_states_exist(self):
        from core.engineering.execution.execution_runner import ApprovalLifecycleState
        states = [s.value for s in ApprovalLifecycleState]
        assert "awaiting_approval" in states
        assert "executing" in states
        assert "testing" in states
        assert "rolled_back" in states
        assert "commit_pending" in states
        assert "committed" in states
        assert "push_pending" in states
        assert "pushed" in states
        assert "failed" in states


# ---------------------------------------------------------------------------
# ExecutionRunner.can_execute
# ---------------------------------------------------------------------------

class TestCanExecute:

    def test_approve_triggers(self):
        from core.engineering.execution.execution_runner import ExecutionRunner
        r = ExecutionRunner(MagicMock(), MagicMock())
        assert r.can_execute("Approve.")
        assert r.can_execute("approve")
        assert r.can_execute("yes")
        assert r.can_execute("proceed")
        assert r.can_execute("execute the plan")

    def test_non_triggers(self):
        from core.engineering.execution.execution_runner import ExecutionRunner
        r = ExecutionRunner(MagicMock(), MagicMock())
        assert not r.can_execute("hello")
        assert not r.can_execute("what risks did you identify")
        assert not r.can_execute("review the architecture")


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

class TestExecutionRunnerSuccess:

    def test_success_returns_commit_pending(self):
        from core.engineering.execution.execution_runner import ApprovalLifecycleState
        coordinator = make_coordinator()
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth login", PLAN, "sess001")
        assert outcome.success
        assert outcome.state == ApprovalLifecycleState.COMMIT_PENDING

    def test_success_produces_change_summary(self):
        coordinator = make_coordinator()
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth login", PLAN, "sess001")
        assert outcome.summary is not None
        assert outcome.summary.tests_passed == 100

    def test_success_markdown_contains_summary(self):
        coordinator = make_coordinator()
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth login", PLAN)
        assert "CHANGE SUMMARY" in outcome.markdown
        assert "Commit" in outcome.markdown

    def test_success_stores_snapshot_sha(self):
        coordinator = make_coordinator(snapshot_sha="deadbeef123")
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth", PLAN)
        assert outcome.snapshot_sha == "deadbeef123"

    def test_pipeline_calls_workers_in_order(self):
        coordinator = make_coordinator()
        runner = make_runner(coordinator)
        runner.run("Add OAuth", PLAN)
        assert coordinator.run.call_count == 3  # snapshot, execute, tests

    def test_no_rollback_on_success(self):
        coordinator = make_coordinator(tests_failed=0)
        runner = make_runner(coordinator)
        runner.run("Add OAuth", PLAN)
        # Only 3 calls: snapshot, execute, tests — no rollback
        assert coordinator.run.call_count == 3

    def test_has_pending_commit_after_success(self):
        coordinator = make_coordinator()
        runner = make_runner(coordinator)
        runner.run("Add OAuth", PLAN)
        assert runner.has_pending_commit()

    def test_get_commit_summary_text(self):
        coordinator = make_coordinator()
        runner = make_runner(coordinator)
        runner.run("Add OAuth", PLAN)
        text = runner.get_commit_summary_text()
        assert "CHANGE SUMMARY" in text

    def test_clear_pending_commit(self):
        coordinator = make_coordinator()
        runner = make_runner(coordinator)
        runner.run("Add OAuth", PLAN)
        assert runner.has_pending_commit()
        runner.clear_pending_commit()
        assert not runner.has_pending_commit()


# ---------------------------------------------------------------------------
# Failure path — snapshot fails
# ---------------------------------------------------------------------------

class TestSnapshotFailure:

    def test_snapshot_failure_stops_pipeline(self):
        coordinator = MagicMock()
        coordinator.run.return_value = make_worker_result(
            success=False,
            data={"sha": "", "results": {"git_worker": {"sha": ""}}},
            error="not a git repo",
        )
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth", PLAN)
        assert not outcome.success
        # Only snapshot was called — pipeline stopped
        assert coordinator.run.call_count == 1

    def test_snapshot_failure_no_rollback(self):
        coordinator = MagicMock()
        coordinator.run.return_value = make_worker_result(
            success=True,
            data={"sha": "", "results": {"git_worker": {"sha": ""}}},
        )
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth", PLAN)
        assert not outcome.success
        # No rollback without a SHA anchor
        assert coordinator.run.call_count == 1

    def test_snapshot_failure_markdown_explains(self):
        coordinator = MagicMock()
        coordinator.run.return_value = make_worker_result(
            success=False,
            data={"sha": "", "results": {}},
        )
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth", PLAN)
        assert "EXECUTION FAILED" in outcome.markdown


# ---------------------------------------------------------------------------
# Failure path — execution fails
# ---------------------------------------------------------------------------

class TestExecutionFailure:

    def test_execution_failure_triggers_rollback(self):
        coordinator = make_coordinator(exec_success=False)
        # Override side_effect: snapshot, exec_fail, rollback
        snapshot_result = make_worker_result(
            True, {"sha": "abc123", "results": {"git_worker": {"sha": "abc123"}}}
        )
        exec_result = make_worker_result(False, {}, "Permission denied")
        rollback_result = make_worker_result(True, {"sha": "abc123", "strategy": "git_rollback"})
        coordinator.run.side_effect = [snapshot_result, exec_result, rollback_result]

        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth", PLAN)

        assert not outcome.success
        assert coordinator.run.call_count == 3  # snapshot + exec + rollback

    def test_execution_failure_returns_failure_state(self):
        from core.engineering.execution.execution_runner import ApprovalLifecycleState
        coordinator = MagicMock()
        snapshot_result = make_worker_result(
            True, {"sha": "abc123", "results": {"git_worker": {"sha": "abc123"}}}
        )
        exec_result = make_worker_result(False, {}, "write error")
        rollback_result = make_worker_result(True, {})
        coordinator.run.side_effect = [snapshot_result, exec_result, rollback_result]

        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth", PLAN)
        assert outcome.state == ApprovalLifecycleState.FAILED


# ---------------------------------------------------------------------------
# Failure path — tests fail
# ---------------------------------------------------------------------------

class TestTestsFailure:

    def _make_coordinator_tests_fail(self):
        coordinator = MagicMock()
        snapshot_result = make_worker_result(
            True, {"sha": "abc123", "results": {"git_worker": {"sha": "abc123"}}}
        )
        exec_result = make_worker_result(
            True,
            {
                "files_created": ["core/new.py"],
                "files_modified": [],
                "files_deleted": [],
                "snapshot_sha": "abc123",
            },
        )
        test_result = make_worker_result(
            False,
            {
                "passed": 95,
                "failed": 5,
                "skipped": 2,
                "failures": ["tests/test_x.py::test_one", "tests/test_x.py::test_two"],
            },
        )
        rollback_result = make_worker_result(True, {"sha": "abc123", "strategy": "git_rollback"})
        coordinator.run.side_effect = [
            snapshot_result, exec_result, test_result, rollback_result
        ]
        return coordinator

    def test_tests_failure_triggers_rollback(self):
        coordinator = self._make_coordinator_tests_fail()
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth", PLAN)
        assert not outcome.success
        # 4 calls: snapshot + exec + tests + rollback
        assert coordinator.run.call_count == 4

    def test_tests_failure_returns_failure_state(self):
        from core.engineering.execution.execution_runner import ApprovalLifecycleState
        coordinator = self._make_coordinator_tests_fail()
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth", PLAN)
        assert outcome.state == ApprovalLifecycleState.FAILED

    def test_tests_failure_error_mentions_rollback(self):
        coordinator = self._make_coordinator_tests_fail()
        runner = make_runner(coordinator)
        outcome = runner.run("Add OAuth", PLAN)
        assert "rolled back" in outcome.error.lower() or "rollback" in outcome.markdown.lower()

    def test_no_pending_commit_after_test_failure(self):
        coordinator = self._make_coordinator_tests_fail()
        runner = make_runner(coordinator)
        runner.run("Add OAuth", PLAN)
        assert not runner.has_pending_commit()


# ---------------------------------------------------------------------------
# ExecutionOutcome
# ---------------------------------------------------------------------------

class TestExecutionOutcome:

    def test_outcome_has_required_fields(self):
        from core.engineering.execution.execution_runner import (
            ExecutionOutcome, ApprovalLifecycleState,
        )
        outcome = ExecutionOutcome(
            state=ApprovalLifecycleState.COMMIT_PENDING,
            description="test",
            summary=None,
            markdown="# test",
            success=True,
        )
        assert outcome.state == ApprovalLifecycleState.COMMIT_PENDING
        assert outcome.success
        assert outcome.error == ""
        assert outcome.snapshot_sha == ""
        assert outcome.session_id == ""
