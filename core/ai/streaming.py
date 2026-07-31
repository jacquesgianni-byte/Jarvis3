"""
Streaming Response Protocol (Genesis-030 Sprint-002)

Defines the provider-agnostic streaming interface.

Any AI provider that supports streaming implements ask_stream() and
returns a StreamHandle. Providers that do not support streaming
simply do not override ask_stream() -- the base class default
falls back to the existing ask() completion path automatically.

Design constraints:
    - No UI coupling
    - No Agent coupling
    - No conversation state coupling
    - Transport concern only

Callback contract:
    on_token(token: str)       -- called once per text chunk, in order
    on_complete(full_text: str) -- called once when stream ends cleanly
    on_error(exc: Exception)   -- called once on failure; on_complete not called

Genesis-030 Sprint-002.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Callback type aliases
# ---------------------------------------------------------------------------

TokenCallback    = Callable[[str], None]
CompleteCallback = Callable[[str], None]
ErrorCallback    = Callable[[Exception], None]


# ---------------------------------------------------------------------------
# StreamCallbacks
# ---------------------------------------------------------------------------

@dataclass
class StreamCallbacks:
    """
    Container for the three streaming lifecycle callbacks.

    Pass one of these to AIProvider.ask_stream(). All callbacks are
    optional -- pass None for any you don't need.
    """
    on_token:    Optional[TokenCallback]    = None
    on_complete: Optional[CompleteCallback] = None
    on_error:    Optional[ErrorCallback]    = None

    def emit_token(self, token: str) -> None:
        """Emit a token -- no-op if no callback registered."""
        if self.on_token and token:
            self.on_token(token)

    def emit_complete(self, full_text: str) -> None:
        """Emit completion -- no-op if no callback registered."""
        if self.on_complete:
            self.on_complete(full_text)

    def emit_error(self, exc: Exception) -> None:
        """Emit error -- no-op if no callback registered."""
        if self.on_error:
            self.on_error(exc)
