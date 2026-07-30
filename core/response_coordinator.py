"""
Response Coordinator (Genesis-030 Sprint-001)

Classifies expected response duration and generates immediate
acknowledgements so the UI can display something while longer
operations complete in the background.

Responsibilities:
    - Classify requests as FAST / MEDIUM / LONG
    - Generate natural acknowledgement phrases for MEDIUM/LONG requests
      via pluggable AcknowledgementStrategy
    - Expose a clean API for future streaming providers to plug into

Classification rules:
    FAST   -- memory recall, property lookup, greetings, calculator, time
              No acknowledgement. Answer immediately.
    MEDIUM -- AI response, web lookup, summarisation
              Immediate acknowledgement. Then final answer.
    LONG   -- coding, document generation, large analysis
              Immediate acknowledgement + optional progress. Then final answer.

Architecture:
    ProcessWorker (desktop)
        -> ResponseCoordinator.classify()        classify before calling Agent
        -> AcknowledgementStrategy.generate()    emit acknowledgement text
        -> Agent.process()                       runs as before
        -> emit finished signal                  final response

Genesis-030 Sprint-001.
"""

from __future__ import annotations

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response duration categories
# ---------------------------------------------------------------------------

class ResponseCategory(str, Enum):
    FAST   = "fast"
    MEDIUM = "medium"
    LONG   = "long"


# ---------------------------------------------------------------------------
# Operation types
# ---------------------------------------------------------------------------

class OperationType(str, Enum):
    RECALL      = "recall"
    EXPLAIN     = "explain"
    SEARCH      = "search"
    SUMMARISE   = "summarise"
    COMPARE     = "compare"
    RECOMMEND   = "recommend"
    TRANSLATE   = "translate"
    WRITE       = "write"
    CODE        = "code"
    ANALYSE     = "analyse"
    GENERAL     = "general"


# ---------------------------------------------------------------------------
# AcknowledgementStrategy (pluggable)
# ---------------------------------------------------------------------------

class AcknowledgementStrategy(ABC):
    """
    Abstract base for acknowledgement generation.

    Subclass to support different tones, languages, voice modes,
    or accessibility preferences without touching ResponseCoordinator.
    """

    @abstractmethod
    def generate(
        self,
        operation: OperationType,
        topic: Optional[str],
        category: ResponseCategory,
    ) -> str:
        """Generate an acknowledgement string."""


class DefaultAcknowledgementStrategy(AcknowledgementStrategy):
    """
    Default conversational acknowledgement strategy.

    Uses operation-aware templates and topic injection where available.
    Cycles through phrase variants to avoid repetition.
    """

    _TEMPLATES: dict[OperationType, list[str]] = {
        OperationType.EXPLAIN:   [
            "Let me explain {topic}...",
            "Sure, I'll explain {topic}...",
            "Good question -- let me walk through {topic}...",
        ],
        OperationType.SEARCH:    [
            "Searching for {topic}...",
            "Let me look that up...",
            "On it -- searching now...",
        ],
        OperationType.SUMMARISE: [
            "Summarising {topic}...",
            "Let me put together a summary...",
            "Working on that summary...",
        ],
        OperationType.COMPARE:   [
            "Let me compare {topic}...",
            "Comparing those for you...",
        ],
        OperationType.RECOMMEND: [
            "Let me think about what to recommend...",
            "Sure, I'll find some options...",
        ],
        OperationType.TRANSLATE: [
            "Translating {topic}...",
            "On it...",
        ],
        OperationType.WRITE:     [
            "Let me draft {topic}...",
            "Writing {topic} now...",
            "Sure, I'll put something together...",
        ],
        OperationType.CODE:      [
            "Let me work on that code...",
            "Sure, I'll write {topic}...",
            "On it -- this may take a moment...",
        ],
        OperationType.ANALYSE:   [
            "Analysing {topic}...",
            "Let me work through that carefully...",
            "This may take a moment -- analysing now...",
        ],
        OperationType.GENERAL:   [
            "Let me think about that...",
            "Sure, give me a moment...",
            "On it...",
            "One moment...",
            "Working on that...",
        ],
    }

    def __init__(self) -> None:
        self._counters: dict[OperationType, int] = {}

    def generate(
        self,
        operation: OperationType,
        topic: Optional[str],
        category: ResponseCategory,
    ) -> str:
        phrases = self._TEMPLATES.get(operation, self._TEMPLATES[OperationType.GENERAL])
        idx = self._counters.get(operation, 0) % len(phrases)
        self._counters[operation] = idx + 1

        template = phrases[idx]
        if topic and "{topic}" in template:
            return template.format(topic=topic)
        result = template.replace(" {topic}", "").replace("{topic}", "")
        return result.strip()


