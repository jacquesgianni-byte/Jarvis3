"""
Engineering Collaboration Framework — Models
Genesis-040 Sprint-002

Immutable structured models for the AI collaboration workflow.

Design principle:
  Data-first. All state is in frozen dataclasses.
  Markdown is a presentation layer only — never the source of truth.
  Every collaboration is tracked as a session, reported as a report,
  and gated by a human approval request.

Pipeline:
  CollaborationRunner creates EngineeringCollaborationSession
  → ClaudeAIWorker executes
  → EngineeringReviewOSWorker validates
  → ReportBuilder produces EngineeringCollaborationReport
  → EngineeringApprovalRequest gates installation
  → Human approves (never automatic)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CollaborationStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    REVIEWING = "reviewing"
    COMPLETE  = "complete"
    FAILED    = "failed"
    BLOCKED   = "blocked"


class ApprovalStatus(Enum):
    AWAITING  = "awaiting"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    BLOCKED   = "blocked"   # engineering gate failed — cannot be approved


# ---------------------------------------------------------------------------
# EngineeringCollaborationState
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineeringCollaborationState:
    """
    A snapshot of a collaboration session at a point in time.

    Immutable — each transition produces a new state.
    The runner holds the current state and produces a new one
    at each stage.
    """
    status:          CollaborationStatus
    stage:           str                    # human-readable current stage
    worker_response: str                    # raw AI worker response
    review_passed:   bool
    tests_passed:    bool
    blocked_reason:  str                    # empty if not blocked
    timestamp:       str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def pending(cls) -> "EngineeringCollaborationState":
        return cls(
            status=CollaborationStatus.PENDING,
            stage="initialising",
            worker_response="",
            review_passed=False,
            tests_passed=False,
            blocked_reason="",
        )

    @classmethod
    def running(cls) -> "EngineeringCollaborationState":
        return cls(
            status=CollaborationStatus.RUNNING,
            stage="ai_worker_executing",
            worker_response="",
            review_passed=False,
            tests_passed=False,
            blocked_reason="",
        )

    def with_worker_response(self, response: str) -> "EngineeringCollaborationState":
        return EngineeringCollaborationState(
            status=CollaborationStatus.REVIEWING,
            stage="engineering_review",
            worker_response=response,
            review_passed=False,
            tests_passed=False,
            blocked_reason="",
        )

    def with_review_result(
        self,
        review_passed: bool,
        tests_passed: bool,
        blocked_reason: str = "",
    ) -> "EngineeringCollaborationState":
        if not review_passed or not tests_passed:
            return EngineeringCollaborationState(
                status=CollaborationStatus.BLOCKED,
                stage="blocked",
                worker_response=self.worker_response,
                review_passed=review_passed,
                tests_passed=tests_passed,
                blocked_reason=blocked_reason,
            )
        return EngineeringCollaborationState(
            status=CollaborationStatus.COMPLETE,
            stage="complete",
            worker_response=self.worker_response,
            review_passed=True,
            tests_passed=True,
            blocked_reason="",
        )

    def failed(self, reason: str) -> "EngineeringCollaborationState":
        return EngineeringCollaborationState(
            status=CollaborationStatus.FAILED,
            stage="failed",
            worker_response=self.worker_response,
            review_passed=False,
            tests_passed=False,
            blocked_reason=reason,
        )


# ---------------------------------------------------------------------------
# EngineeringCollaborationSession
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineeringCollaborationSession:
    """
    Tracks a single AI engineering collaboration from start to finish.

    Immutable — updated via with_state() to produce a new session.
    SessionManager persists these to JSON.
    """
    session_id:       str
    work_package_id:  str
    assigned_worker:  str
    capability:       str
    description:      str
    started_at:       str
    state:            EngineeringCollaborationState
    completed_at:     Optional[str]                  = None
    result:           Optional[dict[str, Any]]       = None    # WorkerResult.data
    engineering_review: Optional[dict[str, Any]]     = None    # review report dict
    test_summary:     Optional[dict[str, Any]]       = None
    recommendation:   str                            = ""

    @classmethod
    def create(
        cls,
        work_package_id: str,
        assigned_worker: str,
        capability: str,
        description: str,
    ) -> "EngineeringCollaborationSession":
        return cls(
            session_id=str(uuid4()),
            work_package_id=work_package_id,
            assigned_worker=assigned_worker,
            capability=capability,
            description=description,
            started_at=datetime.now(timezone.utc).isoformat(),
            state=EngineeringCollaborationState.pending(),
        )

    def with_state(
        self,
        state: EngineeringCollaborationState,
        result: Optional[dict] = None,
        engineering_review: Optional[dict] = None,
        test_summary: Optional[dict] = None,
        recommendation: str = "",
    ) -> "EngineeringCollaborationSession":
        completed_at = (
            datetime.now(timezone.utc).isoformat()
            if state.status in (
                CollaborationStatus.COMPLETE,
                CollaborationStatus.FAILED,
                CollaborationStatus.BLOCKED,
            )
            else self.completed_at
        )
        return EngineeringCollaborationSession(
            session_id=self.session_id,
            work_package_id=self.work_package_id,
            assigned_worker=self.assigned_worker,
            capability=self.capability,
            description=self.description,
            started_at=self.started_at,
            state=state,
            completed_at=completed_at,
            result=result if result is not None else self.result,
            engineering_review=(
                engineering_review
                if engineering_review is not None
                else self.engineering_review
            ),
            test_summary=(
                test_summary if test_summary is not None else self.test_summary
            ),
            recommendation=recommendation or self.recommendation,
        )

    @property
    def is_complete(self) -> bool:
        return self.state.status == CollaborationStatus.COMPLETE

    @property
    def is_blocked(self) -> bool:
        return self.state.status in (
            CollaborationStatus.BLOCKED,
            CollaborationStatus.FAILED,
        )

    @property
    def duration_seconds(self) -> Optional[float]:
        if not self.completed_at:
            return None
        try:
            start = datetime.fromisoformat(self.started_at)
            end   = datetime.fromisoformat(self.completed_at)
            return (end - start).total_seconds()
        except Exception:
            return None


# ---------------------------------------------------------------------------
# EngineeringCollaborationReport
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineeringCollaborationReport:
    """
    The full structured record of a completed collaboration.

    This is the canonical data object — Markdown is derived from it,
    never the other way around.

    Persisted to JSON as part of engineering history.
    """
    report_id:            str
    session_id:           str
    worker:               str
    capability:           str
    description:          str
    duration_seconds:     Optional[float]
    status:               str                   # CollaborationStatus.value
    worker_response:      str
    review_passed:        bool
    tests_passed:         bool
    blocked_reason:       str
    recommendation:       str
    ready_for_approval:   bool
    files_changed:        tuple[str, ...]
    tests_executed:       int
    warnings:             tuple[str, ...]
    engineering_review:   Optional[dict]
    generated_at:         str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_session(cls, session: "EngineeringCollaborationSession") -> "EngineeringCollaborationReport":
        """Build a report from a completed session."""
        review  = session.engineering_review or {}
        tests   = session.test_summary or {}
        state   = session.state

        # Extract files changed from review if available
        review_inner = review.get("review", review)
        files_added    = review_inner.get("files_added", [])
        files_modified = review_inner.get("files_modified", [])
        files_changed  = tuple(files_added + files_modified)

        # Extract test counts
        tr = review_inner.get("test_results", tests)
        tests_executed = (
            tr.get("passed", 0) + tr.get("failed", 0) + tr.get("skipped", 0)
        )

        # Extract warnings from review
        risks = review_inner.get("risks", [])
        warnings = tuple(
            r if isinstance(r, str) else r.get("description", str(r))
            for r in risks
        )

        ready = (
            state.status == CollaborationStatus.COMPLETE
            and state.review_passed
            and state.tests_passed
        )

        return cls(
            report_id=str(uuid4()),
            session_id=session.session_id,
            worker=session.assigned_worker,
            capability=session.capability,
            description=session.description,
            duration_seconds=session.duration_seconds,
            status=state.status.value,
            worker_response=state.worker_response,
            review_passed=state.review_passed,
            tests_passed=state.tests_passed,
            blocked_reason=state.blocked_reason,
            recommendation=session.recommendation,
            ready_for_approval=ready,
            files_changed=files_changed,
            tests_executed=tests_executed,
            warnings=warnings,
            engineering_review=session.engineering_review,
        )


# ---------------------------------------------------------------------------
# EngineeringApprovalRequest
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineeringApprovalRequest:
    """
    The approval gate — produced at the end of every collaboration.

    ready_for_approval is True only when:
      - Worker completed successfully
      - Engineering review passed
      - Regression tests passed

    Human approval is always required — this object is never
    auto-approved by any code path.
    """
    request_id:          str
    session_id:          str
    report_id:           str
    description:         str
    worker:              str
    capability:          str
    status:              ApprovalStatus
    ready_for_approval:  bool
    blocking_reasons:    tuple[str, ...]
    recommendation:      str
    created_at:          str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_report(
        cls,
        report: "EngineeringCollaborationReport",
    ) -> "EngineeringApprovalRequest":
        blocking: list[str] = []
        if not report.review_passed:
            blocking.append("Engineering review did not pass.")
        if not report.tests_passed:
            blocking.append("Regression tests did not pass.")
        if report.blocked_reason:
            blocking.append(report.blocked_reason)

        approval_status = (
            ApprovalStatus.AWAITING
            if report.ready_for_approval
            else ApprovalStatus.BLOCKED
        )

        return cls(
            request_id=str(uuid4()),
            session_id=report.session_id,
            report_id=report.report_id,
            description=report.description,
            worker=report.worker,
            capability=report.capability,
            status=approval_status,
            ready_for_approval=report.ready_for_approval,
            blocking_reasons=tuple(blocking),
            recommendation=report.recommendation,
        )

    def to_text(self) -> str:
        sep = "─" * 56
        lines = [
            sep,
            "ENGINEERING APPROVAL REQUEST",
            sep,
            f"Worker:      {self.worker}",
            f"Capability:  {self.capability}",
            f"Description: {self.description}",
            f"Status:      {self.status.value.upper()}",
            "",
        ]
        if self.ready_for_approval:
            lines += [
                "✅ Ready for approval.",
                "All engineering gates passed.",
                "",
                "⚠️  Human approval required before any installation.",
                "Jarvis never installs automatically.",
            ]
        else:
            lines += [
                "🚫 Installation blocked.",
                "",
                "Blocking reasons:",
            ]
            for reason in self.blocking_reasons:
                lines.append(f"  • {reason}")
        if self.recommendation:
            lines += ["", f"Recommendation: {self.recommendation}"]
        lines.append(sep)
        return "\n".join(lines)
