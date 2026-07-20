"""
Jarvis Desktop Presence Controller (Genesis-023 MP-001)

Maintains the current DesktopState and publishes state change events
through the injected EventBus.

Design constraints:
    - No Qt dependencies.
    - No rendering or animation logic.
    - EventBus received via dependency injection.
    - Duplicate transitions silently ignored.
    - Single responsibility: own the DesktopState lifecycle.
"""

from __future__ import annotations

import logging
from enum import Enum, auto

from core.events import EventBus
from apps.desktop.presence.presence_events import PresenceEvents

logger = logging.getLogger(__name__)


class DesktopState(Enum):
    """
    The observable state of the Jarvis desktop presence.

    IDLE:       Jarvis is available and waiting.
    LISTENING:  Jarvis is receiving user input.
    THINKING:   Jarvis is processing a request.
    SPEAKING:   Jarvis is delivering a response.
    ERROR:      An error has occurred; recovery is pending.
    """
    IDLE      = auto()
    LISTENING = auto()
    THINKING  = auto()
    SPEAKING  = auto()
    ERROR     = auto()

    def label(self) -> str:
        return self.name.title()


class PresenceController:
    """
    Manages the current DesktopState.

    Receives EventBus via constructor injection.
    Emits PRESENCE_STATE_CHANGED on every valid (non-duplicate) transition.

    Public API:
        state        → DesktopState  (read-only)
        set_state(s) → None
        reset()      → None
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus   = event_bus
        self._state = DesktopState.IDLE
        logger.info("[PRESENCE] Initialised (state=IDLE).")

    @property
    def state(self) -> DesktopState:
        """The current desktop state. Read-only."""
        return self._state

    def set_state(self, new_state: DesktopState) -> None:
        """
        Transition to a new state.
        Duplicate transitions are silently ignored — no event emitted.
        """
        if new_state == self._state:
            return

        old_state   = self._state
        self._state = new_state

        logger.info("[PRESENCE] %s → %s", old_state.label(), new_state.label())

        self._bus.emit(
            PresenceEvents.STATE_CHANGED,
            old_state=old_state.name,
            new_state=new_state.name,
        )

    def reset(self) -> None:
        """Return to IDLE. Idempotent — safe when already IDLE."""
        self.set_state(DesktopState.IDLE)

    def summary(self) -> dict:
        return {"state": self._state.name, "label": self._state.label()}

    def __repr__(self) -> str:
        return f"PresenceController(state={self._state.label()})"