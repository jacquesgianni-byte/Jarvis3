"""Desktop Orb Widget."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from apps.desktop.presence.orb_renderer import OrbRenderer


class OrbWidget(QWidget):
    """Widget responsible for displaying the Jarvis orb."""

    def __init__(self, renderer: OrbRenderer, parent=None):
        super().__init__(parent)

        self._renderer = renderer

        self.setMinimumSize(200, 200)

    def paintEvent(self, event):
        """Paint the orb."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(QColor("#4FC3F7"))
        painter.setPen(Qt.NoPen)

        radius = 40

        x = (self.width() - radius * 2) / 2
        y = (self.height() - radius * 2) / 2

        painter.drawEllipse(int(x), int(y), radius * 2, radius * 2)