"""
Jarvis Goal Model (Genesis-020 Sprint-005)

Defines the immutable Goal dataclass and GoalStatus enum.

Design constraints:
    - Frozen dataclass — never mutated after creation.
    - Status transitions produce NEW Goal instances — history preserved.
    - Versioned schema for replay compatibility.
    - Fully independent of KnowledgeEngine, SessionContext, Timeline.
    - Replay-safe: same events always produce same state.

Goal lifecycle:
    PLANNED   → goal is defined but not yet started
    ACTIVE    → goal is being worked on
    BLOCKED   → goal cannot proceed (dependency or blocker)
    COMPLETED → goal has been achieved
    CANCELLED → goal was abandoned

Dependencies:
    A goal may declare other goal IDs as dependencies.
    The GoalEngine tracks these but does not enforce ordering —
    enforcement belongs in Genesis-021 Workers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any


class GoalStatus(Enum):
    """Lifecycle status of a goal."""
    PLANNED   = auto()
    ACTIVE    = auto()
    BLOCKED   = auto()
    COMPLETED = auto()
    CANCELLED = auto()

    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def is_active(self) -> bool:
        return self == GoalStatus.ACTIVE

    @property
    def is_open(self) -> bool:
        """True if the goal is still in progress (not terminal)."""
        return self in (GoalStatus.PLANNED, GoalStatus.ACTIVE, GoalStatus.BLOCKED)

    @property
    def is_terminal(self) -> bool:
        return self in (GoalStatus.COMPLETED, GoalStatus.CANCELLED)


class GoalPriority(Enum):
    """Priority levels for goals."""
    CRITICAL = 1
    HIGH     = 2
    MEDIUM   = 3
    LOW      = 4

    def label(self) -> str:
        return self.name.title()


@dataclass(frozen=True)
class Goal:
    """
    A single immutable goal.

    Attributes:
        title:        Short human-readable title.
        description:  Full description of what this goal achieves.
        status:       Current lifecycle status.
        priority:     Priority level.
        source_turn:  Conversation turn when this goal was created.
        timestamp:    UTC datetime when this goal was created.
        id:           Unique identifier (UUID4 string).
        progress:     Completion percentage (0–100).
        dependencies: IDs of goals this goal depends on.
        parent_id:    ID of parent goal (for sub-goals).
        tags:         Category tags for filtering.
        blocked_by:   Description of what is blocking this goal.
        version:      Schema version for replay compatibility.
        payload:      Structured supplementary data.
    """
    title:        str
    description:  str                  = ""
    status:       GoalStatus           = GoalStatus.PLANNED
    priority:     GoalPriority         = GoalPriority.MEDIUM
    source_turn:  int                  = 0
    timestamp:    datetime             = field(default_factory=lambda: datetime.now(UTC))
    id:           str                  = field(default_factory=lambda: str(uuid.uuid4()))
    progress:     int                  = 0
    dependencies: tuple[str, ...]      = field(default_factory=tuple)
    parent_id:    str                  = ""
    tags:         tuple[str, ...]      = field(default_factory=tuple)
    blocked_by:   str                  = ""
    version:      int                  = 1
    payload:      dict[str, Any]       = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.status.label()}] {self.title} ({self.priority.label()})"

    def date_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d")

    def summary(self) -> str:
        deps = f" | deps: {len(self.dependencies)}" if self.dependencies else ""
        blocked = " | BLOCKED" if self.status == GoalStatus.BLOCKED else ""
        return (
            f"{self.title} [{self.status.label()}] "
            f"P{self.priority.value}{deps}{blocked} "
            f"— Turn {self.source_turn}"
        )

    def explain(self) -> str:
        """Full human-readable explanation of this goal."""
        lines = [
            f"Goal: {self.title}",
            f"",
            f"Description: {self.description or '(no description)'}",
            f"Status:   {self.status.label()}",
            f"Priority: {self.priority.label()}",
            f"Progress: {self.progress}%",
        ]
        if self.dependencies:
            lines += ["", "Depends on:"]
            for dep in self.dependencies:
                lines.append(f"  - {dep}")
        if self.blocked_by:
            lines += ["", f"Blocked by: {self.blocked_by}"]
        if self.parent_id:
            lines += ["", f"Sub-goal of: {self.parent_id}"]
        lines += ["", f"Recorded: Turn {self.source_turn} ({self.date_str()})"]
        return "\n".join(lines)

    def with_status(
        self,
        status: GoalStatus,
        blocked_by: str = "",
        progress: int = -1,
    ) -> "Goal":
        """Return a new Goal with updated status (immutability preserved)."""
        return Goal(
            id=self.id,
            title=self.title,
            description=self.description,
            status=status,
            priority=self.priority,
            source_turn=self.source_turn,
            timestamp=self.timestamp,
            progress=progress if progress >= 0 else self.progress,
            dependencies=self.dependencies,
            parent_id=self.parent_id,
            tags=self.tags,
            blocked_by=blocked_by if blocked_by else self.blocked_by,
            version=self.version,
            payload=self.payload,
        )

    def with_priority(self, priority: GoalPriority) -> "Goal":
        """Return a new Goal with updated priority."""
        return Goal(
            id=self.id,
            title=self.title,
            description=self.description,
            status=self.status,
            priority=priority,
            source_turn=self.source_turn,
            timestamp=self.timestamp,
            progress=self.progress,
            dependencies=self.dependencies,
            parent_id=self.parent_id,
            tags=self.tags,
            blocked_by=self.blocked_by,
            version=self.version,
            payload=self.payload,
        )