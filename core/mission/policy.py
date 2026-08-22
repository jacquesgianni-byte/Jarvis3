"""
Jarvis OS Mission Capability Policy — Genesis-055 Sprint-001

MissionCapabilityPolicy is the single authority for what Jarvis can do
in Mission Mode. One object answers the question.

Security hierarchy (enforced, not described):
    Request
      ↓
    MissionContext          ← server-side, immutable
      ↓
    MissionCapabilityPolicy ← AUTHORITY — checked before dispatch
      ↓
    IntentClassifier        ← interpretation only, cannot grant capabilities
      ↓
    ApprovalGate
      ↓
    Worker

The policy is read-only at runtime. No pipeline stage, AI worker, or
message content can modify it.

MissionBoundaryViolation is raised (not returned) when a request
attempts to cross a denied boundary. It is never caught silently —
callers must handle it explicitly and log the attempt.
"""
from __future__ import annotations

import logging
from typing import FrozenSet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Capability levels
# ---------------------------------------------------------------------------

ALLOWED           = "allowed"
APPROVAL_REQUIRED = "approval_required"
DENIED            = "denied"


# ---------------------------------------------------------------------------
# MissionBoundaryViolation
# ---------------------------------------------------------------------------

class MissionBoundaryViolation(Exception):
    """
    Raised when a request attempts to cross a Mission Mode boundary.

    Never caught silently. Callers must:
      1. Log the attempt (worker name, capability, session_id).
      2. Return a structured MissionErrorResponse to the client.
      3. Never fall through to ConversationPipeline.

    Attributes:
        capability:  The capability that was attempted.
        worker:      The worker that was requested (if applicable).
        session_id:  The session that made the attempt.
        detail:      Human-readable description.
    """
    def __init__(
        self,
        capability: str,
        session_id: str = "",
        worker: str = "",
        detail: str = "",
    ):
        self.capability = capability
        self.session_id = session_id
        self.worker     = worker
        self.detail     = detail or f"Mission boundary violation: {capability!r} is denied."
        super().__init__(self.detail)

    def log(self) -> None:
        """Log the violation at WARNING level."""
        logger.warning(
            "[MISSION_BOUNDARY] VIOLATION | capability=%r | worker=%r | session=%s | %s",
            self.capability, self.worker, self.session_id, self.detail,
        )


# ---------------------------------------------------------------------------
# MissionCapabilityPolicy
# ---------------------------------------------------------------------------

