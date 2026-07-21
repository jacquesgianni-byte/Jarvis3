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
    "I work at Academy of Healthcare."
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

        # Try fixed key patterns first.
        result = self._match_fixed(cleaned)
        if result is not None:
            return result

        # Fall back to dynamic key patterns.
        return self._match_dynamic(cleaned)

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