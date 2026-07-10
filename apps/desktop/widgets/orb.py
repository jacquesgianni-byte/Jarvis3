"""
Jarvis Orb Widget

The animated visual centerpiece of Jarvis OS Desktop.
Communicates Jarvis current state through colour, glow and animation.

States:
    idle        — soft blue pulse
    listening   — expanding rings, rotation
    thinking    — faster segments, dynamic light
    speaking    — pulse synchronized with speech
    error       — orange/red glow
    offline     — dimmed, slow heartbeat
"""

import math

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QPen, QBrush

from apps.desktop.theme import Theme


class JarvisOrb(QWidget):
    """
    Animated Jarvis Orb.

    Custom-painted widget that displays Jarvis current state
    through animated rings, glow and colour transitions.
    """

    STATES = {
        "idle":      {"colour": Theme.ORB_IDLE,      "speed": 2000, "rings": 2},
        "listening": {"colour": Theme.ORB_LISTENING, "speed": 800,  "rings": 4},
        "thinking":  {"colour": Theme.ORB_THINKING,  "speed": 400,  "rings": 3},
        "speaking":  {"colour": Theme.ORB_SPEAKING,  "speed": 600,  "rings": 3},
        "error":     {"colour": Theme.ORB_ERROR,     "speed": 1200, "rings": 2},
        "offline":   {"colour": Theme.ORB_OFFLINE,   "speed": 3000, "rings": 1},
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self._state = "idle"
        self._phase = 0.0
        self._rotation = 0.0

        size = Theme.ORB_SIZE + 40
        self.setFixedSize(size, size)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)  # ~33 fps

    def set_state(self, state: str):
        """
        Change the orb state.

        Args:
            state: One of idle, listening, thinking, speaking, error, offline.
        """
        if state in self.STATES:
            self._state = state
            self._phase = 0.0

    def _tick(self):
        config = self.STATES[self._state]
        increment = 30 / config["speed"]
        self._phase = (self._phase + increment) % 1.0
        self._rotation = (self._rotation + 0.5) % 360.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        config = self.STATES[self._state]
        colour = QColor(config["colour"])
        cx = self.width() / 2
        cy = self.height() / 2
        radius = Theme.ORB_SIZE / 2

        pulse = 0.5 + 0.5 * math.sin(self._phase * 2 * math.pi)

        # Outer glow rings
        num_rings = config["rings"]
        for i in range(num_rings):
            ring_phase = (self._phase + i / num_rings) % 1.0
            ring_radius = radius + 10 + ring_phase * 35
            ring_alpha = int(120 * (1.0 - ring_phase))

            ring_colour = QColor(colour)
            ring_colour.setAlpha(ring_alpha)

            pen = QPen(ring_colour)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(
                QPointF(cx, cy),
                ring_radius,
                ring_radius
            )

        # Core glow
        glow_radius = radius + 8 + pulse * 6
        glow = QRadialGradient(QPointF(cx, cy), glow_radius)
        glow_colour = QColor(colour)
        glow_colour.setAlpha(int(60 + pulse * 40))
        glow.setColorAt(0.0, glow_colour)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            QPointF(cx, cy),
            glow_radius,
            glow_radius
        )

        # Core orb
        orb_gradient = QRadialGradient(
            QPointF(cx - radius * 0.2, cy - radius * 0.2),
            radius
        )
        core_colour = QColor(colour)
        core_colour.setAlpha(int(200 + pulse * 55))

        highlight = QColor(255, 255, 255, int(60 + pulse * 40))
        base = QColor(colour)
        base.setAlpha(180)

        orb_gradient.setColorAt(0.0, highlight)
        orb_gradient.setColorAt(0.4, core_colour)
        orb_gradient.setColorAt(1.0, base)

        painter.setBrush(QBrush(orb_gradient))

        border_colour = QColor(colour)
        border_colour.setAlpha(int(150 + pulse * 100))
        pen = QPen(border_colour)
        pen.setWidth(1)
        painter.setPen(pen)

        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        painter.end()