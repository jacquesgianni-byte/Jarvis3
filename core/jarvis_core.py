"""
Jarvis Core (Genesis-030 Sprint-002)

The central container for all Jarvis subsystems.

Conversation ownership (Genesis-011 Task 002):
    JarvisCore owns the InterruptManager. Every request receives a
    RequestToken. The Agent processes the request with the token as
    opaque context; JarvisCore alone decides whether the finished
    response is still current and may be delivered. Stale responses
    are silently discarded (process() returns None).

Genesis-030 Sprint-002:
    Added process_stream() alongside the existing process().
    Streaming is used when the active AI provider supports it.
    Falls back to process() automatically when not supported.
"""

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
    """
    Owns and manages the Jarvis Core.
    """

    def __init__(self) -> None:
        # Conversation ownership
        self.interrupts = InterruptManager()

        # AI -- both providers registered; Settings selects the active brain.
        _settings = Settings()
        self.ai = AIManager()
        self.ai.register_provider("openai",    OpenAIProvider())
        self.ai.register_provider("anthropic", AnthropicProvider())
        if not self.ai.activate(_settings.default_ai_provider):
            self.ai.activate("openai")

        # Agent
        self.agent = Agent(ai=self.ai)

        # Voice
        self.voice = VoiceManager()
        self.voice.set_provider(SystemTTSProvider())

    def process(self, request: str):
        """
        Process a user request (blocking).

        Returns the Response if still current, or None if a newer
        request arrived while this one was being processed.
        """
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
        Process a user request with streaming (Genesis-030 Sprint-002).

        If the active AI provider supports streaming, tokens are emitted
        via callbacks.on_token() as they arrive from the provider.

        If the provider does not support streaming, falls back to the
        blocking process() path automatically -- callbacks.on_token()
        receives the complete message as a single chunk.

        Returns the Response if still current, or None if interrupted.

        Args:
            request:   The user's message.
            callbacks: StreamCallbacks for on_token / on_complete / on_error.
        """
        token = self.interrupts.new_request()
        telemetry.bind(token)

        # Check if the active provider supports streaming
        active = self.ai.active_provider
        if active and active.supports_streaming:
            # Route through Agent for conversation handling,
            # then call ask_stream for the AI fallback layer.
            # Agent handles memory, skills, and routing first.
            with telemetry.stage("agent_total"):
                response = self.agent.process_stream(request, callbacks, token=token)
        else:
            # Non-streaming fallback -- wrap blocking response as single token
            with telemetry.stage("agent_total"):
                response = self.agent.process(request, token=token)
            if response and response.success:
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
        """
        Stop the active request AND any active speech.
        """
        self.interrupts.interrupt_all()
        self.voice.stop()

    @property
    def is_speaking(self) -> bool:
        return self.voice.is_speaking

    def shutdown(self) -> None:
        self.voice.shutdown()
