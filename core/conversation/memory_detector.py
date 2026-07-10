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
"""

import logging
import re
from typing import Optional

from core.conversation.memory_detection import MemoryDetection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pattern definitions
#
# Each pattern is a tuple of:
#   (compiled regex, key_group, value_group, confidence)
#
# key_group:   The regex group index that captures the memory key.
#              Use 0 to indicate a fixed key defined in the pattern itself.
# value_group: The regex group index that captures the memory value.
# confidence:  A float representing pattern specificity.
#              More specific patterns receive higher confidence.
# ---------------------------------------------------------------------------

# Fixed key patterns — the key is known from the pattern itself.
# These use a lambda to derive the key rather than a capture group.

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
]

# Dynamic key patterns — the key is captured from the message itself.
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

# Minimum confidence threshold — detections below this are discarded.
_MIN_CONFIDENCE: float = 0.70


class MemoryDetector:
    """
    Detects personal facts in user messages using deterministic rule matching.

    Recognises natural memory statements without requiring the keyword
    "remember". Returns a MemoryDetection if a personal fact is found,
    or None if the message does not appear to contain one.

    This class has no side effects. It does not save memories, modify
    context, call AI providers, or interact with MemoryManager.

    Example usage:
        detector = MemoryDetector()

        result = detector.detect("My name is Ludovic.")
        # MemoryDetection(key="name", value="Ludovic", confidence=0.95)

        result = detector.detect("What time is it?")
        # None
    """

    def detect(self, message: str) -> Optional[MemoryDetection]:
        """
        Attempt to detect a personal fact in the given message.

        Tries fixed key patterns first — they are more specific and
        receive higher confidence. Falls back to dynamic key patterns
        if no fixed pattern matches.

        Args:
            message: The raw user message to analyse.

        Returns:
            A MemoryDetection if a personal fact is detected.
            None if no memory statement is recognised.
        """

        if not message or not message.strip():
            return None

        cleaned = message.strip().rstrip(".")

        # Try fixed key patterns first.
        result = self._match_fixed(cleaned)
        if result is not None:
            return result

        # Fall back to dynamic key patterns.
        return self._match_dynamic(cleaned)

    def _match_fixed(self, message: str) -> Optional[MemoryDetection]:
        """
        Attempt to match the message against fixed key patterns.

        Fixed patterns know the key in advance — only the value
        is captured from the message.

        Args:
            message: The cleaned user message.

        Returns:
            A MemoryDetection if a fixed pattern matches, or None.
        """

        for pattern, key, value_group, confidence in _FIXED_KEY_PATTERNS:
            match = pattern.match(message)
            if match:
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
        """
        Attempt to match the message against dynamic key patterns.

        Dynamic patterns capture both the key and value from the message.
        They are less specific than fixed patterns and receive lower confidence.

        Args:
            message: The cleaned user message.

        Returns:
            A MemoryDetection if a dynamic pattern matches and confidence
            meets the minimum threshold, or None.
        """

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