class MissionCapabilityPolicy:
    """
    Single authority for Mission Mode capabilities.

    Read operations:
        READ_PROJECT, READ_ENGINEERING_KNOWLEDGE, READ_GIT,
        READ_REPOSITORY_FILES, RUN_TESTS, ENGINEERING_REVIEW
        → allowed (no approval required)

    Write operations:
        WRITE_FILES, COMMIT, PUSH, EXECUTE_CODE, ROLLBACK,
        CLAUDE_AI_PLANNING
        → approval_required (Gianni must approve before execution)

    Denied operations (hard block — no exception path):
        WEB_ACCESS, EXTERNAL_ACTIONS, GENERAL_CHAT_PIPELINE
        → denied (raises MissionBoundaryViolation)

    Workers are mapped to capabilities. A worker not in PERMITTED_WORKERS
    raises MissionBoundaryViolation regardless of the request content.
    """

    # -- Read operations — allowed, no approval ---------------------------

    READ_PROJECT               = ALLOWED
    READ_ENGINEERING_KNOWLEDGE = ALLOWED
    READ_GIT                   = ALLOWED
    READ_REPOSITORY_FILES      = ALLOWED
    RUN_TESTS                  = ALLOWED
    ENGINEERING_REVIEW         = ALLOWED

    # -- Write operations — approval required ------------------------------

    WRITE_FILES       = APPROVAL_REQUIRED
    COMMIT            = APPROVAL_REQUIRED
    PUSH              = APPROVAL_REQUIRED
    EXECUTE_CODE      = APPROVAL_REQUIRED
    ROLLBACK          = APPROVAL_REQUIRED
    CLAUDE_AI_PLANNING = APPROVAL_REQUIRED

    # -- Denied — hard block, no exception path ---------------------------

    WEB_ACCESS            = DENIED
    EXTERNAL_ACTIONS      = DENIED
    GENERAL_CHAT_PIPELINE = DENIED

    # -- Worker → capability mapping --------------------------------------

    PERMITTED_WORKERS: FrozenSet[str] = frozenset({
        "suite_runner_worker",        # RUN_TESTS
        "git_worker",                 # READ_GIT
        "file_context_reader",        # READ_REPOSITORY_FILES
        "engineering_review_worker",  # ENGINEERING_REVIEW
        "claude_ai_worker",           # CLAUDE_AI_PLANNING (approval_required)
        "execution_worker",           # EXECUTE_CODE (approval_required)
        "rollback_worker",            # ROLLBACK (approval_required)
    })

    DENIED_WORKERS: FrozenSet[str] = frozenset({
        "coding_worker",   # autonomous — no approval gate
        "hello_worker",    # plugin demo — not engineering
        "debug_worker",    # general session analysis — not mission-scoped
    })

    APPROVAL_REQUIRED_WORKERS: FrozenSet[str] = frozenset({
        "claude_ai_worker",
        "execution_worker",
        "rollback_worker",
    })

    # -- Knowledge categories permitted in Mission Mode -------------------

    PERMITTED_KNOWLEDGE_CATEGORIES: FrozenSet[str] = frozenset({
        "engineering",
        "architecture",
        "adr",
        "technical",
        "project",
    })

    # -- Policy enforcement methods ---------------------------------------

    @classmethod
    def check_worker(cls, worker_name: str, session_id: str = "") -> str:
        """
        Check if a worker is permitted in Mission Mode.

        Returns:
            ALLOWED           — dispatch immediately.
            APPROVAL_REQUIRED — check for approval record before dispatch.

        Raises:
            MissionBoundaryViolation — worker is denied. Caller must log
            and return a structured error. Never fall through to CHAT.
        """
        if worker_name in cls.DENIED_WORKERS:
            violation = MissionBoundaryViolation(
                capability=f"worker:{worker_name}",
                session_id=session_id,
                worker=worker_name,
                detail=f"Worker {worker_name!r} is denied in Mission Mode.",
            )
            violation.log()
            raise violation

        if worker_name not in cls.PERMITTED_WORKERS:
            violation = MissionBoundaryViolation(
                capability=f"worker:{worker_name}",
                session_id=session_id,
                worker=worker_name,
                detail=f"Worker {worker_name!r} is not registered in Mission Mode.",
            )
            violation.log()
            raise violation

        if worker_name in cls.APPROVAL_REQUIRED_WORKERS:
            return APPROVAL_REQUIRED

        return ALLOWED

    @classmethod
    def check_web_access(cls, session_id: str = "") -> None:
        """
        Web access is denied in Mission Mode.

        Raises MissionBoundaryViolation unconditionally.
        Web access requires a new MissionContext with web_access=True,
        authorised explicitly by Gianni — not by this method.
        """
        violation = MissionBoundaryViolation(
            capability="WEB_ACCESS",
            session_id=session_id,
            detail="Web access is denied in Mission Mode. Explicit authorisation from Gianni required.",
        )
        violation.log()
        raise violation

    @classmethod
    def check_chat_pipeline(cls, session_id: str = "") -> None:
        """
        General CHAT pipeline is denied from Mission Mode.

        Raises MissionBoundaryViolation unconditionally.
        Mission failures must not fall back to ConversationPipeline.
        """
        violation = MissionBoundaryViolation(
            capability="GENERAL_CHAT_PIPELINE",
            session_id=session_id,
            detail="Mission Mode cannot fall back to the general CHAT pipeline.",
        )
        violation.log()
        raise violation
