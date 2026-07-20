"""
Jarvis Desktop Presence Events (Genesis-023 MP-001)

Event name constants for the presence subsystem.
Constants prevent magic strings and make event names discoverable.
"""


class PresenceEvents:
    """
    Namespace of presence event name constants.
    Do not instantiate.
    """

    # Emitted by PresenceController.set_state() on every valid transition.
    # Payload: emit(STATE_CHANGED, old_state=str, new_state=str)
    STATE_CHANGED: str = "PRESENCE_STATE_CHANGED"

    def __new__(cls):
        raise TypeError("PresenceEvents is a constants namespace — do not instantiate it.")