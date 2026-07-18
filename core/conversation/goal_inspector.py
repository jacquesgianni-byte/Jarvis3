"""
Jarvis Goal Inspector (Genesis-020 Sprint-005)

Developer tool for inspecting the active GoalEngine.

Triggered by: "/goals" or "show goals"

Example output:
    ┌─ Goal Engine (8 goals) ────────────────────────────────┐
    │  Active:     3                                          │
    │  Planned:    2                                          │
    │  Blocked:    1                                          │
    │  Completed:  2                                          │
    │                                                         │
    │  Current Priorities:                                    │
    │    • Genesis-020 Sprint-005          [Critical]         │
    │    • Engineering Academy integration [High]             │
    └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.goal_engine import GoalEngine


class GoalInspector:
    """Read-only inspector for the active GoalEngine."""

    def __init__(self, engine: "GoalEngine"):
        self._engine = engine

    def inspect(self) -> str:
        """Return a formatted snapshot of all goals."""
        s = self._engine.summary()
        total = s["total"]
        header = f"┌─ Goal Engine ({total} goal{'s' if total != 1 else ''}) "
        header = header + "─" * max(0, 52 - len(header)) + "┐"

        lines = [header]
        lines.append(f"  Active:     {s['active']}")
        lines.append(f"  Planned:    {s['planned']}")
        lines.append(f"  Blocked:    {s['blocked']}")
        lines.append(f"  Completed:  {s['completed']}")
        lines.append(f"  Cancelled:  {s['cancelled']}")

        if s["priorities"]:
            lines.append("")
            lines.append("  Current Priorities:")
            for title in s["priorities"]:
                lines.append(f"    • {title}")

        if s["current"]:
            lines.append("")
            lines.append(f"  Current: {s['current']}")

        lines.append("└" + "─" * 52 + "┘")
        return "\n".join(lines)

    def is_empty(self) -> bool:
        return self._engine.count() == 0

    def summary_line(self) -> str:
        s = self._engine.summary()
        return (
            f"Goals: {s['total']} total | "
            f"Active: {s['active']} | "
            f"Blocked: {s['blocked']} | "
            f"Completed: {s['completed']}"
        )