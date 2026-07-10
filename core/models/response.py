"""
Jarvis Response Model

Represents the result of processing a user's request.
"""

from dataclasses import dataclass, field


@dataclass
class Response:
    """
    Represents a response returned by Jarvis.
    """

    success: bool = True
    message: str = ""
    action: str | None = None
    data: dict = field(default_factory=dict)