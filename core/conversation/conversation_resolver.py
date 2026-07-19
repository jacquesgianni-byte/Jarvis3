"""
Jarvis Conversation Reference Resolver (Genesis-022 Sprint-003)

Resolves conversational references in user input before routing occurs.

The resolver receives:
    - raw user input
    - ConversationState  (what the conversation knows right now)
    - ConversationPolicy (confidence thresholds)

and produces a ResolutionResult — never modifying state directly.

Design constraints:
    - Completely deterministic. No AI, no fuzzy matching.
    - Never modifies ConversationState.
    - Always preserves original input.
    - All confidence thresholds come from ConversationPolicy.
    - Returns a ResolutionResult regardless of outcome.
    - Supports ReferenceType categories for extensibility.

Resolution priority (highest to lowest confidence):
    1. Person pronouns (him/her/he/she)      → 0.95
    2. Named references (the project/file)   → 0.90
    3. Neutral pronouns with clear context   → 0.80
    4. Generic pronouns (it/this/that/them)  → 0.70
    5. "the last one"                        → 0.65

If the best candidate confidence is below policy.resolution_threshold,
the original input is returned unchanged with resolved=False.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.conversation_state import ConversationState
    from core.conversation.conversation_policy import ConversationPolicy


# ---------------------------------------------------------------------------
# ReferenceType — categories for extensibility
# ---------------------------------------------------------------------------

class ReferenceType(Enum):
    """
    Categories of conversational reference.

    Categorising references (not just words) makes future features —
    multilingual support, richer context resolution, logging — easy
    to add without redesigning the resolver.
    """
    OBJECT  = auto()   # "it", "this", "that" — generic object reference
    PERSON  = auto()   # "him", "her", "he", "she", "they", "them"
    FILE    = auto()   # "the file", "this file", "that file"
    PROJECT = auto()   # "the project", "this project"
    WORKER  = auto()   # "the worker", "that worker"
    TOPIC   = auto()   # "the topic", "that subject"
    UNKNOWN = auto()   # reference detected but type unclear

    def label(self) -> str:
        return self.name.title()


# ---------------------------------------------------------------------------
# ResolutionResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolutionResult:
    """
    The result of a single reference resolution attempt.

    Immutable. Produced by ReferenceResolver.resolve().
    Pipeline stages read this result and decide what to do with it.
    The resolver never modifies ConversationState.

    Attributes:
        original_input:  The user's exact input — never modified.
        resolved_input:  The input after resolution (may equal original).
        resolved:        True if a resolution was applied.
        confidence:      Resolver confidence in the resolution (0.0–1.0).
        reason:          Human-readable explanation of the resolution decision.
        reference_type:  What category of reference was resolved.
        pronoun:         The specific pronoun/reference that was matched.
        replacement:     The value that replaced the pronoun (if resolved).
    """
    original_input: str
    resolved_input: str
    resolved:       bool
    confidence:     float          = 0.0
    reason:         str            = ""
    reference_type: ReferenceType  = ReferenceType.UNKNOWN
    pronoun:        str            = ""
    replacement:    str            = ""

    @classmethod
    def no_resolution(cls, original: str, reason: str = "") -> "ResolutionResult":
        """Convenience constructor for the no-resolution case."""
        return cls(
            original_input=original,
            resolved_input=original,
            resolved=False,
            confidence=0.0,
            reason=reason or "No resolvable reference found.",
            reference_type=ReferenceType.UNKNOWN,
        )

    def __str__(self) -> str:
        if self.resolved:
            return (
                f"ResolutionResult(resolved={self.pronoun!r}"
                f"→{self.replacement!r}, conf={self.confidence:.2f})"
            )
        return f"ResolutionResult(unresolved, conf={self.confidence:.2f})"


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# Person pronouns — high specificity (PERSON)
_PERSON_PRONOUNS = re.compile(
    r"\b(him|her|he|she|they|them)\b", re.IGNORECASE
)

# Named file references (FILE)
_FILE_REFS = re.compile(
    r"\b(the file|this file|that file|the document|this document|"
    r"the readme|this readme)\b",
    re.IGNORECASE,
)

# Named project references (PROJECT)
_PROJECT_REFS = re.compile(
    r"\b(the project|this project|that project|"
    r"the app|this app|the system|this system)\b",
    re.IGNORECASE,
)

# Named worker references (WORKER)
_WORKER_REFS = re.compile(
    r"\b(the worker|this worker|that worker|"
    r"the agent|this agent)\b",
    re.IGNORECASE,
)

# Generic neutral pronouns — lower specificity (OBJECT)
_NEUTRAL_PRONOUNS = re.compile(
    r"\b(it|this|that)\b", re.IGNORECASE
)

# Plural / collective (OBJECT or PERSON depending on context)
_PLURAL_REFS = re.compile(
    r"\b(them|those|these)\b", re.IGNORECASE
)

# "the last one" — lowest specificity
_LAST_ONE = re.compile(
    r"\b(the last one|the previous one|the one before)\b", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Candidate — internal representation of a match
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Candidate:
    """Internal: a detected reference candidate before resolution."""
    pronoun:        str
    reference_type: ReferenceType
    base_confidence: float
    context_value:  Optional[str]   # what we'd replace it with


# ---------------------------------------------------------------------------
# ReferenceResolver
# ---------------------------------------------------------------------------

class ReferenceResolver:
    """
    Resolves conversational references in user input.

    Never modifies ConversationState. Always returns a ResolutionResult.
    All threshold decisions are delegated to ConversationPolicy.

    Public API:
        resolve(raw_input, state, policy) → ResolutionResult
        has_reference(raw_input)          → bool  (fast pre-check)
        detect_references(raw_input)      → list[str]  (all matched pronouns)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        raw_input: str,
        state: "ConversationState",
        policy: "ConversationPolicy",
    ) -> ResolutionResult:
        """
        Attempt to resolve conversational references in raw_input.

        Steps:
            1. Validate input.
            2. Find the best resolution candidate in priority order.
            3. Check candidate confidence against policy threshold.
            4. If above threshold, apply replacement and return resolved result.
            5. If below threshold, return original unchanged.

        Args:
            raw_input: The user's message.
            state:     Current conversation state (read-only).
            policy:    Conversation policy for threshold decisions.

        Returns:
            ResolutionResult with resolved=True if resolution was applied,
            False if no reference was found or confidence was too low.
        """
        # Validate input
        if not raw_input or not raw_input.strip():
            return ResolutionResult.no_resolution(
                raw_input or "", "Empty input cannot be resolved."
            )

        stripped = raw_input.strip()

        # Find the best candidate (highest confidence with available context)
        candidate = self._find_best_candidate(stripped, state)

        if candidate is None:
            return ResolutionResult.no_resolution(
                raw_input, "No resolvable reference detected."
            )

        if candidate.context_value is None:
            return ResolutionResult.no_resolution(
                raw_input,
                f"Reference {candidate.pronoun!r} detected "
                f"({candidate.reference_type.label()}) "
                f"but no context available to resolve it."
            )

        # Check confidence against policy threshold
        if not policy.should_resolve(candidate.base_confidence):
            return ResolutionResult(
                original_input=raw_input,
                resolved_input=raw_input,
                resolved=False,
                confidence=candidate.base_confidence,
                reason=(
                    f"Confidence {candidate.base_confidence:.2f} is below "
                    f"resolution threshold {policy.resolution_threshold:.2f}. "
                    f"Input left unchanged."
                ),
                reference_type=candidate.reference_type,
                pronoun=candidate.pronoun,
                replacement="",
            )

        # Apply resolution
        resolved = _replace_first(stripped, candidate.pronoun, candidate.context_value)

        return ResolutionResult(
            original_input=raw_input,
            resolved_input=resolved,
            resolved=True,
            confidence=candidate.base_confidence,
            reason=(
                f"Resolved {candidate.pronoun!r} → {candidate.context_value!r} "
                f"({candidate.reference_type.label()}, "
                f"confidence={candidate.base_confidence:.2f})."
            ),
            reference_type=candidate.reference_type,
            pronoun=candidate.pronoun,
            replacement=candidate.context_value,
        )

    def has_reference(self, raw_input: str) -> bool:
        """
        Fast pre-check: does this input contain any resolvable reference?

        Used by pipeline stages to skip resolution entirely when
        no reference is present.
        """
        if not raw_input or not raw_input.strip():
            return False
        text = raw_input.strip()
        return any(p.search(text) for p in [
            _PERSON_PRONOUNS, _FILE_REFS, _PROJECT_REFS,
            _WORKER_REFS, _NEUTRAL_PRONOUNS, _PLURAL_REFS, _LAST_ONE,
        ])

    def detect_references(self, raw_input: str) -> list[str]:
        """
        Return all reference pronouns detected in the input.

        Returns a list of matched strings in order of appearance.
        Used for debugging and testing.
        """
        if not raw_input or not raw_input.strip():
            return []
        text = raw_input.strip()
        found = []
        for pattern in [
            _PERSON_PRONOUNS, _FILE_REFS, _PROJECT_REFS,
            _WORKER_REFS, _NEUTRAL_PRONOUNS, _PLURAL_REFS, _LAST_ONE,
        ]:
            for m in pattern.finditer(text):
                if m.group(0).lower() not in [f.lower() for f in found]:
                    found.append(m.group(0))
        return found

    # ------------------------------------------------------------------
    # Candidate detection — priority order
    # ------------------------------------------------------------------

    def _find_best_candidate(
        self, text: str, state: "ConversationState"
    ) -> Optional[_Candidate]:
        """
        Find the highest-confidence resolvable candidate.

        Checks reference types in priority order. Returns the first
        candidate that has context available, or None if no match found.
        """
        refs = state.references

        # Priority 1: Person pronouns → current_person (confidence 0.95)
        m = _PERSON_PRONOUNS.search(text)
        if m:
            return _Candidate(
                pronoun=m.group(0),
                reference_type=ReferenceType.PERSON,
                base_confidence=0.95,
                context_value=refs.current_person,
            )

        # Priority 2a: Named file references → last_entity (confidence 0.90)
        m = _FILE_REFS.search(text)
        if m:
            return _Candidate(
                pronoun=m.group(0),
                reference_type=ReferenceType.FILE,
                base_confidence=0.90,
                context_value=refs.last_entity or refs.current_it,
            )

        # Priority 2b: Named project references → current_project (confidence 0.90)
        m = _PROJECT_REFS.search(text)
        if m:
            return _Candidate(
                pronoun=m.group(0),
                reference_type=ReferenceType.PROJECT,
                base_confidence=0.90,
                context_value=refs.current_project,
            )

        # Priority 2c: Named worker references → last_entity (confidence 0.90)
        m = _WORKER_REFS.search(text)
        if m:
            return _Candidate(
                pronoun=m.group(0),
                reference_type=ReferenceType.WORKER,
                base_confidence=0.90,
                context_value=refs.last_entity,
            )

        # Priority 3: Neutral pronouns → best available context (confidence 0.80)
        m = _NEUTRAL_PRONOUNS.search(text)
        if m:
            context = (
                refs.current_it
                or refs.current_task
                or refs.current_project
                or refs.last_entity
            )
            return _Candidate(
                pronoun=m.group(0),
                reference_type=ReferenceType.OBJECT,
                base_confidence=0.80,
                context_value=context,
            )

        # Priority 4: Plural refs → person or last_entity (confidence 0.70)
        m = _PLURAL_REFS.search(text)
        if m:
            context = refs.current_person or refs.last_entity
            ref_type = (
                ReferenceType.PERSON if refs.current_person
                else ReferenceType.OBJECT
            )
            return _Candidate(
                pronoun=m.group(0),
                reference_type=ref_type,
                base_confidence=0.70,
                context_value=context,
            )

        # Priority 5: "the last one" → last_entity (confidence 0.65)
        m = _LAST_ONE.search(text)
        if m:
            return _Candidate(
                pronoun=m.group(0),
                reference_type=ReferenceType.OBJECT,
                base_confidence=0.65,
                context_value=refs.last_entity,
            )

        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _replace_first(text: str, old: str, new: str) -> str:
    """Replace the first case-insensitive occurrence of old with new."""
    pattern = re.compile(re.escape(old), re.IGNORECASE)
    return pattern.sub(new, text, count=1)