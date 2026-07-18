"""
Jarvis Timeline Inspector (Genesis-020 Sprint-003)

Developer tool for inspecting the active ConversationTimeline.

Triggered by:
    - Chat command: "show timeline" / "/timeline"
    - Developer console (future)

Produces a clean, readable snapshot of the conversation timeline:
    Turn, event type, value, and timestamp for every recorded event.

Constitutional constraints:
    - Read-only. Never modifies the timeline.
    - No AI calls, no I/O beyond returning a string.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.conversation_timeline import ConversationTimeline


class TimelineInspector:
    """
    Read-only inspector for the active ConversationTimeline.

    Returns a formatted string suitable for the chat UI or console.
    """

    def __init__(self, timeline: "ConversationTimeline"):
        self._timeline = timeline

    def inspect(self) -> str:
        """
        Return a formatted snapshot of the full timeline.

        Example output:
            ┌─ Conversation Timeline (12 events) ────────────────┐
            │  Turn  1  Start Project     Jarvis OS               │
            │  Turn  5  Start Sprint      Sprint-001              │
            │  Turn 14  Finish Sprint     Sprint-001              │
            │  Turn 18  Start Sprint      Sprint-002              │
            └────────────────────────────────────────────────────┘
        """
        events = self._timeline.all_events()
        n = len(events)
        header = f"┌─ Conversation Timeline ({n} event{'s' if n != 1 else ''}) "
        header = header + "─" * max(0, 52 - len(header)) + "┐"

        lines = [header]
        if not events:
            lines.append("│  (no events recorded yet)")
        else:
            for e in events:
                turn_str  = f"Turn {e.turn:>3}"
                type_str  = e.event_type.label()
                value_str = e.value if len(e.value) <= 28 else e.value[:25] + "..."
                line = f"  {turn_str}  {type_str:<16} {value_str}"
                lines.append(line)

        lines.append("└" + "─" * 52 + "┘")
        return "\n".join(lines)

    def summary_line(self) -> str:
        """Return a one-line summary for logging/status bar."""
        s = self._timeline.summary()
        total = s["total_events"]
        proj  = s["latest_project"] or "—"
        sprint = s["latest_sprint"] or "—"
        return f"Timeline: {total} events | Project: {proj} | Sprint: {sprint}"