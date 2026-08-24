"""
Jarvis OS - InvestigationSelector - Genesis-058 Sprint-002

Deterministic keyword-based selector. Maps a user question to the
most relevant investigation in InvestigationRegistry.

Design invariants:
    - No LLM. No inference. No autonomous reasoning.
    - Selection is based only on declared question_keywords in each descriptor.
    - Whole-word matching only (same pattern as IntentStage).
    - If no descriptor matches: SelectionResult.matched = False.
    - If exactly one descriptor matches: SelectionResult.matched = True.
    - If two or more descriptors match equally: SelectionResult.ambiguous = True.
    - Ambiguity is never resolved by guessing. It is reported explicitly.
    - The selector never modifies the registry or any descriptor.
    - The selector never triggers an investigation itself.

When Jarvis does not know, it must not pretend it knows.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from core.mission.investigation_registry import InvestigationDescriptor, InvestigationRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectionResult:
    """
    The result of InvestigationSelector.select().

    Exactly one of these states is true:
        matched=True, ambiguous=False  -> one clear winner in descriptor
        matched=False, ambiguous=False -> no descriptor matched the question
        matched=False, ambiguous=True  -> two or more descriptors matched equally

    candidates is populated only when ambiguous=True.
    descriptor is populated only when matched=True.
    """
    matched:     bool
    ambiguous:   bool
    descriptor:  Optional[InvestigationDescriptor] = None
    candidates:  tuple = field(default_factory=tuple)   # populated on ambiguity
    question:    str   = ""
    match_count: int   = 0

    def __post_init__(self):
        # Invariant: matched and ambiguous are mutually exclusive
        if self.matched and self.ambiguous:
            raise ValueError(
                "[SelectionResult] matched and ambiguous cannot both be True."
            )
        # Invariant: descriptor only set when matched
        if self.descriptor is not None and not self.matched:
            raise ValueError(
                "[SelectionResult] descriptor must be None when matched=False."
            )
        # Invariant: candidates only set when ambiguous
        if self.candidates and not self.ambiguous:
            raise ValueError(
                "[SelectionResult] candidates must be empty when ambiguous=False."
            )

    @property
    def no_match(self) -> bool:
        """True when no investigation matched and no ambiguity."""
        return not self.matched and not self.ambiguous

    def format_for_mission(self) -> str:
        """Human-readable explanation of the selection result."""
        if self.matched:
            return (
                f"Selected investigation: {self.descriptor.display_name}\n"
                f"  ({self.descriptor.description})"
            )
        if self.ambiguous:
            names = ", ".join(c.display_name for c in self.candidates)
            return (
                f"I cannot determine which investigation applies to your question.\n"
                f"Multiple investigations matched equally: {names}.\n"
                f"Please be more specific about what you would like me to investigate."
            )
        return (
            "I don't have an investigation that covers that question.\n"
            "Available investigations:\n"
            + "\n".join(
                f"  - {d.display_name}: {d.description}"
                for d in self._available
            )
        )


class InvestigationSelector:
    """
    Maps a user question to the most relevant investigation descriptor.

    Uses whole-word keyword matching against each descriptor's
    question_keywords. Returns a SelectionResult - never raises.

    Tie-breaking policy:
        If two or more descriptors match with the same keyword count,
        the result is ambiguous. No guess is made.
        This enforces: when Jarvis does not know, it must not pretend it knows.

    The selector does not run investigations. It only selects.
    The selector does not modify the registry.
    """

    def __init__(self, registry: InvestigationRegistry) -> None:
        self._registry = registry

    def select(self, question: str) -> SelectionResult:
        """
        Select the best investigation for a question.

        Returns SelectionResult with:
            matched=True       if exactly one descriptor wins
            ambiguous=True     if two or more descriptors tie
            no_match=True      if no descriptor matched
        """
        question_lower = question.lower()
        available = self._registry.available()

        if not available:
            logger.info("[InvestigationSelector] No investigations available on disk.")
            return SelectionResult(
                matched=False,
                ambiguous=False,
                question=question,
                match_count=0,
            )

        # Score each available descriptor by keyword hit count
        scores: List[tuple] = []   # (hit_count, descriptor)
        for descriptor in available:
            hits = self._count_hits(question_lower, descriptor.question_keywords)
            if hits > 0:
                scores.append((hits, descriptor))
                logger.debug(
                    "[InvestigationSelector] %r scored %d hits for question %r",
                    descriptor.name, hits, question,
                )

        if not scores:
            logger.info(
                "[InvestigationSelector] No descriptor matched question: %r", question
            )
            return SelectionResult(
                matched=False,
                ambiguous=False,
                question=question,
                match_count=0,
            )

        # Find the maximum score
        max_hits = max(s[0] for s in scores)
        winners  = [d for hits, d in scores if hits == max_hits]

        if len(winners) == 1:
            logger.info(
                "[InvestigationSelector] Selected %r (%d hits) for question: %r",
                winners[0].name, max_hits, question,
            )
            return SelectionResult(
                matched=True,
                ambiguous=False,
                descriptor=winners[0],
                question=question,
                match_count=max_hits,
            )

        # Tie - ambiguous, never guess
        logger.info(
            "[InvestigationSelector] Ambiguous: %d descriptors tied at %d hits for: %r",
            len(winners), max_hits, question,
        )
        return SelectionResult(
            matched=False,
            ambiguous=True,
            candidates=tuple(winners),
            question=question,
            match_count=max_hits,
        )

    @staticmethod
    def _count_hits(question_lower: str, keywords: tuple) -> int:
        """
        Count how many keywords from the tuple match the question.
        Whole-word matching only - same pattern as IntentStage.
        Multi-word phrases are matched as substrings (already constrained
        by the keyword list being declared, not user-supplied).
        Single words use word-boundary anchors.
        """
        hits = 0
        for keyword in keywords:
            if " " in keyword:
                # Multi-word phrase: substring match (phrase is pre-declared)
                if keyword in question_lower:
                    hits += 1
            else:
                # Single word: whole-word match
                pattern = r"\b" + re.escape(keyword) + r"\b"
                if re.search(pattern, question_lower):
                    hits += 1
        return hits
