"""
Genesis-018 Sprint 004 — Engineering Dispatcher
Decides which engineering session executes next.

Responsibilities:
    - Receive an EngineeringQueue
    - Select the next EngineeringSession via dispatch policy (FIFO now, extensible later)
    - Record every dispatch as an immutable DispatchRecord
    - Maintain dispatch history and statistics
    - Never execute engineering work itself

Design for extensibility:
    The dispatch policy is isolated in _select_next().
    Future scheduling policies (priority, specialised workers) can be
    introduced by overriding or configuring _select_next() without
    changing the public API.

Design constraints:
    - Deterministic — same queue state always selects the same session
    - Single-threaded — no concurrency
    - Read-only — does not modify sessions or execute work
    - One active dispatch at a time
"""

from __future__ import annotations

import uuid
import time
from typing import Dict, List, Optional

from .models import (
    DispatchRecord,
    DispatchStatus,
    EngineeringSession,
)
from .queue import EngineeringQueue


# ---------------------------------------------------------------------------
# Dispatch policy constants
# ---------------------------------------------------------------------------

class DispatchPolicy:
    """
    Named dispatch policy identifiers.

    Sprint 004: FIFO only.
    Future sprints may introduce PRIORITY, SPECIALISED, ROUND_ROBIN, etc.
    The public API of EngineeringDispatcher will not change when new
    policies are added — only _select_next() evolves internally.
    """
    FIFO = "FIFO"


# ---------------------------------------------------------------------------
# EngineeringDispatcher
# ---------------------------------------------------------------------------

