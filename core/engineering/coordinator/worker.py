"""
Genesis-018 Sprint 005 — Engineering Worker Interface
Abstract worker contract and local single-threaded implementation.

Architectural refinement (pre-freeze):
    - DefaultEngineeringWorker → LocalEngineeringWorker
    - Stable worker_id() identity on the ABC contract
    - capabilities: tuple[str, ...] added to WorkerRecord

The worker interface is intended to be permanent.
Future workers are interchangeable without changing the Coordinator or Dispatcher:

    LocalEngineeringWorker       — single-threaded, local execution
    ClaudeEngineeringWorker      — AI-assisted execution via Claude
    GPTEngineeringWorker         — AI-assisted execution via GPT
    TestingEngineeringWorker     — test-focused execution
    DocumentationEngineeringWorker
    SecurityEngineeringWorker

Design constraints (Sprint 005):
    - One worker only (LocalEngineeringWorker)
    - Single-threaded, deterministic
    - Worker does NOT perform engineering — it owns execution state only
"""

from __future__ import annotations

import abc
import time
import uuid
from typing import List, Optional, Tuple

from .models import EngineeringSession, WorkerRecord, WorkerStatus


# ---------------------------------------------------------------------------
# EngineeringWorker — abstract base class (the permanent contract)
# ---------------------------------------------------------------------------

class EngineeringWorker(abc.ABC):
    """
    Abstract interface every engineering worker must implement.

    This interface is permanent. Future worker implementations are
    interchangeable without modifying EngineeringCoordinator or
    EngineeringDispatcher.

    The dispatcher only ever asks:
        worker_id()         — who are you? (stable identity)
        can_accept()        — are you free?
        accept_session()    — take this work
        status()            — what are you doing?
        current_session()   — which session?
        complete_session()  — you're done
        clear()             — reset to idle
        record()            — give me your current state snapshot
    """

    # ------------------------------------------------------------------
    # Abstract methods — every subclass must implement all of these
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def worker_id(self) -> str:
        """
        Return the stable, permanent identifier for this worker instance.

        Convention: worker-{type}-{sequence}
            worker-local-001
            worker-claude-001
            worker-gpt-001
            worker-testing-001
        """

    @abc.abstractmethod
    def worker_name(self) -> str:
        """Return the human-readable name of this worker."""

    @abc.abstractmethod
    def capabilities(self) -> Tuple[str, ...]:
        """
        Return the immutable set of capabilities this worker provides.

        Examples:
            ("engineering",)
            ("engineering", "planning")
            ("testing",)
            ("documentation",)

        The Dispatcher may use capabilities for routing in future sprints.
        Sprint 005: capabilities are recorded but not used for routing.
        """

    @abc.abstractmethod
    def can_accept(self) -> bool:
        """Return True if this worker can accept a new session right now."""

    @abc.abstractmethod
    def accept_session(self, session: EngineeringSession) -> bool:
        """
        Assign a session to this worker.

        Returns True if accepted, False if the worker cannot accept.
        Must transition the worker to BUSY status on acceptance.
        """

    @abc.abstractmethod
    def status(self) -> WorkerStatus:
        """Return the current operational status of this worker."""

    @abc.abstractmethod
    def current_session(self) -> Optional[EngineeringSession]:
        """Return the session currently assigned to this worker, or None."""

    @abc.abstractmethod
    def complete_session(self) -> Optional[EngineeringSession]:
        """
        Mark the current session as complete.

        Returns the completed session, or None if none was active.
        Must transition the worker to COMPLETED status.
        """

    @abc.abstractmethod
    def clear(self) -> None:
        """Reset this worker to IDLE, clearing any session state."""

    @abc.abstractmethod
    def record(self) -> WorkerRecord:
        """Return an immutable snapshot of this worker's current state."""


# ---------------------------------------------------------------------------
# LocalEngineeringWorker — Sprint 005 single concrete implementation
# ---------------------------------------------------------------------------

