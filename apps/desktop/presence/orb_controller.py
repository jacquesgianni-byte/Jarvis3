"""Desktop Orb Controller."""

from apps.desktop.presence.desktop_state import DesktopState
from apps.desktop.presence.orb_renderer import OrbRenderer
from apps.desktop.presence.presence_events import PRESENCE_STATE_CHANGED


class OrbController:
    """Coordinates orb behaviour from Presence state."""

    def __init__(self, presence_controller, event_bus):
        self._presence_controller = presence_controller
        self._event_bus = event_bus
        self._state = presence_controller.state

        self._renderer = OrbRenderer()
        self._renderer.set_state(self._state)

        self._event_bus.subscribe(
            PRESENCE_STATE_CHANGED,
            self._on_presence_changed,
        )

    @property
    def state(self) -> DesktopState:
        """Return the current orb state."""
        return self._state

    @property
    def renderer(self) -> OrbRenderer:
        """Return the orb renderer."""
        return self._renderer

    def _on_presence_changed(self, old_state, new_state):
        """Handle presence state changes."""
        self._state = new_state
        self._renderer.set_state(new_state)

        if new_state == DesktopState.IDLE:
            self.on_idle()
        elif new_state == DesktopState.LISTENING:
            self.on_listening()
        elif new_state == DesktopState.THINKING:
            self.on_thinking()
        elif new_state == DesktopState.SPEAKING:
            self.on_speaking()
        elif new_state == DesktopState.EXECUTING:
            self.on_executing()
        elif new_state == DesktopState.SUCCESS:
            self.on_success()
        elif new_state == DesktopState.ERROR:
            self.on_error()
        elif new_state == DesktopState.SLEEPING:
            self.on_sleeping()

    def on_idle(self):
        """Handle idle state."""
        pass

    def on_listening(self):
        """Handle listening state."""
        pass

    def on_thinking(self):
        """Handle thinking state."""
        pass

    def on_speaking(self):
        """Handle speaking state."""
        pass

    def on_executing(self):
        """Handle executing state."""
        pass

    def on_success(self):
        """Handle success state."""
        pass

    def on_error(self):
        """Handle error state."""
        pass

    def on_sleeping(self):
        """Handle sleeping state."""
        pass