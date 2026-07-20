"""
Desktop presence states.

This module defines the high-level visual state of the Jarvis desktop.
Every visual component derives its behaviour from this state.
"""

from enum import Enum, auto


class DesktopState(Enum):
    """Represents the current desktop presence state."""

    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    EXECUTING = auto()
    SUCCESS = auto()
    ERROR = auto()
    SLEEPING = auto()