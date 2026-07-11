"""
Jarvis Reasoning Skill (Genesis-013 Task 002).

The gateway between natural language and the Reasoning Engine.

    The skill owns orchestration. The engine owns reasoning.

Responsibilities:
    * Parse reasoning questions into structured infer()/conclusions()
      calls (the engine never sees natural language).
    * Phrase conclusions for speech, honouring outcome bands:
      asserted spoken plainly, hedged spoken with hedging.
    * Answer "why?" follow-ups using the engine's explanation model —
      never regenerating explanations manually.
    * Own reasoning telemetry (TIMING stage=reasoning_infer + the
      REASONING summary line). The gateway measures; the engine reasons.

This skill never touches the Knowledge Engine and never bypasses the
Reasoning Engine.
"""

import re
import time

from core import telemetry
from core.logger import get_logger
from core.models.response import Response
from core.skills.base import Skill

_SUBJECT = "user"

# Follow-up questions about the most recent conclusion. Matched against
# the full request (trailing punctuation stripped) — conservative by
# design: "why is the sky blue?" must still reach the AI.
_FOLLOW_UPS = {
    "why",
    "why is that",
    "how did you work that out",
    "how do you know",
    "how do you know that",
    "explain",
    "explain that",
}

# Bulk-conclusions questions.
_CONCLUDE_ALL = re.compile(
    r"\bwhat can you (?:conclude|infer|work out|tell)\b(?:\s+about me)?",
    re.IGNORECASE,
)

# Direct reasoning questions -> engine attribute. Kept deliberately
# small in V1; most single-attribute reasoning arrives via the
# memory-miss escalation instead ("what is my country?").
_DIRECT_PATTERNS = [
    (re.compile(r"\b(?:what|which) sports? do i (?:follow|play|watch|support)\b",
                re.IGNORECASE), "favourite sport"),
    (re.compile(r"\b(?:what|which) country (?:do i live in|am i in|am i from)\b",
                re.IGNORECASE), "country"),
    (re.compile(r"\b(?:what|which) hemisphere\b", re.IGNORECASE), "hemisphere"),
]


class ReasoningSkill(Skill):
    """Lets Jarvis speak its conclusions — and show its working."""

    def __init__(self, engine):
        """
        Args:
            engine: The ReasoningEngine (owned by the Agent).
        """
        self.engine = engine
        self.logger = get_logger()

        # The most recent spoken conclusion, for "why?" follow-ups.
        self._last_inference = None

        # Gateway-side timing (the engine keeps counts, not clocks).
        self._infer_ms_total = 0.0
        self._infer_calls = 0

    @property
    def name(self) -> str:
        return "reasoning"

    # ------------------------------------------------------------------
    # Raw request entry point (Intent.REASONING)
    # ------------------------------------------------------------------

    def execute(self, request: str) -> Response:
        request = request.strip()
        core = request.lower().rstrip("?!. ").strip()

        if core in _FOLLOW_UPS:
            return self._explain_last()

        if _CONCLUDE_ALL.search(request):
            return self._all_conclusions()

        for pattern, attribute in _DIRECT_PATTERNS:
            if pattern.search(request):
                response = self.infer_attribute(attribute)
                if response is not None:
                    return response
                return Response(
                    success=True,
                    message=f"I can't work out your {attribute} from what "
                            "I know yet, sir."
                )

        return Response(
            success=True,
            message="I'm not sure what you'd like me to work out, sir. "
                    "You can ask what I can conclude about you."
        )

    # ------------------------------------------------------------------
    # Structured entry point (Agent's memory-miss escalation)
    # ------------------------------------------------------------------

    def infer_attribute(self, attribute: str):
        """
        Try to conclude a value for one attribute.

        Returns a spoken Response for asserted/hedged conclusions, or
        None when nothing can be concluded (suppressed or no path) —
        letting the caller fall back to its own honest answer.
        """

        attribute = attribute.strip().lower()
        if not attribute:
            return None

        started = time.perf_counter()
        inference = self.engine.infer(_SUBJECT, attribute)
        self._record(started, inference)

        if inference is None:
            return None

        self._last_inference = inference
        premise = inference.premises[0]

        if inference.outcome.value == "asserted":
            message = (
                f"Your {inference.attribute} is {inference.value}, sir — "
                f"I worked that out from your {premise.attribute} "
                f"being {premise.value}."
            )
        else:  # hedged
            message = (
                f"I believe your {inference.attribute} is {inference.value}, "
                f"sir, though I'm inferring that from your "
                f"{premise.attribute} being {premise.value}."
            )

        return Response(
            success=True,
            message=message,
            data={
                "reasoned": True,
                "confidence": inference.confidence,
                "reason_type": inference.reason_type.value,
            },
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _explain_last(self) -> Response:
        """Answer "why?" using the engine's explanation model."""

        if self._last_inference is None:
            return Response(
                success=True,
                message="I haven't concluded anything recently to "
                        "explain, sir."
            )

        explanation = self.engine.explain(self._last_inference)
        inference = explanation.inference

        because = "; and ".join(
            f"your {p.attribute} is {p.value}"
            f"{' (which I inferred)' if p.source == 'inferred' else ''}"
            for p in inference.premises
        )
        message = (
            f"I concluded your {inference.attribute} is {inference.value} "
            f"with {inference.confidence:.0%} confidence, because "
            f"{because}. Rule chain: {' then '.join(inference.rule_ids)}."
        )
        return Response(success=True, message=message)

    def _all_conclusions(self) -> Response:
        """Answer "what can you conclude about me?" via conclusions()."""

        started = time.perf_counter()
        conclusions = self.engine.conclusions(_SUBJECT)
        self._record(started, conclusions[0] if conclusions else None,
                      bulk=len(conclusions))

        if not conclusions:
            return Response(
                success=True,
                message="I don't have enough stored facts to conclude "
                        "anything new yet, sir."
            )

        conclusions.sort(key=lambda i: i.confidence, reverse=True)
        self._last_inference = conclusions[0]

        spoken = "; ".join(
            f"your {i.attribute} is {i.value}"
            for i in conclusions[:4]
        )
        message = (
            f"From what I know, I can work out {len(conclusions)} "
            f"thing{'s' if len(conclusions) != 1 else ''}: {spoken}, sir."
        )
        return Response(success=True, message=message)

    def _record(self, started, inference, bulk=None) -> None:
        """Emit reasoning telemetry: one TIMING line + REASONING summary."""

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._infer_ms_total += elapsed_ms
        self._infer_calls += 1

        if bulk is not None:
            result = f"conclusions={bulk}"
        elif inference is None:
            result = "no_conclusion"
        else:
            result = inference.outcome.value

        telemetry.log_since("reasoning_infer", started, result=result)

        stats = self.engine.stats()
        avg_ms = self._infer_ms_total / self._infer_calls
        self.logger.info(
            "REASONING | inferences=%d | asserted=%d | hedged=%d | "
            "suppressed=%d | no_path=%d | derived=%d | chained=%d | "
            "multi_premise=%d | avg_ms=%.1f | rules_loaded=%d | "
            "ai_consults=%d",
            stats.inferences, stats.asserted, stats.hedged,
            stats.suppressed, stats.no_path, stats.derived, stats.chained,
            stats.multi_premise, avg_ms, stats.rules_loaded,
            stats.ai_consults,
        )