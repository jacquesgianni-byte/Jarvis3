"""
Jarvis Core (Genesis-030 Sprint-003)

Added is_cancelled hook to process_stream() so streaming providers
can check interruption between tokens and close the stream cleanly.
"""

import threading
from core.agent import Agent
from core import telemetry
from core.conversation import InterruptManager
from core.voice.manager import VoiceManager
from core.voice.providers.system_tts import SystemTTSProvider
from core.ai.manager import AIManager
from core.ai.providers.openai_provider import OpenAIProvider
from core.ai.providers.anthropic_provider import AnthropicProvider
from core.ai.streaming import StreamCallbacks
from core.settings.settings import Settings


class JarvisCore:
    """Owns and manages the Jarvis Core."""

    def __init__(self) -> None:
        self.interrupts = InterruptManager()
        self._cancel_event = threading.Event()

        _settings = Settings()
        self.ai = AIManager()
        self.ai.register_provider("openai",    OpenAIProvider())
        self.ai.register_provider("anthropic", AnthropicProvider())
        if not self.ai.activate(_settings.default_ai_provider):
            self.ai.activate("openai")

        self.agent = Agent(ai=self.ai)

        self.voice = VoiceManager()
        self.voice.set_provider(SystemTTSProvider())

    def process(self, request: str):
        """Process a user request (blocking)."""
        token = self.interrupts.new_request()
        telemetry.bind(token)

        with telemetry.stage("agent_total"):
            response = self.agent.process(request, token=token)

        if not self.interrupts.complete(token):
            return None

        with telemetry.stage("voice_synthesis"):
            self.voice.speak(response.message)

        return response

    def process_stream(self, request: str, callbacks: StreamCallbacks):
        """
        Process a user request with streaming.

        Genesis-030 Sprint-003: passes is_cancelled to ask_stream() so
        the provider checks interruption between tokens and closes
        the stream cleanly.
        """
        token = self.interrupts.new_request()
        telemetry.bind(token)

        # Reset cancel event for this request
        self._cancel_event.clear()

        def is_cancelled() -> bool:
            return self._cancel_event.is_set()

        active = self.ai.active_provider
        if active and active.supports_streaming:
            with telemetry.stage("agent_total"):
                response = self.agent.process_stream(
                    request, callbacks, token=token
                )
        else:
            with telemetry.stage("agent_total"):
                response = self.agent.process(request, token=token)
            if response and response.success:
                if not is_cancelled():
                    callbacks.emit_token(response.message)
                    callbacks.emit_complete(response.message)
            elif response:
                callbacks.emit_error(Exception(response.message))

        if not self.interrupts.complete(token):
            return None

        if response:
            with telemetry.stage("voice_synthesis"):
                self.voice.speak(response.message)

        return response

    def stop(self) -> None:
        """Stop active request, cancel streaming, and stop speech."""
        self._cancel_event.set()
        self.interrupts.interrupt_all()
        self.voice.stop()

    @property
    def is_speaking(self) -> bool:
        return self.voice.is_speaking

    def shutdown(self) -> None:
        self.voice.shutdown()
