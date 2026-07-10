"""
Jarvis Event Bus

A lightweight event system for communication
between Jarvis modules.
"""

from collections import defaultdict


class EventBus:
    def __init__(self):
        self._listeners = defaultdict(list)

    def subscribe(self, event_name, callback):
        """Register a listener for an event."""
        self._listeners[event_name].append(callback)

    def emit(self, event_name, *args, **kwargs):
        """Send an event to all listeners."""
        for callback in self._listeners[event_name]:
            callback(*args, **kwargs)


# Shared instance used across Jarvis
event_bus = EventBus()