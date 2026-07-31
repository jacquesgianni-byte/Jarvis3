"""
Tests for Genesis-030 Sprint-002: Incremental AI Streaming

Covers:
    - StreamCallbacks: emit_token, emit_complete, emit_error
    - AIProvider base: default ask_stream fallback
    - OpenAIProvider: supports_streaming flag
    - Ordering guarantees
    - Empty responses
    - Provider exceptions
    - Non-streaming fallback path
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call
from core.ai.streaming import StreamCallbacks
from core.ai.providers.base import AIProvider
from core.models.response import Response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_callbacks():
    """Return StreamCallbacks with mock callables."""
    return StreamCallbacks(
        on_token=MagicMock(),
        on_complete=MagicMock(),
        on_error=MagicMock(),
    )


class _NonStreamingProvider(AIProvider):
    """Test provider that does NOT support streaming."""
    def ask(self, prompt: str) -> Response:
        return Response(success=True, message="blocking response")


class _StreamingProvider(AIProvider):
    """Test provider that DOES support streaming."""

    @property
    def supports_streaming(self) -> bool:
        return True

    def ask(self, prompt: str) -> Response:
        return Response(success=True, message="full response")

    def ask_stream(self, prompt: str, callbacks: StreamCallbacks) -> Response:
        tokens = ["Hello", " ", "world", "!"]
        for t in tokens:
            callbacks.emit_token(t)
        full = "".join(tokens)
        callbacks.emit_complete(full)
        return Response(success=True, message=full)


class _ErrorProvider(AIProvider):
    """Test provider that raises on ask_stream."""

    @property
    def supports_streaming(self) -> bool:
        return True

    def ask(self, prompt: str) -> Response:
        return Response(success=False, message="error")

    def ask_stream(self, prompt: str, callbacks: StreamCallbacks) -> Response:
        callbacks.emit_token("partial")
        exc = Exception("Stream failed")
        callbacks.emit_error(exc)
        return Response(success=False, message=str(exc))


class _EmptyProvider(AIProvider):
    """Test provider that returns empty response."""
    def ask(self, prompt: str) -> Response:
        return Response(success=True, message="")


# ===========================================================================
# StreamCallbacks
# ===========================================================================

class TestStreamCallbacks:

    def test_emit_token_calls_callback(self):
        cb = _make_callbacks()
        cb.emit_token("hello")
        cb.on_token.assert_called_once_with("hello")

    def test_emit_token_empty_not_called(self):
        cb = _make_callbacks()
        cb.emit_token("")
        cb.on_token.assert_not_called()

    def test_emit_complete_calls_callback(self):
        cb = _make_callbacks()
        cb.emit_complete("full text")
        cb.on_complete.assert_called_once_with("full text")

    def test_emit_error_calls_callback(self):
        cb = _make_callbacks()
        exc = Exception("boom")
        cb.emit_error(exc)
        cb.on_error.assert_called_once_with(exc)

    def test_none_callbacks_no_crash(self):
        cb = StreamCallbacks()
        cb.emit_token("hello")
        cb.emit_complete("full")
        cb.emit_error(Exception("boom"))

    def test_partial_callbacks_no_crash(self):
        cb = StreamCallbacks(on_token=MagicMock())
        cb.emit_token("hello")
        cb.emit_complete("full")   # no callback -- no crash
        cb.emit_error(Exception()) # no callback -- no crash


# ===========================================================================
# AIProvider base -- default ask_stream fallback
# ===========================================================================

class TestAIProviderBase:

    def test_non_streaming_provider_supports_streaming_false(self):
        provider = _NonStreamingProvider()
        assert provider.supports_streaming is False

    def test_default_ask_stream_falls_back_to_ask(self):
        provider = _NonStreamingProvider()
        cb = _make_callbacks()
        result = provider.ask_stream("hello", cb)
        assert result.success is True
        assert result.message == "blocking response"

    def test_default_ask_stream_emits_single_token(self):
        provider = _NonStreamingProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb)
        cb.on_token.assert_called_once_with("blocking response")

    def test_default_ask_stream_emits_complete(self):
        provider = _NonStreamingProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb)
        cb.on_complete.assert_called_once_with("blocking response")

    def test_default_ask_stream_error_emits_error(self):
        provider = _EmptyProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb)
        cb.on_error.assert_called_once()
        cb.on_complete.assert_not_called()


# ===========================================================================
# Streaming provider
# ===========================================================================

class TestStreamingProvider:

    def test_supports_streaming_true(self):
        provider = _StreamingProvider()
        assert provider.supports_streaming is True

    def test_tokens_emitted_in_order(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb)
        calls = [c.args[0] for c in cb.on_token.call_args_list]
        assert calls == ["Hello", " ", "world", "!"]

    def test_complete_emitted_once(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb)
        cb.on_complete.assert_called_once()

    def test_complete_contains_full_text(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb)
        full = cb.on_complete.call_args.args[0]
        assert "Hello" in full
        assert "world" in full

    def test_error_not_emitted_on_success(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb)
        cb.on_error.assert_not_called()

    def test_return_value_is_response(self):
        provider = _StreamingProvider()
        cb = _make_callbacks()
        result = provider.ask_stream("hello", cb)
        assert isinstance(result, Response)
        assert result.success is True


# ===========================================================================
# Error handling
# ===========================================================================

class TestStreamingErrors:

    def test_error_provider_emits_partial_then_error(self):
        provider = _ErrorProvider()
        cb = _make_callbacks()
        provider.ask_stream("hello", cb)
        cb.on_token.assert_called_once_with("partial")
        cb.on_error.assert_called_once()
        cb.on_complete.assert_not_called()

    def test_error_response_not_success(self):
        provider = _ErrorProvider()
        cb = _make_callbacks()
        result = provider.ask_stream("hello", cb)
        assert result.success is False


# ===========================================================================
# OpenAI provider -- streaming flag
# ===========================================================================

class TestOpenAIProviderStreaming:

    def test_supports_streaming_true(self):
        from core.ai.providers.openai_provider import OpenAIProvider
        with patch("core.ai.providers.openai_provider.OpenAI"):
            with patch("core.ai.providers.openai_provider.Settings") as mock_settings:
                mock_settings.return_value.openai_api_key = "test-key"
                mock_settings.return_value.default_model = "gpt-4o"
                mock_settings.return_value.reasoning_effort = None
                provider = OpenAIProvider()
                assert provider.supports_streaming is True

    def test_ask_stream_no_api_key_calls_error(self):
        from core.ai.providers.openai_provider import OpenAIProvider
        with patch("core.ai.providers.openai_provider.OpenAI"):
            with patch("core.ai.providers.openai_provider.Settings") as mock_settings:
                mock_settings.return_value.openai_api_key = ""
                mock_settings.return_value.default_model = "gpt-4o"
                provider = OpenAIProvider()
                cb = _make_callbacks()
                result = provider.ask_stream("hello", cb)
                assert result.success is False
                cb.on_error.assert_called_once()


# ===========================================================================
# Ordering guarantee
# ===========================================================================

class TestOrderingGuarantee:

    def test_tokens_arrive_in_order(self):
        """Verify emit order is preserved end to end."""
        received = []
        cb = StreamCallbacks(on_token=received.append)

        provider = _StreamingProvider()
        provider.ask_stream("hello", cb)

        assert received == ["Hello", " ", "world", "!"]

    def test_complete_arrives_after_all_tokens(self):
        """on_complete should fire after all on_token calls."""
        events = []
        cb = StreamCallbacks(
            on_token=lambda t: events.append(("token", t)),
            on_complete=lambda f: events.append(("complete", f)),
        )

        provider = _StreamingProvider()
        provider.ask_stream("hello", cb)

        types = [e[0] for e in events]
        assert types[-1] == "complete"
        assert all(t == "token" for t in types[:-1])
