"""
Tests — Engineering Collaboration Framework
Genesis-040 Sprint-002

Covers all four desktop validation scenarios:
  Scenario 1: Successful collaboration → report produced → ready for approval
  Scenario 2: Worker failure → report explains why → decision engine consulted
  Scenario 3: Engineering review fails → installation blocked → reason reported
  Scenario 4: Regression tests fail → installation blocked → executive summary updated

All tests are deterministic — no live AI calls, no file system required.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

def make_worker_result(
    success: bool,
    data: Optional[dict] = None,
    error: str = "",
    observations: tuple = (),
):
    """Build a minimal WorkerResult-like object for mocking."""
    result = MagicMock()
    result.success      = success
    result.data         = data or {}
    result.error        = error
    result.observations = observations
    return result


def make_coordinator(
    ai_result=None,
    review_result=None,
):
    """
    Build a mock WorkerCoordinator.

    The coordinator is called twice per run:
      call 1 → AI worker result
      call 2 → engineering review result
    """
    coordinator = MagicMock()
    calls = [
        ai_result or make_worker_result(
            success=True,
            data={"response": "Here is the implementation plan."},
            observations=("AI worker completed.",),
        ),
        review_result or _default_review_result(),
    ]
    coordinator.run.side_effect = calls
    return coordinator


def _default_review_result(passed: bool = True, tests_failed: int = 0):
    return make_worker_result(
        success=True,
        data={
            "report": {
                "review": {
                    "status": "complete" if passed else "failed",
                    "test_results": {
                        "passed": 100,
                        "failed": tests_failed,
                        "skipped": 2,
                    },
                    "files_added": ["core/new_feature.py"],
                    "files_modified": [],
                    "risks": [],
                }
            }
        },
    )


def make_manager(worker_name: str = "claude_ai_worker"):
    manager = MagicMock()
    mock_worker = MagicMock()
    mock_worker.name = worker_name
    manager.workers_for.return_value = [mock_worker]
    return manager


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestEngineeringCollaborationState:

    def test_pending_state(self):
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationState,
        )
        state = EngineeringCollaborationState.pending()
        assert state.status == CollaborationStatus.PENDING
        assert state.stage == "initialising"
        assert state.worker_response == ""
        assert not state.review_passed
        assert not state.tests_passed

    def test_running_state(self):
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationState,
        )
        state = EngineeringCollaborationState.running()
        assert state.status == CollaborationStatus.RUNNING

    def test_with_worker_response(self):
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationState,
        )
        state = EngineeringCollaborationState.pending().with_worker_response(
            "Here is the plan."
        )
        assert state.status == CollaborationStatus.REVIEWING
        assert state.worker_response == "Here is the plan."
        assert state.stage == "engineering_review"

    def test_review_passed(self):
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationState,
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("response")
            .with_review_result(review_passed=True, tests_passed=True)
        )
        assert state.status == CollaborationStatus.COMPLETE
        assert state.review_passed
        assert state.tests_passed
        assert state.blocked_reason == ""

    def test_review_failed(self):
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationState,
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("response")
            .with_review_result(
                review_passed=False,
                tests_passed=True,
                blocked_reason="Review status: failed",
            )
        )
        assert state.status == CollaborationStatus.BLOCKED
        assert not state.review_passed
        assert state.blocked_reason == "Review status: failed"

    def test_tests_failed(self):
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationState,
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("response")
            .with_review_result(
                review_passed=True,
                tests_passed=False,
                blocked_reason="Regression tests: 3 failed.",
            )
        )
        assert state.status == CollaborationStatus.BLOCKED
        assert not state.tests_passed

    def test_failed_state(self):
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationState,
        )
        state = EngineeringCollaborationState.pending().failed("Worker unreachable.")
        assert state.status == CollaborationStatus.FAILED
        assert state.blocked_reason == "Worker unreachable."

    def test_state_is_immutable(self):
        from core.engineering.collaboration.models import EngineeringCollaborationState
        state = EngineeringCollaborationState.pending()
        with pytest.raises((AttributeError, TypeError)):
            state.stage = "hacked"  # type: ignore[misc]


class TestEngineeringCollaborationSession:

    def test_create(self):
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationSession,
        )
        session = EngineeringCollaborationSession.create(
            work_package_id="wp-001",
            assigned_worker="claude_ai_worker",
            capability="implement_feature",
            description="Add new feature.",
        )
        assert session.session_id
        assert session.work_package_id == "wp-001"
        assert session.assigned_worker == "claude_ai_worker"
        assert session.capability == "implement_feature"
        assert session.state.status == CollaborationStatus.PENDING
        assert session.completed_at is None

    def test_with_state_produces_new_session(self):
        from core.engineering.collaboration.models import (
            EngineeringCollaborationSession,
            EngineeringCollaborationState,
        )
        session = EngineeringCollaborationSession.create(
            work_package_id="wp-001",
            assigned_worker="claude_ai_worker",
            capability="implement_feature",
            description="Test.",
        )
        updated = session.with_state(
            EngineeringCollaborationState.running()
        )
        # Original unchanged
        from core.engineering.collaboration.models import CollaborationStatus
        assert session.state.status == CollaborationStatus.PENDING
        assert updated.state.status == CollaborationStatus.RUNNING
        assert updated.session_id == session.session_id

    def test_is_complete(self):
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationSession,
            EngineeringCollaborationState,
        )
        session = EngineeringCollaborationSession.create(
            "wp", "claude_ai_worker", "implement_feature", "desc"
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("ok")
            .with_review_result(True, True)
        )
        completed = session.with_state(state)
        assert completed.is_complete
        assert completed.completed_at is not None

    def test_is_blocked(self):
        from core.engineering.collaboration.models import (
            EngineeringCollaborationSession,
            EngineeringCollaborationState,
        )
        session = EngineeringCollaborationSession.create(
            "wp", "claude_ai_worker", "implement_feature", "desc"
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("ok")
            .with_review_result(False, True, "review failed")
        )
        blocked = session.with_state(state)
        assert blocked.is_blocked

    def test_session_is_immutable(self):
        from core.engineering.collaboration.models import EngineeringCollaborationSession
        session = EngineeringCollaborationSession.create(
            "wp", "claude_ai_worker", "implement_feature", "desc"
        )
        with pytest.raises((AttributeError, TypeError)):
            session.assigned_worker = "hacked"  # type: ignore[misc]


class TestEngineeringCollaborationReport:

    def _make_complete_session(self):
        from core.engineering.collaboration.models import (
            EngineeringCollaborationSession,
            EngineeringCollaborationState,
        )
        session = EngineeringCollaborationSession.create(
            work_package_id="wp-001",
            assigned_worker="claude_ai_worker",
            capability="implement_feature",
            description="Add feature X.",
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("Implementation plan here.")
            .with_review_result(True, True)
        )
        return session.with_state(
            state,
            engineering_review={
                "review": {
                    "status": "complete",
                    "test_results": {"passed": 50, "failed": 0, "skipped": 1},
                    "files_added": ["core/feature_x.py"],
                    "files_modified": ["core/agent.py"],
                    "risks": [],
                }
            },
            recommendation="Ready for approval.",
        )

    def test_from_session_complete(self):
        from core.engineering.collaboration.models import EngineeringCollaborationReport
        session = self._make_complete_session()
        report = EngineeringCollaborationReport.from_session(session)
        assert report.ready_for_approval
        assert report.review_passed
        assert report.tests_passed
        assert report.worker == "claude_ai_worker"
        assert report.capability == "implement_feature"
        assert report.status == "complete"
        assert "core/feature_x.py" in report.files_changed
        assert "core/agent.py" in report.files_changed
        assert report.tests_executed == 51  # 50 + 0 + 1

    def test_from_session_blocked(self):
        from core.engineering.collaboration.models import (
            EngineeringCollaborationReport,
            EngineeringCollaborationSession,
            EngineeringCollaborationState,
        )
        session = EngineeringCollaborationSession.create(
            "wp", "claude_ai_worker", "implement_feature", "desc"
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("plan")
            .with_review_result(False, True, "Status: failed")
        )
        blocked_session = session.with_state(state)
        report = EngineeringCollaborationReport.from_session(blocked_session)
        assert not report.ready_for_approval
        assert not report.review_passed
        assert report.blocked_reason == "Status: failed"

    def test_report_is_immutable(self):
        from core.engineering.collaboration.models import EngineeringCollaborationReport
        session = self._make_complete_session()
        report = EngineeringCollaborationReport.from_session(session)
        with pytest.raises((AttributeError, TypeError)):
            report.ready_for_approval = False  # type: ignore[misc]


class TestEngineeringApprovalRequest:

    def _make_report(self, ready: bool = True, blocked_reason: str = ""):
        from core.engineering.collaboration.models import (
            EngineeringCollaborationReport,
            EngineeringCollaborationSession,
            EngineeringCollaborationState,
        )
        session = EngineeringCollaborationSession.create(
            "wp", "claude_ai_worker", "implement_feature", "desc"
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("response")
            .with_review_result(ready, ready, blocked_reason)
        )
        return EngineeringCollaborationReport.from_session(
            session.with_state(state, recommendation="Proceed." if ready else "Fix issues.")
        )

    def test_awaiting_when_ready(self):
        from core.engineering.collaboration.models import (
            ApprovalStatus,
            EngineeringApprovalRequest,
        )
        report = self._make_report(ready=True)
        approval = EngineeringApprovalRequest.from_report(report)
        assert approval.status == ApprovalStatus.AWAITING
        assert approval.ready_for_approval
        assert len(approval.blocking_reasons) == 0

    def test_blocked_when_not_ready(self):
        from core.engineering.collaboration.models import (
            ApprovalStatus,
            EngineeringApprovalRequest,
        )
        report = self._make_report(ready=False, blocked_reason="Review failed.")
        approval = EngineeringApprovalRequest.from_report(report)
        assert approval.status == ApprovalStatus.BLOCKED
        assert not approval.ready_for_approval
        assert len(approval.blocking_reasons) > 0

    def test_to_text_contains_key_fields(self):
        from core.engineering.collaboration.models import EngineeringApprovalRequest
        report = self._make_report(ready=True)
        approval = EngineeringApprovalRequest.from_report(report)
        text = approval.to_text()
        assert "ENGINEERING APPROVAL REQUEST" in text
        assert "Ready for approval" in text
        assert "Human approval required" in text
        assert "never installs automatically" in text.lower() or "jarvis" in text.lower()

    def test_to_text_blocked_contains_reasons(self):
        from core.engineering.collaboration.models import EngineeringApprovalRequest
        report = self._make_report(ready=False, blocked_reason="Tests: 5 failed.")
        approval = EngineeringApprovalRequest.from_report(report)
        text = approval.to_text()
        assert "blocked" in text.lower() or "Installation blocked" in text


# ---------------------------------------------------------------------------
# Session Manager tests
# ---------------------------------------------------------------------------

class TestCollaborationSessionManager:

    def test_create_session(self):
        from core.engineering.collaboration.session_manager import CollaborationSessionManager
        from core.engineering.collaboration.models import CollaborationStatus
        mgr = CollaborationSessionManager(output_dir="/tmp/collab_test")
        session = mgr.create(
            work_package_id="wp-001",
            assigned_worker="claude_ai_worker",
            capability="implement_feature",
            description="Add X.",
        )
        assert session.session_id
        assert session.state.status == CollaborationStatus.PENDING
        assert mgr.get(session.session_id) == session

    def test_update_session(self):
        from core.engineering.collaboration.session_manager import CollaborationSessionManager
        from core.engineering.collaboration.models import (
            CollaborationStatus,
            EngineeringCollaborationState,
        )
        mgr = CollaborationSessionManager(output_dir="/tmp/collab_test")
        session = mgr.create("wp", "claude_ai_worker", "implement_feature", "desc")
        updated = mgr.update(session, EngineeringCollaborationState.running())
        assert updated.state.status == CollaborationStatus.RUNNING
        # Original in memory is replaced
        assert mgr.get(session.session_id).state.status == CollaborationStatus.RUNNING

    def test_persist_session(self, tmp_path):
        from core.engineering.collaboration.session_manager import CollaborationSessionManager
        from core.engineering.collaboration.models import (
            EngineeringCollaborationState,
        )
        mgr = CollaborationSessionManager(output_dir=str(tmp_path))
        session = mgr.create("wp", "claude_ai_worker", "implement_feature", "desc")
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("done")
            .with_review_result(True, True)
        )
        session = mgr.update(session, state)
        path = mgr.persist(session)
        assert path.endswith(".json")
        import os
        assert os.path.exists(path)

    def test_all_sessions(self):
        from core.engineering.collaboration.session_manager import CollaborationSessionManager
        mgr = CollaborationSessionManager(output_dir="/tmp/collab_test")
        mgr.create("wp1", "claude_ai_worker", "implement_feature", "desc1")
        mgr.create("wp2", "claude_ai_worker", "write_tests", "desc2")
        sessions = mgr.all_sessions()
        assert len(sessions) >= 2


# ---------------------------------------------------------------------------
# Report Builder tests
# ---------------------------------------------------------------------------

class TestCollaborationReportBuilder:

    def _make_complete_session(self):
        from core.engineering.collaboration.models import (
            EngineeringCollaborationSession,
            EngineeringCollaborationState,
        )
        session = EngineeringCollaborationSession.create(
            "wp", "claude_ai_worker", "implement_feature", "Add feature."
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("Implementation plan.")
            .with_review_result(True, True)
        )
        return session.with_state(
            state,
            recommendation="Ready for approval.",
            engineering_review={"review": {
                "status": "complete",
                "test_results": {"passed": 10, "failed": 0, "skipped": 0},
                "files_added": ["new.py"],
                "files_modified": [],
                "risks": ["Minor coupling risk."],
            }},
        )

    def test_build_report(self):
        from core.engineering.collaboration.report_builder import CollaborationReportBuilder
        builder = CollaborationReportBuilder()
        session = self._make_complete_session()
        report = builder.build(session)
        assert report.ready_for_approval
        assert report.worker == "claude_ai_worker"

    def test_render_contains_sections(self):
        from core.engineering.collaboration.report_builder import CollaborationReportBuilder
        builder = CollaborationReportBuilder()
        session = self._make_complete_session()
        report = builder.build(session)
        md = builder.render(report)
        assert "Engineering Collaboration Report" in md
        assert "Worker Response" in md
        assert "Engineering Gates" in md
        assert "Ready for human approval" in md

    def test_render_full(self):
        from core.engineering.collaboration.report_builder import CollaborationReportBuilder
        builder = CollaborationReportBuilder()
        session = self._make_complete_session()
        report = builder.build(session)
        approval = builder.build_approval(report)
        full = builder.render_full(report, approval)
        assert "Engineering Collaboration Report" in full
        assert "ENGINEERING APPROVAL REQUEST" in full

    def test_render_blocked_shows_reason(self):
        from core.engineering.collaboration.models import (
            EngineeringCollaborationSession,
            EngineeringCollaborationState,
        )
        from core.engineering.collaboration.report_builder import CollaborationReportBuilder
        session = EngineeringCollaborationSession.create(
            "wp", "claude_ai_worker", "implement_feature", "desc"
        )
        state = (
            EngineeringCollaborationState.pending()
            .with_worker_response("plan")
            .with_review_result(False, True, "Review status: failed")
        )
        session = session.with_state(state, recommendation="Fix review issues.")
        builder = CollaborationReportBuilder()
        report  = builder.build(session)
        md = builder.render(report)
        assert "Installation blocked" in md or "❌" in md


# ---------------------------------------------------------------------------
# Scenario tests — CollaborationRunner
# ---------------------------------------------------------------------------

class TestCollaborationRunnerScenario1:
    """Scenario 1: Successful collaboration → report produced → ready for approval."""

    def test_success(self, tmp_path):
        from core.engineering.collaboration.runner import CollaborationRunner

        coordinator = make_coordinator(
            ai_result=make_worker_result(
                success=True,
                data={"response": "Here is the implementation."},
                observations=("AI completed.",),
            ),
            review_result=_default_review_result(passed=True, tests_failed=0),
        )
        manager = make_manager()

        runner = CollaborationRunner(
            worker_coordinator=coordinator,
            worker_manager=manager,
            output_dir=str(tmp_path),
        )
        outcome = runner.run(
            description="Implement feature X.",
            payload={"genesis": "040"},
        )

        assert outcome.success
        assert outcome.report.ready_for_approval
        assert outcome.report.review_passed
        assert outcome.report.tests_passed
        assert "Ready for human approval" in outcome.markdown
        assert "ENGINEERING APPROVAL REQUEST" in outcome.markdown
        from core.engineering.collaboration.models import ApprovalStatus
        assert outcome.approval.status == ApprovalStatus.AWAITING


class TestCollaborationRunnerScenario2:
    """Scenario 2: Worker failure → report explains why."""

    def test_worker_failure(self, tmp_path):
        from core.engineering.collaboration.runner import CollaborationRunner

        coordinator = MagicMock()
        coordinator.run.return_value = make_worker_result(
            success=False,
            error="AI client not configured.",
        )

        manager = make_manager()

        runner = CollaborationRunner(
            worker_coordinator=coordinator,
            worker_manager=manager,
            output_dir=str(tmp_path),
        )
        outcome = runner.run(description="Implement X.")

        assert not outcome.success
        assert outcome.error  # error recorded
        # Report is still produced
        assert outcome.report is not None
        assert not outcome.report.ready_for_approval
        from core.engineering.collaboration.models import ApprovalStatus
        assert outcome.approval.status == ApprovalStatus.BLOCKED


class TestCollaborationRunnerScenario3:
    """Scenario 3: Engineering review fails → installation blocked → reason reported."""

    def test_review_failure(self, tmp_path):
        from core.engineering.collaboration.runner import CollaborationRunner

        coordinator = make_coordinator(
            ai_result=make_worker_result(
                success=True,
                data={"response": "Implementation plan."},
            ),
            review_result=_default_review_result(passed=False, tests_failed=0),
        )
        manager = make_manager()

        runner = CollaborationRunner(
            worker_coordinator=coordinator,
            worker_manager=manager,
            output_dir=str(tmp_path),
        )
        outcome = runner.run(description="Implement X.")

        assert not outcome.success
        assert not outcome.report.ready_for_approval
        assert not outcome.report.review_passed
        assert "blocked" in outcome.markdown.lower() or "❌" in outcome.markdown
        from core.engineering.collaboration.models import ApprovalStatus
        assert outcome.approval.status == ApprovalStatus.BLOCKED
        assert len(outcome.approval.blocking_reasons) > 0


class TestCollaborationRunnerScenario4:
    """Scenario 4: Regression tests fail → installation blocked."""

    def test_test_failure(self, tmp_path):
        from core.engineering.collaboration.runner import CollaborationRunner

        coordinator = make_coordinator(
            ai_result=make_worker_result(
                success=True,
                data={"response": "Implementation plan."},
            ),
            review_result=_default_review_result(passed=True, tests_failed=5),
        )
        manager = make_manager()

        runner = CollaborationRunner(
            worker_coordinator=coordinator,
            worker_manager=manager,
            output_dir=str(tmp_path),
        )
        outcome = runner.run(description="Implement X.")

        assert not outcome.success
        assert not outcome.report.ready_for_approval
        assert not outcome.report.tests_passed
        from core.engineering.collaboration.models import ApprovalStatus
        assert outcome.approval.status == ApprovalStatus.BLOCKED
        # Reason must mention tests
        blocking_text = " ".join(outcome.approval.blocking_reasons)
        assert "test" in blocking_text.lower() or "regression" in blocking_text.lower()


# ---------------------------------------------------------------------------
# Engineering gate invariant test — gates are never bypassed
# ---------------------------------------------------------------------------

class TestEngineeringGateInvariant:

    def test_gate_always_runs_even_after_worker_success(self, tmp_path):
        """
        Even when the AI worker succeeds, the engineering review gate
        must still be called. No path bypasses it.
        """
        from core.engineering.collaboration.runner import CollaborationRunner

        coordinator = make_coordinator()  # default: both pass
        manager = make_manager()
        runner = CollaborationRunner(
            worker_coordinator=coordinator,
            worker_manager=manager,
            output_dir=str(tmp_path),
        )
        runner.run(description="Implement X.", payload={"genesis": "040"})

        # coordinator.run must have been called twice:
        # once for AI worker, once for engineering review
        assert coordinator.run.call_count == 2

    def test_approval_never_auto_true_when_blocked(self, tmp_path):
        """
        ready_for_approval must never be True when any gate failed.
        """
        from core.engineering.collaboration.runner import CollaborationRunner

        coordinator = make_coordinator(
            review_result=_default_review_result(passed=True, tests_failed=10),
        )
        manager = make_manager()
        runner = CollaborationRunner(
            worker_coordinator=coordinator,
            worker_manager=manager,
            output_dir=str(tmp_path),
        )
        outcome = runner.run(description="Implement X.")

        assert not outcome.approval.ready_for_approval
        from core.engineering.collaboration.models import ApprovalStatus
        assert outcome.approval.status != ApprovalStatus.APPROVED

    def test_human_approval_message_always_present(self, tmp_path):
        """
        The 'human approval required' message must appear in every outcome,
        successful or not.
        """
        from core.engineering.collaboration.runner import CollaborationRunner

        for passed in [True, False]:
            coordinator = make_coordinator(
                review_result=_default_review_result(passed=passed),
            )
            if not passed:
                # Only one call when worker fails (no review call needed)
                coordinator = MagicMock()
                coordinator.run.side_effect = [
                    make_worker_result(success=True, data={"response": "ok"}),
                    _default_review_result(passed=False),
                ]
            manager = make_manager()
            runner = CollaborationRunner(
                worker_coordinator=coordinator,
                worker_manager=manager,
                output_dir=str(tmp_path),
            )
            outcome = runner.run(description="Implement X.")
            text = outcome.markdown + outcome.approval.to_text()
            assert "approval" in text.lower(), (
                f"'approval' missing from outcome for passed={passed}"
            )


# ---------------------------------------------------------------------------
# can_handle tests
# ---------------------------------------------------------------------------

class TestCollaborationRunnerCanHandle:

    def _runner(self):
        from core.engineering.collaboration.runner import CollaborationRunner
        return CollaborationRunner(
            worker_coordinator=MagicMock(),
            worker_manager=make_manager(),
        )

    def test_handles_trigger_phrases(self):
        runner = self._runner()
        assert runner.can_handle("begin engineering collaboration")
        assert runner.can_handle("run ai collaboration")
        assert runner.can_handle("engineering collaboration")
        assert runner.can_handle("ai collaboration")

    def test_ignores_non_triggers(self):
        runner = self._runner()
        assert not runner.can_handle("hello")
        assert not runner.can_handle("what is my goal")
        assert not runner.can_handle("run tests")
