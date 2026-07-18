"""
Jarvis Session Summary Inspector (Genesis-020 Sprint-006)

Developer tool for the /summary command.

Example output:
    ┌─ Session Summary ───────────────────────────────────────┐
    │  Duration:    23 minutes                                 │
    │  Turns:       41                                         │
    │                                                          │
    │  Goals:       2 created, 1 completed, 0 blocked          │
    │  Decisions:   3 made, 0 superseded                       │
    │  Memories:    5 added                                    │
    │                                                          │
    │  Key Events:                                             │
    │    • Decision Accepted: Event Sourcing                   │
    │    • Goal Completed: Sprint-005                          │
    └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.session_summary_engine import SessionSummaryEngine


class SessionSummaryInspector:
    """Read-only inspector for the active SessionSummaryEngine."""

    def __init__(self, engine: "SessionSummaryEngine"):
        self._engine = engine

    def inspect(self) -> str:
        """Return a formatted session summary snapshot."""
        if self._engine.is_empty():
            return (
                "┌─ Session Summary ──────────────────────────────────────┐\n"
                "│  Session just started — no events yet.                 │\n"
                "└────────────────────────────────────────────────────────┘"
            )

        summary = self._engine.current_summary()
        lines = [
            "┌─ Session Summary " + "─" * 35 + "┐",
            f"  Duration:    {summary.duration_str}",
            f"  Turns:       {summary.turn_count}",
            f"",
            f"  Goals:       {summary.goals_created} created, "
            f"{summary.goals_completed} completed, "
            f"{summary.goals_blocked} blocked",
            f"  Decisions:   {summary.decisions_made} made, "
            f"{summary.decisions_superseded} superseded",
            f"  Memories:    {summary.memories_created} added",
        ]

        if summary.projects_mentioned:
            lines += ["", f"  Projects:    {', '.join(summary.projects_mentioned)}"]

        if summary.milestones_reached:
            lines += ["", f"  Milestones:  {', '.join(summary.milestones_reached)}"]

        if summary.people_mentioned:
            lines += ["", f"  People:      {', '.join(summary.people_mentioned)}"]

        if summary.important_events:
            lines += ["", "  Key Events:"]
            for ev in summary.important_events[:5]:
                lines.append(f"    • {ev}")

        lines.append("└" + "─" * 52 + "┘")
        return "\n".join(lines)

    def summary_line(self) -> str:
        """One-line status for logging."""
        if self._engine.is_empty():
            return "Session: no events yet"
        s = self._engine.current_summary()
        return (
            f"Session: {s.turn_count} turns | "
            f"{s.goals_completed}/{s.goals_created} goals | "
            f"{s.decisions_made} decisions | "
            f"{s.duration_str}"
        )
    def is_empty(self) -> bool:
        return self._engine.is_empty()