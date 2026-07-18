"""
Jarvis Decision Inspector (Genesis-020 Sprint-004)

Developer tool for inspecting the active Decision Engine.

Triggered by:
    - Chat command: "/decisions" or "show decisions"
    - Developer console (future)

Example output:
    ┌─ Decision Engine (18 decisions) ──────────────────────┐
    │  Active:       14                                      │
    │  Superseded:    3                                      │
    │  Experimental:  1                                      │
    │  Rejected:      0                                      │
    │                                                        │
    │  Latest decisions:                                     │
    │    • Event Sourcing                  [Accepted]        │
    │    • Projection Architecture         [Accepted]        │
    │    • Immutable Timeline              [Accepted]        │
    └────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.decision_engine import DecisionEngine


class DecisionInspector:
    """
    Read-only inspector for the active DecisionEngine.

    Returns formatted strings for the chat UI or developer console.
    """

    def __init__(self, engine: "DecisionEngine"):
        self._engine = engine

    def inspect(self) -> str:
        """Return a formatted snapshot of all decisions."""
        s = self._engine.summary()
        total = s["total"]
        header = f"┌─ Decision Engine ({total} decision{'s' if total != 1 else ''}) "
        header = header + "─" * max(0, 52 - len(header)) + "┐"

        lines = [header]
        lines.append(f"  Active:        {s['active']}")
        lines.append(f"  Superseded:    {s['superseded']}")
        lines.append(f"  Experimental:  {s['experimental']}")
        lines.append(f"  Rejected:      {s['rejected']}")
        lines.append(f"  Proposed:      {s['proposed']}")

        if s["latest"]:
            lines.append("")
            lines.append("  Latest decisions:")
            for title in s["latest"]:
                lines.append(f"    • {title}")

        lines.append("└" + "─" * 52 + "┘")
        return "\n".join(lines)

    def explain_latest(self) -> str:
        """Return the full explanation of the most recent decision."""
        decisions = self._engine.latest(1)
        if not decisions:
            return "No decisions recorded yet, sir."
        return decisions[0].explain()

    def is_empty(self) -> bool:
        """Return True if no decisions have been recorded."""
        return self._engine.count() == 0