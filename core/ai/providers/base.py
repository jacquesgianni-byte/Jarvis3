"""
Base AI Provider (Genesis-030 Sprint-003)

Updated ask_stream() signature to accept optional is_cancelled callable.
Providers that support streaming and interruption implement both.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional
from core.models.response import Response
from core.ai.streaming import StreamCallbacks


class AIProvider(ABC):
    """
    Base class for all AI providers.

    Streaming and interruption are both opt-in.
    The default ask_stream() falls back to ask() automatically.
    """

    @abstractmethod
    def ask(self, prompt: str) -> Response:
        """Process a prompt and return a complete Response."""

    @property
    def supports_streaming(self) -> bool:
        """True if this provider implements incremental streaming."""
        return False

    def ask_stream(
        self,
        prompt: str,
        callbacks: StreamCallbacks,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Response:
        """
        Stream a response incrementally via callbacks.

        Default falls back to ask() for non-streaming providers.

        Args:
            prompt:       The user's prompt.
            callbacks:    StreamCallbacks for token/complete/error events.
            is_cancelled: Optional callable returning True when cancelled.
        """
        # Check cancellation before even starting
        if is_cancelled and is_cancelled():
            return Response(success=False, message="Cancelled.", data={"cancelled": True})

        response = self.ask(prompt)
        if response.success and response.message:
            callbacks.emit_token(response.message)
            callbacks.emit_complete(response.message)
        else:
            callbacks.emit_error(Exception(response.message or "Unknown error"))
        return response
