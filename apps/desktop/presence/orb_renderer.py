"""Desktop Orb Renderer."""

from apps.desktop.presence.desktop_state import DesktopState


class OrbRenderer:
    """Renders the desktop orb."""

    def __init__(self):
        self._state = DesktopState.IDLE

        self._radius = 40
        self._glow = 0.4
        self._pulse_speed = 1.0
        self._colour = "#4FC3F7"

    @property
    def state(self) -> DesktopState:
        """Return the current orb state."""
        return self._state

    def set_state(self, state: DesktopState):
        """Update the orb state."""
        self._state = state

        if state == DesktopState.IDLE:
            self._radius = 40
            self._glow = 0.4
            self._pulse_speed = 1.0
            self._colour = "#4FC3F7"

        elif state == DesktopState.LISTENING:
            self._radius = 44
            self._glow = 0.8
            self._pulse_speed = 1.6
            self._colour = "#29B6F6"

        elif state == DesktopState.THINKING:
            self._radius = 42
            self._glow = 0.9
            self._pulse_speed = 2.0
            self._colour = "#7E57C2"

        elif state == DesktopState.SPEAKING:
            self._radius = 45
            self._glow = 1.0
            self._pulse_speed = 2.5
            self._colour = "#26C6DA"

        elif state == DesktopState.EXECUTING:
            self._radius = 43
            self._glow = 0.9
            self._pulse_speed = 2.2
            self._colour = "#66BB6A"

        elif state == DesktopState.SUCCESS:
            self._radius = 44
            self._glow = 1.0
            self._pulse_speed = 1.8
            self._colour = "#43A047"

        elif state == DesktopState.ERROR:
            self._radius = 42
            self._glow = 1.0
            self._pulse_speed = 3.0
            self._colour = "#EF5350"

        elif state == DesktopState.SLEEPING:
            self._radius = 36
            self._glow = 0.2
            self._pulse_speed = 0.4
            self._colour = "#78909C"