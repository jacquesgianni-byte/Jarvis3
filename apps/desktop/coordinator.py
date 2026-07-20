"""
Jarvis Desktop Coordinator (Genesis-023 MP-001)

Bridge between Jarvis Core and the Desktop Framework.

Responsibilities:
    - Receive injected EventBus
    - Own desktop subsystem controllers
    - Subscribe to core events and route to desktop components

No business logic here. Routing only.
"""

from __future__ import annotations

import logging

from core.events import EventBus
from apps.desktop.presence.presence_controller import PresenceController, DesktopState
from apps.desktop.presence.presence_events import PresenceEvents

logger = logging.getLogger(__name__)


class DesktopCoordinator:
    """
    Bridge between Jarvis Core and the Desktop Framework.

    Owns desktop subsystem controllers.
    Receives EventBus via constructor injection — never creates one.

    Public API:
        presence     → PresenceController
        shutdown()   → None
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus        = event_bus
        self._presence   = PresenceController(event_bus=event_bus)
        self._subscribed = []   # [(event_name, callback)] for teardown

        self._subscribe()
        logger.info("[COORDINATOR] Initialised.")

    @property
    def presence(self) -> PresenceController:
        """The presence controller. Read-only access."""
        return self._presence

    def _subscribe(self) -> None:
        """
        Subscribe to core events.
        Extend here as new core events are defined in MP-002+.

        Example (MP-002):
            self._bus.subscribe("AGENT_THINKING", self._on_thinking)
            self._subscribed.append(("AGENT_THINKING", self._on_thinking))
        """
        pass

    def shutdown(self) -> None:
        """Unsubscribe all handlers and reset presence to IDLE."""
        for event_name, callback in self._subscribed:
            self._bus.unsubscribe(event_name, callback)
        self._subscribed.clear()
        self._presence.reset()
        logger.info("[COORDINATOR] Shut down.")

    def __repr__(self) -> str:
        return f"DesktopCoordinator(presence={self._presence.state.label()})"