"""
Genesis-018 Sprint 003 — Engineering Queue
FIFO scheduling foundation for the Engineering Coordinator.

Responsibilities:
    - Maintain an ordered list of pending EngineeringSessions
    - Track the currently active session
    - Track completed sessions (count + IDs)
    - Produce immutable QueueSnapshots
    - Provide queue statistics

Design constraints:
    - FIFO only — no priority ordering
    - Single-threaded — no concurrency
    - Deterministic — same inputs always produce same outputs
    - Read-only — does not modify sessions or execute work
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional

from .models import EngineeringRequest, EngineeringSession, QueueSnapshot, QueueStatus


class EngineeringQueue:
    """
    FIFO queue for EngineeringSessions.

    One session may be active at a time. All others wait in insertion order.
    The queue does not process sessions — it only manages their order.

    Usage pattern:
        queue.enqueue(session)          # add to back
        session = queue.dequeue()       # remove from front, set as active
        queue.mark_active_complete()    # move active → completed
        snapshot = queue.snapshot()     # read current state
    """

    def __init__(self) -> None:
        self._pending:          Deque[EngineeringSession] = deque()
        self._active:           Optional[EngineeringSession] = None
        self._completed_ids:    List[str] = []
        self._completed_count:  int = 0
        self._total_submitted:  int = 0
        self._position_map:     Dict[str, int] = {}   # session_id → 1-based enqueue position

    # ------------------------------------------------------------------
    # Core FIFO operations
    # ------------------------------------------------------------------

    def enqueue(self, session: EngineeringSession) -> int:
        """
        Add a session to the back of the queue.

        Args:
            session: The EngineeringSession to enqueue.

        Returns:
            The 1-based queue position of the newly added session.

        Raises:
            TypeError:  if session is not an EngineeringSession.
            ValueError: if the same session_id is already in the queue.
        """
        if not isinstance(session, EngineeringSession):
            raise TypeError(
                f"enqueue() expects EngineeringSession, "
                f"got {type(session).__name__}"
            )
        if self._is_known(session.session_id):
            raise ValueError(
                f"Session {session.session_id!r} is already in the queue"
            )

        self._total_submitted += 1
        position = self._total_submitted
        self._position_map[session.session_id] = position
        self._pending.append(session)
        return position

    def dequeue(self) -> Optional[EngineeringSession]:
        """
        Remove the session at the front of the queue and set it as active.

        Returns:
            The next EngineeringSession, or None if the queue is empty.

        Raises:
            RuntimeError: if another session is already active.
        """
        if self._active is not None:
            raise RuntimeError(
                f"Cannot dequeue — session {self._active.session_id!r} is "
                f"still active. Call mark_active_complete() first."
            )
        if not self._pending:
            return None

        self._active = self._pending.popleft()
        return self._active

    def peek(self) -> Optional[EngineeringSession]:
        """
        Return the session at the front of the queue without removing it.

        Returns:
            The next EngineeringSession, or None if the queue is empty.
        """
        return self._pending[0] if self._pending else None

    def remove(self, session_id: str) -> bool:
        """
        Remove a specific pending session by session_id.

        Cannot remove the active session (use mark_active_complete()).

        Args:
            session_id: The ID of the session to remove.

        Returns:
            True if the session was found and removed, False otherwise.
        """
        for i, session in enumerate(self._pending):
            if session.session_id == session_id:
                del self._pending[i]
                return True
        return False

    def clear(self) -> int:
        """
        Remove all pending sessions from the queue.
        Does not affect the active session or completed sessions.

        Returns:
            The number of sessions that were cleared.
        """
        count = len(self._pending)
        self._pending.clear()
        return count

    def mark_active_complete(self) -> Optional[EngineeringSession]:
        """
        Move the currently active session to completed status.

        Returns:
            The completed session, or None if no session was active.
        """
        if self._active is None:
            return None
        completed = self._active
        self._completed_ids.append(completed.session_id)
        self._completed_count += 1
        self._active = None
        return completed

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def size(self) -> int:
        """Return the number of sessions waiting in the queue (not including active)."""
        return len(self._pending)

    def empty(self) -> bool:
        """Return True if there are no pending sessions."""
        return len(self._pending) == 0

    @property
    def has_active(self) -> bool:
        return self._active is not None

    @property
    def active_session(self) -> Optional[EngineeringSession]:
        return self._active

    @property
    def completed_count(self) -> int:
        return self._completed_count

    @property
    def total_submitted(self) -> int:
        return self._total_submitted

    @property
    def completed_session_ids(self) -> List[str]:
        """Return a snapshot list of completed session IDs (ordered)."""
        return list(self._completed_ids)

    def position_of(self, session_id: str) -> Optional[int]:
        """
        Return the original 1-based enqueue position of a session.
        Returns None if the session was never enqueued.
        """
        return self._position_map.get(session_id)

    def pending_session_ids(self) -> List[str]:
        """Return ordered list of session IDs currently waiting."""
        return [s.session_id for s in self._pending]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> QueueStatus:
        """Return the current operational status of the queue."""
        if self._active is not None:
            return QueueStatus.PROCESSING
        if self._pending:
            return QueueStatus.WAITING
        if self._completed_count > 0:
            return QueueStatus.COMPLETE
        return QueueStatus.EMPTY

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def statistics(self) -> Dict[str, int]:
        """Return a dict of queue statistics."""
        return {
            "total_submitted": self._total_submitted,
            "pending":         len(self._pending),
            "active":          1 if self._active is not None else 0,
            "completed":       self._completed_count,
            "remaining":       len(self._pending) + (1 if self._active else 0),
        }

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> QueueSnapshot:
        """
        Produce an immutable point-in-time snapshot of the queue state.

        The snapshot is independent of the queue — subsequent queue
        mutations do not affect previously produced snapshots.
        """
        pending_ids = tuple(s.session_id for s in self._pending)
        return QueueSnapshot(
            queue_size=len(self._pending),
            status=self.status(),
            timestamp_ms=int(time.monotonic() * 1000),
            active_session_id=(
                self._active.session_id if self._active is not None else None
            ),
            pending_session_ids=pending_ids,
            completed_count=self._completed_count,
            total_submitted=self._total_submitted,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_known(self, session_id: str) -> bool:
        """Return True if this session_id is pending or currently active."""
        if self._active and self._active.session_id == session_id:
            return True
        return any(s.session_id == session_id for s in self._pending)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"EngineeringQueue("
            f"status={self.status().value}, "
            f"pending={self.size()}, "
            f"active={self.has_active}, "
            f"completed={self._completed_count}"
            f")"
        )