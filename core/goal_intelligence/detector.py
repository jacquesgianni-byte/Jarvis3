"""
Goal & Task Intelligence — Detector
Genesis-033 Sprint-002

Deterministic pattern detection for Goal, Project, and Task declarations
and recall queries. No AI. Pure regex + string matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class DetectionKind(Enum):
    GOAL_DECLARATION    = auto()
    PROJECT_DECLARATION = auto()
    TASK_DECLARATION    = auto()
    GOAL_RECALL         = auto()
    PROJECT_RECALL      = auto()
    TASK_RECALL         = auto()
    STATUS_RECALL       = auto()    # "what am I working on?"


@dataclass
class WorkDetection:
    kind:  DetectionKind
    value: str              # extracted title / empty for pure recall queries


# ── Goal declaration patterns ──────────────────────────────────────────────────
# "My goal is to release Jarvis 1.0"
# "My goal is Jarvis 1.0"
# "I want to release Jarvis 1.0"
# "I'm trying to build a robot"
# "I aim to finish the project"

_GOAL_DECL_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"^my\s+(?:main\s+)?goal\s+is\s+(?:to\s+)?(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:i\s+want|i\s+need|i\s+aim|i\s+plan)\s+to\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:i['']m\s+trying\s+to|i\s+am\s+trying\s+to)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:my\s+objective|my\s+mission|my\s+target)\s+is\s+(?:to\s+)?(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^set\s+(?:my\s+)?goal\s+(?:to|as)\s+(?:to\s+)?(.+)$",
        re.IGNORECASE,
    ),
]

# ── Project declaration patterns ───────────────────────────────────────────────
# "I'm working on Genesis-033"
# "Current project is Genesis-033"
# "I've started Genesis-033"
# "My project is Genesis-033"

_PROJECT_DECL_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"^(?:i['']m|i\s+am)\s+(?:currently\s+)?working\s+on\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:my\s+)?(?:current\s+)?project\s+is\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^i(?:'ve|\s+have)\s+(?:started|begun|kicked\s+off)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:the\s+)?(?:active|current)\s+project\s+is\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:i['']m|i\s+am)\s+(?:now\s+)?on\s+(.+)$",
        re.IGNORECASE,
    ),
]

# ── Task declaration patterns ──────────────────────────────────────────────────
# "Today I'm implementing GoalEngine"
# "I'm implementing GoalEngine"          — more specific than project
# "My task is to write tests"
# "I'm working on implementing GoalEngine"  — has a verb after "on"

_TASK_DECL_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"^today\s+(?:i['']m|i\s+am)\s+(?:implementing|building|writing|fixing|testing|debugging|refactoring|creating|coding|designing)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:i['']m|i\s+am)\s+(?:implementing|building|writing|fixing|testing|debugging|refactoring|creating|coding|designing)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:my\s+)?(?:current\s+)?task\s+is\s+(?:to\s+)?(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:today\s+)?(?:i['']m|i\s+am)\s+working\s+on\s+(?:implementing|building|writing|fixing|testing|debugging|refactoring|creating|coding|designing)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:i['']m|i\s+am)\s+(?:now\s+)?(?:tackling|handling|completing)\s+(.+)$",
        re.IGNORECASE,
    ),
]

# ── Recall query patterns ──────────────────────────────────────────────────────

_GOAL_RECALL_TRIGGERS: frozenset[str] = frozenset({
    "what are my goals",
    "what are my goals?",
    "what is my goal",
    "what is my goal?",
    "what's my goal",
    "what's my goal?",
    "show my goals",
    "list my goals",
    "what goals do i have",
    "what goals do i have?",
    "my goals",
})

_PROJECT_RECALL_TRIGGERS: frozenset[str] = frozenset({
    "what is my current project",
    "what is my current project?",
    "what's my current project",
    "what's my current project?",
    "what project am i on",
    "what project am i working on",
    "current project",
    "my project",
    "my current project",
})

_TASK_RECALL_TRIGGERS: frozenset[str] = frozenset({
    "what is my current task",
    "what is my current task?",
    "what's my current task",
    "what's my current task?",
    "what am i working on today",
    "what am i doing today",
    "what am i doing today?",
    "my current task",
    "my task",
    "current task",
})

_STATUS_RECALL_TRIGGERS: frozenset[str] = frozenset({
    "what am i working on",
    "what am i working on?",
    "what am i doing",
    "what am i doing?",
    "give me a status",
    "give me a status update",
    "status update",
    "my status",
    "where am i",
    "where am i at",
    "show my status",
    "what are we working on",
    "what are we working on?",
})


class WorkDetector:
    """
    Detects Goal, Project, and Task declarations and recall queries.
    Deterministic — no AI, no external calls.

    Detection order (important — prevents misclassification):
      1. STATUS_RECALL    (broadest recall, checked first)
      2. GOAL_RECALL
      3. PROJECT_RECALL
      4. TASK_RECALL
      5. TASK_DECLARATION (checked before project — task patterns are more specific)
      6. PROJECT_DECLARATION
      7. GOAL_DECLARATION
    """

    def detect(self, utterance: str) -> Optional[WorkDetection]:
        """
        Analyse an utterance and return a WorkDetection or None.

        Args:
            utterance: The raw user message.

        Returns:
            WorkDetection if a goal/project/task intent is found, else None.
        """
        normalised = utterance.strip().lower().rstrip("?!.")

        # ── Recall queries (exact match first) ────────────────────────────────
        if normalised in _STATUS_RECALL_TRIGGERS or utterance.strip().lower() in _STATUS_RECALL_TRIGGERS:
            return WorkDetection(kind=DetectionKind.STATUS_RECALL, value="")

        if normalised in _GOAL_RECALL_TRIGGERS or utterance.strip().lower() in _GOAL_RECALL_TRIGGERS:
            return WorkDetection(kind=DetectionKind.GOAL_RECALL, value="")

        if normalised in _PROJECT_RECALL_TRIGGERS or utterance.strip().lower() in _PROJECT_RECALL_TRIGGERS:
            return WorkDetection(kind=DetectionKind.PROJECT_RECALL, value="")

        if normalised in _TASK_RECALL_TRIGGERS or utterance.strip().lower() in _TASK_RECALL_TRIGGERS:
            return WorkDetection(kind=DetectionKind.TASK_RECALL, value="")

        # ── Task declarations (before project — more specific patterns) ────────
        for pattern in _TASK_DECL_PATTERNS:
            m = pattern.match(utterance.strip())
            if m:
                title = _clean_title(m.group(1))
                if title:
                    return WorkDetection(kind=DetectionKind.TASK_DECLARATION, value=title)

        # ── Project declarations ───────────────────────────────────────────────
        for pattern in _PROJECT_DECL_PATTERNS:
            m = pattern.match(utterance.strip())
            if m:
                title = _clean_title(m.group(1))
                if title:
                    return WorkDetection(kind=DetectionKind.PROJECT_DECLARATION, value=title)

        # ── Goal declarations ──────────────────────────────────────────────────
        for pattern in _GOAL_DECL_PATTERNS:
            m = pattern.match(utterance.strip())
            if m:
                title = _clean_title(m.group(1))
                if title:
                    return WorkDetection(kind=DetectionKind.GOAL_DECLARATION, value=title)

        return None


def _clean_title(raw: str) -> str:
    """Strip trailing punctuation and whitespace from an extracted title."""
    return raw.strip().rstrip("?!.,;:")
