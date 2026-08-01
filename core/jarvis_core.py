"""
Jarvis Core (Genesis-030 Sprint-003 safe fix)

process_stream() uses agent.process() for all conversation handling.
Tokens are emitted after the response arrives.
True token-by-token streaming will be implemented in Sprint-004
once the Agent streaming hook is properly designed.
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
        Process a user request, emitting the response via callbacks.

        Currently uses agent.process() for all conversation handling
        and emits the complete response as a single token.
        True incremental streaming at the Agent level is Sprint-004.
        """
        token = self.interrupts.new_request()
        telemetry.bind(token)
        self._cancel_event.clear()

        with telemetry.stage("agent_total"):
            response = self.agent.process(request, token=token)

        if not self.interrupts.complete(token):
            return None

        if response and response.success:
            if not self._cancel_event.is_set():
                callbacks.emit_token(response.message)
                callbacks.emit_complete(response.message)
        elif response:
            callbacks.emit_error(Exception(response.message))

        if response:
            with telemetry.stage("voice_synthesis"):
                self.voice.speak(response.message)

        return response

    def stop(self) -> None:
        self._cancel_event.set()
        self.interrupts.interrupt_all()
        self.voice.stop()

    @property
    def is_speaking(self) -> bool:
        return self.voice.is_speaking

    def shutdown(self) -> None:
        self.voice.shutdown()