# ---------------------------------------------------------------------------
# Classification patterns
# ---------------------------------------------------------------------------

_LONG_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"\b(?:write|generate|create|build|implement|code|develop)\b"
        r".*\b(?:code|script|function|class|module|program|app|application|document|report|essay|article)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:analyse|analyze|review|audit)\b"
        r".*\b(?:file|document|codebase|repo|repository|project)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:summarise|summarize)\b"
        r".*\b(?:document|file|report|article|paper|book)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:refactor|debug|fix|optimise|optimize)\b"
        r".*\b(?:code|function|class|module|script)\b",
        re.IGNORECASE,
    ),
]

_MEDIUM_PATTERNS: list[tuple[re.Pattern, OperationType]] = [
    (re.compile(r"\b(?:explain|describe)\b", re.IGNORECASE), OperationType.EXPLAIN),
    (re.compile(r"\b(?:what is|what are|how does|how do|why does|why do|how would|what would)\b", re.IGNORECASE), OperationType.EXPLAIN),
    (re.compile(r"\b(?:compare|contrast|difference between|similarities between)\b", re.IGNORECASE), OperationType.COMPARE),
    (re.compile(r"\b(?:search|look up|find|google|web search|browse)\b", re.IGNORECASE), OperationType.SEARCH),
    (re.compile(r"\b(?:summarise|summarize|summary of)\b", re.IGNORECASE), OperationType.SUMMARISE),
    (re.compile(r"\b(?:translate|convert)\b", re.IGNORECASE), OperationType.TRANSLATE),
    (re.compile(r"\b(?:recommend|suggest|advise)\b", re.IGNORECASE), OperationType.RECOMMEND),
    (re.compile(r"\b(?:help me|help with)\b", re.IGNORECASE), OperationType.GENERAL),
    (re.compile(r"\b(?:write|draft|compose)\b.*\b(?:email|message|letter|reply|response|post)\b", re.IGNORECASE), OperationType.WRITE),
]

_FAST_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(?:hi|hello|hey|good morning|good afternoon|good evening|howdy)\b", re.IGNORECASE),
    re.compile(r"\bhow old is\b", re.IGNORECASE),
    re.compile(r"\bwhat colou?r is\b", re.IGNORECASE),
    re.compile(r"\bwhat is (?:my|his|her|its|their)\b", re.IGNORECASE),
    re.compile(r"\bwho is\b", re.IGNORECASE),
    re.compile(r"\bremember\b", re.IGNORECASE),
    re.compile(r"\bwhat time is it\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is) the time\b", re.IGNORECASE),
    re.compile(r"^(?:exit|quit|bye|goodbye|stop)\b", re.IGNORECASE),
    re.compile(r"^(?:inspect|show|/)\w*", re.IGNORECASE),
    re.compile(r"\btell me about\b", re.IGNORECASE),
    re.compile(r"\bwhat about\b", re.IGNORECASE),
    re.compile(r"\bback to\b", re.IGNORECASE),
]

