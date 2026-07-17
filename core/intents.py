"""
Jarvis Intents

The set of intents the IntentRouter can detect. Each maps to a skill
(or, for UNKNOWN, to the AI fallback).
"""

from enum import Enum, auto


class Intent(Enum):
    GREETING = auto()
    IDENTITY = auto()
    MEMORY = auto()
    REASONING = auto()   # Genesis-013: questions answered by thinking,
                         # not remembering — plus "why?" follow-ups.
    TOOL = auto()
    EXIT = auto()
    ENGINEERING = auto() # Genesis-019.5: questions answered by the
                         # Engineering Academy before any AI provider
                         # is invoked.
    UNKNOWN = auto()