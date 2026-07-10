"""
Entity Model

Represents a piece of information extracted from a user's request.
"""

from dataclasses import dataclass


@dataclass
class Entity:
    """
    Represents a single entity identified within a request.
    """

    type: str
    value: str