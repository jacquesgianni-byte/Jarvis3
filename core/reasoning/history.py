"""
Inference history (Genesis-013 Task 001).

[R4] Version 1 keeps history IN MEMORY ONLY, behind a repository
interface, so file or SQLite persistence in a later Genesis is an
implementation swap with zero interface change.

History is diagnostic memory, not knowledge: it never feeds back into
inference and is never stored in knowledge.json. Its V1 purpose is
explainability within a session — a user asking "why?" about an answer
they just received.
"""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, UTC

from core.reasoning.models import Inference, Outcome


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """One inference attempt, successful or not."""

    subject: str
    attribute: str
    outcome: Outcome
    inference: Inference = None      # None when outcome is NO_PATH
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InferenceHistoryRepository(ABC):
    """Storage interface for inference history."""

    @abstractmethod
    def record(self, entry: HistoryEntry) -> None:
        """Store one history entry."""

    @abstractmethod
    def recent(self, limit: int = 20) -> list:
        """Return the newest entries, newest first."""

    @abstractmethod
    def clear(self) -> None:
        """Discard all history."""


class InMemoryInferenceHistory(InferenceHistoryRepository):
    """Bounded in-memory history (newest-N, oldest evicted first)."""

    def __init__(self, max_entries: int = 200):
        self._entries = deque(maxlen=max_entries)

    def record(self, entry: HistoryEntry) -> None:
        self._entries.append(entry)

    def recent(self, limit: int = 20) -> list:
        return list(self._entries)[-limit:][::-1]

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)