"""
Action Model

Represents a single action that Jarvis intends to perform.
"""

from dataclasses import dataclass, field


@dataclass
class Action:
    """
    Represents a single action for Jarvis to execute.
    """

    name: str
    confidence: float = 1.0
    parameters: dict = field(default_factory=dict)