"""
Decision Intelligence — Detector
Genesis-036 Sprint-001

Detects decision query commands. No AI. Pure pattern matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class DecisionQueryKind(Enum):
    WHAT_NEXT        = auto()   # "What should we do next?"
    CAN_CLOSE        = auto()   # "Can we close Genesis-036?"
    WHY_CANT_CLOSE   = auto()   # "Why can't we close it?"
    BLOCKERS         = auto()   # "Is anything blocking us?"


@dataclass
class DecisionQuery:
    kind:    DecisionQueryKind
    genesis: str = ""     # extracted genesis number, or "" for active
    raw:     str = ""


# ── Pattern sets ───────────────────────────────────────────────────────────────

_WHAT_NEXT_TRIGGERS: frozenset[str] = frozenset({
    "what should we do next",
    "what should i do next",
    "what do we do next",
    "what's next",
    "whats next",
    "what now",
    "next step",
    "next steps",
    "what should we do",
    "what should i do",
    "recommend next action",
    "what is the next action",
    "what is the next step",
})

_CAN_CLOSE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^can\s+(?:we|i)\s+close\s+(?:genesis[-\s]?(\d+)|this|it)\??$", re.IGNORECASE),
    re.compile(r"^(?:is|are)\s+(?:genesis[-\s]?(\d+)|we|this)\s+ready\s+to\s+close\??$", re.IGNORECASE),
    re.compile(r"^(?:is|are)\s+(?:genesis[-\s]?(\d+)|we)\s+ready\??$", re.IGNORECASE),
    re.compile(r"^ready\s+to\s+close\??$", re.IGNORECASE),
    re.compile(r"^can\s+(?:genesis[-\s]?(\d+))\s+be\s+closed\??$", re.IGNORECASE),
]

_WHY_CANT_CLOSE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^why\s+can'?t\s+(?:we|i)\s+close\s+(?:genesis[-\s]?(\d+)|it|this)\??$", re.IGNORECASE),
    re.compile(r"^why\s+(?:is|are)\s+(?:genesis[-\s]?(\d+)|we|this)\s+not\s+ready\??$", re.IGNORECASE),
    re.compile(r"^what'?s?\s+(?:blocking|preventing)\s+(?:us\s+from\s+)?clos(?:ing|ure)\??$", re.IGNORECASE),
    re.compile(r"^why\s+(?:can'?t|cannot)\s+(?:genesis[-\s]?(\d+))\s+close\??$", re.IGNORECASE),
]

_BLOCKER_TRIGGERS: frozenset[str] = frozenset({
    "is anything blocking us",
    "is anything blocking",
    "what's blocking us",
    "whats blocking us",
    "what is blocking us",
    "are we blocked",
    "what are the blockers",
    "show blockers",
    "list blockers",
    "any blockers",
    "blockers",
    "what's in the way",
    "whats in the way",
})


class DecisionDetector:
    """Detects decision query commands. Deterministic — no AI."""

    def detect(self, utterance: str) -> Optional[DecisionQuery]:
        text       = utterance.strip()
        normalised = text.lower().rstrip("?!.")

        # WHAT_NEXT — exact triggers
        if normalised in _WHAT_NEXT_TRIGGERS:
            return DecisionQuery(kind=DecisionQueryKind.WHAT_NEXT, raw=text)

        # BLOCKERS — exact triggers
        if normalised in _BLOCKER_TRIGGERS:
            return DecisionQuery(kind=DecisionQueryKind.BLOCKERS, raw=text)

        # WHY_CANT_CLOSE — patterns (check before CAN_CLOSE)
        for pattern in _WHY_CANT_CLOSE_PATTERNS:
            m = pattern.match(text)
            if m:
                genesis = ""
                if m.lastindex and m.group(1):
                    genesis = m.group(1).zfill(3)
                return DecisionQuery(
                    kind=DecisionQueryKind.WHY_CANT_CLOSE,
                    genesis=genesis,
                    raw=text,
                )

        # CAN_CLOSE — patterns
        for pattern in _CAN_CLOSE_PATTERNS:
            m = pattern.match(text)
            if m:
                genesis = ""
                if m.lastindex and m.group(1):
                    genesis = m.group(1).zfill(3)
                return DecisionQuery(
                    kind=DecisionQueryKind.CAN_CLOSE,
                    genesis=genesis,
                    raw=text,
                )

        return None
