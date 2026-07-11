"""
Jarvis AI Manager

Coordinates all AI providers.

Genesis-011 Maintenance Patch 002:
    ask() now guarantees a Response in all circumstances. A missing
    provider or an unexpected provider crash returns a clean failure
    Response instead of raising — no exception ever escapes the AI
    layer into the Agent or the desktop UI.

Genesis-015 Task 001:
    Provider registry pattern: register_provider() accepts any
    AIProvider implementation by name. The active provider is selected
    by activate() and defaults to whatever default_ai_provider names
    in Settings at construction time. Existing callers that call
    set_provider(instance) directly continue to work unchanged.
"""

from core.logger import get_logger
from core.models.response import Response


class AIManager:
    """
    Central manager for Jarvis AI providers.
    """

    def __init__(self):
        self.provider = None
        self._registry: dict = {}
        self.logger = get_logger()

    # ------------------------------------------------------------------
    # Registry API (Genesis-015)
    # ------------------------------------------------------------------

    def register_provider(self, name: str, provider) -> None:
        """Register a named AIProvider implementation."""
        self._registry[name] = provider
        self.logger.info("AIManager: registered provider %r.", name)

    def activate(self, name: str) -> bool:
        """
        Set the active provider by registry name.

        Returns True if found, False (+ warning) otherwise.
        """
        if name not in self._registry:
            self.logger.warning(
                "AIManager: provider %r not registered — keeping current.",
                name,
            )
            return False
        self.provider = self._registry[name]
        self.logger.info("AIManager: active provider -> %r.", name)
        return True

    def active_provider_name(self) -> str:
        """
        Return the display name of the active provider.

        Used by the status bar indicator (Genesis-015 UI feature) and
        the F12 Engineering Console. Returns 'none' when no provider is
        active.
        """
        if self.provider is None:
            return "none"
        for name, p in self._registry.items():
            if p is self.provider:
                return name
        # Provider was set directly via set_provider() (backward compat)
        return type(self.provider).__name__.replace("Provider", "").lower()

    # ------------------------------------------------------------------
    # Legacy API (unchanged)
    # ------------------------------------------------------------------

    def set_provider(self, provider) -> None:
        """
        Set the active AI provider directly.

        Preserved for backward compatibility. New code should prefer
        register_provider() + activate().
        """
        self.provider = provider

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

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

        except Exception as e:  # noqa: BLE001
            self.logger.exception("AIManager: provider raised unexpectedly.")
            return Response(
                success=False,
                message="Sorry sir, something unexpected went wrong while "
                        "contacting the AI service.",
                data={"error": str(e), "error_kind": "provider_crash"},
            )