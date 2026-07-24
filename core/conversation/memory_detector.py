"""
Memory Detector

Detects personal facts in user messages using deterministic pattern matching.

This module recognises natural memory statements without requiring
the keyword "remember". It does not save memories, call AI providers,
or modify any other module.

Examples of recognised statements:
    "My name is Ludovic."
    "My drink is coffee."
    "My favourite colour is blue."
    "I drive a Ranger."
    "I work as a painter."
    "My wife's name is Catriana."
    "I have 2 dogs."
    "Their names are Rex and Tom."
    "My dogs are Rex and Tom."
    "I work at Academy of Healthcare."
    "And my favourite food is pizza."
"""

import logging
import re
from typing import Optional

from core.conversation.memory_detection import MemoryDetection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Leading conjunction strip
# GC-007: statements like "And my favourite food is pizza." have a leading
# conjunction that breaks all ^-anchored patterns. Strip them before matching.
# ---------------------------------------------------------------------------
_LEADING_CONJUNCTION = re.compile(
    r"^(?:and|but|also|plus|oh and|oh|well)\s+",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# GC-012: Context-aware continuation patterns
# Matches a pet quantity hint from SessionContext ("3 cats", "2 dogs", etc.)
# Used by detect_with_context() — never looked up internally.
# ---------------------------------------------------------------------------
_PET_CONTEXT_RE = re.compile(
    r"^(\d+|a|an|one|two|three|four|five|some)\s+"
    r"(?:dogs?|cats?|pets?|birds?|fish|rabbits?|hamsters?)$",
    re.IGNORECASE,
)

# Matches a bare name or comma-separated name list ("Tom, Tim and Tam")
_NAME_LIST_RE = re.compile(
    r"^[A-Z][a-z]+(?:(?:[,\s]+(?:and\s+)?)[A-Z][a-z]+)*\.?$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

_FIXED_KEY_PATTERNS: list[tuple[re.Pattern, str, int, float]] = [
    # "My name is Ludovic"
    (
        re.compile(r"^my name is (.+)", re.IGNORECASE),
        "name",
        1,
        0.95
    ),
    # "My favourite colour is blue" / "My favorite color is blue"
    (
        re.compile(r"^my favou?rite colou?r is (.+)", re.IGNORECASE),
        "favourite colour",
        1,
        0.95
    ),
    # "My favourite food is pizza"
    (
        re.compile(r"^my favou?rite food is (.+)", re.IGNORECASE),
        "favourite food",
        1,
        0.95
    ),
    # "My favourite drink is coffee"
    (
        re.compile(r"^my favou?rite drink is (.+)", re.IGNORECASE),
        "favourite drink",
        1,
        0.95
    ),
    # "My favourite sport is AFL"
    (
        re.compile(r"^my favou?rite sport is (.+)", re.IGNORECASE),
        "favourite sport",
        1,
        0.95
    ),
    # "My favourite team is Brisbane Lions"
    (
        re.compile(r"^my favou?rite team is (.+)", re.IGNORECASE),
        "favourite team",
        1,
        0.95
    ),
    # "I drive a Ranger" / "I drive an SUV"
    (
        re.compile(r"^i drive (?:a |an )?(.+)", re.IGNORECASE),
        "car",
        1,
        0.90
    ),
    # "I work as a painter" / "I work as an engineer"
    (
        re.compile(r"^i work as (?:a |an )?(.+)", re.IGNORECASE),
        "occupation",
        1,
        0.90
    ),
    # "I work at Academy of Healthcare" / "I work for Google"
    (
        re.compile(r"^i work (?:at|for) (.+)", re.IGNORECASE),
        "workplace",
        1,
        0.90
    ),
    # "I live in Melbourne"
    (
        re.compile(r"^i live in (.+)", re.IGNORECASE),
        "location",
        1,
        0.90
    ),
    # "I am from Brisbane" / "I'm from Brisbane"
    (
        re.compile(r"^i(?:'m| am) from (.+)", re.IGNORECASE),
        "hometown",
        1,
        0.85
    ),
    # "I have 2 dogs" / "I have a cat" / "I've got three fish"
    (
        re.compile(r"^i(?:'ve| have| got|'ve got) (\d+|a|an|some|two|three|four|five) ([a-z]+s?)", re.IGNORECASE),
        "pets",
        0,   # special: value built from groups 1+2 in detect()
        0.88
    ),
    # "Their names are Rex and Tom" / "His name is Rex"
    (
        re.compile(r"^(?:their|his|her|its) names? (?:is|are) (.+)", re.IGNORECASE),
        "pet names",
        1,
        0.88
    ),
    # "My dogs are Rex and Tom" / "My cats are Bella and Max"
    # GC-007: alternative phrasing for pet name assignment
    (
        re.compile(r"^my (?:dogs?|cats?|pets?|birds?|fish|rabbits?|hamsters?) (?:is|are) (.+)", re.IGNORECASE),
        "pet names",
        1,
        0.88
    ),
]

_DYNAMIC_KEY_PATTERNS: list[tuple[re.Pattern, int, int, float]] = [
    # "My drink is coffee" — key = "drink", value = "coffee"
    (
        re.compile(r"^my ([a-z ]{2,30}) is (.+)", re.IGNORECASE),
        1,
        2,
        0.75
    ),
    # "My wife's name is Catriana" — key = "wife's name", value = "Catriana"
    (
        re.compile(r"^my ([a-z']{2,30}(?:'s)? [a-z ]{2,20}) is (.+)", re.IGNORECASE),
        1,
        2,
        0.80
    ),
]

_MIN_CONFIDENCE: float = 0.70


class MemoryDetector:
    """
    Detects personal facts in user messages using deterministic rule matching.

    Recognises natural memory statements without requiring the keyword
    "remember". Returns a MemoryDetection if a personal fact is found,
    or None if the message does not appear to contain one.

    This class has no side effects. It does not save memories, modify
    context, call AI providers, or interact with MemoryManager.
    """

    def detect(self, message: str) -> Optional[MemoryDetection]:
        """
        Attempt to detect a personal fact in the given message.

        Tries fixed key patterns first — they are more specific and
        receive higher confidence. Falls back to dynamic key patterns
        if no fixed pattern matches.
        """
        if not message or not message.strip():
            return None

        cleaned = message.strip().rstrip(".")

        # GC-007: strip leading conjunctions so "And my favourite food is
        # pizza." matches the same patterns as "My favourite food is pizza."
        cleaned = _LEADING_CONJUNCTION.sub("", cleaned).strip().rstrip(".")

        # Try fixed key patterns first.
        result = self._match_fixed(cleaned)
        if result is not None:
            return result

        # Fall back to dynamic key patterns.
        return self._match_dynamic(cleaned)

    def detect_with_context(self, message: str, context_hint: str = "") -> Optional[MemoryDetection]:
        """
        Context-aware detection.

        The Agent supplies a context hint; the detector classifies the
        message. This method never performs lookups — it only uses what
        the caller provides.

        GC-012: When context_hint indicates pets ("3 cats", "2 dogs")
        and the message looks like a bare name list ("Tom, Tim and Tam."),
        infer it as a pet names statement.

        Args:
            message:      The user's raw message.
            context_hint: A hint from the Agent about current context
                          (e.g. "3 cats", "2 dogs"). Never looked up here.

        Returns:
            MemoryDetection if a fact is detected, None otherwise.
        """
        # Try standard detection first
        result = self.detect(message)
        if result:
            return result

        # GC-012: context-aware bare name list inference
        if not context_hint:
            return None

        # Context hint must look like a pet quantity
        if not _PET_CONTEXT_RE.match(context_hint.strip()):
            return None

        # Message must look like a name or comma-separated name list
        stripped = message.strip().rstrip(".")
        if not _NAME_LIST_RE.match(stripped):
            return None

        logger.debug(
            "[DETECTOR] Inferred pet names from context %r + message %r",
            context_hint, stripped,
        )
        return MemoryDetection(
            key="pet names",
            value=stripped,
            confidence=0.82,
        )

    def _match_fixed(self, message: str) -> Optional[MemoryDetection]:
        """Match against fixed key patterns."""
        for pattern, key, value_group, confidence in _FIXED_KEY_PATTERNS:
            match = pattern.match(message)
            if match:
                # Special case: pets pattern uses groups 1+2 to build value
                if key == "pets" and value_group == 0:
                    value = f"{match.group(1)} {match.group(2)}".strip()
                else:
                    value = match.group(value_group).strip()

                if value:
                    detection = MemoryDetection(
                        key=key,
                        value=value,
                        confidence=confidence
                    )
                    logger.debug(
                        "Fixed pattern matched — key: %r, value: %r, confidence: %.2f",
                        detection.key,
                        detection.value,
                        detection.confidence
                    )
                    return detection

        return None

    def _match_dynamic(self, message: str) -> Optional[MemoryDetection]:
        """Match against dynamic key patterns."""
        for pattern, key_group, value_group, confidence in _DYNAMIC_KEY_PATTERNS:
            match = pattern.match(message)
            if match:
                key = match.group(key_group).strip().lower()
                value = match.group(value_group).strip()

                if not key or not value:
                    continue

                if confidence < _MIN_CONFIDENCE:
                    logger.debug(
                        "Dynamic pattern matched but confidence too low — "
                        "key: %r, value: %r, confidence: %.2f",
                        key, value, confidence
                    )
                    continue

                detection = MemoryDetection(
                    key=key,
                    value=value,
                    confidence=confidence
                )
                logger.debug(
                    "Dynamic pattern matched — key: %r, value: %r, confidence: %.2f",
                    detection.key,
                    detection.value,
                    detection.confidence
                )
                return detection

        return None