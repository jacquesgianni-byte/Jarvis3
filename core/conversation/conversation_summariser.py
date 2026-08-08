"""
ConversationSummariser — Genesis-043 Sprint-004 (PROP-0003)
Hierarchical conversation summarisation for Jarvis-OS.
Three tiers: verbatim (last 5 turns), compressed (one line each), abstract.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.conversation_state import ConversationState

logger = logging.getLogger(__name__)

DEFAULT_VERBATIM_TURNS: int = 5
DEFAULT_COMPRESSED_MAX: int = 20


@dataclass
class TurnSummary:
    turn_number:  int
    user_intent:  str
    jarvis_brief: str
    topic:        str = ""

    def to_line(self) -> str:
        line = f"Turn {self.turn_number}"
        if self.topic:
            line += f" [{self.topic}]"
        line += f" -- User: {self.user_intent}"
        if self.jarvis_brief:
            line += f" -> Jarvis: {self.jarvis_brief}"
        return line


@dataclass
class SummarySnapshot:
    verbatim_turns:    list
    compressed_lines:  list
    session_abstract:  str
    total_turns:       int
    verbatim_count:    int
    compressed_count:  int

    def to_context_string(self) -> str:
        parts = []
        if self.session_abstract:
            parts.append(f"[Session context: {self.session_abstract}]")
        if self.compressed_lines:
            parts.append("[Earlier in this conversation:]")
            parts.extend(self.compressed_lines)
        if self.verbatim_turns:
            if self.compressed_lines or self.session_abstract:
                parts.append("[Recent conversation:]")
            for user_msg, jarvis_resp in self.verbatim_turns:
                parts.append(f"User: {user_msg}")
                if jarvis_resp:
                    parts.append(f"Jarvis: {jarvis_resp}")
        return "\n".join(parts)

    def is_empty(self) -> bool:
        return not self.verbatim_turns and not self.compressed_lines


class ConversationSummariser:
    def __init__(
        self,
        verbatim_turns: int = DEFAULT_VERBATIM_TURNS,
        compressed_max: int = DEFAULT_COMPRESSED_MAX,
    ) -> None:
        self._verbatim_turns = verbatim_turns
        self._compressed_max = compressed_max
        self._raw_turns: list = []
        self._session_abstract: str = ""
        self._total_turns_seen: int = 0

    def add_turn(self, user_msg: str, jarvis_response: str, topic: str = "", turn_number: int = 0) -> None:
        self._raw_turns.append((user_msg, jarvis_response, topic, turn_number))
        self._total_turns_seen += 1
        max_stored = self._verbatim_turns + self._compressed_max
        if len(self._raw_turns) > max_stored:
            self._raw_turns.pop(0)

    def set_session_abstract(self, text: str) -> None:
        self._session_abstract = text

    def build_abstract_from_state(self, state) -> str:
        parts = []
        tracker = getattr(state, "topic_tracker", None)
        if tracker is not None:
            current = tracker.current_name
            history = tracker.history_names
            all_topics = history + ([current] if current else [])
            if all_topics:
                unique = list(dict.fromkeys(all_topics))
                parts.append(f"Topics: {', '.join(unique)}")
        registry = getattr(state, "entity_registry", None)
        if registry is not None:
            current_turn = getattr(state, "current_turn", 0)
            active = registry.active(current_turn)
            if active:
                sorted_entities = sorted(active, key=lambda e: e.mention_count, reverse=True)
                names = [e.display_name for e in sorted_entities[:5]]
                parts.append(f"Entities: {', '.join(names)}")
        turn_count = getattr(state, "_turn_count", 0) or self._total_turns_seen
        if turn_count:
            parts.append(f"{turn_count} turns")
        abstract = ". ".join(parts) + "." if parts else ""
        if abstract:
            self._session_abstract = abstract
        return abstract

    def snapshot(self) -> SummarySnapshot:
        total = len(self._raw_turns)
        if total == 0:
            return SummarySnapshot(
                verbatim_turns=[], compressed_lines=[],
                session_abstract=self._session_abstract,
                total_turns=self._total_turns_seen,
                verbatim_count=0, compressed_count=0,
            )
        verbatim_count   = min(self._verbatim_turns, total)
        compressed_count = total - verbatim_count
        raw_compressed   = self._raw_turns[:compressed_count]
        raw_verbatim     = self._raw_turns[compressed_count:]
        compressed_lines = []
        for user_msg, jarvis_resp, topic, turn_num in raw_compressed:
            ts = TurnSummary(
                turn_number=turn_num,
                user_intent=user_msg[:80].strip(),
                jarvis_brief=jarvis_resp[:120].strip(),
                topic=topic,
            )
            compressed_lines.append(ts.to_line())
        verbatim_turns = [
            (user_msg, jarvis_resp)
            for user_msg, jarvis_resp, _, _ in raw_verbatim
        ]
        return SummarySnapshot(
            verbatim_turns=verbatim_turns,
            compressed_lines=compressed_lines,
            session_abstract=self._session_abstract,
            total_turns=self._total_turns_seen,
            verbatim_count=verbatim_count,
            compressed_count=compressed_count,
        )

    def to_context_string(self) -> str:
        return self.snapshot().to_context_string()

    def reset(self) -> None:
        self._raw_turns = []
        self._session_abstract = ""
        self._total_turns_seen = 0

    def turn_count(self) -> int:
        return self._total_turns_seen

    def stored_count(self) -> int:
        return len(self._raw_turns)

    def summary(self) -> dict:
        snap = self.snapshot()
        return {
            "total_turns_seen": self._total_turns_seen,
            "stored_turns":     len(self._raw_turns),
            "verbatim_count":   snap.verbatim_count,
            "compressed_count": snap.compressed_count,
            "has_abstract":     bool(self._session_abstract),
            "verbatim_window":  self._verbatim_turns,
            "compressed_max":   self._compressed_max,
        }
