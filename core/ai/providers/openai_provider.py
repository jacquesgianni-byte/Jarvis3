"""
OpenAI Provider (Genesis-030 Sprint-003)

Adds interruption support to ask_stream():
    - Accepts an optional is_cancelled callable
    - Checks cancellation between each token
    - Closes the stream cleanly on cancellation
    - Emits partial response if cancelled mid-stream
"""

import time

import httpx

from openai import (
    OpenAI,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from core import telemetry
from core.ai.providers.base import AIProvider
from core.ai.streaming import StreamCallbacks
from core.logger import get_logger
from core.models.response import Response
from core.settings.settings import Settings

_MAX_RESPONSE_TOKENS = 2000
_CONNECT_TIMEOUT_S = 10.0
_READ_TIMEOUT_S = 45.0

# Sentinel returned when stream was cancelled mid-way
_CANCELLED = object()


class OpenAIProvider(AIProvider):
    """
    OpenAI implementation of AIProvider with streaming + interruption support.
    """

    def __init__(self):
        self.settings = Settings()
        self.logger = get_logger()
        self._token_param = "max_completion_tokens"
        self.client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=httpx.Timeout(_READ_TIMEOUT_S, connect=_CONNECT_TIMEOUT_S),
            max_retries=0,
        )

    @property
    def supports_streaming(self) -> bool:
        return True

    def ask_stream(
        self,
        prompt: str,
        callbacks: StreamCallbacks,
        is_cancelled=None,
    ) -> Response:
        """
        Stream a response from OpenAI incrementally.

        Genesis-030 Sprint-003: accepts optional is_cancelled callable.
        If is_cancelled() returns True mid-stream, the stream is closed
        cleanly and the partial response is returned.

        Args:
            prompt:       The user's prompt.
            callbacks:    StreamCallbacks for token/complete/error events.
            is_cancelled: Optional callable returning True when cancelled.
        """
        if not self.settings.openai_api_key:
            err = Exception("OpenAI API key has not been configured.")
            callbacks.emit_error(err)
            return Response(success=False, message=str(err))

        fields = {"provider": "openai", "model": self.settings.default_model}
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user",   "content": prompt},
        ]

        full_text = []

        try:
            with telemetry.stage("openai_response", **fields):
                stream = self.client.chat.completions.create(
                    model=self.settings.default_model,
                    messages=messages,
                    stream=True,
                    **{self._token_param: _MAX_RESPONSE_TOKENS},
                )

            with telemetry.stage("response_parsing", **fields):
                for chunk in stream:
                    # Genesis-030 Sprint-003: check cancellation each token
                    if is_cancelled and is_cancelled():
                        stream.close()
                        partial = "".join(full_text).strip()
                        if partial:
                            callbacks.emit_complete(partial)
                            return Response(
                                success=True,
                                message=partial,
                                data={"cancelled": True},
                            )
                        return Response(
                            success=False,
                            message="Cancelled.",
                            data={"cancelled": True},
                        )

                    delta = chunk.choices[0].delta if chunk.choices else None
                    token = getattr(delta, "content", None) if delta else None
                    if token:
                        full_text.append(token)
                        callbacks.emit_token(token)

            complete = "".join(full_text).strip()

            if not complete:
                err = Exception(
                    "Sorry the AI service returned an empty response. Please try again."
                )
                callbacks.emit_error(err)
                return Response(success=False, message=str(err))

            callbacks.emit_complete(complete)
            return Response(success=True, message=complete)

        except APITimeoutError as e:
            msg = "Sorry the AI service is taking too long to respond. Please try again."
            callbacks.emit_error(e)
            return self._fail("timeout", e, msg)
        except APIConnectionError as e:
            msg = "Sorry I'm having trouble contacting the AI service right now."
            callbacks.emit_error(e)
            return self._fail("connection", e, msg)
        except AuthenticationError as e:
            msg = "My OpenAI API key appears to be invalid. Please check the key configuration."
            callbacks.emit_error(e)
            return self._fail("authentication", e, msg)
        except RateLimitError as e:
            msg = "We've hit the AI service rate limit. Give it a moment and try again."
            callbacks.emit_error(e)
            return self._fail("rate_limit", e, msg)
        except APIStatusError as e:
            msg = "Sorry the AI service reported an error. Please try again shortly."
            callbacks.emit_error(e)
            return self._fail("api_status", e, msg)
        except Exception as e:
            self.logger.exception("OpenAIProvider: unexpected streaming failure.")
            msg = "Sorry something unexpected went wrong while contacting the AI service."
            callbacks.emit_error(e)
            return self._fail("unexpected", e, msg)

    def ask(self, prompt: str) -> Response:
        """Send a prompt to OpenAI (blocking)."""
        if not self.settings.openai_api_key:
            return Response(
                success=False,
                message="OpenAI API key has not been configured."
            )

        fields = {"provider": "openai", "model": self.settings.default_model}

        with telemetry.stage("ai_total", **fields):
            with telemetry.stage("openai_request", **fields):
                messages = [
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user",   "content": prompt},
                ]

            request_started = time.perf_counter()
            try:
                with telemetry.stage("openai_response", **fields):
                    completion = self._create_completion(messages)

            except APITimeoutError as e:
                return self._fail(
                    "timeout", e,
                    "Sorry the AI service is taking too long to respond. Please try again."
                )
            except APIConnectionError as e:
                return self._fail(
                    "connection", e,
                    "Sorry I'm having trouble contacting the AI service right now."
                )
            except AuthenticationError as e:
                return self._fail(
                    "authentication", e,
                    "my OpenAI API key appears to be invalid or rejected."
                )
            except RateLimitError as e:
                return self._fail(
                    "rate_limit", e,
                    "we've hit the AI service rate limit. Give it a moment and try again."
                )
            except APIStatusError as e:
                return self._fail(
                    "api_status", e,
                    "Sorry the AI service reported an error. Please try again shortly."
                )
            except Exception as e:
                self.logger.exception("OpenAIProvider: unexpected failure.")
                return self._fail(
                    "unexpected", e,
                    "Sorry something unexpected went wrong while contacting the AI service."
                )

            with telemetry.stage("response_parsing", **fields):
                ai_ms = (time.perf_counter() - request_started) * 1000.0
                self._log_usage(completion, ai_ms)

                reply = (completion.choices[0].message.content or "").strip()

                if not reply:
                    finish = getattr(completion.choices[0], "finish_reason", None)
                    self.logger.error(
                        "OpenAIProvider: empty completion | model=%s | finish_reason=%s",
                        self.settings.default_model, finish,
                    )
                    return Response(
                        success=False,
                        message="Sorry the AI service returned an empty response. Please try again.",
                        data={"error_kind": "empty_completion", "finish_reason": str(finish)},
                    )

                return Response(success=True, message=reply)

    def _create_completion(self, messages):
        for attempt in range(2):
            try:
                return self.client.chat.completions.create(
                    model=self.settings.default_model,
                    messages=messages,
                    **{self._token_param: _MAX_RESPONSE_TOKENS},
                    reasoning_effort=self.settings.reasoning_effort,
                )
            except APIStatusError as e:
                detail = str(e)
                if (
                    attempt == 0
                    and "unsupported_parameter" in detail
                    and self._token_param in detail
                ):
                    previous = self._token_param
                    self._token_param = (
                        "max_tokens"
                        if previous == "max_completion_tokens"
                        else "max_completion_tokens"
                    )
                    self.logger.info(
                        "OpenAIProvider: model %s rejected %r -- switching to %r.",
                        self.settings.default_model, previous, self._token_param,
                    )
                    continue
                raise

    def _log_usage(self, completion, ai_ms: float) -> None:
        try:
            choice = completion.choices[0]
            usage = getattr(completion, "usage", None)
            details = getattr(usage, "completion_tokens_details", None)
            self.logger.info(
                "USAGE | req=%s | model=%s | ai_ms=%d | prompt=%s | "
                "completion=%s | reasoning=%s | finish=%s",
                telemetry.current_request_id(),
                self.settings.default_model,
                round(ai_ms),
                getattr(usage, "prompt_tokens", None),
                getattr(usage, "completion_tokens", None),
                getattr(details, "reasoning_tokens", None),
                getattr(choice, "finish_reason", None),
            )
        except Exception:
            self.logger.exception("OpenAIProvider: failed to log usage.")

    def _fail(self, kind: str, error: Exception, message: str) -> Response:
        self.logger.error(
            "OpenAIProvider: %s error | model=%s | %s",
            kind, self.settings.default_model, error,
        )
        return Response(
            success=False,
            message=message,
            data={"error": str(error), "error_kind": kind},
        )

    def _system_prompt(self) -> str:
        return (
            f"You are {self.settings.assistant_name}. "
            f"Your personality is {self.settings.personality}. "
            f"Always reply in {self.settings.language}. "
            "Be concise, helpful and professional."
        )
