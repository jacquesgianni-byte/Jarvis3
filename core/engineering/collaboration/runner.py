"""
Engineering Collaboration Framework — Collaboration Runner
Genesis-040 Sprint-002

Orchestrates the complete AI engineering collaboration pipeline:

  1. Create EngineeringCollaborationSession
  2. Execute ClaudeAIWorker (via WorkerCoordinator)
  3. Execute EngineeringReviewOSWorker (via WorkerCoordinator)
  4. Build EngineeringCollaborationReport
  5. Build EngineeringApprovalRequest
  6. Persist session
  7. Return report + approval

Engineering gates are MANDATORY — no path bypasses them.
Human approval is ALWAYS required — never automatic.

Design:
  CollaborationRunner is a thin orchestrator.
  All intelligence lives in the workers and models.
  It never calls AI directly — only via WorkerCoordinator.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from core.engineering.collaboration.models import (
    ApprovalStatus,
    CollaborationStatus,
    EngineeringApprovalRequest,
    EngineeringCollaborationReport,
    EngineeringCollaborationSession,
    EngineeringCollaborationState,
)
from core.engineering.collaboration.session_manager import CollaborationSessionManager
from core.engineering.collaboration.report_builder import CollaborationReportBuilder
from core.workers.models import WorkerTask

logger = logging.getLogger(__name__)

# Trigger phrases for Section 7.46
_COLLABORATION_TRIGGERS: frozenset[str] = frozenset({
    "begin engineering collaboration",
    "run ai collaboration",
    "start ai collaboration",
    "engineering collaboration",
    "run collaboration",
    "ai collaboration",
    "collaborate on this",
})


@dataclass
class CollaborationOutcome:
    """
    The result of a full collaboration run.
    Carries both the structured report and the rendered Markdown.
    """
    session:   EngineeringCollaborationSession
    report:    EngineeringCollaborationReport
    approval:  EngineeringApprovalRequest
    markdown:  str
    success:   bool
    error:     str = ""


class CollaborationRunner:
    """
    Orchestrates the complete engineering collaboration workflow.

    Requires:
        worker_coordinator  — WorkerCoordinator (already on Agent)
        worker_manager      — WorkerManager (already on Agent)
        worker_intelligence — WorkerIntelligenceEngine (already on Agent)

    Public API:
        can_handle(utterance)          -> bool
        run(description, payload)      -> CollaborationOutcome
    """

    def __init__(
        self,
        worker_coordinator,
        worker_manager,
        worker_intelligence=None,
        output_dir: str = "engineering_reviews",
    ) -> None:
        self._coordinator    = worker_coordinator
        self._manager        = worker_manager
        self._intelligence   = worker_intelligence
        self._session_mgr    = CollaborationSessionManager(output_dir)
        self._report_builder = CollaborationReportBuilder()
        self._last_outcome: Optional[CollaborationOutcome] = None  # for approval routing

    # -- Approval routing API ------------------------------------------------

    def has_pending_approval(self) -> bool:
        """True if the last collaboration is complete and awaiting approval."""
        if self._last_outcome is None:
            return False
        return (
            self._last_outcome.success
            and self._last_outcome.approval.ready_for_approval
        )

    def get_pending_approval_text(self) -> str:
        """Return the approval gate text for the last completed collaboration."""
        if self._last_outcome is None:
            return ""
        return self._last_outcome.approval.to_text()

    def clear_pending_approval(self) -> None:
        """Clear the pending approval after it has been presented."""
        self._last_outcome = None

    def has_active_session(self) -> bool:
        """True if any collaboration outcome is available for follow-up."""
        return self._last_outcome is not None

    def get_session_summary(self) -> str:
        """Return a brief summary of the last collaboration for follow-up questions."""
        if self._last_outcome is None:
            return ""
        r = self._last_outcome.report
        lines = [
            f"Last collaboration: {r.capability} -- {r.status.upper()}",
            f"Description: {r.description}",
        ]
        if r.worker_response:
            lines.append(f"Worker response:\n{r.worker_response}")
        if r.recommendation:
            lines.append(f"Recommendation: {r.recommendation}")
        if r.blocked_reason:
            lines.append(f"Blocked: {r.blocked_reason}")
        return "\n".join(lines)

    def can_handle(self, utterance: str) -> bool:
        return utterance.strip().lower().rstrip("?!.") in _COLLABORATION_TRIGGERS

    def run(
        self,
        description: str,
        payload: Optional[dict] = None,
        work_package_id: str = "",
        capability: str = "implement_feature",
    ) -> CollaborationOutcome:
        """
        Run the full collaboration pipeline.

        Steps:
          1. Create session
          2. Execute AI worker
          3. Engineering review gate (mandatory)
          4. Build report
          5. Build approval request
          6. Persist session
          7. Return outcome

        Never raises — always returns a CollaborationOutcome.
        """
        _start = time.perf_counter()
        payload = payload or {}

        # ── Step 1: Create session ────────────────────────────────────────
        ai_worker = self._resolve_ai_worker(capability)
        session = self._session_mgr.create(
            work_package_id=work_package_id or "direct",
            assigned_worker=ai_worker,
            capability=capability,
            description=description,
        )
        session = self._session_mgr.update(
            session, EngineeringCollaborationState.running()
        )

        # ── Step 2: Execute AI worker ─────────────────────────────────────
        worker_response, worker_error = self._execute_ai_worker(
            description=description,
            capability=capability,
            worker_name=ai_worker,
            payload=payload,
        )

        if worker_error:
            failed_state = EngineeringCollaborationState.pending().failed(worker_error)
            session = self._session_mgr.update(
                session,
                failed_state,
                recommendation="Worker failed. Check worker configuration and retry.",
            )
            self._session_mgr.persist(session)
            outcome = self._build_outcome(session, "Worker execution failed.")
            self._last_outcome = outcome
            return outcome

        worker_state = EngineeringCollaborationState.pending().with_worker_response(
            worker_response
        )
        session = self._session_mgr.update(
            session, worker_state, result={"response": worker_response}
        )

        # ── Step 3: Engineering review gate (mandatory) ───────────────────
        review_passed, tests_passed, review_data, blocked_reason = (
            self._run_engineering_gates(description, payload)
        )

        final_state = worker_state.with_review_result(
            review_passed=review_passed,
            tests_passed=tests_passed,
            blocked_reason=blocked_reason,
        )
        recommendation = self._build_recommendation(
            review_passed, tests_passed, blocked_reason
        )
        session = self._session_mgr.update(
            session,
            final_state,
            engineering_review=review_data,
            recommendation=recommendation,
        )

        # ── Steps 4-5: Build report and approval ──────────────────────────
        self._session_mgr.persist(session)
        outcome = self._build_outcome(session)
        self._last_outcome = outcome  # store for approval and follow-up routing
        return outcome

    # ── Private ───────────────────────────────────────────────────────────

    def _resolve_ai_worker(self, capability: str) -> str:
        """Find the worker name registered for this capability."""
        try:
            workers = self._manager.workers_for(capability)
            if workers:
                return workers[0].name
        except Exception:
            pass
        return "claude_ai_worker"

    def _execute_ai_worker(
        self,
        description: str,
        capability: str,
        worker_name: str,
        payload: dict,
    ) -> tuple[str, str]:
        """
        Execute the AI worker via WorkerCoordinator.
        Returns (response_text, error_message).
        error_message is empty on success.
        """
        workflow_name = f"ai_collab_{capability}"
        try:
            self._coordinator.register_workflow(workflow_name, [worker_name])
        except Exception:
            pass  # may already be registered

        task = WorkerTask(
            task_type=workflow_name,
            payload={
                "description": description,
                "capability_used": capability,
                "objective": description,
                **payload,
            },
            requester="collaboration_runner",
        )

        try:
            result = self._coordinator.run(task)

            if self._intelligence:
                self._intelligence.observe(result, capability)

            if not result.success:
                return "", result.error or "Worker returned failure."

            # Extract response from worker data
            worker_data = (
                result.data.get("results", {}).get(worker_name, {})
                or result.data
            )
            response = worker_data.get("response", "")
            if not response and result.observations:
                response = " ".join(result.observations)

            return response or "[Worker completed — no response text]", ""

        except Exception as exc:
            logger.exception("[COLLAB_RUNNER] AI worker execution raised.")
            return "", str(exc)

    def _run_engineering_gates(
        self,
        description: str,
        payload: dict,
    ) -> tuple[bool, bool, dict, str]:
        """
        Run the mandatory engineering review gate.

        Returns:
            (review_passed, tests_passed, review_data, blocked_reason)

        The review gate always runs — no path bypasses it.
        Regression test status is derived from the review data.
        """
        review_workflow = "run_engineering_review"
        try:
            self._coordinator.register_workflow(
                review_workflow, ["engineering_review_worker"]
            )
        except Exception:
            pass

        task = WorkerTask(
            task_type=review_workflow,
            payload={
                "description": description,
                "genesis": payload.get("genesis", ""),
            },
            requester="collaboration_runner",
        )

        try:
            result = self._coordinator.run(task)

            if self._intelligence:
                self._intelligence.observe(result, "run_engineering_review")

            if not result.success:
                return False, False, {}, (
                    result.error or "Engineering review worker returned failure."
                )

            # Extract review data
            worker_data = (
                result.data.get("results", {}).get("engineering_review_worker", {})
                or result.data
            )

            # Parse review result to determine pass/fail
            report_dict = worker_data.get("report", {})
            review      = report_dict.get("review", {})
            tr          = review.get("test_results", {})
            failed      = tr.get("failed", 0)
            status      = review.get("status", "complete")

            review_passed = status in ("complete", "COMPLETE")
            tests_passed  = failed == 0

            blocked_reason = ""
            if not review_passed:
                blocked_reason = f"Engineering review status: {status}"
            elif not tests_passed:
                blocked_reason = f"Regression tests: {failed} failed."

            return review_passed, tests_passed, worker_data, blocked_reason

        except Exception as exc:
            logger.exception("[COLLAB_RUNNER] Engineering review gate raised.")
            return False, False, {}, str(exc)

    def _build_recommendation(
        self,
        review_passed: bool,
        tests_passed: bool,
        blocked_reason: str,
    ) -> str:
        if review_passed and tests_passed:
            return (
                "All engineering gates passed. "
                "Ready for human review and approval."
            )
        if not review_passed:
            return (
                "Engineering review did not pass. "
                "Address review findings before proceeding."
            )
        if not tests_passed:
            return (
                "Regression tests failed. "
                "Fix failing tests before requesting approval."
            )
        return blocked_reason or "Collaboration blocked. Review findings above."

    def _build_outcome(
        self,
        session: EngineeringCollaborationSession,
        error: str = "",
    ) -> CollaborationOutcome:
        """Build the final CollaborationOutcome from a completed session."""
        report   = self._report_builder.build(session)
        approval = self._report_builder.build_approval(report)
        markdown = self._report_builder.render_full(report, approval)

        return CollaborationOutcome(
            session=session,
            report=report,
            approval=approval,
            markdown=markdown,
            success=session.is_complete,
            error=error,
        )
