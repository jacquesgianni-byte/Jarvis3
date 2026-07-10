"""
Memory Detection

Represents a personal fact detected in a user message.

This model carries only the result of detection.
It has no behaviour and no knowledge of how the memory will be stored.
"""

from dataclasses import dataclass


@dataclass(slots=True)
class MemoryDetection:
    """
    A personal fact detected in a user message.

    Returned by MemoryDetector when a message appears to contain
    information that Jarvis should remember about the user.

    This model does not save, validate, or act on the memory.
    That responsibility belongs to the Agent and MemoryManager.

    Attributes:
        key:        The subject of the memory.
                    Examples: "name", "favourite colour", "drink", "car"
        value:      The value associated with the key.
                    Examples: "Ludovic", "blue", "coffee", "Ranger"
        confidence: A float between 0.0 and 1.0 indicating how confident
                    the detector is that this is a genuine memory statement.
                    Rule-based detections currently return fixed confidence
                    values based on pattern specificity.
    """

    key: str
    value: str
    confidence: float