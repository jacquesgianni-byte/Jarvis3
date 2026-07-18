"""
Jarvis Session Summary Model (Genesis-020 Sprint-006)

Defines the immutable SessionSummary dataclass.

Design constraints:
    - Frozen dataclass — never mutated after creation.
    - Produced by replaying the Conversation Timeline.
    - No independent storage — fully reconstructable from replay.
    - Deterministic: same Timeline → same Summary, always.
    - Versioned for replay compatibility.

A SessionSummary is a snapshot of what happened in a conversation
session. It is not AI-generated prose — it is a structured
deterministic record derived from Timeline events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class SessionSummary:
    """
    An immutable deterministic summary of a conversation session.

    All fields are derived from Timeline events via replay.
    Nothing is generated, inferred, or AI-produced.

    Attributes:
        session_id:         Unique session identifier.
        started_at:         UTC datetime of first Timeline event.
        ended_at:           UTC datetime of last Timeline event.
        turn_count:         Total number of conversation turns.
        goals_created:      Number of goals created this session.
        goals_completed:    Number of goals completed this session.
        goals_blocked:      Number of goals blocked this session.
        goals_cancelled:    Number of goals cancelled this session.
        decisions_made:     Number of decisions recorded this session.
        decisions_superseded: Number of decisions superseded.
        decisions_rejected: Number of decisions rejected.
        memories_created:   Number of facts extracted/stored.
        projects_mentioned: Project names mentioned in session.
        milestones_reached: Milestones completed or frozen.
        people_mentioned:   People introduced or discussed.
        important_events:   Key event descriptions in turn order.
        summary_lines:      Human-readable summary bullet points.
        version:            Schema version for replay compatibility.
        payload:            Structured supplementary data.
    """
    session_id:           str
    started_at:           datetime
    ended_at:             datetime
    turn_count:           int                  = 0
    goals_created:        int                  = 0
    goals_completed:      int                  = 0
    goals_blocked:        int                  = 0
    goals_cancelled:      int                  = 0
    decisions_made:       int                  = 0
    decisions_superseded: int                  = 0
    decisions_rejected:   int                  = 0
    memories_created:     int                  = 0
    projects_mentioned:   tuple[str, ...]      = field(default_factory=tuple)
    milestones_reached:   tuple[str, ...]      = field(default_factory=tuple)
    people_mentioned:     tuple[str, ...]      = field(default_factory=tuple)
    important_events:     tuple[str, ...]      = field(default_factory=tuple)
    summary_lines:        tuple[str, ...]      = field(default_factory=tuple)
    version:              int                  = 1
    payload:              dict[str, Any]       = field(default_factory=dict)

    @property
    def duration_minutes(self) -> float:
        """Session duration in minutes."""
        delta = self.ended_at - self.started_at
        return round(delta.total_seconds() / 60, 1)

    @property
    def duration_str(self) -> str:
        """Human-readable duration string."""
        minutes = self.duration_minutes
        if minutes < 1:
            seconds = int((self.ended_at - self.started_at).total_seconds())
            return f"{seconds} second{'s' if seconds != 1 else ''}"
        if minutes < 60:
            m = int(minutes)
            return f"{m} minute{'s' if m != 1 else ''}"
        hours = minutes / 60
        return f"{hours:.1f} hour{'s' if hours != 1 else ''}"

    def format(self) -> str:
        """
        Full formatted session summary.
        Deterministic — same Summary always produces same output.
        """
        lines = [
            "Session Summary",
            "═" * 40,
            f"",
            f"Duration:     {self.duration_str}",
            f"Turns:        {self.turn_count}",
            f"",
            f"Goals Created:    {self.goals_created}",
            f"Goals Completed:  {self.goals_completed}",
            f"Goals Blocked:    {self.goals_blocked}",
            f"",
            f"Decisions Made:   {self.decisions_made}",
            f"Decisions Superseded: {self.decisions_superseded}",
            f"",
            f"Memories Added:   {self.memories_created}",
        ]

        if self.projects_mentioned:
            lines += ["", "Projects:"]
            for p in self.projects_mentioned:
                lines.append(f"  • {p}")

        if self.milestones_reached:
            lines += ["", "Milestones:"]
            for m in self.milestones_reached:
                lines.append(f"  • {m}")

        if self.people_mentioned:
            lines += ["", "People:"]
            for p in self.people_mentioned:
                lines.append(f"  • {p}")

        if self.important_events:
            lines += ["", "Key Events:"]
            for e in self.important_events:
                lines.append(f"  • {e}")

        return "\n".join(lines)

    def __str__(self) -> str:
        return (
            f"Session [{self.session_id[:8]}] "
            f"— {self.turn_count} turns, "
            f"{self.duration_str}, "
            f"{self.goals_completed} goals completed, "
            f"{self.decisions_made} decisions"
        )