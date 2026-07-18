"""
Jarvis Context Inspector (Genesis-020 Sprint-002)

Developer tool for inspecting the active SessionContext.

Triggered by:
    - Chat command: "inspect context" / "/context"
    - Future: F10 in the Engineering Console

Produces a clean, readable snapshot of working memory:
    Current turn, all active slots, their values and effective confidence.

Constitutional constraints:
    - Read-only. Never modifies SessionContext.
    - No AI calls, no I/O beyond returning a string.
    - Available in all builds (not debug-only) for transparency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.session_context import SessionContext


class ContextInspector:
    """
    Read-only inspector for the active SessionContext.

    Returns a formatted string suitable for display in the chat UI
    or engineering console.
    """

    def __init__(self, session: "SessionContext"):
        self._session = session

    def inspect(self) -> str:
        """
        Return a formatted snapshot of the current SessionContext.

        Example output:
            ┌─ Active Session Context (Turn 7) ─────────────────┐
            │  Project:   Jarvis OS           [conf: 0.90]       │
            │  Milestone: Genesis-020         [conf: 0.72]       │
            │  Task:      Sprint-002          [conf: 1.00]       │
            │  Person:    Claude              [conf: 0.95]       │
            │  Topic:     —                                      │
            └────────────────────────────────────────────────────┘
        """
        s = self._session
        turn = s.current_turn

        def fmt(slot, label):
            if slot is None:
                return f"  {label:<12} —"
            ec = slot.effective_confidence(turn)
            if ec < 0.20:
                return f"  {label:<12} — (faded)"
            return f"  {label:<12} {slot.value:<24} [conf: {ec:.2f}]"

        lines = [
            f"┌─ Active Session Context (Turn {turn}) {'─' * max(0, 28 - len(str(turn)))}┐",
            fmt(s.active_project,   "Project:"),
            fmt(s.active_milestone, "Milestone:"),
            fmt(s.active_task,      "Task:"),
            fmt(s.active_person,    "Person:"),
            fmt(s.active_topic,     "Topic:"),
            "└" + "─" * 52 + "┘",
        ]
        return "\n".join(lines)

    def is_empty(self) -> bool:
        """Return True if no slots are currently active."""
        s = self._session
        return all(
            not s.is_usable(slot)
            for slot in [s.active_project, s.active_milestone,
                         s.active_task, s.active_person, s.active_topic]
        )