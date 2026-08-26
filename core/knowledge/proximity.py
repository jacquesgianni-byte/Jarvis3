"""
Jarvis OS - ProximityResult + CapabilityProximityAnalyser - Genesis-061 Sprint-001

Deterministic proximity analysis of capability-gap observations.

Given a failed question that produced a CapabilityGapObservation, the analyser
computes how much each registered investigation's declared question_keywords
overlap with the failed question. This locates the failure relative to
Jarvis's existing registered capabilities.

Design invariants:
    - No LLM. No embedding. No semantic model. No cosine similarity.
    - Comparison uses whole-word keyword overlap only ? same method as
      InvestigationSelector. Declared keywords, deterministic result.
    - ProximityResult is frozen ? immutable after creation.
    - all_scores preserves the complete audit trail for every comparison.
    - A score of 0 means zero keyword overlap ? nothing more, nothing less.
      It does NOT mean the analyser understands the question is unrelated.
    - Ties are reported as ties ? never resolved by guessing.
    - gap_is_isolated = True when ALL scores are 0.
    - The analyser never reinterprets scores. It never names a semantic domain.
    - The analyser never modifies the gap observation or the registry.

Level 2 of CAA self-knowledge progression:
    Level 1 (Genesis-060): Jarvis knows THAT it has a gap.
    Level 2 (Genesis-061): Jarvis knows WHERE the gap sits relative to
                           its existing registered capabilities.
    Level 3 (future):      Jarvis knows WHAT KIND of gap it is.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProximityResult:
    """
    Immutable result of a proximity analysis for one capability-gap observation.

    observation_id:     links back to the CapabilityGapObservation that was analysed.
    closest_names:      name(s) of the highest-scoring descriptor(s).
                        Empty list when gap_is_isolated (all scores zero).
                        Two or more names when tied at the highest score.
    closest_score:      the highest keyword overlap count across all descriptors.
                        0 when gap_is_isolated.
    total_capabilities: how many descriptors were compared.
    all_scores:         {descriptor.name: overlap_count} for every descriptor.
                        Complete audit trail ? never omitted.
    gap_is_isolated:    True when closest_score == 0.
                        Means: no declared keyword in any registered capability
                        overlapped the failed question.
                        Does NOT mean: the gap is semantically unrelated.
    is_tied:            True when two or more descriptors share the highest score.
    """
    observation_id:     str
    closest_names:      Tuple[str, ...]
    closest_score:      int
    total_capabilities: int
    all_scores:         Dict[str, int]
    gap_is_isolated:    bool
    is_tied:            bool

    def format_for_report(self) -> str:
        """Format the proximity result as evidence for a gap report."""
        lines = [
            "Proximity analysis:",
            f"  Capabilities compared: {self.total_capabilities}",
        ]

        if self.gap_is_isolated:
            lines += [
                "  Closest match score:   0",
                "  Gap status:            ISOLATED",
                "  Interpretation:        No declared keyword in any registered",
                "                         capability overlapped the failed question.",
                "  Note: score=0 is a keyword-overlap result, not a semantic judgment.",
            ]
        elif self.is_tied:
            names = ", ".join(self.closest_names)
            lines += [
                f"  Closest match score:   {self.closest_score} (tied)",
                f"  Tied capabilities:     {names}",
                "  Gap status:            AMBIGUOUS ? tie, no single closest capability.",
            ]
        else:
            lines += [
                f"  Closest capability:    {self.closest_names[0]}",
                f"  Closest match score:   {self.closest_score}",
                "  Gap status:            PROXIMATE",
            ]

        lines += ["", "  Full audit trail (capability: keyword overlap score):"]
        for name, score in sorted(self.all_scores.items()):
            lines.append(f"    {name}: {score}")

        return "\n".join(lines)


class CapabilityProximityAnalyser:
    """
    Deterministic proximity analyser for capability-gap observations.

    Takes a failed question and an InvestigationRegistry.
    Returns a ProximityResult showing keyword overlap scores for every
    registered investigation descriptor.

    No LLM. No embedding. No semantic model.
    Uses whole-word keyword matching ? same method as InvestigationSelector.
    Never modifies the observation or the registry.
    Never names a semantic domain.
    Never reinterprets scores beyond what the overlap count literally means.
    """

    def analyse(
        self,
        question: str,
        observation_id: str,
        registry,  # InvestigationRegistry ? not imported to avoid circular deps
    ) -> ProximityResult:
        """
        Compute keyword overlap between a failed question and every registered
        investigation descriptor.

        Returns a ProximityResult with the complete audit trail.
        """
        question_lower = question.lower()
        descriptors    = registry.all_descriptors()
        all_scores: Dict[str, int] = {}

        for descriptor in descriptors:
            score = self._count_hits(question_lower, descriptor.question_keywords)
            all_scores[descriptor.name] = score
            logger.debug(
                "[CapabilityProximityAnalyser] %r scored %d for question %r",
                descriptor.name, score, question[:60],
            )

        total = len(descriptors)

        if not all_scores:
            return ProximityResult(
                observation_id     = observation_id,
                closest_names      = (),
                closest_score      = 0,
                total_capabilities = 0,
                all_scores         = {},
                gap_is_isolated    = True,
                is_tied            = False,
            )

        max_score = max(all_scores.values())
        gap_is_isolated = max_score == 0

        if gap_is_isolated:
            return ProximityResult(
                observation_id     = observation_id,
                closest_names      = (),
                closest_score      = 0,
                total_capabilities = total,
                all_scores         = dict(all_scores),
                gap_is_isolated    = True,
                is_tied            = False,
            )

        winners = tuple(
            name for name, score in all_scores.items() if score == max_score
        )
        is_tied = len(winners) > 1

        return ProximityResult(
            observation_id     = observation_id,
            closest_names      = winners,
            closest_score      = max_score,
            total_capabilities = total,
            all_scores         = dict(all_scores),
            gap_is_isolated    = False,
            is_tied            = is_tied,
        )

    @staticmethod
    def _count_hits(question_lower: str, keywords: tuple) -> int:
        """
        Count keyword overlaps using whole-word matching.
        Same method as InvestigationSelector ? declared keywords, deterministic.
        Multi-word phrases: substring match.
        Single words: word-boundary anchor.
        """
        hits = 0
        for keyword in keywords:
            if " " in keyword:
                if keyword in question_lower:
                    hits += 1
            else:
                pattern = r"\b" + re.escape(keyword) + r"\b"
                if re.search(pattern, question_lower):
                    hits += 1
        return hits
