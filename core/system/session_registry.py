"""
Jarvis OS Session Registry — Android Alpha Phase-2 / Sprint-004

Tracks today's operational events.
Powers /session endpoint and "What did we do today?" queries.
No AI. Pure operational history.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass
class SessionEvent:
    time:     str
    event:    str
    category: str = "general"   # general | engineering | conversation | system | memory


class SessionRegistry:
    """Append-only log of today's operational events."""

    def __init__(self):
        self._events: List[SessionEvent] = []
        self._conversation_count = 0
        self._memory_count = 0
        self._topics_discussed: list = []
        self._log("Jarvis server started", "system")

    def _log(self, event: str, category: str = "general") -> None:
        t = datetime.now().strftime("%H:%M")
        self._events.append(SessionEvent(time=t, event=event, category=category))

    def log_conversation(self, topic: str = "") -> None:
        self._conversation_count += 1
        if topic and topic not in self._topics_discussed:
            self._topics_discussed.append(topic)
            self._log(f"Discussed: {topic}", "conversation")
        elif self._conversation_count == 1:
            self._log("First conversation of the session", "conversation")

    def log_memory_stored(self, key: str, value: str) -> None:
        self._memory_count += 1
        short_val = value[:40] + "..." if len(value) > 40 else value
        self._log(f"Remembered: {key} = {short_val}", "memory")

    def log_android_connected(self) -> None:
        self._log("Android connected", "system")

    def log_engineering(self, description: str) -> None:
        self._log(description, "engineering")

    def log_system(self, description: str) -> None:
        self._log(description, "system")

    def log_genesis_started(self, genesis: str) -> None:
        self._log(f"Genesis-{genesis} work started", "engineering")

    def log_tests_run(self, passed: int, failed: int) -> None:
        self._log(f"Tests run: {passed} passed, {failed} failed", "engineering")

    def all_events(self) -> List[dict]:
        return [
            {"time": e.time, "event": e.event, "category": e.category}
            for e in self._events
        ]

    def today_summary(self) -> str:
        """Human-readable summary of today's activity."""
        if not self._events:
            return "No activity recorded today."

        lines = ["Today's activity:"]
        lines.append("")

        # Group by category
        by_cat: dict = {}
        for e in self._events:
            by_cat.setdefault(e.category, []).append(e)

        if "system" in by_cat:
            lines.append("System:")
            for e in by_cat["system"]:
                lines.append(f"  {e.time}  {e.event}")

        if "engineering" in by_cat:
            lines.append("Engineering:")
            for e in by_cat["engineering"]:
                lines.append(f"  {e.time}  {e.event}")

        if "memory" in by_cat:
            lines.append("Memory stored:")
            for e in by_cat["memory"]:
                lines.append(f"  {e.time}  {e.event}")

        if "conversation" in by_cat:
            lines.append("Conversations:")
            for e in by_cat["conversation"]:
                lines.append(f"  {e.time}  {e.event}")

        if "general" in by_cat:
            for e in by_cat["general"]:
                lines.append(f"  {e.time}  {e.event}")

        lines.append("")
        lines.append(f"Total: {self._conversation_count} conversations, {self._memory_count} memories stored.")
        return "\n".join(lines)

    def quick_summary(self) -> str:
        """One-line summary for greetings."""
        parts = []
        if self._conversation_count > 0:
            parts.append(f"{self._conversation_count} conversations")
        if self._memory_count > 0:
            parts.append(f"{self._memory_count} memories stored")
        if self._topics_discussed:
            topics = ", ".join(self._topics_discussed[:3])
            parts.append(f"topics: {topics}")
        eng = [e for e in self._events if e.category == "engineering"]
        if eng:
            parts.append(f"{len(eng)} engineering events")
        if not parts:
            return "Session just started."
        return " | ".join(parts)
