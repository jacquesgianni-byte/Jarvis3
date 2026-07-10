"""
Knowledge Engine — Memory Record Model

Defines the MemoryRecord dataclass representing a single unit of knowledge
in the Jarvis Knowledge Engine.

Every memory follows a subject / attribute / value fact model:
    "Ludovic's favourite colour is blue."
     subject   attribute              value
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Imported here to avoid circular imports — exceptions has no knowledge of models.
from core.knowledge_engine.exceptions import InvalidMemoryError
from enum import Enum


class MemorySource(str, Enum):
    """
    The source of a memory — who or what provided it.

    Inherits from str so instances serialise cleanly to JSON
    without requiring custom serialisation logic.
    """
    USER = "user"
    INFERRED = "inferred"
    SYSTEM = "system"


class Visibility(str, Enum):
    """
    Access control for a memory record.

    Inherits from str so instances serialise cleanly to JSON.
    """
    PRIVATE = "private"
    SHARED = "shared"
    SYSTEM = "system"




@dataclass
class MemoryRecord:
    """
    A single unit of knowledge stored in the Knowledge Engine.

    Represents a structured fact about a subject following the
    subject / attribute / value model defined in the Knowledge
    Engine Specification v1.1.

    Attributes:
        id:           Unique identifier (UUID).
        subject:      Who or what this fact is about.
                      Examples: "user", "wife", "son", "printer"
        category:     Organisational grouping. Must match a category
                      defined in categories.json.
        attribute:    The property being described.
                      Examples: "favourite_colour", "name", "model"
        value:        The value of the attribute.
                      Examples: "blue", "Catriana", "A1 Mini"
        data_type:    The value type for future typed memory support.
                      Examples: "str", "int", "date", "bool"
        confidence:   0.0 – 1.0. How certain Jarvis is this is correct.
        importance:   0.0 – 1.0. How significant this memory is.
                      Affects prompt enrichment priority.
        visibility:   Access control. One of: "private", "shared", "system".
        source:       Who provided this memory.
                      One of: "user", "inferred", "system".
        created_at:   When this memory was first stored.
        updated_at:   When this memory was last modified.
        expires_at:   Optional expiry date. None = permanent.
        tags:         Searchable labels.
        notes:        Optional context or provenance notes.
                      Updated automatically when a value is changed.
    """

    subject: str
    category: str
    attribute: str
    value: str

    id: str = field(default_factory=lambda: str(uuid4()))
    data_type: str = "str"
    confidence: float = 1.0
    importance: float = 0.5
    visibility: Visibility = Visibility.PRIVATE
    source: MemorySource = MemorySource.USER
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        """
        Validate the MemoryRecord after construction.

        Raises InvalidMemoryError if any field contains an invalid value.
        This ensures no invalid memory can ever enter the Knowledge Engine,
        regardless of which code path created it.

        Raises:
            InvalidMemoryError: If any required field is empty or any
                                numeric field is out of its valid range.
        """
        if not self.subject or not self.subject.strip():
            raise InvalidMemoryError("subject", "subject must not be empty.")

        if not self.attribute or not self.attribute.strip():
            raise InvalidMemoryError("attribute", "attribute must not be empty.")

        if not self.value or not self.value.strip():
            raise InvalidMemoryError("value", "value must not be empty.")

        if not 0.0 <= self.confidence <= 1.0:
            raise InvalidMemoryError(
                "confidence",
                f"confidence must be between 0.0 and 1.0, got {self.confidence}."
            )

        if not 0.0 <= self.importance <= 1.0:
            raise InvalidMemoryError(
                "importance",
                f"importance must be between 0.0 and 1.0, got {self.importance}."
            )

    def is_expired(self) -> bool:
        """
        Return True if this memory has passed its expiry date.

        Returns:
            True if expires_at is set and is in the past.
        """
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def to_dict(self) -> dict:
        """
        Serialise the MemoryRecord to a JSON-compatible dictionary.

        Datetime fields are converted to ISO 8601 strings.
        None values are preserved as null.

        Returns:
            A dictionary suitable for JSON serialisation.
        """
        return {
            "id": self.id,
            "subject": self.subject,
            "category": self.category,
            "attribute": self.attribute,
            "value": self.value,
            "data_type": self.data_type,
            "confidence": self.confidence,
            "importance": self.importance,
            "visibility": self.visibility.value,
            "source": self.source.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "tags": self.tags,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        """
        Deserialise a MemoryRecord from a dictionary.

        Converts ISO 8601 strings back to datetime objects.

        Args:
            data: A dictionary as produced by to_dict().

        Returns:
            A MemoryRecord instance.
        """
        return cls(
            id=data["id"],
            subject=data["subject"],
            category=data["category"],
            attribute=data["attribute"],
            value=data["value"],
            data_type=data.get("data_type", "str"),
            confidence=data.get("confidence", 1.0),
            importance=data.get("importance", 0.5),
            visibility=Visibility(data.get("visibility", "private")),
            source=MemorySource(data.get("source", "user")),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            tags=data.get("tags", []),
            notes=data.get("notes"),
        )