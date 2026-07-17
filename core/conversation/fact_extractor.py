"""
Jarvis Conversation Memory — Fact Extractor (Genesis-020 Sprint-001)

Deterministic pattern-based extraction of facts from natural language.

Constitutional constraints:
    - No LLM calls. All extraction is deterministic regex.
    - No external services.
    - Returns structured ExtractedFact objects only.
    - Never modifies any storage directly.

Extraction targets:
    - Projects:      "I'm building Jarvis", "we're working on Genesis-020"
    - Milestones:    "we finished Engineering Academy", "Genesis-019 is frozen"
    - People:        "Claude is my senior engineer", "GPT handles specs"
    - Current tasks: "we're starting Genesis-020", "I'm starting sprint 001"
    - Decisions:     "we decided to use Flask", "I chose to use Tavily"
    - Achievements:  "we completed 529 tests", "Genesis-019 passed"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Optional


class FactType(Enum):
    PROJECT     = auto()   # ongoing project or work
    MILESTONE   = auto()   # completed or frozen milestone
    PERSON      = auto()   # named person and their role/relationship
    TASK        = auto()   # current or upcoming task
    DECISION    = auto()   # a decision made
    ACHIEVEMENT = auto()   # something completed or accomplished
    PREFERENCE  = auto()   # a stated preference or like/dislike
    UNKNOWN     = auto()   # could not be classified


@dataclass(frozen=True)
class ExtractedFact:
    """A single fact extracted from a user message."""
    fact_type:  FactType
    subject:    str          # who/what the fact is about ("user", "claude", "jarvis")
    attribute:  str          # the property ("current project", "role", "milestone")
    value:      str          # the value ("Jarvis OS", "senior engineer", "Genesis-019")
    confidence: float = 0.8  # extraction confidence (0.0–1.0)
    raw:        str = ""     # original text that triggered extraction
    extracted_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )


# ---------------------------------------------------------------------------
# Extraction patterns
# Each tuple: (regex, handler_name)
# Handlers return Optional[ExtractedFact]
# ---------------------------------------------------------------------------

_PROJECT_PATTERNS = [
    re.compile(r"\bi(?:'m| am) (?:building|working on|developing|creating|making)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bwe(?:'re| are) (?:building|working on|developing|creating|making)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bmy (?:project|app|system|platform|tool)\s+is\s+(.+)", re.IGNORECASE),
    re.compile(r"\bour (?:project|app|system|platform|tool)\s+is\s+(.+)", re.IGNORECASE),
]

_MILESTONE_PATTERNS = [
    re.compile(r"\bwe(?:'ve| have)?\s+(?:just\s+)?(?:finished|completed|frozen?|shipped|released)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi(?:'ve| have)\s+(?:just\s+)?(?:finished|completed|frozen?|shipped|released)\s+(.+)", re.IGNORECASE),
    re.compile(r"\b(.+?)\s+is\s+(?:done|complete|finished|frozen|locked)", re.IGNORECASE),
    re.compile(r"\b(genesis[- ]?[\d\.]+)\s+(?:is\s+)?(?:done|complete|finished|frozen|locked|passed)", re.IGNORECASE),
    re.compile(r"\btoday\s+we\s+(?:finished|completed|shipped)\s+(.+)", re.IGNORECASE),
]

_PERSON_PATTERNS = [
    # "Claude is my senior engineer" → person=Claude, role=senior engineer
    re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+is\s+my\s+(.+)", re.IGNORECASE),
    # "my senior engineer is Claude"
    re.compile(r"\bmy\s+(.+?)\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.IGNORECASE),
    # "GPT handles specs" → person=GPT, role=handles specs
    re.compile(r"\b(GPT|ChatGPT|Claude|Anthropic|OpenAI)\s+(?:handles|manages|does|owns)\s+(.+)", re.IGNORECASE),
]

_TASK_PATTERNS = [
    re.compile(r"\bwe(?:'re| are) (?:starting|beginning|kicking off|about to start)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am) (?:starting|beginning|kicking off|about to start)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bnext(?:\s+up)?\s+(?:is\s+)?(.+)", re.IGNORECASE),
    re.compile(r"\bstarting\s+(genesis[- ]?[\d\.]+)", re.IGNORECASE),
]

_DECISION_PATTERNS = [
    re.compile(r"\bwe\s+decided\s+to\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi\s+decided\s+to\s+(.+)", re.IGNORECASE),
    re.compile(r"\bwe(?:'ve| have)\s+decided\s+to\s+(.+)", re.IGNORECASE),
    re.compile(r"\bthe\s+decision\s+is\s+(.+)", re.IGNORECASE),
    re.compile(r"\bwe(?:'re| are)\s+going\s+to\s+use\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi\s+chose\s+(?:to\s+use\s+)?(.+)", re.IGNORECASE),
]

_ACHIEVEMENT_PATTERNS = [
    re.compile(r"\bwe(?:'ve| have)\s+(?:built|implemented|created|added|written)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi(?:'ve| have)\s+(?:built|implemented|created|added|written)\s+(.+)", re.IGNORECASE),
    re.compile(r"\b(\d+)\s+tests?\s+(?:are\s+)?(?:passing|passed|green)", re.IGNORECASE),
]

# Noise words that indicate an extraction isn't useful
_NOISE_VALUES = {
    "it", "that", "this", "them", "something", "anything",
    "everything", "nothing", "a lot", "more", "some", "the",
    "me", "you", "us", "we", "i", "my", "your",
}


def _clean_value(value: str) -> str:
    """Strip trailing punctuation and whitespace from an extracted value."""
    return value.strip().rstrip(".,;:!?").strip()


def _is_noise(value: str) -> bool:
    """Return True if the extracted value is too generic to be useful."""
    cleaned = value.lower().strip()
    return len(cleaned) < 2 or cleaned in _NOISE_VALUES


class FactExtractor:
    """
    Deterministic fact extractor for natural language conversation.

    Applies ordered regex patterns to extract structured facts.
    Returns a list of ExtractedFact objects — never modifies storage.

    Designed to be called on every user message in the conversation.
    Fast enough for synchronous use (no I/O, no LLM, pure regex).
    """

    def extract(self, text: str) -> list[ExtractedFact]:
        """
        Extract all facts from a single text message.

        Args:
            text: The user's message.

        Returns:
            A list of ExtractedFact objects. May be empty.
        """
        if not text or not text.strip():
            return []

        facts: list[ExtractedFact] = []

        facts.extend(self._extract_projects(text))
        facts.extend(self._extract_milestones(text))
        facts.extend(self._extract_people(text))
        facts.extend(self._extract_tasks(text))
        facts.extend(self._extract_decisions(text))
        facts.extend(self._extract_achievements(text))

        # Deduplicate by (attribute, value)
        seen: set[tuple[str, str]] = set()
        unique: list[ExtractedFact] = []
        for fact in facts:
            key = (fact.attribute.lower(), fact.value.lower())
            if key not in seen:
                seen.add(key)
                unique.append(fact)

        return unique

    # ------------------------------------------------------------------
    # Extraction methods
    # ------------------------------------------------------------------

    def _extract_projects(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _PROJECT_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.PROJECT,
                        subject="user",
                        attribute="current project",
                        value=value,
                        confidence=0.85,
                        raw=text,
                    ))
                    break  # one project per message
        return facts

    def _extract_milestones(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _MILESTONE_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.MILESTONE,
                        subject="user",
                        attribute="last milestone",
                        value=value,
                        confidence=0.80,
                        raw=text,
                    ))
                    break
        return facts

    def _extract_people(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _PERSON_PATTERNS:
            m = pattern.search(text)
            if m:
                # Pattern 1: "Claude is my senior engineer"
                # group(1)=Claude, group(2)=senior engineer
                name = _clean_value(m.group(1))
                role = _clean_value(m.group(2))
                if not _is_noise(name) and not _is_noise(role):
                    # Store as: subject=name.lower(), attribute="role", value=role
                    facts.append(ExtractedFact(
                        fact_type=FactType.PERSON,
                        subject=name.lower(),
                        attribute="role",
                        value=role,
                        confidence=0.85,
                        raw=text,
                    ))
                    # Also store relationship from user's perspective
                    facts.append(ExtractedFact(
                        fact_type=FactType.PERSON,
                        subject="user",
                        attribute=f"{name.lower()} role",
                        value=role,
                        confidence=0.85,
                        raw=text,
                    ))
        return facts

    def _extract_tasks(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _TASK_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.TASK,
                        subject="user",
                        attribute="current task",
                        value=value,
                        confidence=0.80,
                        raw=text,
                    ))
                    break
        return facts

    def _extract_decisions(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _DECISION_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.DECISION,
                        subject="user",
                        attribute="recent decision",
                        value=value,
                        confidence=0.75,
                        raw=text,
                    ))
                    break
        return facts

    def _extract_achievements(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _ACHIEVEMENT_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.ACHIEVEMENT,
                        subject="user",
                        attribute="recent achievement",
                        value=value,
                        confidence=0.75,
                        raw=text,
                    ))
                    break
        return facts