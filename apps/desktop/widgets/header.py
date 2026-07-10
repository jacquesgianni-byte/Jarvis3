"""
Jarvis OS Header Widget

The top bar of the Jarvis OS Desktop interface.
Displays the logo, active AI provider, connection status,
current profile and system status indicator.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from apps.desktop.theme import Theme


class HeaderWidget(QWidget):
    """
    Top header bar for Jarvis OS Desktop.

    Displays identity and system status in a clean, minimal strip.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(Theme.HEADER_HEIGHT)
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Theme.MARGIN, 0, Theme.MARGIN, 0)
        layout.setSpacing(Theme.SPACING_MD)

        # Logo
        logo = QLabel("◈  JARVIS OS")
        logo.setStyleSheet(f"""
            color: {Theme.ACCENT};
            font-family: "{Theme.FONT_FAMILY}";
            font-size: {Theme.FONT_LARGE}px;
            font-weight: 700;
            letter-spacing: 2px;
        """)

        # Spacer
        layout.addWidget(logo)
        layout.addStretch()

        # Provider badge
        self._provider = QLabel("◉  Claude")
        self._provider.setStyleSheet(f"""
            color: {Theme.TEXT_SECONDARY};
            font-size: {Theme.FONT_SMALL}px;
            background: {Theme.SURFACE};
            border: 1px solid {Theme.BORDER};
            border-radius: {Theme.RADIUS_SM}px;
            padding: 3px 10px;
        """)

        # Connection status
        self._status = QLabel("● Connected")
        self._status.setStyleSheet(f"""
            color: {Theme.SUCCESS};
            font-size: {Theme.FONT_SMALL}px;
        """)

        # Profile
        self._profile = QLabel("Ludovic")
        self._profile.setStyleSheet(f"""
            color: {Theme.TEXT_SECONDARY};
            font-size: {Theme.FONT_SMALL}px;
            background: {Theme.SURFACE};
            border: 1px solid {Theme.BORDER};
            border-radius: {Theme.RADIUS_SM}px;
            padding: 3px 10px;
        """)

        layout.addWidget(self._provider)
        layout.addWidget(self._status)
        layout.addWidget(self._profile)

    def _apply_style(self):
        self.setStyleSheet(f"""
            HeaderWidget {{
                background-color: {Theme.SURFACE};
                border-bottom: 1px solid {Theme.BORDER};
            }}
        """)

    def set_provider(self, name: str):
        """Update the displayed AI provider name."""
        self._provider.setText(f"◉  {name}")

    def set_connected(self, connected: bool):
        """Update the connection status indicator."""
        if connected:
            self._status.setText("● Connected")
            self._status.setStyleSheet(f"color: {Theme.SUCCESS}; font-size: {Theme.FONT_SMALL}px;")
        else:
            self._status.setText("● Offline")
            self._status.setStyleSheet(f"color: {Theme.ERROR}; font-size: {Theme.FONT_SMALL}px;")

    def set_profile(self, name: str):
        """Update the displayed profile name."""
        self._profile.setText(name)