class LocalEngineeringWorker(EngineeringWorker):
    """
    Single-threaded, deterministic local engineering worker.

    Executes sessions in the same process, no concurrency, no AI.
    The reference implementation of the EngineeringWorker interface.

    Identity convention:  worker-local-{sequence:03d}
        First instance:   worker-local-001
        Second instance:  worker-local-002

    Capabilities: ("engineering",)
    """

    _instance_counter: int = 0

    def __init__(
        self,
        *,
        name:        str           = "LocalWorker",
        worker_id:   Optional[str] = None,
        capabilities: Optional[Tuple[str, ...]] = None,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("LocalEngineeringWorker name must be a non-blank string")

        LocalEngineeringWorker._instance_counter += 1
        seq = LocalEngineeringWorker._instance_counter

        self._worker_id:       str              = (
            worker_id if worker_id is not None
            else f"worker-local-{seq:03d}"
        )
        self._worker_name:     str              = name
        self._capabilities:    Tuple[str, ...]  = (
            capabilities if capabilities is not None
            else ("engineering",)
        )
        self._status:          WorkerStatus     = WorkerStatus.IDLE
        self._current_session: Optional[EngineeringSession] = None
        self._completed_count: int              = 0
        self._completed_ids:   List[str]        = []
        self._created_at:      int              = int(time.monotonic() * 1000)
        self._last_activity_ms: Optional[int]   = None

    # ------------------------------------------------------------------
    # EngineeringWorker contract implementation
    # ------------------------------------------------------------------

    def worker_id(self) -> str:
        return self._worker_id

    def worker_name(self) -> str:
        return self._worker_name

    def capabilities(self) -> Tuple[str, ...]:
        return self._capabilities

    def can_accept(self) -> bool:
        return self._status.can_accept()

    def accept_session(self, session: EngineeringSession) -> bool:
        if not isinstance(session, EngineeringSession):
            raise TypeError(
                f"accept_session() expects EngineeringSession, "
                f"got {type(session).__name__}"
            )
        if not self.can_accept():
            return False
        self._current_session  = session
        self._status           = WorkerStatus.BUSY
        self._last_activity_ms = int(time.monotonic() * 1000)
        return True

    def status(self) -> WorkerStatus:
        return self._status

    def current_session(self) -> Optional[EngineeringSession]:
        return self._current_session

    def complete_session(self) -> Optional[EngineeringSession]:
        if self._current_session is None:
            return None
        completed              = self._current_session
        self._completed_ids.append(completed.session_id)
        self._completed_count += 1
        self._current_session  = None
        self._status           = WorkerStatus.COMPLETED
        self._last_activity_ms = int(time.monotonic() * 1000)
        return completed

    def clear(self) -> None:
        self._current_session  = None
        self._status           = WorkerStatus.IDLE
        self._last_activity_ms = int(time.monotonic() * 1000)

    def record(self) -> WorkerRecord:
        return WorkerRecord(
            worker_id=self._worker_id,
            worker_name=self._worker_name,
            status=self._status,
            created_at=self._created_at,
            completed_sessions=self._completed_count,
            current_session_id=(
                self._current_session.session_id
                if self._current_session is not None else None
            ),
            last_activity_ms=self._last_activity_ms,
            capabilities=self._capabilities,
        )

    # ------------------------------------------------------------------
    # Additional inspection (beyond the abstract contract)
    # ------------------------------------------------------------------

    @property
    def completed_count(self) -> int:
        return self._completed_count

    @property
    def completed_session_ids(self) -> List[str]:
        return list(self._completed_ids)

    @property
    def is_idle(self) -> bool:
        return self._status == WorkerStatus.IDLE

    @property
    def is_busy(self) -> bool:
        return self._status.is_busy()

    def mark_unavailable(self) -> None:
        """Transition to UNAVAILABLE (error/shutdown path)."""
        self._status           = WorkerStatus.UNAVAILABLE
        self._last_activity_ms = int(time.monotonic() * 1000)

    def mark_idle(self) -> None:
        """Alias for clear() — semantic clarity."""
        self.clear()

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        session_part = (
            f", session={self._current_session.session_id[:8]}…"
            if self._current_session else ""
        )
        return (
            f"LocalEngineeringWorker("
            f"id={self._worker_id!r}, "
            f"name={self._worker_name!r}, "
            f"status={self._status.value}, "
            f"completed={self._completed_count}, "
            f"capabilities={self._capabilities}"
            f"{session_part}"
            f")"
        )


# ---------------------------------------------------------------------------
# Backwards-compatibility alias
# ---------------------------------------------------------------------------

# Retained so any external code referencing DefaultEngineeringWorker
# continues to work without modification. Will be removed in a future
# milestone once all call sites are updated.
DefaultEngineeringWorker = LocalEngineeringWorker