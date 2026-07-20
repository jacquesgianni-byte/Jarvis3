"""Jarvis Desktop Page Manager."""

from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import QStackedWidget, QWidget


class PageManager:
    """Manages desktop pages and navigation."""

    def __init__(self, stack: QStackedWidget):
        self._stack = stack
        self._pages: Dict[str, QWidget] = {}

    def register(self, name: str, page: QWidget) -> None:
        """Register a page with the desktop shell."""
        if name in self._pages:
            raise ValueError(f"Page '{name}' is already registered.")

        self._pages[name] = page
        self._stack.addWidget(page)

    def show(self, name: str) -> None:
        """Display a registered page."""
        try:
            page = self._pages[name]
        except KeyError as exc:
            raise KeyError(f"Unknown page '{name}'.") from exc

        self._stack.setCurrentWidget(page)

    def current(self) -> str | None:
        """Return the current page name."""
        current = self._stack.currentWidget()

        for name, page in self._pages.items():
            if page is current:
                return name

        return None

    def has_page(self, name: str) -> bool:
        """Return True if a page exists."""
        return name in self._pages

    @property
    def pages(self) -> Dict[str, QWidget]:
        """Registered pages."""
        return dict(self._pages)