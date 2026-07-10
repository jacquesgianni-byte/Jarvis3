"""
Thought & Reasoning Engine (Genesis-013 Task 001).

Deterministic, rule-driven inference over facts stored in the
Knowledge Engine.

    Knowledge answers: "What do I know?"
    Reasoning answers: "What follows from what I know?"

Contracts (design v1.1, APPROVED):
    * [R1] READ-ONLY consumer of the Knowledge Engine — this module
      calls recall_memory() only and never any write method. It holds
      no facts and caches nothing: every inference is computed fresh
      from current knowledge, so there is no staleness class of bugs.
    * Deterministic: same facts + same rules => same conclusion, always.
    * Explainable: every conclusion carries its rule chain and premise
      snapshots, built during inference rather than reconstructed.
    * Confidence: conclusion = rule.confidence x min(premise
      confidences), hard-capped at 0.9 so an inferred value can never
      tie a user-stated fact. Conclusions below 0.5 are suppressed —
      recorded in history, never returned.
    * Bounded: chains of at most 3 rules, with cycle protection.
    * [R5] AI advises, rules decide: the ai_assist seam is reserved and
      MUST remain None in Version 1. User facts prevail.
"""

import logging

from core.reasoning.history import HistoryEntry, InMemoryInferenceHistory
from core.reasoning.models import (
    CONFIDENCE_CAP,
    SUPPRESS_THRESHOLD,
    Explanation,
    Inference,
    Outcome,
    PremiseSnapshot,
    ReasoningStats,
    ReasonType,
)
from core.reasoning.rules import RuleLoader

logger = logging.getLogger(__name__)

# Maximum number of rules in one inference chain (design §4).
MAX_CHAIN_DEPTH = 3


