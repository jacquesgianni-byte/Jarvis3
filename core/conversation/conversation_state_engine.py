"""
Conversation State Engine (Genesis-029 Sprint-002)

Maintains short-lived conversational context so users don't have to
repeat entity names within a dialogue.

Responsibilities:
    - Track the active entity (last explicitly named subject)
    - Track the active entity group (last declared group)
    - Detect explicit conversation focus changes ("Tell me about X", "What about X")
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
        └── ConversationStateEngine.detect_focus_change()  ← Sprint-002: topic switching
        └── ConversationStateEngine.resolve_pronoun()      ← before property ops
        └── ConversationStateEngine.update_entity()        ← after property assignment

    SessionContext owns the live state slots.
    ConversationStateEngine reads and writes them.

Three-layer model:
    Knowledge          → KnowledgeEngine (persisted, long-term)
    Conversation State → SessionContext  (in-memory, short-lived)   ← this module
    Reasoning          → ReasoningEngine (derives from both)

Genesis-029 Sprint-001: pronoun resolution
Genesis-029 Sprint-002: focus change detection
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
# ---------------------------------------------------------------------------

_SUBJECT_IS_PATTERN = re.compile(
    r"^([A-Z][a-zA-Z\-]*)(?:\s+\w+)*\s+is\b",
    re.IGNORECASE,
)

_SUBJECT_IS_NOW_PATTERN = re.compile(
    r"^([A-Z][a-zA-Z\-]*)\s+is\s+now\b",
    re.IGNORECASE,
)

_SUBJECT_WEIGHS_PATTERN = re.compile(
    r"^([A-Z][a-zA-Z\-]*)\s+weighs?\b",
    re.IGNORECASE,
)

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

_MIN_ENTITY_LEN = 2

# ---------------------------------------------------------------------------
# Focus change patterns (Genesis-029 Sprint-002)
#
# Detect explicit topic/entity switches. Each pattern captures:
#   group 1 = the entity or group name the user is switching to.
#
# Rules:
#   - Only fire on deterministic signals — never guess.
#   - If the capture is a stop word, ignore it.
#   - Group-level switches (my printers, my children) update active_topic.
#   - Entity-level switches (Lucas, Canon, HP) update active_person.
# ---------------------------------------------------------------------------

_FOCUS_ENTITY_PATTERNS: list[re.Pattern] = [
    # "Tell me about Lucas." / "Tell me about Canon."
    re.compile(r"\btell\s+me\s+about\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
    # "What about Chase?" / "What about HP?"
    re.compile(r"\bwhat\s+about\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
    # "Let's talk about Rex." / "Let's focus on Canon."
    re.compile(r"\blet'?s?\s+(?:talk|focus|go)\s+(?:about|on)\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
    # "Back to Lucas." / "Back to HP."
    re.compile(r"\bback\s+to\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
    # "Speaking of Rex." / "Speaking of Canon."
    re.compile(r"\bspeaking\s+of\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
    # "Now, Lucas." / "Now Rex." — bare "now + name" as a topic signal
    re.compile(r"^now[,\s]+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
    # "Focus on HP." / "Switch to Lucas."
    re.compile(r"\b(?:focus|switch)\s+(?:on|to)\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
    # JTI-001 Fix 3b (P5): "Who is Chase?" / "Who is Leo?" -- entity identity queries
    re.compile(r"\bwho\s+is\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
    # JTI-001 Fix 3b (P5): "Who is Chase?" / "Who is Leo?" -- entity identity queries
    re.compile(r"\bwho\s+is\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
]

_FOCUS_GROUP_PATTERNS: list[re.Pattern] = [
    # "Let's talk about my printers." / "Now let's talk about my children."
    re.compile(
        r"\blet'?s?\s+(?:talk|focus|go)\s+(?:about|on)\s+my\s+(\w+)\b",
        re.IGNORECASE,
    ),
    # "Tell me about my dogs." / "Tell me about my children."
    re.compile(
        r"\btell\s+me\s+about\s+my\s+(\w+)\b",
        re.IGNORECASE,
    ),
    # "What about my printers?"
    re.compile(
        r"\bwhat\s+about\s+my\s+(\w+)\b",
        re.IGNORECASE,
    ),
    # "Back to my children." / "Now my printers."
    re.compile(
        r"\b(?:back\s+to|now)\s+my\s+(\w+)\b",
        re.IGNORECASE,
    ),
    # "Speaking of my dogs."
    re.compile(
        r"\bspeaking\s+of\s+my\s+(\w+)\b",
        re.IGNORECASE,
    ),
]

# Stop group words — generic words that aren't meaningful group names
_STOP_GROUPS: frozenset[str] = frozenset({
    "other", "another", "thing", "stuff", "things", "it", "that", "this",
})


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PronounResolution:
    """
    Result of resolving a pronoun in a user message.
    """
    resolved:   bool
    pronoun:    str       = ""
    entity:     str       = ""
    is_plural:  bool      = False
    confidence: float     = 0.0

    @classmethod
    def not_found(cls) -> "PronounResolution":
        return cls(resolved=False)


@dataclass(frozen=True)
class FocusChange:
    """
    Result of detecting a conversation focus change.

    detected:    True if a focus change signal was found.
    entity:      The entity or group name to focus on.
    is_group:    True if this is a group-level switch (my printers).
    confidence:  How confident we are in the detection.
    """
    detected:   bool
    entity:     str   = ""
    is_group:   bool  = False
    confidence: float = 0.0

    @classmethod
    def not_found(cls) -> "FocusChange":
        return cls(detected=False)


# ---------------------------------------------------------------------------
# ConversationStateEngine
# ---------------------------------------------------------------------------

class ConversationStateEngine:
    """
    Maintains conversational context and resolves pronouns deterministically.

    Reads from and writes to SessionContext. Does not own state itself.

    Public API:
        detect_focus_change(text)             — Sprint-002: detect topic switch
        apply_focus_change(change, session)   — Sprint-002: update session state
        update_entity(name, session)          — call after detecting a named entity
        update_group(group_name, session)     — call after detecting a group declaration
        resolve_pronoun(text, session)        — returns PronounResolution
        extract_entity_from_text(text)        — returns entity name or None
        rewrite_with_entity(text, resolution) — replace pronoun with entity name
    """

    # ------------------------------------------------------------------
    # Sprint-002: Focus change detection
    # ------------------------------------------------------------------

    def detect_focus_change(self, text: str) -> FocusChange:
        """
        Detect an explicit conversation focus change signal.

        Matches patterns like:
            "Tell me about Lucas."
            "What about Chase?"
            "Let's talk about my printers."
            "Back to HP."
            "Speaking of Rex."

        Args:
            text: The user's raw message.

        Returns:
            FocusChange — detected=True if a focus change was found.
        """
        if not text or not text.strip():
            return FocusChange.not_found()

        text = text.strip()

        # Check group patterns first (more specific — "my X")
        for pattern in _FOCUS_GROUP_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue
            group_name = m.group(1).strip().lower()
            if group_name in _STOP_GROUPS:
                continue
            if len(group_name) < _MIN_ENTITY_LEN:
                continue
            logger.info("[STATE] Focus change (group) → %r", group_name)
            return FocusChange(
                detected=True,
                entity=group_name,
                is_group=True,
                confidence=0.92,
            )

        # Check entity patterns
        for pattern in _FOCUS_ENTITY_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue
            entity_name = m.group(1).strip()
            if entity_name.lower() in _STOP_SUBJECTS:
                continue
            if len(entity_name) < _MIN_ENTITY_LEN:
                continue
            logger.info("[STATE] Focus change (entity) → %r", entity_name)
            return FocusChange(
                detected=True,
                entity=entity_name,
                is_group=False,
                confidence=0.92,
            )

        return FocusChange.not_found()

    def apply_focus_change(
        self,
        change: FocusChange,
        session: "SessionContext",
    ) -> None:
        """
        Apply a detected focus change to the SessionContext.

        Group changes update active_topic with high confidence.
        Entity changes update active_person with high confidence.
        Genesis-043 Sprint-003: also updates TopicTracker.

        Args:
            change:  A detected FocusChange.
            session: The current SessionContext.
        """
        if not change.detected:
            return

        if change.is_group:
            session.set_topic(change.entity, raw=change.entity, confidence=change.confidence)
            logger.info("[STATE] Focus → group %r", change.entity)
            # Genesis-043 Sprint-003: record in TopicTracker
            self.update_topic(change.entity, session,
                              confidence=change.confidence, explicit=True)
        else:
            session.set_person(change.entity, raw=change.entity, confidence=change.confidence)
            logger.info("[STATE] Focus → entity %r", change.entity)
            # Entity focus change also updates topic tracker
            self.update_topic(change.entity, session,
                              confidence=change.confidence, explicit=True)

    # ------------------------------------------------------------------
    # Sprint-001: Entity / group tracking
    # ------------------------------------------------------------------

    def update_entity(self, name: str, session: "SessionContext") -> None:
        """
        Set the active entity in SessionContext.

        Called whenever a named entity is explicitly mentioned as the
        subject of a statement (property assignment, introduction, etc.)
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
        """
        if not group_name:
            return

        prev = session.active_topic
        session.set_topic(group_name, raw=group_name, confidence=0.90)

        if not prev or prev.value.lower() != group_name.lower():
            logger.info("[STATE] Active group → %r", group_name)

    def update_topic(
        self,
        name:       str,
        session:    "SessionContext",
        confidence: float = 0.65,
        explicit:   bool  = False,
    ) -> None:
        """
        Update the current topic in ConversationState.TopicTracker.

        Genesis-043 Sprint-003: Topic Tracker (PROP-0002).

        Called by:
            apply_focus_change() — explicit topic switch, confidence=0.92
            update_group()       — group declaration, confidence=0.90
            ContextManager       — implicit detection, confidence=0.65

        Args:
            name:       The topic name to set.
            session:    The current SessionContext (or SessionContextAdapter).
            confidence: Topic confidence (use TopicTracker constants).
            explicit:   True if set via an explicit focus-change signal.
        """
        if not name or not name.strip():
            return

        # Resolve ConversationState from the session object
        # Works with both SessionContextAdapter and direct ConversationState
        state = getattr(session, "_s", None) or session
        tracker = getattr(state, "topic_tracker", None)
        if tracker is None:
            logger.debug("[STATE] No topic_tracker on state — skipping topic update")
            return

        # Collect current entity names for drift detection
        entity_registry = getattr(state, "entity_registry", None)
        entity_set: set[str] = set()
        if entity_registry is not None:
            entity_set = {
                e.name for e in entity_registry.active(
                    getattr(state, "current_turn", 0)
                )
            }

        tracker.set(
            name       = name,
            confidence = confidence,
            turn       = getattr(state, "current_turn", 0),
            explicit   = explicit,
            entity_set = entity_set,
        )

    def detect_implicit_topic_shift(
        self,
        session:      "SessionContext",
        new_entities: set[str],
    ) -> bool:
        """
        Detect whether a topic shift has occurred implicitly.

        Compares the active entity set in the current turn against the
        entity set recorded when the current topic was set. Low overlap
        suggests the conversation has drifted to a new topic.

        Genesis-043 Sprint-003.
        """
        state   = getattr(session, "_s", None) or session
        tracker = getattr(state, "topic_tracker", None)
        if tracker is None:
            return False
        current_turn = getattr(state, "current_turn", 0)
        return tracker.detect_shift(new_entities, current_turn)

    # ------------------------------------------------------------------
    # Sprint-001: Pronoun resolution
    # ------------------------------------------------------------------

    def resolve_pronoun(
        self,
        text: str,
        session: "SessionContext",
    ) -> PronounResolution:
        """
        Detect and resolve a pronoun in the user's message.

        Checks for singular pronouns (he/she/it) → active_person
        Checks for plural pronouns (they/their) → active_topic
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
        """
        if not text or not text.strip():
            return None

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
        """
        if not resolution.resolved:
            return text

        pattern = re.compile(
            rf"\b{re.escape(resolution.pronoun)}\b",
            re.IGNORECASE,
        )
        rewritten = pattern.sub(resolution.entity, text, count=1)
        logger.debug("[STATE] Rewritten: %r → %r", text, rewritten)
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