"""
Jarvis Core

The central container for all Jarvis subsystems.

Conversation ownership (Genesis-011 Task 002):
    JarvisCore owns the InterruptManager. Every request receives a
    RequestToken. The Agent processes the request with the token as
    opaque context; JarvisCore alone decides whether the finished
    response is still current and may be delivered. Stale responses
    are silently discarded (process() returns None).
"""

from core.agent import Agent

from core import telemetry

from core.conversation import InterruptManager

from core.voice.manager import VoiceManager
from core.voice.providers.system_tts import SystemTTSProvider

from core.ai.manager import AIManager
from core.ai.providers.openai_provider import OpenAIProvider


class JarvisCore:
    """
    Owns and manages the Jarvis Core.
    """

    def __init__(self) -> None:

        # Conversation ownership
        self.interrupts = InterruptManager()

        # AI
        self.ai = AIManager()
        self.ai.set_provider(OpenAIProvider())

        # Agent
        self.agent = Agent(ai=self.ai)

        # Voice
        self.voice = VoiceManager()
        self.voice.set_provider(SystemTTSProvider())

    def process(self, request: str):
        """
        Process a user request.

        Returns the Response if it is still current, or None if a newer
        request arrived while this one was being processed. Callers must
        treat None as "silently discard — do nothing".
        """

        token = self.interrupts.new_request()
        telemetry.bind(token)

        with telemetry.stage("agent_total"):
            response = self.agent.process(request, token=token)

        # Delivery gate: atomically checks the token is still current
        # and marks it COMPLETED. If a newer request took ownership
        # while the Agent was working, discard this response.
        if not self.interrupts.complete(token):
            return None

        # NOTE: if VoiceManager queues speech asynchronously, this
        # measures dispatch time, not actual speaking time. True
        # synthesis timing belongs inside the voice layer.
        with telemetry.stage("voice_synthesis"):
            self.voice.speak(response.message)

        return response

    def stop(self) -> None:
        """
        Stop the active request AND any active speech (Stop button).

        Two independent effects, both safe no-ops when not applicable:
          * interrupt_all() — a still-processing request's response will
            be silently discarded when it finishes.
          * voice.stop()    — speech already underway halts at the next
            word boundary.

        This is the expansion of stop() anticipated in Task 002 Part 2 —
        the Desktop's call site is unchanged.
        """

        self.interrupts.interrupt_all()
        self.voice.stop()

    @property
    def is_speaking(self) -> bool:
        """
        True while Jarvis is speaking (or about to speak).

        Facade over VoiceManager so interfaces observe voice state
        through JarvisCore rather than reaching into subsystems.
        """

        return self.voice.is_speaking

    def shutdown(self) -> None:
        """
        Shut down all Jarvis services cleanly.
        """

        self.voice.shutdown()