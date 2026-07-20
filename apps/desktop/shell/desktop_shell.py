"""
Jarvis Desktop Shell (Genesis-023 MP-004 Sprint-006)

Hosts and navigates all desktop pages via a QStackedWidget.

Sprint-006 migration note:
    ChatPage is the initial page. HomePage is deferred until
    OrbRenderer/OrbWidget dependencies are production-ready (Sprint-007+).

Future pages:
    home    → HomePage  (Sprint-007, pending Orb dependencies)
    debug   → DebugPage
    settings → SettingsPage
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

from apps.desktop.pages.chat_page import ChatPage
from apps.desktop.shell.page_manager import PageManager


class DesktopShell(QWidget):
    """Hosts and navigates all desktop pages."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._stack = QStackedWidget()
        self._manager = PageManager(self._stack)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._stack)

        self._create_pages()

    def _create_pages(self) -> None:
        """
        Create and register all desktop pages.

        Sprint-006: ChatPage only.
        HomePage deferred — OrbRenderer/OrbWidget not yet production-ready.
        """
        self.chat_page = ChatPage()
        self._manager.register("chat", self.chat_page)
        self._manager.show("chat")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_page(self, name: str) -> None:
        """Display a registered page by name."""
        self._manager.show(name)

    def show_chat(self) -> None:
        """Display the chat page."""
        self.show_page("chat")

    def show_home(self) -> None:
        """
        Display the home page.

        Sprint-006: home page not yet registered — falls back to chat.
        Will route to HomePage once Orb dependencies land (Sprint-007).
        """
        if self._manager.has_page("home"):
            self.show_page("home")
        else:
            self.show_chat()

    @property
    def current_page(self) -> str | None:
        """Return the current page name."""
        return self._manager.current()