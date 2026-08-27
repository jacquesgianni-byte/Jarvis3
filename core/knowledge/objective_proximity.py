"""
Jarvis OS - ObjectiveProximityAnalyser - Genesis-063 Sprint-001

Deterministic keyword-overlap analysis between a failed question
and current project objectives.

Design invariants:
    - No LLM. No embedding. No semantic model.
    - Uses whole-word keyword matching ? same method as
      CapabilityProximityAnalyser and InvestigationSelector.
    - Objectives are supplied as a list of dicts at construction time.
      The analyser never reads project_state.json directly.
    - ObjectiveProximityResult is frozen ? immutable after creation.
    - A score of 0 means no keyword overlap ? not "unrelated."
    - The analyser never claims semantic understanding.
    - The analyser never generates recommendations or actions.
    - Results are proximity evidence only.

This is groundwork for Level 4 CAA:
    Gap detected ? capability proximity ? objective relevance
    (NOT: gap detected ? recommendation generated)
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObjectiveMatch:
    """
    One objective that overlapped with the failed question.

    objective_text: the exact text of the objective from project_state.json
    score:          keyword overlap count
    done:           whether this objective is marked complete
    """
    objective_text: str
    score:          int
    done:           bool


@dataclass(frozen=True)
class ObjectiveProximityResult:
    """
    Immutable result of objective proximity analysis for one gap observation.

    observation_id:   links back to the CapabilityGapObservation analysed.
    question:         the failed question that was analysed.
    matches:          ObjectiveMatch entries with score > 0, sorted by score desc.
    total_objectives: how many objectives were compared.
    has_overlap:      True when at least one objective scored > 0.
    all_scores:       {objective_text: score} for full audit trail.

    A score > 0 means keyword overlap exists.
    It does NOT mean the gap is semantically related to the objective.
    This is proximity evidence only.
    """
    observation_id:    str
    question:          str
    matches:           Tuple[ObjectiveMatch, ...]
    total_objectives:  int
    has_overlap:       bool
    all_scores:        Dict[str, int]

    def format_for_report(self) -> str:
        """Format objective relevance section for gap reports."""
        lines = ["Objective relevance (keyword proximity):"]

        if not self.has_overlap:
            lines += [
                f"  Objectives compared: {self.total_objectives}",
                "  No keyword overlap detected between the failed question",
                "  and any current project objective.",
                "  Note: absence of overlap is a keyword result, not a semantic judgment.",
            ]
            return "\n".join(lines)

        lines.append(f"  Objectives compared: {self.total_objectives}")
        lines.append(f"  Objectives with overlap: {len(self.matches)}")
        lines.append("")
        lines.append("  Overlapping objectives (sorted by overlap score):")
        for m in self.matches:
            status = "done" if m.done else "active"
            lines.append(f"    [{status}] score={m.score}: {m.objective_text!r}")

        lines += [
            "",
            "  Note: overlap scores reflect keyword proximity only.",
            "  This is not semantic classification or a recommendation.",
        ]
        return "\n".join(lines)


class ObjectiveProximityAnalyser:
    """
    Computes keyword overlap between a failed question and project objectives.

    Objectives are supplied at construction ? the analyser never reads files.
    Uses whole-word matching, same method as CapabilityProximityAnalyser.
    Never modifies objectives. Never generates recommendations.
    """

    def __init__(self, objectives: List[dict]) -> None:
        """
        objectives: list of {"text": str, "done": bool} dicts
                    from project_state.json / engineering_context
        """
        self._objectives = objectives or []

    def analyse(
        self,
        question: str,
        observation_id: str,
    ) -> ObjectiveProximityResult:
        """
        Compute keyword overlap between question and each objective.

        Returns ObjectiveProximityResult with full audit trail.
        """
        question_lower = question.lower()
        all_scores: Dict[str, int] = {}
        matches: List[ObjectiveMatch] = []

        for obj in self._objectives:
            text = obj.get("text", "")
            done = obj.get("done", False)
            if not text:
                continue

            score = self._count_overlap(question_lower, text.lower())
            all_scores[text] = score

            if score > 0:
                matches.append(ObjectiveMatch(
                    objective_text = text,
                    score          = score,
                    done           = done,
                ))
                logger.debug(
                    "[ObjectiveProximityAnalyser] objective=%r scored %d for question=%r",
                    text[:50], score, question[:50],
                )

        matches.sort(key=lambda m: m.score, reverse=True)

        return ObjectiveProximityResult(
            observation_id   = observation_id,
            question         = question,
            matches          = tuple(matches),
            total_objectives = len(self._objectives),
            has_overlap      = len(matches) > 0,
            all_scores       = dict(all_scores),
        )

    @staticmethod
    def _count_overlap(question_lower: str, objective_lower: str) -> int:
        """
        Count how many words from the objective appear in the question.
        Whole-word matching for single words; substring for multi-word phrases.
        """
        words = objective_lower.split()
        hits  = 0
        for word in words:
            if len(word) <= 2:
                continue  # skip short words (is, a, to, etc.)
            pattern = r"\b" + re.escape(word) + r"\b"
            if re.search(pattern, question_lower):
                hits += 1
        return hits
