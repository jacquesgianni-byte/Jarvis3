"""
Base AI Provider (Genesis-030 Sprint-002)

Every AI provider must inherit from this class.

Genesis-030 Sprint-002:
    Added optional ask_stream() method. Providers that support streaming
    override it. The default implementation falls back to ask() so
    non-streaming providers require zero changes.
"""

from abc import ABC, abstractmethod
from core.models.response import Response
from core.ai.streaming import StreamCallbacks


class AIProvider(ABC):
    """
    Base class for all AI providers.

    Streaming is opt-in. Check supports_streaming before calling
    ask_stream(). The default ask_stream() falls back to ask()
    automatically so non-streaming providers work unchanged.
    """

    @abstractmethod
    def ask(self, prompt: str) -> Response:
        """
        Process a prompt and return a complete Response.
        """

    @property
    def supports_streaming(self) -> bool:
        """
        True if this provider implements incremental streaming.

        Override in subclasses that implement ask_stream().
        Default: False -- safe fallback for all existing providers.
        """
        return False

    def ask_stream(self, prompt: str, callbacks: StreamCallbacks) -> Response:
        """
        Stream a response incrementally via callbacks.

        Default implementation falls back to ask() for providers that
        do not support streaming. Tokens are emitted as a single chunk.

        Override this method in providers that support true streaming.

        Args:
            prompt:    The user's prompt.
            callbacks: StreamCallbacks instance with on_token/on_complete/on_error.

        Returns:
            A complete Response (same as ask()) for compatibility.
        """
        response = self.ask(prompt)
        if response.success and response.message:
            callbacks.emit_token(response.message)
            callbacks.emit_complete(response.message)
        else:
            callbacks.emit_error(Exception(response.message or "Unknown error"))
        return response
