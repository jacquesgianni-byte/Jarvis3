"""
Request Model

Represents a user's request as it moves through the Jarvis pipeline.
"""

from dataclasses import dataclass, field

from core.models.action import Action
from core.models.entity import Entity


@dataclass
class Request:
    """
    Represents a request being processed by Jarvis.
    """

    original_text: str
    normalized_text: str = ""

    actions: list[Action] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)

    context: dict = field(default_factory=dict)