_TOPIC_EXTRACT: dict[str, re.Pattern] = {
    op: re.compile(
        rf"\b{op}\s+(.{{3,50}}?)(?:\.|$|\?|,)",
        re.IGNORECASE,
    )
    for op in [
        "explain", "describe", "summarise", "summarize",
        "search for", "find", "compare", "write", "generate",
        "create", "translate", "analyse", "analyze",
    ]
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClassificationResult:
    """
    Result of classifying a user request.

    category:        FAST / MEDIUM / LONG
    operation:       What kind of operation this is
    topic:           Optional extracted topic string
    acknowledgement: Text to display immediately (empty for FAST)
    needs_ack:       True if acknowledgement should be shown
    """
    category:        ResponseCategory
    operation:       OperationType
    topic:           Optional[str]
    acknowledgement: str
    needs_ack:       bool

    @classmethod
    def fast(cls) -> "ClassificationResult":
        return cls(
            category=ResponseCategory.FAST,
            operation=OperationType.RECALL,
            topic=None,
            acknowledgement="",
            needs_ack=False,
        )


# ---------------------------------------------------------------------------
# ResponseCoordinator
# ---------------------------------------------------------------------------

class ResponseCoordinator:
    """
    Classifies requests and generates immediate acknowledgements.

    Accepts an optional AcknowledgementStrategy -- defaults to
    DefaultAcknowledgementStrategy. Swap the strategy for different
    tones, locales, or voice modes without changing this class.

    Public API:
        classify(text) -> ClassificationResult
    """

    def __init__(
        self,
        strategy: Optional[AcknowledgementStrategy] = None,
    ) -> None:
        self._strategy = strategy or DefaultAcknowledgementStrategy()

    def classify(self, text: str) -> ClassificationResult:
        """
        Classify a request as FAST, MEDIUM, or LONG.

        Args:
            text: The user's raw message.

        Returns:
            ClassificationResult with category, operation, topic and acknowledgement.
        """
        if not text or not text.strip():
            return ClassificationResult.fast()

        # FAST -- local operations, no AI needed
        for pattern in _FAST_PATTERNS:
            if pattern.search(text):
                logger.debug("[COORD] FAST: %r", text[:40])
                return ClassificationResult.fast()

        # LONG -- check before MEDIUM (more specific)
        for pattern in _LONG_PATTERNS:
            if pattern.search(text):
                topic = self._extract_topic(text)
                operation = self._infer_long_operation(text)
                ack = self._strategy.generate(operation, topic, ResponseCategory.LONG)
                logger.info("[COORD] LONG: %r -> ack=%r", text[:40], ack)
                return ClassificationResult(
                    category=ResponseCategory.LONG,
                    operation=operation,
                    topic=topic,
                    acknowledgement=ack,
                    needs_ack=True,
                )

        # MEDIUM
        for pattern, operation in _MEDIUM_PATTERNS:
            if pattern.search(text):
                topic = self._extract_topic(text)
                ack = self._strategy.generate(operation, topic, ResponseCategory.MEDIUM)
                logger.info("[COORD] MEDIUM: %r -> ack=%r", text[:40], ack)
                return ClassificationResult(
                    category=ResponseCategory.MEDIUM,
                    operation=operation,
                    topic=topic,
                    acknowledgement=ack,
                    needs_ack=True,
                )

        # Default: FAST
        logger.debug("[COORD] FAST (default): %r", text[:40])
        return ClassificationResult.fast()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_topic(self, text: str) -> Optional[str]:
        """Extract a topic phrase from the request text."""
        for _, pattern in _TOPIC_EXTRACT.items():
            m = pattern.search(text)
            if m:
                topic = m.group(1).strip().rstrip(".,?!")
                if len(topic) >= 3:
                    return topic
        return None

    def _infer_long_operation(self, text: str) -> OperationType:
        """Infer the operation type for a LONG request."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["code", "script", "function", "class", "implement", "program"]):
            return OperationType.CODE
        if any(w in text_lower for w in ["analyse", "analyze", "review", "audit"]):
            return OperationType.ANALYSE
        if any(w in text_lower for w in ["summarise", "summarize", "summary"]):
            return OperationType.SUMMARISE
        if any(w in text_lower for w in ["write", "generate", "create", "document", "report", "essay"]):
            return OperationType.WRITE
        return OperationType.GENERAL
