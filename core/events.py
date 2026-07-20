"""
Jarvis Event Bus

A lightweight event system for communication
between Jarvis modules.

Genesis-023 MP-001: added unsubscribe() only.
All existing behaviour preserved unchanged.
"""

from collections import defaultdict


class EventBus:
    def __init__(self):
        self._listeners = defaultdict(list)

    def subscribe(self, event_name, callback):
        """Register a listener for an event."""
        self._listeners[event_name].append(callback)

    def unsubscribe(self, event_name, callback):
        """Remove a previously registered listener. Safe if not found."""
        try:
            self._listeners[event_name].remove(callback)
        except ValueError:
            pass

    def emit(self, event_name, *args, **kwargs):
        """Send an event to all listeners."""
        for callback in list(self._listeners[event_name]):
            callback(*args, **kwargs)


# Shared instance used across Jarvis
event_bus = EventBus()