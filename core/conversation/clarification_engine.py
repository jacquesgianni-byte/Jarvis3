"""
Clarification Engine (Genesis-029 Sprint-003)

Detects ambiguous pronoun references and generates deterministic
clarification questions when multiple equally-valid candidates exist.

Responsibilities:
    - Detect when a pronoun could refer to multiple recent entities
    - Generate a natural clarification question
    - Track pending clarification state
    - Resume the original request once the user clarifies

Design constraints:
    - No AI calls
    - No KnowledgeEngine reads or writes
    - Deterministic — same input + same context → same output
    - Only fires when ambiguity is genuine (two+ candidates at similar confidence)
    - Never fires when ConversationStateEngine has a clear focus set explicitly

Architecture position:
    Agent._route()
        └── ClarificationEngine.check()   ← before pronoun resolution
        └── ClarificationEngine.resolve() ← when user replies to clarification

    ConversationStateEngine → focus (explicit)
    ClarificationEngine    → ambiguity (implicit, multiple candidates)

    These two never conflict:
        - Explicit focus (detect_focus_change) → no clarification needed
        - Implicit last-entity tracking → clarification possible if ambiguous

Genesis-029 Sprint-003.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.session_context import SessionContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pronoun triggers
#
# Only these pronouns trigger ambiguity checking.
# Possessives (his/her) and plurals (they/their) are lower priority.
# ---------------------------------------------------------------------------

_AMBIGUOUS_SINGULAR: frozenset[str] = frozenset({
    "he", "she", "it", "him", "her", "his",
})

_AMBIGUOUS_PATTERN = re.compile(
    r"\b(?:he|she|it|him|her|his)\b",
    re.IGNORECASE,
)

# Confidence similarity threshold:
# If two candidates' effective confidence differs by less than this,
# they are considered equally valid and clarification is needed.
_SIMILARITY_THRESHOLD: float = 0.25

# Minimum confidence for a candidate to be considered valid
_MIN_CANDIDATE_CONFIDENCE: float = 0.20


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClarificationNeeded:
    """
    Signals that clarification is required before proceeding.

    candidates:       List of entity names to choose from.
    question:         Natural language clarification question.
    original_request: The user's original message, preserved for resumption.
    pronoun:          The pronoun that triggered the ambiguity.
    """
    candidates:       list[str]
    question:         str
    original_request: str
    pronoun:          str
    confidence:       float = 1.0


@dataclass
class PendingClarification:
    """
    Mutable state tracking an outstanding clarification request.

    Stored on the Agent between turns.
    Cleared once the user resolves it or after timeout.
    """
    candidates:       list[str]
    original_request: str
    pronoun:          str
    question:         str
    resolved:         bool = False
    resolved_entity:  str = ""


@dataclass(frozen=True)
class ClarificationResolution:
    """
    Result of attempting to resolve a pending clarification.

    resolved:        True if the user's reply matched a candidate.
    entity:          The resolved entity name.
    rewritten:       The original request rewritten with the entity name.
    """
    resolved:  bool
    entity:    str = ""
    rewritten: str = ""


# ---------------------------------------------------------------------------
# ClarificationEngine
# ---------------------------------------------------------------------------

class ClarificationEngine:
    """
    Detects ambiguous pronoun references and manages clarification flow.

    Stateless detection logic. Pending clarification state is stored
    externally (on the Agent) as a PendingClarification instance.

    Public API:
        check(text, candidates, session)  → Optional[ClarificationNeeded]
        try_resolve(text, pending)        → ClarificationResolution
        build_question(candidates)        → str
    """

    def check(
        self,
        text: str,
        candidates: list[str],
        session: "SessionContext",
        explicit_focus: bool = False,
    ) -> Optional[ClarificationNeeded]:
        """
        Check if a pronoun reference is ambiguous given the candidate list.
        """
        if not text or not text.strip():
            return None

        # Never clarify if focus was explicitly set this turn
        if explicit_focus:
            return None

        # Only trigger on ambiguous pronouns
        if not _AMBIGUOUS_PATTERN.search(text):
            return None

        pronoun_match = _AMBIGUOUS_PATTERN.search(text)
        pronoun = pronoun_match.group(0).lower() if pronoun_match else ""

        # Need at least 2 candidates to be ambiguous
        if len(candidates) < 2:
            return None

        # If we have 2+ explicitly tracked recent entities and a pronoun,
        # always ask — we never guess when multiple entities are in play.
        # Use the two most recent entities (end of list).
        recent_two = candidates[-2:]
        question = self.build_question(recent_two)
        logger.info(
            "[CLARIFY] Ambiguous pronoun %r — candidates: %r",
            pronoun, recent_two,
        )

        return ClarificationNeeded(
            candidates=recent_two,
            question=question,
            original_request=text,
            pronoun=pronoun,
        )

    def try_resolve(
        self,
        text: str,
        pending: PendingClarification,
    ) -> ClarificationResolution:
        """
        Attempt to resolve a pending clarification from the user's reply.

        Matches the user's reply against the pending candidates.
        Case-insensitive. Partial matches accepted (e.g. "leo" matches "Leo").

        Args:
            text:    The user's reply message.
            pending: The outstanding PendingClarification.

        Returns:
            ClarificationResolution — resolved=True if a match was found.
        """
        if not text or not text.strip():
            return ClarificationResolution(resolved=False)

        text_clean = text.strip().rstrip(".?!").lower()

        for candidate in pending.candidates:
            if candidate.lower() == text_clean:
                rewritten = self._rewrite(pending.original_request, pending.pronoun, candidate)
                logger.info(
                    "[CLARIFY] Resolved: %r → %r, rewritten: %r",
                    text, candidate, rewritten,
                )
                return ClarificationResolution(
                    resolved=True,
                    entity=candidate,
                    rewritten=rewritten,
                )

        # Partial match — if the reply contains exactly one candidate name
        matches = [c for c in pending.candidates if c.lower() in text_clean]
        if len(matches) == 1:
            rewritten = self._rewrite(pending.original_request, pending.pronoun, matches[0])
            logger.info(
                "[CLARIFY] Partial match: %r → %r, rewritten: %r",
                text, matches[0], rewritten,
            )
            return ClarificationResolution(
                resolved=True,
                entity=matches[0],
                rewritten=rewritten,
            )

        return ClarificationResolution(resolved=False)

    def build_question(self, candidates: list[str]) -> str:
        """
        Build a natural clarification question from a list of candidates.

        Args:
            candidates: List of entity name strings.

        Returns:
            A natural language question string.
        """
        if not candidates:
            return "Could you clarify who you mean?"
        if len(candidates) == 1:
            return f"Do you mean {candidates[0]}?"
        if len(candidates) == 2:
            return f"Do you mean {candidates[0]} or {candidates[1]}?"
        # 3+ candidates
        options = ", ".join(candidates[:-1]) + f" or {candidates[-1]}"
        return f"Do you mean {options}?"

    def collect_recent_entities(self, session: "SessionContext") -> list[str]:
        """
        Collect recently active entity names from SessionContext.

        Returns entities from active_person and active_topic slots
        that are still within confidence threshold.

        Args:
            session: The current SessionContext.

        Returns:
            List of entity name strings (may be empty).
        """
        entities = []

        person_slot = session.active_person
        if person_slot and session.is_usable(person_slot):
            entities.append(person_slot.value)

        # active_topic might hold a group name or a secondary entity
        # Only include if it looks like a single entity name (not "3 dogs")
        topic_slot = session.active_topic
        if topic_slot and session.is_usable(topic_slot):
            topic_val = topic_slot.value
            # Single word or short name = likely an entity, not a group description
            if len(topic_val.split()) == 1 and not any(c.isdigit() for c in topic_val):
                if topic_val.lower() != (person_slot.value.lower() if person_slot else ""):
                    entities.append(topic_val)

        return entities

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filter_candidates(
        self,
        candidates: list[str],
        session: "SessionContext",
    ) -> list[tuple[str, float]]:
        """
        Filter candidates to those with sufficient confidence in SessionContext.

        For entities tracked in _recent_entities but no longer in the active
        session slot, we assign a baseline confidence so they remain eligible
        for clarification — they were explicitly mentioned this session.

        Returns list of (name, confidence) tuples sorted by confidence desc.
        """
        result = []
        for name in candidates:
            conf = self._confidence_for(name, session)
            # Always include explicitly tracked recent entities with at least
            # a baseline confidence — they were mentioned this session.
            effective = max(conf, _MIN_CANDIDATE_CONFIDENCE + 0.05)
            result.append((name, effective))

        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def _are_ambiguous(
        self,
        candidates: list[tuple[str, float]],
        session: "SessionContext",
    ) -> bool:
        """
        Return True if the candidates are too similar to distinguish.

        When candidates come from _recent_entities (explicitly tracked this
        session), treat them as ambiguous unless one has significantly higher
        session confidence than the others.
        """
        if len(candidates) < 2:
            return False
        top_conf = candidates[0][1]
        second_conf = candidates[1][1]
        return (top_conf - second_conf) <= _SIMILARITY_THRESHOLD

    def _confidence_for(self, name: str, session: "SessionContext") -> float:
        """Return the effective confidence for an entity name in SessionContext."""
        person = session.active_person
        if person and person.value.lower() == name.lower():
            return session.effective_confidence(person)

        topic = session.active_topic
        if topic and topic.value.lower() == name.lower():
            return session.effective_confidence(topic)

        # Not in session — treat as low confidence
        return _MIN_CANDIDATE_CONFIDENCE

    def _are_ambiguous(
        self,
        candidates: list[tuple[str, float]],
        session: "SessionContext",
    ) -> bool:
        """
        Return True if the top two candidates are too similar to distinguish.

        Two candidates are ambiguous when their confidence difference
        is within _SIMILARITY_THRESHOLD.
        """
        if len(candidates) < 2:
            return False
        top_conf = candidates[0][1]
        second_conf = candidates[1][1]
        return (top_conf - second_conf) <= _SIMILARITY_THRESHOLD

    def _rewrite(self, original: str, pronoun: str, entity: str) -> str:
        """Replace the pronoun in the original request with the entity name."""
        pattern = re.compile(rf"\b{re.escape(pronoun)}\b", re.IGNORECASE)
        return pattern.sub(entity, original, count=1)