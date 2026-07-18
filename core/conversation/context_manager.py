"""
Jarvis Context Manager (Genesis-020 Sprint-002)

Updates the SessionContext from each conversation turn.

Responsibilities:
    - Detect mentions of projects, milestones, tasks, people, topics.
    - Update the appropriate SessionContext slot.
    - Advance the turn counter on every call.
    - Log context changes with [CONTEXT] prefix for easy tracing.

Constitutional constraints:
    - No AI calls. All detection is deterministic regex.
    - No I/O. Pure in-memory.
    - Never modifies the KnowledgeEngine directly.
    - Errors are caught and logged — never propagated.

Integration:
    Called by the Agent AFTER every turn (alongside ConversationObserver).
    Receives both the user message and Jarvis's response so it can
    extract context from either direction.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from core.conversation.session_context import SessionContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Project patterns — "we're starting Genesis-020", "I'm working on Jarvis"
_PROJECT_PATTERNS = [
    re.compile(
        r"\b(?:starting|beginning|working on|building|developing|doing)\s+"
        r"(genesis[- ]?[\d\.]+|jarvis[\w\s]*(?:os)?|sprint[- ]?\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(genesis[- ]?[\d\.]+)\b",
        re.IGNORECASE,
    ),
]

# Milestone patterns — "Genesis-020 is frozen", "we just froze Sprint-001"
_MILESTONE_PATTERNS = [
    re.compile(
        r"\b(genesis[- ]?[\d\.]+(?:\s+sprint[- ]?\d+)?)\s+"
        r"(?:is\s+)?(?:frozen|done|complete|finished|shipped)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:frozen?|completed?|finished?|shipped?)\s+"
        r"(genesis[- ]?[\d\.]+(?:\s+sprint[- ]?\d+)?)",
        re.IGNORECASE,
    ),
]

# Task patterns — "implementing Sprint-002", "Claude is doing Sprint-001"
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
            session: The SessionContext owned by the Agent.
        """
        self._session = session

    def update(self, user_message: str, jarvis_response: str = "") -> None:
        """
        Update session context from a conversation turn.

        Advances the turn counter and detects context from the
        user message. The Jarvis response is reserved for future
        use (e.g. detecting what Jarvis just explained).

        Args:
            user_message:    The user's message.
            jarvis_response: Jarvis's response (not currently used for detection).
        """
        try:
            self._session.increment_turn()
            self._detect_and_update(user_message)
        except Exception:
            logger.exception("[CONTEXT] ContextManager: error updating context.")

    def _detect_and_update(self, text: str) -> None:
        """Detect context mentions and update slots."""
        if not text or not text.strip():
            return

        self._detect_milestone(text)   # milestone before project (more specific)
        self._detect_task(text)        # task before project
        self._detect_project(text)
        self._detect_person(text)
        self._detect_topic(text)

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
                # Use the last capture group (name is always last)
                value = _clean(m.group(m.lastindex or 1))
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