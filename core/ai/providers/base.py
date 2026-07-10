"""
Base AI Provider

Every AI provider must inherit from this class.
"""

from abc import ABC, abstractmethod

from core.models.response import Response


class AIProvider(ABC):
    """
    Base class for all AI providers.
    """

    @abstractmethod
    def ask(self, prompt: str) -> Response:
        """
        Process a prompt and return a Response.
        """
        pass