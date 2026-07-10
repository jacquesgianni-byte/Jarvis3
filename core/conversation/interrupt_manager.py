"""Conversation Interrupt Engine — ownership manager.

The ``InterruptManager`` is the single authority for deciding which user
request currently "owns" the conversation. It knows nothing about AI
providers, the desktop UI, Android, speech, or the Knowledge Engine —
it only manages conversation state.

Typical flow::

    manager = InterruptManager()

    token = manager.new_request()        # user sends a message
    ... agent processes the request ...
    if manager.is_current(token):        # AI response comes back
        manager.complete(token)
        deliver(response)
    else:
        pass                             # silently discard stale response

Thread safety
-------------
All public methods are guarded by an internal lock, because in Jarvis OS
requests are processed on background worker threads while new requests
arrive from the UI thread.

Future-proofing
---------------
``cancel()`` exists now so that real provider-level cancellation can be
added later without changing any public API: callers already receive a
token, already check ``is_current()``, and already report completion.
When true cancellation lands, only the *internals* of ``interrupt_all``
/ ``cancel`` need to grow (e.g. firing a callback that aborts an HTTP
request).
"""

from __future__ import annotations

import threading
from typing import List, Optional

from .request_token import RequestStatus, RequestToken


class InterruptManager:
    """Manages conversation ownership via generation-numbered tokens."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation: int = 0
        self._active_token: Optional[RequestToken] = None
        self._history: List[RequestToken] = []

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------
    def new_request(self) -> RequestToken:
        """Start a new request and make it the active conversation.

        Any previously active request is interrupted. The conversation
        generation number is incremented. Returns the new token, which
        the caller should carry through the processing pipeline and pass
        back to :meth:`is_current` / :meth:`complete`.
        """
        with self._lock:
            if self._active_token is not None and self._active_token.is_active:
                self._active_token._mark_interrupted()
            self._generation += 1
            token = RequestToken(generation=self._generation)
            self._active_token = token
            self._history.append(token)
            return token

    def is_current(self, token: Optional[RequestToken]) -> bool:
        """Return ``True`` if ``token`` still owns the conversation.

        A token is current only if it is the most recent request *and*
        it is still in the ``ACTIVE`` state. ``None`` is never current.
        """
        if token is None:
            return False
        with self._lock:
            return token is self._active_token and token.is_active

    def complete(self, token: RequestToken) -> bool:
        """Mark ``token`` completed if it is still the current request.

        Returns ``True`` if the token was current and is now completed —
        meaning the caller should deliver the response. Returns ``False``
        if the token was stale — meaning the caller should silently
        discard the response. Never raises for stale tokens.
        """
        with self._lock:
            if token is self._active_token and token.is_active:
                token._mark_completed()
                return True
            return False

    # ------------------------------------------------------------------
    # Explicit interruption / cancellation
    # ------------------------------------------------------------------
    def interrupt_all(self) -> Optional[RequestToken]:
        """Interrupt the active request without starting a new one.

        Useful for a future "Stop" button. Returns the token that was
        interrupted, or ``None`` if nothing was active.
        """
        with self._lock:
            token = self._active_token
            if token is not None and token.is_active:
                token._mark_interrupted()
                return token
            return None

    def cancel(self, token: RequestToken) -> bool:
        """Mark ``token`` as CANCELLED if it is still active.

        Placeholder for real provider-level cancellation. Returns
        ``True`` if the token was active and is now cancelled.
        """
        with self._lock:
            if token.is_active:
                token._mark_cancelled()
                if token is self._active_token:
                    self._active_token = None
                return True
            return False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def generation(self) -> int:
        """Current conversation generation (0 before any request)."""
        with self._lock:
            return self._generation

    @property
    def active_token(self) -> Optional[RequestToken]:
        """The token that currently owns the conversation, if any."""
        with self._lock:
            token = self._active_token
            return token if (token is not None and token.is_active) else None

    def history(self, limit: Optional[int] = None) -> List[RequestToken]:
        """Return past tokens (oldest first), optionally limited."""
        with self._lock:
            items = list(self._history)
        return items[-limit:] if limit else items

    def completed_count(self) -> int:
        """Number of requests that finished successfully."""
        with self._lock:
            return sum(
                1 for t in self._history if t.status is RequestStatus.COMPLETED
            )

    def interrupted_count(self) -> int:
        """Number of requests that were interrupted by newer ones."""
        with self._lock:
            return sum(
                1 for t in self._history if t.status is RequestStatus.INTERRUPTED
            )