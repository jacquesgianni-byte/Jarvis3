"""
Jarvis OS Session Registry — Android Alpha Phase-2 / Sprint-003

Tracks today's operational events.
Powers /session endpoint and "What happened today?" queries.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class SessionEvent:
    time:     str
    event:    str
    category: str = "general"   # general | engineering | conversation | system


class SessionRegistry:
    """Append-only log of today's operational events."""

    def __init__(self):
        self._events: List[SessionEvent] = []
        self._log("Jarvis server started", "system")

    def _log(self, event: str, category: str = "general") -> None:
        t = datetime.now().strftime("%H:%M")
        self._events.append(SessionEvent(time=t, event=event, category=category))

    def log_conversation(self) -> None:
        self._log("Conversation", "conversation")

    def log_android_connected(self) -> None:
        self._log("Android connected", "system")

    def log_engineering(self, description: str) -> None:
        self._log(description, "engineering")

    def log_system(self, description: str) -> None:
        self._log(description, "system")

    def all_events(self) -> List[dict]:
        return [
            {"time": e.time, "event": e.event, "category": e.category}
            for e in self._events
        ]

    def today_summary(self) -> str:
        if not self._events:
            return "No activity recorded today."
        lines = [f"{e.time}  {e.event}" for e in self._events]
        return "\n".join(lines)
