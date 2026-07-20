"""
Jarvis Desktop Controller (Genesis-023 MP-004 Sprint-006)

Coordinates the Desktop Shell and JarvisCore.
Owns desktop behaviour. Does NOT own window layout.

Sprint-006: startup() routes to chat page.
Sprint-007+: startup() will route to home page once Orb lands.
"""

from __future__ import annotations


class DesktopController:
    """
    Coordinates the Desktop Shell and JarvisCore.

    This class owns desktop behaviour.
    It intentionally does NOT own window layout.
    """

    def __init__(self, jarvis, shell):
        self._jarvis = jarvis
        self._shell = shell

    @property
    def jarvis(self):
        return self._jarvis

    @property
    def shell(self):
        return self._shell

    def startup(self) -> None:
        """
        Initialise the desktop.

        Sprint-006: shows chat page (home deferred until Sprint-007).
        """
        self._shell.show_chat()

    def shutdown(self) -> None:
        """Shutdown hook."""
        pass