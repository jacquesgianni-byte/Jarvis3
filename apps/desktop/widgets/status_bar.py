"""
Jarvis OS Status Bar Widget

Displays the current system status at the bottom of the window.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from apps.desktop.theme import Theme


class StatusBar(QWidget):
    """
    Bottom status bar for Jarvis OS Desktop.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Theme.MARGIN, 0, Theme.MARGIN, 0)

        self._status = QLabel("Ready")
        self._status.setStyleSheet(f"""
            color: {Theme.TEXT_MUTED};
            font-size: {Theme.FONT_XS}px;
            background: transparent;
        """)

        self._version = QLabel("Jarvis OS  ·  Genesis-010")
        self._version.setStyleSheet(f"""
            color: {Theme.TEXT_MUTED};
            font-size: {Theme.FONT_XS}px;
            background: transparent;
        """)

        layout.addWidget(self._status)
        layout.addStretch()
        layout.addWidget(self._version)

    def _apply_style(self):
        self.setStyleSheet(f"""
            StatusBar {{
                background: {Theme.SURFACE};
                border-top: 1px solid {Theme.BORDER};
            }}
        """)

    def set_status(self, text: str):
        """Update the status message."""
        self._status.setText(text)