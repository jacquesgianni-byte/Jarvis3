"""
Jarvis AI Manager

Coordinates all AI providers.

Genesis-011 Maintenance Patch 002:
    ask() now guarantees a Response in all circumstances. A missing
    provider or an unexpected provider crash returns a clean failure
    Response instead of raising — no exception ever escapes the AI
    layer into the Agent or the desktop UI.
"""

from core.logger import get_logger
from core.models.response import Response


class AIManager:
    """
    Central manager for Jarvis AI providers.
    """

    def __init__(self):

        self.provider = None
        self.logger = get_logger()

    def set_provider(self, provider):
        """
        Set the active AI provider.
        """

        self.provider = provider

    def ask(self, prompt: str) -> Response:
        """
        Send a prompt to the active provider.

        Always returns a Response — success or graceful failure.
        """

        if self.provider is None:
            self.logger.error("AIManager.ask() called with no provider configured.")
            return Response(
                success=False,
                message="Sorry sir, no AI provider is configured.",
            )

        try:
            return self.provider.ask(prompt)

        except Exception as e:  # noqa: BLE001 — providers should never raise,
            # but if one does, the worker must still finish cleanly.
            self.logger.exception("AIManager: provider raised unexpectedly.")
            return Response(
                success=False,
                message="Sorry sir, something unexpected went wrong while "
                        "contacting the AI service.",
                data={"error": str(e), "error_kind": "provider_crash"},
            )