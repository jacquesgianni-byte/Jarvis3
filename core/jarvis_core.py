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
from core.voice.providers.elevenlabs_tts import ElevenLabsTTSProvider
from core.ai.manager import AIManager
from core.ai.providers.openai_provider import OpenAIProvider
from core.ai.providers.anthropic_provider import AnthropicProvider
from core.ai.streaming import StreamCallbacks
from core.settings.settings import Settings
from core.conversation.json_timeline_repository import JsonTimelineRepository  # Genesis-047


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

        # Genesis-047 Sprint-001: Timeline persistence wiring
        try:
            from datetime import UTC, datetime, timedelta
            from core.config import TIMELINE_RETENTION_DAYS
            _tl_repo = JsonTimelineRepository()
            if TIMELINE_RETENTION_DAYS > 0:
                _cutoff = (
                    datetime.now(UTC) - timedelta(days=TIMELINE_RETENTION_DAYS)
                ).strftime("%Y-%m-%d")
                _tl_repo.purge_before(_cutoff)
            self.agent = Agent(ai=self.ai, timeline_repository=_tl_repo)
        except Exception as _exc:
            import logging as _logging
            _logging.getLogger(__name__).error(
                "[JARVIS CORE] Timeline repository init failed: %s "
                "— starting without persistence.", _exc
            )
            self.agent = Agent(ai=self.ai)

        self.voice = VoiceManager()
        _elevenlabs = ElevenLabsTTSProvider.from_env(
            voice_id = "ydOzToQj00qmJ4VuQWPU",
            speed    = 1.08,
        )
        import logging as _log
        if _elevenlabs is not None:
            self.voice.set_provider(_elevenlabs)
            _log.getLogger(__name__).info("Voice: ElevenLabs provider active.")
        else:
            self.voice.set_provider(SystemTTSProvider())
            _log.getLogger(__name__).info("Voice: SystemTTS fallback active (ELEVENLABS_API_KEY not set).")

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
