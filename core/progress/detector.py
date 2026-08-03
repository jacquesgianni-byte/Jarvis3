"""
Executive Intelligence — Progress Detector
Genesis-035 Sprint-001

Deterministic detection of progress update and query commands.
No AI. Pure pattern matching.

Handles new patterns not covered by existing detectors:
  "Genesis-035 is in progress"
  "Genesis-035 is now in progress"
  "The parser task is complete"
  "Genesis-035 is blocked waiting for desktop validation"
  "How is Genesis-035 progressing?"
  "What is the progress on Genesis-035?"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from core.progress.models import ProgressState


class ProgressCommandKind(Enum):
    UPDATE_STATE  = auto()   # "X is in progress / complete / blocked"
    QUERY_PROGRESS = auto()  # "How is X progressing?"


@dataclass
class ProgressCommand:
    kind:       ProgressCommandKind
    subject:    str            # what entity (genesis number, task name, etc.)
    state:      Optional[ProgressState] = None   # for UPDATE_STATE
    blocker:    str = ""                         # for BLOCKED/WAITING states
    raw:        str = ""


# ── State keyword mapping ──────────────────────────────────────────────────────
_STATE_KEYWORDS: dict[str, ProgressState] = {
    "in progress":   ProgressState.IN_PROGRESS,
    "in-progress":   ProgressState.IN_PROGRESS,
    "now in progress": ProgressState.IN_PROGRESS,
    "started":       ProgressState.IN_PROGRESS,
    "underway":      ProgressState.IN_PROGRESS,
    "complete":      ProgressState.COMPLETED,
    "completed":     ProgressState.COMPLETED,
    "done":          ProgressState.COMPLETED,
    "finished":      ProgressState.COMPLETED,
    "blocked":       ProgressState.BLOCKED,
    "waiting":       ProgressState.WAITING,
    "on hold":       ProgressState.WAITING,
    "cancelled":     ProgressState.CANCELLED,
    "canceled":      ProgressState.CANCELLED,
    "not started":   ProgressState.NOT_STARTED,
}

# ── Update patterns ────────────────────────────────────────────────────────────
# "{subject} is {state}"
# "{subject} is {state} waiting for {blocker}"
# "The {subject} task is {state}"
_UPDATE_PATTERNS: list[re.Pattern] = [
    # "Genesis-035 is blocked waiting for X" / "is blocked on X"
    re.compile(
        r"^(?:genesis[-\s]?\d+|[\w\s\-]+?)\s+is\s+(?:blocked|waiting)\s+"
        r"(?:waiting\s+for|on|for|because of|due to)\s+(.+)$",
        re.IGNORECASE,
    ),
    # "X is now in progress" / "X is complete" / "X is blocked"
    re.compile(
        r"^(genesis[-\s]?\d+|[\w][\w\s\-]*?)\s+is\s+(?:now\s+)?"
        r"(in[\s\-]progress|in progress|started|underway|complete|completed|"
        r"done|finished|blocked|waiting|on hold|cancelled|canceled|not started)\.?$",
        re.IGNORECASE,
    ),
    # "The X task is complete"
    re.compile(
        r"^the\s+([\w][\w\s\-]*?)\s+(?:task|feature|sprint|project|genesis)\s+is\s+"
        r"(complete|completed|done|finished|blocked|waiting|in[\s\-]progress|cancelled)\.?$",
        re.IGNORECASE,
    ),
    # "Mark X as complete"
    re.compile(
        r"^mark\s+([\w][\w\s\-]*?)\s+as\s+"
        r"(complete|completed|done|in[\s\-]progress|blocked|waiting|cancelled)\.?$",
        re.IGNORECASE,
    ),
]

# ── Query patterns ─────────────────────────────────────────────────────────────
_QUERY_PATTERNS: list[re.Pattern] = [
    re.compile(r"^how\s+is\s+([\w][\w\s\-]*?)\s+(?:progressing|going|coming along)\??$", re.IGNORECASE),
    re.compile(r"^what(?:'s|\s+is)\s+the\s+(?:progress|status)\s+(?:on|of|for)\s+([\w][\w\s\-]*?)\??$", re.IGNORECASE),
    re.compile(r"^(?:give\s+me\s+)?(?:a\s+)?progress\s+(?:update|report|summary)\s+(?:on|for)\s+([\w][\w\s\-]*?)\??$", re.IGNORECASE),
    re.compile(r"^(?:what(?:'s|\s+is)\s+)?(?:the\s+)?status\s+(?:of|on|for)\s+([\w][\w\s\-]*?)\??$", re.IGNORECASE),
    re.compile(r"^how\s+(?:far|much)\s+(?:through|along)\s+(?:is\s+)?([\w][\w\s\-]*?)\??$", re.IGNORECASE),
]


class ProgressDetector:
    """
    Detects progress update and query commands.
    Deterministic — no AI, no external calls.
    """

    def detect(self, utterance: str) -> Optional[ProgressCommand]:
        text = utterance.strip()

        # Check query patterns first (they're more specific)
        for pattern in _QUERY_PATTERNS:
            m = pattern.match(text)
            if m:
                return ProgressCommand(
                    kind=ProgressCommandKind.QUERY_PROGRESS,
                    subject=_clean(m.group(1)),
                    raw=text,
                )

        # Blocked/waiting with reason (first update pattern)
        blocked_pattern = _UPDATE_PATTERNS[0]
        m = blocked_pattern.match(text)
        if m:
            # Extract subject — everything before "is blocked/waiting"
            bm = re.match(
                r"^(.+?)\s+is\s+(?:blocked|waiting)\s+(?:waiting\s+for|on|for|because of|due to)\s+(.+)$",
                text, re.IGNORECASE
            )
            if bm:
                subject = _clean(bm.group(1))
                blocker = _clean(bm.group(2))
                # Determine state
                state_word = "blocked" if "blocked" in text.lower() else "waiting"
                state = ProgressState.BLOCKED if state_word == "blocked" else ProgressState.WAITING
                return ProgressCommand(
                    kind=ProgressCommandKind.UPDATE_STATE,
                    subject=subject,
                    state=state,
                    blocker=blocker,
                    raw=text,
                )

        # Other update patterns
        for pattern in _UPDATE_PATTERNS[1:]:
            m = pattern.match(text)
            if m:
                subject    = _clean(m.group(1))
                state_word = m.group(2).lower().strip()
                state      = _resolve_state(state_word)
                if state is not None:
                    return ProgressCommand(
                        kind=ProgressCommandKind.UPDATE_STATE,
                        subject=subject,
                        state=state,
                        raw=text,
                    )

        return None


def _clean(s: str) -> str:
    return s.strip().rstrip("?!.,;:")


def _resolve_state(word: str) -> Optional[ProgressState]:
    """Map a state keyword string to a ProgressState."""
    word = word.lower().strip()
    for keyword, state in _STATE_KEYWORDS.items():
        if keyword in word or word in keyword:
            return state
    return None
