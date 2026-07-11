"""
Anthropic Provider (Genesis-015 Task 001)

Implements the AIProvider interface using the Anthropic Python SDK.

Design mirrors OpenAIProvider exactly:
    * Same ask() contract: always returns a Response, never raises.
    * Same telemetry style: anthropic_request / anthropic_response /
      response_parsing / ai_total, all tagged provider=anthropic.
    * Same USAGE line format, with Anthropic token field names mapped
      to the established prompt/completion/reasoning vocabulary.
    * Same system-prompt construction from Settings.
    * Same timeout posture (10s connect, 45s read).

The only caller-visible difference is the telemetry stage names
(anthropic_* vs openai_*) so the Engineering Console can distinguish
which brain answered each request.
"""

import time

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from core import telemetry
try:
    from core.ai.providers.base import AIProvider
except ImportError:
    # Fallback if base module uses a different name or path
    from abc import ABC, abstractmethod
    class AIProvider(ABC):
        @abstractmethod
        def ask(self, prompt: str): ...  # pragma: no cover
from core.logger import get_logger
from core.models.response import Response
from core.settings.settings import Settings

# Match the OpenAI provider's token budget. Anthropic does not burn
# hidden reasoning tokens by default (no separate reasoning budget),
# so 2000 completion tokens is generous for spoken-length responses.
_MAX_TOKENS = 2000

_CONNECT_TIMEOUT_S = 10.0
_READ_TIMEOUT_S = 45.0


class AnthropicProvider(AIProvider):
    """
    Anthropic Claude implementation of the AIProvider interface.

    Every call to ask() ends in exactly one of two states: a successful
    Response, or a graceful-failure Response. Never an exception.
    """

    def __init__(self):
        self.settings = Settings()
        self.logger = get_logger()

        self.client = Anthropic(
            api_key=self.settings.anthropic_api_key,
            timeout=_READ_TIMEOUT_S,
            max_retries=0,
        )

    def ask(self, prompt: str) -> Response:
        """
        Send a prompt to Anthropic Claude.

        Returns a Response in all circumstances — success or a clean,
        user-friendly failure. Exceptions never escape.
        """

        if not self.settings.anthropic_api_key:
            return Response(
                success=False,
                message="Anthropic API key has not been configured, sir.",
            )

        fields = {
            "provider": "anthropic",
            "model": self.settings.anthropic_model,
        }

        with telemetry.stage("ai_total", **fields):

            with telemetry.stage("anthropic_request", **fields):
                system = self._system_prompt()
                messages = [{"role": "user", "content": prompt}]

            request_started = time.perf_counter()
            try:
                with telemetry.stage("anthropic_response", **fields):
                    response = self.client.messages.create(
                        model=self.settings.anthropic_model,
                        max_tokens=_MAX_TOKENS,
                        system=system,
                        messages=messages,
                    )

            except APITimeoutError as e:
                return self._fail(
                    "timeout", e,
                    "Sorry sir, Claude is taking too long to respond. "
                    "Please try again.",
                )
            except AuthenticationError as e:
                return self._fail(
                    "auth", e,
                    "Sorry sir, the Anthropic API key appears to be "
                    "invalid. Please check your configuration.",
                )
            except RateLimitError as e:
                return self._fail(
                    "rate_limit", e,
                    "Sorry sir, the Anthropic rate limit has been reached. "
                    "Please try again in a moment.",
                )
            except APIConnectionError as e:
                return self._fail(
                    "connection", e,
                    "Sorry sir, I cannot reach the Anthropic service. "
                    "Please check your internet connection.",
                )
            except APIStatusError as e:
                return self._fail(
                    "api_status", e,
                    "Sorry sir, the Anthropic service reported an error. "
                    "Please try again shortly.",
                )
            except Exception as e:  # noqa: BLE001 — final safety net
                self.logger.exception("AnthropicProvider: unexpected failure.")
                return self._fail(
                    "unexpected", e,
                    "Sorry sir, something unexpected went wrong while "
                    "contacting Claude.",
                )

            with telemetry.stage("response_parsing", **fields):
                ai_ms = (time.perf_counter() - request_started) * 1000.0
                self._log_usage(response, ai_ms)

                # Anthropic returns a list of content blocks; we join
                # all text blocks into one reply.
                reply = "".join(
                    block.text
                    for block in response.content
                    if hasattr(block, "text")
                ).strip()

                if not reply:
                    self.logger.error(
                        "AnthropicProvider: empty response | model=%s | "
                        "stop_reason=%s",
                        self.settings.anthropic_model,
                        getattr(response, "stop_reason", None),
                    )
                    return Response(
                        success=False,
                        message="Sorry sir, Claude returned an empty "
                                "response. Please try again.",
                        data={
                            "error_kind": "empty_completion",
                            "stop_reason": str(
                                getattr(response, "stop_reason", None)
                            ),
                        },
                    )

                return Response(success=True, message=reply)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _log_usage(self, response, ai_ms: float) -> None:
        """
        Emit the same single-glance USAGE line as OpenAIProvider:

            USAGE | req=N | model=claude-sonnet-4-6 | ai_ms=420 |
            prompt=38 | completion=212 | reasoning=None | finish=end_turn

        Anthropic's SDK uses input_tokens / output_tokens. reasoning is
        always None for Sonnet (no hidden reasoning budget). Never
        raises — logging must not break the pipeline.
        """

        try:
            usage = getattr(response, "usage", None)
            self.logger.info(
                "USAGE | req=%s | model=%s | ai_ms=%d | prompt=%s | "
                "completion=%s | reasoning=%s | finish=%s",
                telemetry.current_request_id(),
                self.settings.anthropic_model,
                round(ai_ms),
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
                None,           # Sonnet has no hidden reasoning tokens
                getattr(response, "stop_reason", None),
            )
        except Exception:
            self.logger.exception("AnthropicProvider: failed to log usage.")

    def _fail(self, kind: str, error: Exception, message: str) -> Response:
        """Log a categorised failure and return a clean Response."""

        self.logger.error(
            "AnthropicProvider: %s error | model=%s | %s",
            kind, self.settings.anthropic_model, error,
        )
        return Response(
            success=False,
            message=message,
            data={"error": str(error), "error_kind": kind},
        )

    def _system_prompt(self) -> str:
        """Build the system prompt from Settings."""

        return (
            f"You are {self.settings.assistant_name}. "
            f"Your personality is {self.settings.personality}. "
            f"Always reply in {self.settings.language}. "
            "Be concise, helpful and professional."
        )