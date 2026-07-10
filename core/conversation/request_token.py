"""Request token model for the Conversation Interrupt Engine.

A ``RequestToken`` represents ownership of a single user request within a
conversation. Tokens are created exclusively by the ``InterruptManager``;
nothing else in the system should construct one directly.

Design notes
------------
* Identity fields (``id``, ``generation``, ``created_at``) are immutable.
* ``status`` is the only mutable field and may only move through the
  legal lifecycle transitions below. Once a token reaches a terminal
  state it can never change again.

Lifecycle::

    ACTIVE ──> INTERRUPTED   (a newer request took ownership)
    ACTIVE ──> COMPLETED     (response delivered while still current)
    ACTIVE ──> CANCELLED     (reserved for future real cancellation)

This module has no dependencies on the UI, AI providers, speech, or the
Knowledge Engine.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import FrozenSet


class RequestStatus(Enum):
    """Lifecycle status of a request token."""

    ACTIVE = "active"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


#: States a token can never leave.
_TERMINAL_STATUSES: FrozenSet[RequestStatus] = frozenset(
    {
        RequestStatus.INTERRUPTED,
        RequestStatus.COMPLETED,
        RequestStatus.CANCELLED,
    }
)


class InvalidStatusTransitionError(RuntimeError):
    """Raised when a token is asked to make an illegal status transition."""


class RequestToken:
    """Lightweight, effectively-immutable handle for one user request.

    The identity of the token (``id``, ``generation``, ``created_at``)
    never changes. Only ``status`` evolves, and only via the internal
    transition methods used by the ``InterruptManager``.
    """

    __slots__ = ("_id", "_generation", "_created_at", "_status")

    def __init__(self, generation: int) -> None:
        if generation < 1:
            raise ValueError("generation must be >= 1")
        self._id: str = uuid.uuid4().hex
        self._generation: int = generation
        self._created_at: float = time.time()
        self._status: RequestStatus = RequestStatus.ACTIVE

    # ------------------------------------------------------------------
    # Read-only identity
    # ------------------------------------------------------------------
    @property
    def id(self) -> str:
        """Globally unique identifier for this request."""
        return self._id

    @property
    def generation(self) -> int:
        """Monotonically increasing conversation generation number."""
        return self._generation

    @property
    def created_at(self) -> float:
        """Unix timestamp of when the request was created."""
        return self._created_at

    @property
    def status(self) -> RequestStatus:
        """Current lifecycle status."""
        return self._status

    # ------------------------------------------------------------------
    # Convenience predicates
    # ------------------------------------------------------------------
    @property
    def is_active(self) -> bool:
        return self._status is RequestStatus.ACTIVE

    @property
    def is_terminal(self) -> bool:
        return self._status in _TERMINAL_STATUSES

    # ------------------------------------------------------------------
    # Internal transitions (called by InterruptManager only)
    # ------------------------------------------------------------------
    def _transition_to(self, new_status: RequestStatus) -> None:
        """Move to ``new_status`` if the transition is legal.

        Terminal states are final: any attempt to leave one raises
        :class:`InvalidStatusTransitionError`. Transitioning to the same
        status is a harmless no-op.
        """
        if new_status is self._status:
            return
        if self._status in _TERMINAL_STATUSES:
            raise InvalidStatusTransitionError(
                f"Token {self._id[:8]} is already {self._status.value!r} "
                f"and cannot become {new_status.value!r}."
            )
        self._status = new_status

    def _mark_interrupted(self) -> None:
        self._transition_to(RequestStatus.INTERRUPTED)

    def _mark_completed(self) -> None:
        self._transition_to(RequestStatus.COMPLETED)

    def _mark_cancelled(self) -> None:
        self._transition_to(RequestStatus.CANCELLED)

    # ------------------------------------------------------------------
    # Dunders
    # ------------------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"RequestToken(id={self._id[:8]}, gen={self._generation}, "
            f"status={self._status.value})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RequestToken):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)