"""
Engineering Collaboration Framework — Session Manager
Genesis-040 Sprint-002

Owns the lifecycle of EngineeringCollaborationSession objects.

Responsibilities:
  - Create new sessions
  - Update sessions with state transitions
  - Persist sessions to JSON (engineering history)
  - Retrieve sessions by ID

Does NOT:
  - Execute workers
  - Build reports
  - Make approval decisions
  - Call AI
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from typing import Optional

from core.engineering.collaboration.models import (
    EngineeringCollaborationSession,
    EngineeringCollaborationState,
)

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = "engineering_reviews"


class CollaborationSessionManager:
    """
    Manages the lifecycle of EngineeringCollaborationSession objects.

    Sessions are immutable — each update produces a new session object.
    The manager tracks the current session and persists it on completion.

    Public API:
        create(work_package_id, worker, capability, description) -> session
        update(session, state, **kwargs)                         -> session
        persist(session)                                         -> path
        load(session_id)                                         -> session | None
    """

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR) -> None:
        self._output_dir = output_dir
        self._sessions: dict[str, EngineeringCollaborationSession] = {}

    def create(
        self,
        work_package_id: str,
        assigned_worker: str,
        capability: str,
        description: str,
    ) -> EngineeringCollaborationSession:
        """Create a new collaboration session in PENDING state."""
        session = EngineeringCollaborationSession.create(
            work_package_id=work_package_id,
            assigned_worker=assigned_worker,
            capability=capability,
            description=description,
        )
        self._sessions[session.session_id] = session
        logger.info(
            "[SESSION_MGR] Created session %s for worker=%r cap=%r",
            session.session_id[:8], assigned_worker, capability,
        )
        return session

    def update(
        self,
        session: EngineeringCollaborationSession,
        state: EngineeringCollaborationState,
        result: Optional[dict] = None,
        engineering_review: Optional[dict] = None,
        test_summary: Optional[dict] = None,
        recommendation: str = "",
    ) -> EngineeringCollaborationSession:
        """Produce an updated session with the new state and optional data."""
        updated = session.with_state(
            state=state,
            result=result,
            engineering_review=engineering_review,
            test_summary=test_summary,
            recommendation=recommendation,
        )
        self._sessions[updated.session_id] = updated
        logger.info(
            "[SESSION_MGR] Session %s → %s",
            updated.session_id[:8], state.status.value,
        )
        return updated

    def persist(self, session: EngineeringCollaborationSession) -> str:
        """
        Persist a session to JSON in the output directory.
        Returns the file path written.
        """
        os.makedirs(self._output_dir, exist_ok=True)
        filename = f"collab_session_{session.session_id[:8]}.json"
        path = os.path.join(self._output_dir, filename)

        data = self._serialise(session)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            logger.info("[SESSION_MGR] Persisted session to %s", path)
        except Exception:
            logger.exception("[SESSION_MGR] Failed to persist session %s", session.session_id[:8])

        return path

    def get(self, session_id: str) -> Optional[EngineeringCollaborationSession]:
        """Return a session by ID if held in memory."""
        return self._sessions.get(session_id)

    def all_sessions(self) -> list[EngineeringCollaborationSession]:
        """Return all in-memory sessions, most recent first."""
        return list(reversed(list(self._sessions.values())))

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _serialise(session: EngineeringCollaborationSession) -> dict:
        """Convert a session to a JSON-serialisable dict."""
        return {
            "session_id":          session.session_id,
            "work_package_id":     session.work_package_id,
            "assigned_worker":     session.assigned_worker,
            "capability":          session.capability,
            "description":         session.description,
            "started_at":          session.started_at,
            "completed_at":        session.completed_at,
            "duration_seconds":    session.duration_seconds,
            "recommendation":      session.recommendation,
            "state": {
                "status":          session.state.status.value,
                "stage":           session.state.stage,
                "review_passed":   session.state.review_passed,
                "tests_passed":    session.state.tests_passed,
                "blocked_reason":  session.state.blocked_reason,
                "timestamp":       session.state.timestamp,
            },
            "result":              session.result,
            "engineering_review":  session.engineering_review,
            "test_summary":        session.test_summary,
        }
