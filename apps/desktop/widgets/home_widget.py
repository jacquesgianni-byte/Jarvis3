"""Jarvis Home Widget."""

from PySide6.QtWidgets import QWidget, QVBoxLayout

from apps.desktop.presence.orb_renderer import OrbRenderer
from apps.desktop.widgets.orb_widget import OrbWidget


class HomeWidget(QWidget):
    """Primary Jarvis desktop experience."""

    def __init__(self, parent=None):
        super().__init__(parent)

        renderer = OrbRenderer()
        self.orb = OrbWidget(renderer)

        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self.orb, alignment=0x84)  # Qt.AlignCenter
        layout.addStretch()