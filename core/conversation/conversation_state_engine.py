"""
Conversation State Engine (Genesis-029 Sprint-001)

Maintains short-lived conversational context so users don't have to
repeat entity names within a dialogue.

Responsibilities:
    - Track the active entity (last explicitly named subject)
    - Track the active entity group (last declared group)
    - Resolve pronouns (he, she, it, they, their) deterministically
    - Expire stale context naturally via SessionContext decay

Design constraints:
    - No AI calls
    - No KnowledgeEngine reads or writes
    - No PropertyAssigner / PropertyRecallEngine dependency
    - Stateless resolver — all state lives in SessionContext
    - Generic — no person-, pet-, or device-specific logic
    - Deterministic — same input + same context → same output

Architecture position:
    Agent._route()
        └── ConversationStateEngine.resolve_pronouns()  ← before property ops
        └── ConversationStateEngine.update_from_text()  ← after each turn

    SessionContext owns the live state slots.
    ConversationStateEngine reads and writes them.

Three-layer model:
    Knowledge          → KnowledgeEngine (persisted, long-term)
    Conversation State → SessionContext  (in-memory, short-lived)   ← this module
    Reasoning          → ReasoningEngine (derives from both)

Genesis-029 Sprint-001.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.session_context import SessionContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pronoun sets
# ---------------------------------------------------------------------------

# Singular — resolves to active_entity
_SINGULAR_PRONOUNS: frozenset[str] = frozenset({
    "he", "him", "his",
    "she", "her", "hers",
    "it", "its",
})

# Plural — resolves to active_group
_PLURAL_PRONOUNS: frozenset[str] = frozenset({
    "they", "them", "their", "theirs",
})

_ALL_PRONOUNS: frozenset[str] = _SINGULAR_PRONOUNS | _PLURAL_PRONOUNS

# ---------------------------------------------------------------------------
# Entity detection patterns
#
# Detects the subject of a statement so we can track the active entity.
# Intentionally broad — we want to catch property assignments, introductions,
# and bare declarations.
# ---------------------------------------------------------------------------

# "Rex is brown." / "Leo is 9." / "Canon is offline."
_SUBJECT_IS_PATTERN = re.compile(
    r"^([A-Z][a-zA-Z\-]*)(?:\s+\w+)*\s+is\b",
    re.IGNORECASE,
)

# "Leo is now 9." / "Rex is now online."
_SUBJECT_IS_NOW_PATTERN = re.compile(
    r"^([A-Z][a-zA-Z\-]*)\s+is\s+now\b",
    re.IGNORECASE,
)

# "Rex weighs 35 kg."
_SUBJECT_WEIGHS_PATTERN = re.compile(
    r"^([A-Z][a-zA-Z\-]*)\s+weighs?\b",
    re.IGNORECASE,
)

# "He likes football." / "She plays piano." — after pronoun resolution
# Used to detect subject from a resolved sentence, not needed here.

# Stop words — never treat these as entity names
_STOP_SUBJECTS: frozenset[str] = frozenset({
    "he", "she", "it", "they", "we", "i", "you",
    "that", "this", "there", "here",
    "my", "your", "his", "her", "their", "our",
    "a", "an", "the",
    "what", "who", "where", "when", "why", "how",
    "jarvis", "ok", "okay", "yes", "no",
    "how", "which", "is", "are", "was", "were",
})

# Minimum entity name length
_MIN_ENTITY_LEN = 2


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PronounResolution:
    """
    Result of resolving a pronoun in a user message.

    resolved:       True if the pronoun was successfully resolved.
    pronoun:        The original pronoun that was found ("he", "it", etc.)
    entity:         The resolved entity name (e.g. "Leo", "Canon")
    is_plural:      True if pronoun refers to a group
    confidence:     How confident we are in the resolution
    """
    resolved:   bool
    pronoun:    str       = ""
    entity:     str       = ""
    is_plural:  bool      = False
    confidence: float     = 0.0

    @classmethod
    def not_found(cls) -> "PronounResolution":
        return cls(resolved=False)


# ---------------------------------------------------------------------------
# ConversationStateEngine
# ---------------------------------------------------------------------------

class ConversationStateEngine:
    """
    Maintains conversational context and resolves pronouns deterministically.

    Reads from and writes to SessionContext. Does not own state itself.
    Injected with SessionContext at construction time.

    Public API:
        update_entity(name, session)          — call after detecting a named entity
        update_group(group_name, session)     — call after detecting a group declaration
        resolve_pronoun(text, session)        — returns PronounResolution
        extract_entity_from_text(text)        — returns entity name or None
    """

    def update_entity(self, name: str, session: "SessionContext") -> None:
        """
        Set the active entity in SessionContext.

        Called whenever a named entity is explicitly mentioned as the
        subject of a statement (property assignment, introduction, etc.)

        Args:
            name:    The entity name (e.g. "Leo", "Rex", "Canon")
            session: The current SessionContext
        """
        if not name or name.lower() in _STOP_SUBJECTS:
            return
        if len(name) < _MIN_ENTITY_LEN:
            return

        prev = session.active_person
        session.set_person(name, raw=name, confidence=0.95)

        if not prev or prev.value.lower() != name.lower():
            logger.info("[STATE] Active entity → %r", name)

    def update_group(self, group_name: str, session: "SessionContext") -> None:
        """
        Set the active group in SessionContext.

        Called after a group declaration ("I have 3 dogs.") so that
        plural pronouns ("they", "their") resolve correctly.

        Args:
            group_name: The group description (e.g. "3 dogs", "2 children")
            session:    The current SessionContext
        """
        if not group_name:
            return

        prev = session.active_topic
        session.set_topic(group_name, raw=group_name, confidence=0.90)

        if not prev or prev.value.lower() != group_name.lower():
            logger.info("[STATE] Active group → %r", group_name)

    def resolve_pronoun(
        self,
        text: str,
        session: "SessionContext",
    ) -> PronounResolution:
        """
        Detect and resolve a pronoun in the user's message.

        Checks for singular pronouns (he/she/it) → active_person
        Checks for plural pronouns (they/their) → active_topic

        Args:
            text:    The user's raw message.
            session: The current SessionContext.

        Returns:
            PronounResolution — resolved=True if a pronoun was found and
            an entity could be determined.
        """
        if not text or not text.strip():
            return PronounResolution.not_found()

        text_lower = text.lower().strip()
        words = set(re.findall(r"\b\w+\b", text_lower))

        # Check for singular pronouns
        found_singular = words & _SINGULAR_PRONOUNS
        if found_singular:
            pronoun = next(iter(found_singular))
            entity = self._resolve_singular(session)
            if entity:
                logger.info(
                    "[STATE] Resolved pronoun %r → %r (conf=%.2f)",
                    pronoun, entity, session.effective_confidence(session.active_person),
                )
                return PronounResolution(
                    resolved=True,
                    pronoun=pronoun,
                    entity=entity,
                    is_plural=False,
                    confidence=session.effective_confidence(session.active_person),
                )

        # Check for plural pronouns
        found_plural = words & _PLURAL_PRONOUNS
        if found_plural:
            pronoun = next(iter(found_plural))
            entity = self._resolve_plural(session)
            if entity:
                logger.info(
                    "[STATE] Resolved pronoun %r → %r (conf=%.2f)",
                    pronoun, entity, session.effective_confidence(session.active_topic),
                )
                return PronounResolution(
                    resolved=True,
                    pronoun=pronoun,
                    entity=entity,
                    is_plural=True,
                    confidence=session.effective_confidence(session.active_topic),
                )

        return PronounResolution.not_found()

    def extract_entity_from_text(self, text: str) -> Optional[str]:
        """
        Extract the subject entity name from a statement.

        Detects the named subject of "X is Y", "X weighs Y" etc.
        Returns None if no valid entity name found.

        Args:
            text: The user's raw message.

        Returns:
            Entity name string or None.
        """
        if not text or not text.strip():
            return None

        # Questions never introduce a new subject
        if text.strip().endswith("?"):
            return None

        for pattern in [
            _SUBJECT_IS_NOW_PATTERN,
            _SUBJECT_WEIGHS_PATTERN,
            _SUBJECT_IS_PATTERN,
        ]:
            m = pattern.match(text.strip())
            if m:
                candidate = m.group(1).strip()
                if (candidate.lower() not in _STOP_SUBJECTS
                        and len(candidate) >= _MIN_ENTITY_LEN):
                    return candidate

        return None

    def rewrite_with_entity(self, text: str, resolution: PronounResolution) -> str:
        """
        Replace the pronoun in text with the resolved entity name.

        Used to rewrite "What colour is he?" → "What colour is Rex?"
        before passing to PropertyAssigner or PropertyRecallEngine.

        Args:
            text:       The original user message.
            resolution: A successful PronounResolution.

        Returns:
            Rewritten text with pronoun replaced by entity name.
        """
        if not resolution.resolved:
            return text

        # Replace pronoun with entity name (case-insensitive, whole word)
        pattern = re.compile(
            rf"\b{re.escape(resolution.pronoun)}\b",
            re.IGNORECASE,
        )
        rewritten = pattern.sub(resolution.entity, text, count=1)
        logger.debug(
            "[STATE] Rewritten: %r → %r",
            text, rewritten,
        )
        return rewritten

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_singular(self, session: "SessionContext") -> Optional[str]:
        """Resolve a singular pronoun to the active entity name."""
        slot = session.fresh(session.active_person)
        if slot is not None:
            return slot.value
        return None

    def _resolve_plural(self, session: "SessionContext") -> Optional[str]:
        """Resolve a plural pronoun to the active group name."""
        slot = session.fresh(session.active_topic)
        if slot is not None:
            return slot.value
        return None