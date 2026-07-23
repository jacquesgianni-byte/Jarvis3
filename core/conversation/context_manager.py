"""
Jarvis Context Manager (Genesis-020 Sprint-002)

Updates the active SessionContext slots after each conversation turn.

Responsibilities:
    - Scan the user message for context signals
    - Update SessionContext slots (project, milestone, task, person, topic)
    - Increment the turn counter
    - Log context changes for debugging

Design constraints:
    - No AI calls
    - No external services
    - No KnowledgeEngine writes (that is ConversationObserver's job)
    - Pure slot-filling — does not decide how slots are used downstream

Architecture position:
    Agent._post_turn()
        └── ContextManager.update()   ← this module
                └── SessionContext    (writes active slots)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from core.conversation.session_context import SessionContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Project patterns — "I'm building Jarvis", "we're working on Genesis-020"
_PROJECT_PATTERNS = [
    re.compile(
        r"\b(?:building|working on|developing|shipping|releasing)\s+"
        r"(genesis[- ]?\d+(?:[-.]\d+)?|jarvis\s*\w*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:starting|beginning|kicking off)\s+"
        r"(genesis[- ]?\d+(?:[-.]\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(genesis[- ]?\d+(?:[-.]\d+)?)\s+is\s+(?:next|current|active|live)",
        re.IGNORECASE,
    ),
]

# Milestone patterns — "we finished Genesis-019", "Genesis-019 is frozen"
_MILESTONE_PATTERNS = [
    re.compile(
        r"\b(?:finished|completed|frozen?|shipped|released|closed|done with)\s+"
        r"(genesis[- ]?\d+(?:[-.]\d+)?(?:\s+sprint[- ]?\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(genesis[- ]?\d+(?:[-.]\d+)?(?:\s+sprint[- ]?\d+)?)\s+"
        r"(?:is\s+)?(?:done|complete|finished|frozen|locked|passed|closed)",
        re.IGNORECASE,
    ),
]

# Task patterns — "implementing Sprint-002", "doing Sprint-002"
# Narrow: only matches sprint identifiers to avoid matching project names
_TASK_PATTERNS = [
    re.compile(
        r"\b(?:implement(?:ing)?|doing|building|working on|starting)\s+"
        r"(sprint[- ]?\d+|sprint[- ]?\d+[- ]\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(sprint[- ]?\d+)\b",
        re.IGNORECASE,
    ),
]

# Person patterns — named capitalised words (not Jarvis itself)
_PERSON_PATTERNS = [
    re.compile(
        r"\b(Claude|GPT|ChatGPT|Anthropic|OpenAI|Gianni|Ludovic)\b",
        re.IGNORECASE,
    ),
    # "my engineer/architect/partner is X"
    re.compile(
        r"\bmy\s+(?:engineer|architect|partner|assistant|senior|colleague)\s+is\s+([A-Z][a-z]+)",
        re.IGNORECASE,
    ),
    # "X is my engineer/architect"
    re.compile(
        r"\b([A-Z][a-z]+)\s+is\s+my\s+(?:engineer|architect|partner|assistant|senior|colleague)\b",
        re.IGNORECASE,
    ),
]

# Topic patterns — engineering concepts, patterns, anti-patterns
_TOPIC_PATTERNS = [
    re.compile(
        r"\b(?:the\s+)?(\w+\s+(?:pattern|anti-pattern|principle|architecture))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:explaining?|discussing?|talking about|looking at)\s+(.+?)(?:\.|$)",
        re.IGNORECASE,
    ),
]

# Pet patterns for GC-009 pronoun resolution
# Enables "they/them/it" to resolve after pet statements
_PET_PATTERNS = [
    # "I have 2 dogs" / "I have a cat" — two capture groups (count + animal)
    re.compile(
        r"\bi(?:'ve| have| got|'ve got)\s+(\d+|a|an|some|two|three|four|five)\s+([a-z]+s?)",
        re.IGNORECASE,
    ),
    # "Their names are Rex and Tom"
    re.compile(r"\b(?:their|his|her|its)\s+names?\s+(?:is|are)\s+(.+)", re.IGNORECASE),
    # "My dogs are Rex and Tom"
    re.compile(
        r"\bmy\s+(?:dogs?|cats?|pets?|birds?|fish|rabbits?|hamsters?)\s+(?:is|are)\s+(.+)",
        re.IGNORECASE,
    ),
]

# Noise values that should not be set as context
_NOISE = {
    "it", "that", "this", "them", "something", "anything",
    "everything", "nothing", "more", "some", "the",
    "me", "you", "us", "we", "i", "my", "your", "jarvis",
}


def _clean(value: str) -> str:
    return value.strip().rstrip(".,;:!?").strip()


def _is_noise(value: str) -> bool:
    return not value or len(value) < 2 or value.lower() in _NOISE


class ContextManager:
    """
    Updates the SessionContext from each conversation turn.

    Called once per turn by the Agent. Detects what the conversation
    is about and updates the appropriate slots in the SessionContext.
    """

    def __init__(self, session: SessionContext):
        """
        Args:
            session: The SessionContext to update. Shared with the
                     ContextResolver and ContextInspector.
        """
        self._session = session

    def update(self, user_message: str, jarvis_response: str = "") -> None:
        """
        Process one conversation turn and update the SessionContext.

        Args:
            user_message:    The raw user message for this turn.
            jarvis_response: The response Jarvis produced (currently
                             unused — reserved for response-based context
                             extraction in a future sprint).
        """
        self._session.increment_turn()

        if not user_message or not user_message.strip():
            return

        self._detect_and_update(user_message)

    def _detect_and_update(self, text: str) -> None:
        """Detect context mentions and update slots."""
        if not text or not text.strip():
            return

        self._detect_milestone(text)   # milestone before project (more specific)
        self._detect_task(text)        # task before project
        self._detect_project(text)
        self._detect_person(text)
        self._detect_topic(text)
        self._detect_pet(text)         # GC-009: pronoun resolution for pets

        logger.debug("[CONTEXT] Turn %d: %s", self._session.current_turn,
                     self._session.summary())

    def _detect_project(self, text: str) -> None:
        for pattern in _PROJECT_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean(m.group(1))
                if not _is_noise(value):
                    prev = self._session.active_project
                    self._session.set_project(value, raw=text)
                    if not prev or prev.value.lower() != value.lower():
                        logger.info("[CONTEXT] Active project → %r", value)
                    return

    def _detect_milestone(self, text: str) -> None:
        for pattern in _MILESTONE_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean(m.group(1))
                if not _is_noise(value):
                    prev = self._session.active_milestone
                    self._session.set_milestone(value, raw=text)
                    if not prev or prev.value.lower() != value.lower():
                        logger.info("[CONTEXT] Active milestone → %r", value)
                    return

    def _detect_task(self, text: str) -> None:
        for pattern in _TASK_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean(m.group(1))
                if not _is_noise(value):
                    prev = self._session.active_task
                    self._session.set_task(value, raw=text)
                    if not prev or prev.value.lower() != value.lower():
                        logger.info("[CONTEXT] Active task → %r", value)
                    return

    def _detect_person(self, text: str) -> None:
        for pattern in _PERSON_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean(m.group(1))
                if not _is_noise(value):
                    prev = self._session.active_person
                    self._session.set_person(value, raw=text)
                    if not prev or prev.value.lower() != value.lower():
                        logger.info("[CONTEXT] Active person → %r", value)
                    return

    def _detect_topic(self, text: str) -> None:
        for pattern in _TOPIC_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean(m.group(1))
                if not _is_noise(value) and len(value) > 3:
                    prev = self._session.active_topic
                    self._session.set_topic(value, raw=text)
                    if not prev or prev.value.lower() != value.lower():
                        logger.info("[CONTEXT] Active topic → %r", value)
                    return

    def _detect_pet(self, text: str) -> None:
        """
        GC-009: Set active_topic from pet facts so generic pronouns
        (they/them/it) resolve correctly in the next turn.

        Covers:
            "I have 2 dogs"               → topic = "2 dogs"
            "Their names are Rex and Tom" → topic = "Rex and Tom"
            "My dogs are Rex and Tom"     → topic = "Rex and Tom"
        """
        # Pattern 0: "I have 2 dogs" — two capture groups (count + animal)
        m = _PET_PATTERNS[0].search(text)
        if m:
            value = _clean(f"{m.group(1)} {m.group(2)}")
            if not _is_noise(value) and len(value) > 1:
                prev = self._session.active_topic
                self._session.set_topic(value, raw=text)
                if not prev or prev.value.lower() != value.lower():
                    logger.info("[CONTEXT] Active topic (pet) → %r", value)
                return

        # Patterns 1+: single capture group
        for pattern in _PET_PATTERNS[1:]:
            m = pattern.search(text)
            if m:
                value = _clean(m.group(1))
                if not _is_noise(value) and len(value) > 1:
                    prev = self._session.active_topic
                    self._session.set_topic(value, raw=text)
                    if not prev or prev.value.lower() != value.lower():
                        logger.info("[CONTEXT] Active topic (pet) → %r", value)
                    return