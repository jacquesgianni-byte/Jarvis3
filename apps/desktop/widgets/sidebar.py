"""
Jarvis OS Sidebar Widget

The left panel containing the Jarvis Orb, status display
and navigation menu.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt

from apps.desktop.theme import Theme
from apps.desktop.widgets.orb import JarvisOrb


class NavItem(QPushButton):
    """A single navigation item in the sidebar."""

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(f"  {icon}  {label}", parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.TEXT_SECONDARY};
                font-family: "{Theme.FONT_FAMILY}";
                font-size: {Theme.FONT_NORMAL}px;
                text-align: left;
                border: none;
                border-radius: {Theme.RADIUS_SM}px;
                padding: 0 {Theme.SPACING_MD}px;
            }}
            QPushButton:hover {{
                background: {Theme.SURFACE_HOVER};
                color: {Theme.TEXT};
            }}
        """)


class SidebarWidget(QWidget):
    """
    Left sidebar for Jarvis OS Desktop.

    Contains the Jarvis Orb, current status label and navigation menu.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(Theme.SIDEBAR_WIDTH)
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            Theme.SPACING_MD,
            Theme.SPACING_LG,
            Theme.SPACING_MD,
            Theme.SPACING_LG
        )
        layout.setSpacing(Theme.SPACING_SM)

        # Orb
        orb_container = QWidget()
        orb_layout = QVBoxLayout(orb_container)
        orb_layout.setContentsMargins(0, 0, 0, 0)
        orb_layout.setAlignment(Qt.AlignCenter)

        self.orb = JarvisOrb()
        orb_layout.addWidget(self.orb, alignment=Qt.AlignCenter)

        layout.addWidget(orb_container)

        # Status label
        self._status_label = QLabel("Idle")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet(f"""
            color: {Theme.ACCENT};
            font-family: "{Theme.FONT_FAMILY}";
            font-size: {Theme.FONT_SMALL}px;
            letter-spacing: 2px;
            text-transform: uppercase;
            padding-bottom: {Theme.SPACING_MD}px;
        """)
        layout.addWidget(self._status_label)

        # Divider
        layout.addWidget(self._divider())

        # Navigation
        layout.addSpacing(Theme.SPACING_SM)
        layout.addWidget(NavItem("◈", "Memory"))
        layout.addWidget(NavItem("◇", "Skills"))
        layout.addWidget(NavItem("○", "Devices"))
        layout.addWidget(NavItem("◎", "Automations"))

        layout.addStretch()

        layout.addWidget(self._divider())
        layout.addSpacing(Theme.SPACING_SM)
        layout.addWidget(NavItem("⚙", "Settings"))

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {Theme.BORDER};")
        return line

    def _apply_style(self):
        self.setStyleSheet(f"""
            SidebarWidget {{
                background-color: {Theme.SURFACE};
                border-right: 1px solid {Theme.BORDER};
            }}
        """)

    def set_orb_state(self, state: str):
        """Update the orb animation state."""
        self.orb.set_state(state)

        labels = {
            "idle":      "Idle",
            "listening": "Listening",
            "thinking":  "Thinking",
            "speaking":  "Speaking",
            "error":     "Error",
            "offline":   "Offline",
        }
        self._status_label.setText(labels.get(state, state.capitalize()))