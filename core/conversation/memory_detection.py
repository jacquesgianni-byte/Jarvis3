"""
Memory Detection

Represents a personal fact detected in a user message.

This model carries only the result of detection.
It has no behaviour and no knowledge of how the memory will be stored.
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class MemoryDetection:
    """
    A personal fact detected in a user message.

    Returned by MemoryDetector or SlotCompletionEngine when a message
    appears to contain information that Jarvis should remember.

    This model does not save, validate, or act on the memory.
    That responsibility belongs to the Agent and MemorySkill.

    Attributes:
        key:                  The subject of the memory.
                              Examples: "name", "favourite colour", "pets"
        value:                The value associated with the key.
                              Examples: "Ludovic", "blue", "2 dogs"
        confidence:           A float between 0.0 and 1.0 indicating how
                              confident the detector is that this is a
                              genuine memory statement.
        is_group_declaration: True when this detection represents a group
                              declaration ("I have 2 dogs.") that opens a
                              new slot-completion frame. The Agent uses this
                              signal to set active_topic without enumerating
                              entity type names. Set by SlotCompletionEngine;
                              always False for MemoryDetector detections.
                              Genesis-025 Sprint-003.
    """
    key:                  str
    value:                str
    confidence:           float
    is_group_declaration: bool = False