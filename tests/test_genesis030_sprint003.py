"""
Tests for Genesis-030 Sprint-003: Interruptible Responses

Covers:
    - StreamCallbacks: cancellation before start
    - AIProvider base: is_cancelled check before ask()
    - Streaming provider: cancellation mid-stream
    - Partial response preservation
    - Clean stream closure
    - No regression on Sprint-002 streaming
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from core.ai.streaming import StreamCallbacks
from core.ai.providers.base import AIProvider
from core.models.response import Response


# ---------------------------------------------------------------------------
# Test providers
# ---------------------------------------------------------------------------

class _StreamingProvider(AIProvider):
    """Streaming provider that respects is_cancelled."""

    @property
    def supports_streaming(self) -> bool:
        return True

    def ask(self, prompt: str) -> Response:
        return Response(success=True, message="full response")

    def ask_stream(self, prompt, callbacks, is_cancelled=None):
        tokens = ["Hello", " ", "world", "!", " More", " text"]
        for i, t in enumerate(tokens):
            if is_cancelled and is_cancelled():
                # Close cleanly, emit partial
                partial = "".join(tokens[:i])
                if partial:
                    callbacks.emit_complete(partial)
                    return Response(success=True, message=partial, data={"cancelled": True})
                return Response(success=False, message="Cancelled.", data={"cancelled": True})
            callbacks.emit_token(t)
        full = "".join(tokens)
        callbacks.emit_complete(full)
        return Response(success=True, message=full)


class _NonStreamingProvider(AIProvider):
    def ask(self, prompt: str) -> Response:
        return Response(success=True, message="blocking response")


def _make_callbacks():
    return StreamCallbacks(
        on_token=MagicMock(),
        on_complete=MagicMock(),
        on_error=MagicMock(),
    )


# ===========================================================================
# Base provider -- is_cancelled before ask
# ===========================================================================

class TestBaseCancellation:

    def test_cancelled_before_start_returns_cancelled(self):
        provider = _NonStreamingProvider()
        cb = _make_callbacks()
        result = provider.ask_stream("hello", cb, is_cancelled=lambda: True)
        assert result.success is False
        assert "Cancelled" in result.message

    def test_cancelled_before_start_no_token_emitted(self):
        provider = _NonStreamingProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb, is_cancelled=lambda: True)
        cb.on_token.assert_not_called()

    def test_not_cancelled_proceeds_normally(self):
        provider = _NonStreamingProvider()
        cb = _make_callbacks()
        result = provider.ask_stream("hello", cb, is_cancelled=lambda: False)
        assert result.success is True
        cb.on_token.assert_called_once()

    def test_none_is_cancelled_no_crash(self):
        provider = _NonStreamingProvider()
        cb = _make_callbacks()
        result = provider.ask_stream("hello", cb, is_cancelled=None)
        assert result.success is True


# ===========================================================================
# Streaming provider -- mid-stream cancellation
# ===========================================================================

class TestMidStreamCancellation:

    def test_cancel_after_two_tokens(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()

        call_count = [0]
        def is_cancelled():
            call_count[0] += 1
            return call_count[0] > 2  # cancel after 2 tokens

        result = provider.ask_stream("hello", cb, is_cancelled=is_cancelled)
        # Should have received some but not all tokens
        assert cb.on_token.call_count < 6

    def test_partial_response_returned_on_cancel(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()

        call_count = [0]
        def is_cancelled():
            call_count[0] += 1
            return call_count[0] > 2

        result = provider.ask_stream("hello", cb, is_cancelled=is_cancelled)
        # Partial response preserved
        assert result.message != ""

    def test_complete_emitted_with_partial_on_cancel(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()

        call_count = [0]
        def is_cancelled():
            call_count[0] += 1
            return call_count[0] > 3

        provider.ask_stream("hello", cb, is_cancelled=is_cancelled)
        cb.on_complete.assert_called_once()

    def test_no_tokens_after_cancel(self):
        provider = _StreamingProvider()
        received = []
        cancelled = [False]

        def on_token(t):
            received.append(t)
            if len(received) >= 2:
                cancelled[0] = True

        cb = StreamCallbacks(on_token=on_token)
        provider.ask_stream("hello", cb, is_cancelled=lambda: cancelled[0])

        # Should not have received all 6 tokens
        assert len(received) < 6

    def test_immediate_cancel_no_tokens(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb, is_cancelled=lambda: True)
        cb.on_token.assert_not_called()

    def test_no_cancel_all_tokens_received(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb, is_cancelled=lambda: False)
        assert cb.on_token.call_count == 6
        cb.on_complete.assert_called_once()


# ===========================================================================
# Ordering preserved after cancellation
# ===========================================================================

class TestOrderingAfterCancellation:

    def test_received_tokens_are_in_order(self):
        provider = _StreamingProvider()
        received = []
        cancelled = [False]

        def on_token(t):
            received.append(t)
            if len(received) >= 3:
                cancelled[0] = True

        cb = StreamCallbacks(on_token=on_token)
        provider.ask_stream("hello", cb, is_cancelled=lambda: cancelled[0])

        assert received == ["Hello", " ", "world"]

    def test_partial_text_matches_received_tokens(self):
        provider = _StreamingProvider()
        received = []
        complete_text = [None]
        cancelled = [False]

        def on_token(t):
            received.append(t)
            if len(received) >= 2:
                cancelled[0] = True

        def on_complete(full):
            complete_text[0] = full

        cb = StreamCallbacks(on_token=on_token, on_complete=on_complete)
        provider.ask_stream("hello", cb, is_cancelled=lambda: cancelled[0])

        if complete_text[0]:
            # Partial text should match what was received
            assert all(t in complete_text[0] for t in received)


# ===========================================================================
# Sprint-002 regression guard
# ===========================================================================

class TestSprint002Regression:

    def test_streaming_without_cancellation_unchanged(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()
        result = provider.ask_stream("hello", cb)
        assert result.success is True
        assert cb.on_token.call_count == 6
        cb.on_complete.assert_called_once()
        cb.on_error.assert_not_called()

    def test_non_streaming_fallback_unchanged(self):
        provider = _NonStreamingProvider()
        cb = _make_callbacks()
        result = provider.ask_stream("hello", cb)
        assert result.success is True
        cb.on_token.assert_called_once_with("blocking response")
