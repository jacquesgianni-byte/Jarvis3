"""
Jarvis Conversation Reference Detector (CV-003)

Detects explicit conversational reference statements and produces a
structured ConversationReference for the Agent to restore active_topic.

Examples recognised:
    "Earlier I mentioned my servers."
    "The servers I told you about."
    "Remember my dogs?"
    "We talked about my cars."
    "I was telling you about my children."
    "Going back to my servers."
    "Back to my dogs."

Responsibilities:
    - Detect conversational reference patterns
    - Extract the entity noun ("servers", "dogs", "cars")
    - Infer entity kind via EntityGroupRegistry
    - Return a ConversationReference if recognised, None otherwise

Does NOT:
    - Update SessionContext directly (Agent does that)
    - Store anything
    - Call AI
    - Handle slot fills or declarations (SlotCompletionEngine owns those)

Architecture position:
    Agent.process() — before Step 4 (SlotCompletionEngine)
        └── ConversationReferenceDetector.detect()   ← this module
                └── EntityGroupRegistry (kind inference)

Design constraints:
    - Stateless — same input → same output
    - Deterministic — no AI calls
    - Generic — works for any registered entity kind
    - Silent — produces no user-facing response directly

CV-003 (Genesis-026 stabilization).
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

from core.conversation.entity_group_registry import EntityGroupRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConversationReference:
    """
    Result of detecting a conversational reference statement.

    The Agent uses this to restore session.active_topic without
    producing a user-facing acknowledgement.

    Attributes:
        entity:     The raw noun extracted ("servers", "dogs", "cars")
        kind:       The canonical entity kind ("server", "animal", "vehicle")
        raw_value:  The active_topic value to restore (e.g. "5 servers")
                    — empty string if only the kind is known, not the count.
        confidence: Detection confidence (0.0–1.0)
    """
    entity:     str
    kind:       str
    raw_value:  str   = ""
    confidence: float = 0.85


# ---------------------------------------------------------------------------
# Reference patterns
#
# Each pattern must capture the entity noun in group 1.
# Ordered from most specific to most general.
# ---------------------------------------------------------------------------

_REFERENCE_PATTERNS: list[re.Pattern] = [
    # "Earlier I mentioned my servers"
    # "Earlier I mentioned my 5 dogs"
    re.compile(
        r"\bearlier\s+i\s+(?:mentioned|talked about|told you about|discussed)\s+"
        r"my\s+(?:\d+\s+)?(\w+)",
        re.IGNORECASE,
    ),
    # "I mentioned my servers earlier"
    re.compile(
        r"\bi\s+(?:mentioned|talked about|told you about|discussed)\s+"
        r"my\s+(?:\d+\s+)?(\w+)\s+earlier",
        re.IGNORECASE,
    ),
    # "Remember my dogs" / "You remember my servers"
    re.compile(
        r"\b(?:you\s+)?remember\s+my\s+(?:\d+\s+)?(\w+)",
        re.IGNORECASE,
    ),
    # "Going back to my servers" / "Back to my dogs"
    re.compile(
        r"\b(?:going\s+)?back\s+to\s+my\s+(?:\d+\s+)?(\w+)",
        re.IGNORECASE,
    ),
    # "We talked about my cars" / "We discussed my servers"
    re.compile(
        r"\bwe\s+(?:talked about|discussed|mentioned)\s+my\s+(?:\d+\s+)?(\w+)",
        re.IGNORECASE,
    ),
    # "I was telling you about my children"
    re.compile(
        r"\bi\s+was\s+(?:telling you about|talking about|discussing)\s+"
        r"my\s+(?:\d+\s+)?(\w+)",
        re.IGNORECASE,
    ),
    # "The servers I told you about" / "The dogs I mentioned"
    re.compile(
        r"\bthe\s+(\w+)\s+i\s+(?:told you about|mentioned|talked about|discussed)",
        re.IGNORECASE,
    ),
    # "What about my servers" / "About my dogs"
    re.compile(
        r"\b(?:what\s+)?about\s+my\s+(?:\d+\s+)?(\w+)",
        re.IGNORECASE,
    ),
]

# Tokens that should never be treated as entity nouns
_STOP_TOKENS: frozenset[str] = frozenset({
    "earlier", "before", "previously", "ago", "that", "this", "those",
    "these", "it", "them", "they", "which", "what", "who", "when",
    "today", "yesterday", "session", "chat", "conversation",
    "time", "day", "week", "month", "year",
    "idea", "thing", "stuff", "point", "topic", "subject",
})


class ConversationReferenceDetector:
    """
    Detects explicit conversational reference statements.

    Called by the Agent before SlotCompletionEngine. When a reference
    is detected, the Agent silently restores session.active_topic and
    continues through the normal pipeline — no acknowledgement is
    produced and the user's follow-up question is answered naturally.

    Public API:
        detect(message) -> Optional[ConversationReference]
    """

    def __init__(self) -> None:
        self._registry = EntityGroupRegistry()

    def detect(self, message: str) -> Optional[ConversationReference]:
        """
        Detect a conversational reference in a user message.

        Args:
            message: The user's raw message.

        Returns:
            ConversationReference if detected, None otherwise.
        """
        if not message or not message.strip():
            return None

        # Questions are not reference restoration statements
        # (e.g. "Remember my dogs?" could be a question or a reference;
        # we handle it as a reference because the "remember my X" pattern
        # is unambiguous enough and the worst case is a silent no-op if
        # the kind is not recognised.)

        for pattern in _REFERENCE_PATTERNS:
            m = pattern.search(message.strip())
            if not m:
                continue

            raw_noun = m.group(1).strip().rstrip("?.!")
            if not raw_noun or raw_noun.lower() in _STOP_TOKENS:
                continue

            # Infer kind from the extracted noun
            kind = self._registry.infer_kind(raw_noun)
            if not kind:
                logger.debug(
                    "[CVREF] Matched pattern but unknown entity kind: %r", raw_noun
                )
                continue

            logger.info(
                "[CVREF] Conversation reference detected: noun=%r kind=%r",
                raw_noun, kind,
            )

            return ConversationReference(
                entity=raw_noun,
                kind=kind,
                raw_value="",   # Agent will look up the stored declaration
                confidence=0.85,
            )

        return None