class ReasoningEngine:
    """
    Jarvis's first thinking subsystem.

    Consumes the Knowledge Engine through its public read API and
    produces conclusions with confidence scores and complete traces.
    """

    def __init__(self, knowledge, rules_dir=None, history=None, ai_assist=None):
        """
        Args:
            knowledge: The KnowledgeEngine (read-only dependency).
            rules_dir: Optional override for the rules directory.
            history:   Optional InferenceHistoryRepository.
            ai_assist: RESERVED [R5]. Must be None in Version 1.
        """

        if ai_assist is not None:
            raise ValueError(
                "ai_assist is reserved for a future version. "
                "AI advises, rules decide — and in V1, rules decide alone."
            )

        self.knowledge = knowledge
        # NOTE: explicit None check — an injected EMPTY history defines
        # __len__ == 0 and is falsy, so `history or Default()` would
        # silently discard it. Caught by test [15].
        self.history = history if history is not None else InMemoryInferenceHistory()
        self._stats = ReasoningStats()

        loader = RuleLoader(rules_dir)
        self._rules = loader.load()
        self._sets = {
            name: {value.lower() for value in values}
            for name, values in loader.sets.items()
        }
        self._stats.rules_loaded = len(self._rules)

        # Index rules by the attribute they conclude (load order kept
        # within each bucket — determinism).
        self._by_conclusion = {}
        for rule in self._rules:
            self._by_conclusion.setdefault(rule.conclusion_attribute, []).append(rule)

        logger.info(
            "ReasoningEngine initialised. Rules loaded: %d (concluding %d attribute(s)).",
            len(self._rules), len(self._by_conclusion),
        )

    # ------------------------------------------------------------------
    # Public API (design §2)
    # ------------------------------------------------------------------

    def infer(self, subject: str, attribute: str):
        """
        Attempt to conclude a value for an attribute that is not
        directly stored.

        Returns the single best Inference (asserted or hedged), or None
        when nothing can be concluded or the best conclusion falls
        below the suppression threshold. Every attempt — including
        suppressed and no-path outcomes — is recorded in history.
        """

        subject = subject.strip().lower()
        attribute = attribute.strip().lower()

        inference = self._infer_best(subject, attribute, depth=1, visited={attribute})

        self._stats.inferences += 1

        if inference is None:
            self._stats.no_path += 1
            self.history.record(
                HistoryEntry(subject=subject, attribute=attribute,
                             outcome=Outcome.NO_PATH)
            )
            logger.debug(
                "infer: no rule path — subject=%r attribute=%r", subject, attribute
            )
            return None

        outcome = inference.outcome
        self.history.record(
            HistoryEntry(subject=subject, attribute=attribute,
                         outcome=outcome, inference=inference)
        )
        self._count(inference, outcome)

        if outcome is Outcome.SUPPRESSED:
            logger.debug(
                "infer: conclusion suppressed (confidence %.2f) — "
                "subject=%r attribute=%r value=%r",
                inference.confidence, subject, attribute, inference.value,
            )
            return None

        logger.info(
            "infer: %s %s=%r (confidence %.2f, %s, rules=%s)",
            outcome.value, attribute, inference.value,
            inference.confidence, inference.reason_type.value,
            "->".join(inference.rule_ids),
        )
        return inference

    def conclusions(self, subject: str) -> list:
        """
        Every conclusion currently derivable for a subject whose
        attribute is NOT already stored as a fact. Diagnostic /
        bulk-scan API: does not write history entries.
        """

        subject = subject.strip().lower()
        results = []

        for attribute in self._by_conclusion:
            if self.knowledge.recall_memory(subject, attribute) is not None:
                continue    # already known — knowing beats concluding
            inference = self._infer_best(
                subject, attribute, depth=1, visited={attribute}
            )
            if inference is not None and inference.outcome is not Outcome.SUPPRESSED:
                results.append(inference)

        return results

    def explain(self, inference: Inference) -> Explanation:
        """Build the human-readable trace for a conclusion."""

        lines = [
            f"Concluded {inference.attribute} = {inference.value} "
            f"(confidence {inference.confidence:.2f}, "
            f"{inference.reason_type.value}).",
            f"Rule chain: {' -> '.join(inference.rule_ids)}.",
            "Because:",
        ]
        for premise in inference.premises:
            lines.append(
                f"  - {premise.attribute} = {premise.value} "
                f"({premise.source}, confidence {premise.confidence:.2f})"
            )
        return Explanation(inference=inference, lines=tuple(lines))

    def stats(self) -> ReasoningStats:
        return self._stats

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _infer_best(self, subject, attribute, depth, visited):
        """
        Try every rule that concludes `attribute`; return the highest-
        confidence Inference, or None. Deterministic: rules are tried
        in load order and ties keep the earlier rule.
        """

        if depth > MAX_CHAIN_DEPTH:
            return None

        best = None
        for rule in self._by_conclusion.get(attribute, []):
            candidate = self._apply_rule(rule, subject, depth, visited)
            if candidate is not None and (
                best is None or candidate.confidence > best.confidence
            ):
                best = candidate
        return best

    def _apply_rule(self, rule, subject, depth, visited):
        """Try to satisfy every premise of one rule (AND semantics)."""

        snapshots = []
        chain_rule_ids = [rule.id]
        chained = False

        for premise in rule.premises:
            record = self.knowledge.recall_memory(subject, premise.attribute)

            if record is not None and self._matches(premise, record.value):
                snapshots.append(PremiseSnapshot(
                    attribute=premise.attribute,
                    value=str(record.value),
                    confidence=float(getattr(record, "confidence", 1.0)),
                    source=str(getattr(record.source, "value", getattr(record, "source", "user"))),
                ))
                continue

            if record is not None:
                return None    # fact exists but does not satisfy the premise

            # Premise not stored — try to infer it (chaining), with
            # cycle protection: never re-enter an attribute already on
            # this chain.
            if premise.attribute in visited:
                return None
            sub = self._infer_best(
                subject, premise.attribute,
                depth=depth + 1,
                visited=visited | {premise.attribute},
            )
            if sub is None or not self._matches(premise, sub.value):
                return None

            chained = True
            chain_rule_ids.extend(sub.rule_ids)
            snapshots.append(PremiseSnapshot(
                attribute=premise.attribute,
                value=sub.value,
                confidence=sub.confidence,
                source="inferred",
            ))

        confidence = min(
            rule.confidence * min(s.confidence for s in snapshots),
            CONFIDENCE_CAP,
        )

        if chained:
            reason_type = ReasonType.CHAINED
        elif len(snapshots) > 1:
            reason_type = ReasonType.MULTI_PREMISE
        else:
            reason_type = ReasonType.DERIVED

        return Inference(
            subject=subject,
            attribute=rule.conclusion_attribute,
            value=rule.conclusion_value,
            confidence=confidence,
            reason_type=reason_type,
            rule_ids=tuple(chain_rule_ids),
            premises=tuple(snapshots),
        )

    def _matches(self, premise, value) -> bool:
        value = str(value).strip().lower()
        if premise.kind == "equals":
            return value == premise.operand.strip().lower()
        if premise.kind == "in_set":
            return value in self._sets.get(premise.operand, set())
        return bool(value)          # exists

    def _count(self, inference, outcome):
        if outcome is Outcome.ASSERTED:
            self._stats.asserted += 1
        elif outcome is Outcome.HEDGED:
            self._stats.hedged += 1
        else:
            self._stats.suppressed += 1

        if inference.reason_type is ReasonType.DERIVED:
            self._stats.derived += 1
        elif inference.reason_type is ReasonType.CHAINED:
            self._stats.chained += 1
        elif inference.reason_type is ReasonType.MULTI_PREMISE:
            self._stats.multi_premise += 1