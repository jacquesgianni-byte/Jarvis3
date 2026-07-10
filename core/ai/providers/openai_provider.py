"""
OpenAI Provider

Implements the AIProvider interface using the OpenAI API.

Genesis-011 Maintenance Patch 002:
    * Connection timeout (10s) and read timeout (45s) on every request.
    * Retries disabled (max_retries=0) — a timed-out request is never
      silently retried, keeping worst-case latency predictable and
      avoiding double-billing for abandoned generations.
    * Response length capped (_MAX_RESPONSE_TOKENS) so open-ended
      prompts cannot generate for a minute at the user's expense.
    * Every failure mode maps to a clean, spoken-friendly Response —
      no exception ever escapes this module.
    * Telemetry split into openai_request / openai_response /
      response_parsing / ai_total, each tagged with provider and model.

Telemetry honesty note:
    openai_response measures the full blocking API round-trip. True
    separation of network latency vs model generation time requires
    streaming (time-to-first-token vs total) and is future work.
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
from core.logger import get_logger
from core.models.response import Response
from core.settings.settings import Settings

# Cap on completion tokens per reply. IMPORTANT: on reasoning models
# (gpt-5, o-series) this budget ALSO covers hidden reasoning tokens —
# set too low, the model spends it all on thinking and returns an EMPTY
# answer. 2000 leaves room to think and still write a spoken-length
# reply, while keeping worst-case cost bounded. Candidate for Settings.
_MAX_RESPONSE_TOKENS = 2000

_CONNECT_TIMEOUT_S = 10.0
_READ_TIMEOUT_S = 45.0


class OpenAIProvider(AIProvider):
    """
    OpenAI implementation of the AIProvider interface.

    Every call to ask() ends in exactly one of two states: a successful
    Response, or a graceful-failure Response. Never an exception.
    """

    def __init__(self):

        self.settings = Settings()
        self.logger = get_logger()

        # Which token-limit parameter the model accepts. Newer models
        # (gpt-5, o-series) require max_completion_tokens; older ones
        # use max_tokens. We default to the modern name and adapt once,
        # automatically, if the API rejects it — no model list to
        # maintain (Maintenance Patch 002.1).
        self._token_param = "max_completion_tokens"

        self.client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=httpx.Timeout(_READ_TIMEOUT_S, connect=_CONNECT_TIMEOUT_S),
            max_retries=0,
        )

    def ask(self, prompt: str) -> Response:
        """
        Send a prompt to OpenAI.

        Returns a Response in all circumstances — success or a clean,
        user-friendly failure. Exceptions never escape.
        """

        if not self.settings.openai_api_key:
            return Response(
                success=False,
                message="OpenAI API key has not been configured."
            )

        fields = {"provider": "openai", "model": self.settings.default_model}

        with telemetry.stage("ai_total", **fields):

            with telemetry.stage("openai_request", **fields):
                messages = [
                    {
                        "role": "system",
                        "content": self._system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ]

            request_started = time.perf_counter()
            try:
                with telemetry.stage("openai_response", **fields):
                    completion = self._create_completion(messages)

            # Order matters: APITimeoutError subclasses APIConnectionError.
            except APITimeoutError as e:
                return self._fail(
                    "timeout", e,
                    "Sorry sir, the AI service is taking too long to "
                    "respond. Please try again."
                )
            except APIConnectionError as e:
                return self._fail(
                    "connection", e,
                    "Sorry sir, I'm having trouble contacting the AI "
                    "service right now."
                )
            except AuthenticationError as e:
                return self._fail(
                    "authentication", e,
                    "Sir, my OpenAI API key appears to be invalid or "
                    "rejected. Please check the key configuration."
                )
            except RateLimitError as e:
                return self._fail(
                    "rate_limit", e,
                    "Sir, we've hit the AI service rate limit. Give it a "
                    "moment and try again."
                )
            except APIStatusError as e:
                return self._fail(
                    "api_status", e,
                    "Sorry sir, the AI service reported an error. Please "
                    "try again shortly."
                )
            except Exception as e:  # noqa: BLE001 — final safety net
                self.logger.exception("OpenAIProvider: unexpected failure.")
                return self._fail(
                    "unexpected", e,
                    "Sorry sir, something unexpected went wrong while "
                    "contacting the AI service."
                )

            with telemetry.stage("response_parsing", **fields):
                ai_ms = (time.perf_counter() - request_started) * 1000.0
                self._log_usage(completion, ai_ms)

                reply = (completion.choices[0].message.content or "").strip()

                # An empty completion must never become a silent blank
                # bubble. On reasoning models this typically means the
                # token budget was consumed by hidden reasoning
                # (finish_reason='length').
                if not reply:
                    finish = getattr(
                        completion.choices[0], "finish_reason", None
                    )
                    self.logger.error(
                        "OpenAIProvider: empty completion | model=%s | finish_reason=%s",
                        self.settings.default_model, finish,
                    )
                    return Response(
                        success=False,
                        message="Sorry sir, the AI service returned an "
                                "empty response. Please try again.",
                        data={
                            "error_kind": "empty_completion",
                            "finish_reason": str(finish),
                        },
                    )

                return Response(
                    success=True,
                    message=reply,
                )

    def _create_completion(self, messages):
        """
        Call the chat completions API with the response-length cap,
        adapting the token-limit parameter name to what the model
        accepts.

        First call uses the current parameter (modern name by default).
        If the API rejects it as unsupported_parameter, we switch to the
        other name, remember the choice for all future requests, and
        retry once. Any other error propagates to ask()'s handlers.
        """

        for attempt in range(2):
            try:
                return self.client.chat.completions.create(
                    model=self.settings.default_model,
                    messages=messages,
                    **{self._token_param: _MAX_RESPONSE_TOKENS},
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
                        "OpenAIProvider: model %s rejected %r — switching to %r.",
                        self.settings.default_model, previous, self._token_param,
                    )
                    continue
                raise

    def _log_usage(self, completion, ai_ms: float) -> None:
        """
        Log one summary line per AI request — the single-glance record:

            USAGE | req=13 | model=gpt-5 | ai_ms=8421 | prompt=45 |
            completion=1900 | reasoning=1680 | finish=length

        reasoning is only reported by reasoning models; None otherwise.
        Never raises — logging must not break the pipeline.
        """

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
        """Log a categorised failure and return a clean Response."""

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
        """
        Build the system prompt.
        """

        return (
            f"You are {self.settings.assistant_name}. "
            f"Your personality is {self.settings.personality}. "
            f"Always reply in {self.settings.language}. "
            "Be concise, helpful and professional."
        )