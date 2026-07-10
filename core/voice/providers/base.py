"""
Base Voice Provider

Every voice provider must inherit from this class.
"""

from abc import ABC, abstractmethod


class VoiceProvider(ABC):
    """
    Base class for all voice providers.
    """

    @abstractmethod
    def speak(self, text: str):
        """
        Speak text.
        """
        pass

    def stop(self) -> None:
        """
        Request that any in-progress speech stop as soon as possible.

        Optional — providers that cannot interrupt speech may ignore
        this. The default implementation does nothing, so existing and
        future providers remain valid without changes.

        Must be safe to call from any thread.
        """
        pass