class EngineeringDispatcher:
    """
    Selects which engineering session to execute next.

    The dispatcher operates on an EngineeringQueue.  It does not own the
    queue — the coordinator owns both and passes the queue to the dispatcher
    when dispatch is requested.

    Public API (stable — designed not to change when policies evolve):
        dispatch_next(queue)    → Optional[DispatchRecord]
        can_dispatch(queue)     → bool
        current_dispatch()      → Optional[DispatchRecord]
        dispatch_history()      → List[DispatchRecord]
        statistics()            → Dict[str, int]
        reset_current()         → None
    """

    VERSION = "018.004"

    def __init__(self, *, policy: str = DispatchPolicy.FIFO) -> None:
        """
        Initialise the dispatcher with a named scheduling policy.

        Args:
            policy: Scheduling policy name (see DispatchPolicy).
                    Currently only FIFO is supported.
        """
        if policy not in (DispatchPolicy.FIFO,):
            raise ValueError(
                f"Unknown dispatch policy {policy!r}. "
                f"Supported: {DispatchPolicy.FIFO!r}"
            )
        self._policy:          str                    = policy
        self._current:         Optional[DispatchRecord] = None
        self._history:         List[DispatchRecord]   = []
        self._total_dispatched: int                   = 0
        self._total_completed:  int                   = 0

    # ------------------------------------------------------------------
    # Core dispatch API
    # ------------------------------------------------------------------

    def can_dispatch(self, queue: EngineeringQueue) -> bool:
        """
        Return True if the dispatcher is able to dispatch a session now.

        Conditions for True:
            - No dispatch is currently active
            - The queue has at least one pending session
            - The queue has no currently active session (it will be set by us)
        """
        if not isinstance(queue, EngineeringQueue):
            raise TypeError(
                f"can_dispatch() expects EngineeringQueue, "
                f"got {type(queue).__name__}"
            )
        return (
            self._current is None
            and not queue.empty()
            and not queue.has_active
        )

    def dispatch_next(
        self,
        queue: EngineeringQueue,
        *,
        queued_at: Optional[int] = None,
    ) -> Optional[DispatchRecord]:
        """
        Select the next session from the queue and create a DispatchRecord.

        The selected session is moved to active status in the queue via
        queue.dequeue().  The caller is responsible for executing the session
        and calling complete_dispatch() when done.

        Args:
            queue:     The EngineeringQueue to select from.
            queued_at: Monotonic ms timestamp when the session was enqueued.
                       Used to calculate scheduling latency (wait_ms).
                       If None, defaults to dispatched_at (wait_ms = 0).

        Returns:
            A DispatchRecord in DISPATCHING status, or None if cannot dispatch.

        Raises:
            TypeError:    if queue is not an EngineeringQueue.
            RuntimeError: if a dispatch is already active.
        """
        if not isinstance(queue, EngineeringQueue):
            raise TypeError(
                f"dispatch_next() expects EngineeringQueue, "
                f"got {type(queue).__name__}"
            )
        if self._current is not None:
            raise RuntimeError(
                f"Cannot dispatch — dispatch "
                f"{self._current.dispatch_id!r} is still active. "
                f"Call complete_dispatch() first."
            )

        session = self._select_next(queue)
        if session is None:
            return None

        now = int(time.monotonic() * 1000)
        record = DispatchRecord(
            dispatch_id=str(uuid.uuid4()),
            session_id=session.session_id,
            queued_at=queued_at if queued_at is not None else now,
            dispatched_at=now,
            status=DispatchStatus.DISPATCHING,
        )

        self._current = record
        self._total_dispatched += 1
        return record

    def complete_dispatch(self) -> Optional[DispatchRecord]:
        """
        Mark the current dispatch as COMPLETE and move it to history.

        Returns:
            The completed DispatchRecord, or None if no dispatch was active.
        """
        if self._current is None:
            return None

        completed_at = int(time.monotonic() * 1000)
        completed    = self._current.complete(completed_at)
        self._history.append(completed)
        self._current = None
        self._total_completed += 1
        return completed

    def reset_current(self) -> bool:
        """
        Abandon the current dispatch without marking it complete.

        Used for error recovery only. Returns True if a dispatch was reset.
        """
        if self._current is None:
            return False
        self._history.append(
            DispatchRecord(
                dispatch_id=self._current.dispatch_id,
                session_id=self._current.session_id,
                queued_at=self._current.queued_at,
                dispatched_at=self._current.dispatched_at,
                status=DispatchStatus.COMPLETE,
                completed_at=int(time.monotonic() * 1000),
                duration_ms=0,
            )
        )
        self._current = None
        return True

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def current_dispatch(self) -> Optional[DispatchRecord]:
        """Return the currently active DispatchRecord, or None."""
        return self._current

    def dispatch_history(self) -> List[DispatchRecord]:
        """Return an ordered snapshot of all completed dispatch records."""
        return list(self._history)

    @property
    def has_active_dispatch(self) -> bool:
        return self._current is not None

    @property
    def policy(self) -> str:
        return self._policy

    @property
    def total_dispatched(self) -> int:
        return self._total_dispatched

    @property
    def total_completed(self) -> int:
        return self._total_completed

    @property
    def history_count(self) -> int:
        return len(self._history)

    def statistics(self) -> Dict[str, int]:
        """Return a dict of dispatcher statistics."""
        return {
            "total_dispatched": self._total_dispatched,
            "total_completed":  self._total_completed,
            "history_count":    self.history_count,
            "active":           1 if self._current is not None else 0,
        }

    def last_dispatch(self) -> Optional[DispatchRecord]:
        """Return the most recently completed DispatchRecord, or None."""
        return self._history[-1] if self._history else None

    # ------------------------------------------------------------------
    # Policy engine (extensible — only this method changes for new policies)
    # ------------------------------------------------------------------

    def _select_next(
        self, queue: EngineeringQueue
    ) -> Optional[EngineeringSession]:
        """
        Select and dequeue the next session according to the current policy.

        Sprint 004: FIFO — always selects the front of the queue.

        Future policies override this method's behaviour without changing
        the public dispatch_next() contract.

        Returns:
            The selected EngineeringSession (now active in queue), or None.
        """
        if self._policy == DispatchPolicy.FIFO:
            return queue.dequeue()
        # Future policies inserted here
        return None  # pragma: no cover

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"EngineeringDispatcher("
            f"policy={self._policy!r}, "
            f"active={self.has_active_dispatch}, "
            f"dispatched={self._total_dispatched}, "
            f"completed={self._total_completed}"
            f")"
        )