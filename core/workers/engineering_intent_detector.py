"""
Jarvis Engineering Intent Detector (Genesis-027 Sprint-004)

Detects whether a user request is an engineering task that should be
routed to the Worker Operating System rather than to AI.

Responsibilities:
    - Analyse a natural language request
    - Return an EngineeringIntent with is_engineering flag and confidence
    - Remain completely independent from execution

Design:
    Initially keyword-based — fast and deterministic.
    The router asks a question: is this engineering?
    It never needs to know how the answer is determined.
    Future improvements (LLM classification, rules, confidence scores)
    can be made here without touching the router.

Genesis-027 Sprint-004.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineeringIntent:
    """
    Result of engineering intent detection.

    Attributes:
        is_engineering: True if the request should go to the Worker OS.
        confidence:     Detection confidence (0.0-1.0).
        matched_signals: The signal names that triggered detection.
    """
    is_engineering:  bool
    confidence:      float
    matched_signals: tuple[str, ...]

    @classmethod
    def positive(cls, confidence: float, signals: list[str]) -> "EngineeringIntent":
        return cls(is_engineering=True, confidence=confidence,
                   matched_signals=tuple(signals))

    @classmethod
    def negative(cls) -> "EngineeringIntent":
        return cls(is_engineering=False, confidence=0.0, matched_signals=())


# ---------------------------------------------------------------------------
# Signal patterns
# Data-driven — no if/elif chains.
# Adding a new signal = one new entry here.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntentSignal:
    name:     str
    patterns: tuple[str, ...]
    weight:   float   # contribution to confidence


_INTENT_SIGNALS: list[IntentSignal] = [
    IntentSignal(
        name="review",
        patterns=(
            r"\b(?:review|analyse|analyze|inspect|audit|evaluate|assess)\b",
            r"\b(?:architecture|design|structure|module|component|system)\b",
        ),
        weight=0.4,
    ),
    IntentSignal(
        name="implement",
        patterns=(
            r"\b(?:implement|add|create|build|write|develop|introduce|extend)\b",
            r"\b(?:refactor|improve|optimise|optimize|clean up)\b",
        ),
        weight=0.4,
    ),
    IntentSignal(
        name="debug",
        patterns=(
            r"\b(?:debug|diagnose|investigate|analyse|analyze|inspect|trace)\b",
            r"\b(?:bug|error|issue|problem|failure|crash|broken|not working)\b",
        ),
        weight=0.4,
    ),
    IntentSignal(
        name="validate",
        patterns=(
            r"\b(?:test|tests|suite|pytest|validate|verify)\b",
            r"\b(?:make sure|ensure|confirm|check).*\b(?:pass|green|work)\b",
        ),
        weight=0.3,
    ),
    IntentSignal(
        name="fix",
        patterns=(
            r"\b(?:fix|patch|resolve|correct|repair)\b",
        ),
        weight=0.35,
    ),
]

_COMPILED_SIGNALS: list[tuple[IntentSignal, list[re.Pattern]]] = [
    (sig, [re.compile(p, re.IGNORECASE) for p in sig.patterns])
    for sig in _INTENT_SIGNALS
]

_CONFIDENCE_THRESHOLD = 0.15


class EngineeringIntentDetector:
    """
    Detects engineering intent in user requests.

    The router asks: is_engineering?
    This class answers — the router never knows how.

    Public API:
        detect(request) -> EngineeringIntent
    """

    def detect(self, request: str) -> EngineeringIntent:
        """
        Detect whether a request is an engineering task.

        Args:
            request: The user's raw message.

        Returns:
            EngineeringIntent with is_engineering flag and confidence.
        """
        if not request or not request.strip():
            return EngineeringIntent.negative()

        matched_signals = []
        total_weight = 0.0

        for signal, patterns in _COMPILED_SIGNALS:
            for pattern in patterns:
                if pattern.search(request):
                    matched_signals.append(signal.name)
                    total_weight += signal.weight
                    break

        # Normalise confidence to 0-1
        max_possible = sum(s.weight for s in _INTENT_SIGNALS)
        confidence = min(total_weight / max_possible, 1.0)

        if confidence >= _CONFIDENCE_THRESHOLD:
            logger.debug(
                "[ENG_INTENT] Engineering intent detected: signals=%s conf=%.2f",
                matched_signals, confidence,
            )
            return EngineeringIntent.positive(confidence, matched_signals)

        return EngineeringIntent.negative()
