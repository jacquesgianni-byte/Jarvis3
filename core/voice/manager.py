"""
Jarvis Voice Manager

Coordinates voice services for Jarvis OS.
Creates the VoiceWorker and wires it to the active provider.
The Desktop interacts only with VoiceManager — never with the worker or provider directly.
"""

import logging

from core.voice.providers.base import VoiceProvider
from core.voice.worker import VoiceWorker

logger = logging.getLogger(__name__)


class VoiceManager:
    """
    Central manager for Jarvis voice services.

    Owns the VoiceWorker and manages its lifecycle.
    Accepts any VoiceProvider implementation.
    """

    def __init__(self) -> None:
        """
        Initialise the VoiceManager with no active provider.
        """

        self._worker: VoiceWorker | None = None

    def set_provider(self, provider: VoiceProvider) -> None:
        """
        Set the active voice provider and start the worker.

        If a worker is already running it is shut down cleanly
        before the new provider is applied.
        """

        if self._worker is not None and self._worker.is_running():
            self._worker.stop()

        self._worker = VoiceWorker(provider)
        self._worker.start()

        logger.info(
            "VoiceManager started with provider: %s",
            type(provider).__name__,
        )

    def speak(self, text: str) -> None:
        """
        Queue a speech request.
        """

        if self._worker is None:
            logger.warning(
                "VoiceManager.speak() called before a provider was set."
            )
            return

        self._worker.speak(text)

    def stop(self) -> None:
        """
        Interrupt any active or queued speech immediately.

        The worker stays alive and ready for future speech. Safe to
        call at any time, from any thread, including when nothing is
        speaking.
        """

        if self._worker is not None and self._worker.is_running():
            self._worker.stop_speaking()

    @property
    def is_speaking(self) -> bool:
        """
        True while speech is queued or actively being spoken.

        This is the source of truth for the voice lifecycle — the UI
        observes this rather than inferring speech state itself.
        """

        if self._worker is None:
            return False

        return self._worker.is_speaking()

    def shutdown(self) -> None:
        """
        Shut down the voice worker cleanly.
        """

        if self._worker is not None and self._worker.is_running():
            self._worker.stop()
            logger.info("VoiceManager shut down.")

        self._worker = None