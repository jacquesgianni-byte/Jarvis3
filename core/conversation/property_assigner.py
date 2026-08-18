"""
Property Assigner (Genesis-028 Sprint-001)

Detects and stores arbitrary property assignments for recognised entities.

Responsibilities:
    - Detect "X is Y", "X weighs Y", "X is located in Y" patterns
    - Resolve the subject to a known entity in any EntityGroup
    - Store property as key-value on that entity via KnowledgeEngine
    - Detect property queries: "How old is Leo?", "What colour is Rex?"
    - Detect group-property queries: "Which printer is offline?"

Design constraints:
    - No hardcoded entity types
    - No hardcoded property names
    - Data-driven pattern matching throughout
    - No AI calls
    - Deterministic — same input → same output

Architecture position:
    Agent._route()
        └── PropertyAssigner.detect_assignment()   ← assignment path
        └── PropertyAssigner.detect_query()        ← query path
                └── KnowledgeEngine.store_memory() / recall_memory()
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Assignment patterns
#
# Each entry: (compiled regex, property_key_template, value_group_index)
# Group 1 is always the subject. Group 2 is always the value.
# property_key_template may be a string or None (inferred from verb/preposition).
# ---------------------------------------------------------------------------

_ASSIGNMENT_PATTERNS: list[tuple[re.Pattern, Optional[str]]] = [
    # More specific patterns first — order matters.

    # "Server Alpha is located in Sydney" / "Voron is located at the garage"
    (re.compile(
        r"^(.+?)\s+is\s+located\s+(?:in|at|near)\s+(.+?)\.?$",
        re.IGNORECASE,
    ), "location"),

    # "Tom weighs 35 kg" / "Alpha weighs 1.2 tonnes"
    (re.compile(
        r"^([A-Za-z][\w\s\-]*?)\s+weighs?\s+(.+?)\.?$",
        re.IGNORECASE,
    ), "weight"),

    # "Leo likes football." / "Rex enjoys running." / "Lucas plays guitar."
    (re.compile(
        r"^(.+?)\s+(?:likes?|enjoys?|loves?|plays?|hates?|prefers?)\s+(.+?)\.?$",
        re.IGNORECASE,
    ), "interest"),

    # "Lucas is 14" / "Rex is brown" / "Voron is offline"
    # Generic — must come after more specific "is located in" pattern.
    (re.compile(
        r"^([A-Za-z][\w\s\-]*?)\s+is\s+(?!a\b|an\b|the\b)(.+?)\.?$",
        re.IGNORECASE,
    ), None),
]


# ---------------------------------------------------------------------------
# JTI-001 Fix 2 (P2): Conjunction split pattern
# Matches "Lucas is 14 and Leo is 8" to extract two independent assignments.
# Group 1: first subject, Group 2: first value,
# Group 3: second subject, Group 4: second value.
# ---------------------------------------------------------------------------
_CONJUNCTION_ASSIGNMENT_RE = re.compile(
    r"^([A-Za-z][\w\-]*?)\s+is\s+(.+?)\s+and\s+([A-Za-z][a-z][\w\-]*)\s+is\s+(.+?)\s*\.?$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Property key inference
#
# When the assignment pattern doesn't fix the key (None template),
# infer a canonical key from the value string.
# Order matters — more specific first.
# ---------------------------------------------------------------------------

_PROPERTY_VALUE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Age — "14", "8 years old", "14 years"
    (re.compile(r"^\d+\s*(?:years?\s*old|yrs?\.?\s*old|years?)?$", re.IGNORECASE), "age"),
    # Weight — "35 kg", "12 lbs", "1.2 tonnes"
    (re.compile(r"^\d+(?:\.\d+)?\s*(?:kg|kgs?|lbs?|pounds?|tonnes?|grams?|g)\b", re.IGNORECASE), "weight"),
    # Colour — common colour words
    (re.compile(
        r"^(?:red|orange|yellow|green|blue|purple|pink|brown|black|white|grey|gray|"
        r"golden|silver|cream|beige|tan|teal|navy|maroon|violet|indigo)(?:\s+and\s+\w+)?$",
        re.IGNORECASE,
    ), "colour"),
    # Status — known status words
    (re.compile(
        r"^(?:online|offline|active|inactive|enabled|disabled|running|stopped|"
        r"pending|complete|completed|done|open|closed|available|unavailable)$",
        re.IGNORECASE,
    ), "status"),
    # Priority
    (re.compile(r"^(?:high|medium|low|critical|urgent)\s+priority$", re.IGNORECASE), "priority"),
    # Location — "in X", "at X"
    (re.compile(r"^(?:in|at|near)\s+.+", re.IGNORECASE), "location"),
]

# ---------------------------------------------------------------------------
# Query patterns
#
# Detect property queries about a specific entity.
# Group 1 = property hint, Group 2 = entity name
# ---------------------------------------------------------------------------

_ATTRIBUTE_QUERY_PATTERNS: list[tuple[re.Pattern, Optional[str]]] = [
    # "How old is Leo?" → property=age, entity=Leo
    (re.compile(r"\bhow\s+old\s+is\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE), "age"),
    # "What colour is Rex?" / "What color is Rex?"
    (re.compile(r"\bwhat\s+colou?r\s+is\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE), "colour"),
    # "What is Rex's colour?" / "What is Leo's age?"
    (re.compile(r"\bwhat\s+is\s+([A-Za-z][\w\-]*)'s?\s+(\w+)\b", re.IGNORECASE), None),
    # "How much does Tom weigh?" / "What does Tom weigh?"
    (re.compile(r"\bhow\s+much\s+does\s+([A-Za-z][\w\-]*)\s+weigh\b", re.IGNORECASE), "weight"),
    (re.compile(r"\bwhat\s+does\s+([A-Za-z][\w\-]*)\s+weigh\b", re.IGNORECASE), "weight"),
    # "Where is Voron?" / "Where is Server Alpha?"
    (re.compile(r"\bwhere\s+is\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE), "location"),
    # "What does Leo like?" / "What does Rex enjoy?"
    (re.compile(r"\bwhat\s+does\s+([A-Za-z][\w\-]*)\s+(?:like|enjoy|love|play|prefer)\b.*\?", re.IGNORECASE), "interest"),
    # Without question mark too
    (re.compile(r"\bwhat\s+does\s+([A-Za-z][\w\-]*)\s+(?:like|enjoy|love|play|prefer)\b", re.IGNORECASE), "interest"),
    # "Is Voron online?" / "Is Voron offline?"
    (re.compile(r"\bis\s+([A-Za-z][\w\-]*)\s+(online|offline|active|inactive|running|stopped)\b", re.IGNORECASE), "status"),
]

# ---------------------------------------------------------------------------
# Group-property query patterns
#
# "Which printer is offline?" → scan group members for status=offline
# "Which child is 14?" → scan person group for age=14
# ---------------------------------------------------------------------------

_GROUP_QUERY_PATTERNS: list[re.Pattern] = [
    # "Which printer is offline?" / "Which dog is brown?"
    re.compile(
        r"\bwhich\s+(\w+)\s+is\s+(.+?)\??$",
        re.IGNORECASE,
    ),
    # "Which of my dogs is brown?"
    re.compile(
        r"\bwhich\s+(?:of\s+(?:my|the)\s+)?(\w+)\s+is\s+(.+?)\??$",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Stop subjects — single words that are NOT entity names
# ---------------------------------------------------------------------------

_STOP_SUBJECTS: frozenset[str] = frozenset({
    "he", "she", "it", "they", "we", "i", "you",
    "that", "this", "there", "here",
    "my", "your", "his", "her", "their", "our",
    "a", "an", "the",
    "what", "who", "where", "when", "why", "how",
    "jarvis", "ok", "okay", "yes", "no",
})


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PropertyAssignment:
    """
    Result of detecting a property assignment statement.

    e.g. "Lucas is 14." → subject="lucas", property_key="age", value="14"
    """
    subject:      str    # lowercased entity name
    property_key: str    # canonical key ("age", "colour", "status", …)
    value:        str    # raw value string
    confidence:   float = 0.88


@dataclass(frozen=True)
class PropertyQuery:
    """
    Result of detecting a property query about a specific entity.

    e.g. "How old is Leo?" → subject="leo", property_key="age"
    """
    subject:      str
    property_key: str
    confidence:   float = 0.90


@dataclass(frozen=True)
class GroupPropertyQuery:
    """
    Result of detecting a group-property query.

    e.g. "Which printer is offline?" → kind_hint="printer", property_key="status", value="offline"
    """
    kind_hint:    str    # raw word from query ("printer", "dog", "child")
    property_key: str    # inferred property key
    value:        str    # value to match
    confidence:   float = 0.85


# ---------------------------------------------------------------------------
# PropertyAssigner
# ---------------------------------------------------------------------------

class PropertyAssigner:
    """
    Detects property assignments and queries in natural language.

    Stateless. No KnowledgeEngine dependency — callers pass entity lists
    for resolution and call KnowledgeEngine themselves.

    Public API:
        detect_assignment(text) -> Optional[PropertyAssignment]
        detect_query(text)      -> Optional[PropertyQuery]
        detect_group_query(text) -> Optional[GroupPropertyQuery]
    """

    def detect_assignment(self, text: str) -> Optional[PropertyAssignment]:
        """
        Detect a property assignment statement.

        Matches patterns like:
            "Lucas is 14."
            "Rex is brown."
            "Tom weighs 35 kg."
            "Voron is offline."
            "Server Alpha is located in Sydney."

        Args:
            text: The user's raw message.

        Returns:
            PropertyAssignment if detected, None otherwise.
        """
        if not text or not text.strip():
            return None

        # Questions are never assignments
        if text.strip().endswith("?"):
            return None

        text = text.strip()

        # JTI-001 Fix 1b: strip leading correction qualifiers so
        # "actually, leo is 8" / "no, leo is 8" / "wait, leo is 8"
        # match the same patterns as "leo is 8".
        text = re.sub(
            r"^(?:actually|no|wait|sorry|correction|nope|hmm|oh)[,\s]+",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        for pattern, fixed_key in _ASSIGNMENT_PATTERNS:
            m = pattern.match(text)
            if not m:
                continue

            subject_raw = m.group(1).strip()
            value_raw = m.group(2).strip().rstrip(".")
            # Strip update qualifiers ("now", "currently") before key inference
            value_raw = re.sub(r"^(?:now|currently)\s+", "", value_raw, flags=re.IGNORECASE)

            # Reject stop subjects
            if subject_raw.lower() in _STOP_SUBJECTS:
                continue

            # Reject imperative memory triggers as subject prefix.
            # "Remember that Leo is 8" must not produce subject="remember that leo".
            # These messages belong to the MemorySkill explicit-memory pathway.
            _MEMORY_TRIGGERS = {"remember", "note", "store", "save"}
            if subject_raw.lower().split()[0] in _MEMORY_TRIGGERS:
                continue

            # Reject subjects containing possessive words
            _subject_words = set(subject_raw.lower().split())
            if _subject_words & {"my", "your", "his", "her", "their", "our", "its"}:
                continue

            # Reject multi-word subjects that look like sentences
            if len(subject_raw.split()) > 3:
                continue

            # Reject if subject contains punctuation (likely a sentence fragment)
            if re.search(r"[,;:!]", subject_raw):
                continue

            # Determine property key
            if fixed_key:
                property_key = fixed_key
            else:
                property_key = self._infer_property_key(value_raw)

            logger.info(
                "[PROPERTY] Assignment detected: subject=%r key=%r value=%r",
                subject_raw, property_key, value_raw,
            )

            return PropertyAssignment(
                subject=subject_raw.lower(),
                property_key=property_key,
                value=value_raw,
            )

        return None


    def detect_assignments(self, text: str) -> list:
        """
        JTI-001 Fix 2 (P2): Detect one or more property assignments.

        Handles conjunction statements like "Lucas is 14 and Leo is 8"
        by splitting into two independent PropertyAssignment objects.

        Single-entity statements return a list of one item.
        Falls back to empty list if no assignment detected.

        Args:
            text: The user's raw message.

        Returns:
            List of PropertyAssignment objects (0, 1, or 2 items).
        """
        if not text or not text.strip():
            return []

        stripped = text.strip()

        # Try conjunction split first on the raw text
        m = _CONJUNCTION_ASSIGNMENT_RE.match(stripped)
        if m:
            subj1 = m.group(1).strip().lower()
            val1  = m.group(2).strip().rstrip(".")
            subj2 = m.group(3).strip().lower()
            val2  = m.group(4).strip().rstrip(".")

            # Strip update qualifiers from values
            val1 = re.sub(r"^(?:now|currently)\s+", "", val1, flags=re.IGNORECASE)
            val2 = re.sub(r"^(?:now|currently)\s+", "", val2, flags=re.IGNORECASE)

            # Reject stop subjects
            if subj1 not in _STOP_SUBJECTS and subj2 not in _STOP_SUBJECTS:
                # Reject multi-word subjects
                if len(subj1.split()) <= 3 and len(subj2.split()) <= 3:
                    key1 = self._infer_property_key(val1)
                    key2 = self._infer_property_key(val2)
                    return [
                        PropertyAssignment(subject=subj1, property_key=key1, value=val1),
                        PropertyAssignment(subject=subj2, property_key=key2, value=val2),
                    ]

        # Fall back to single assignment
        single = self.detect_assignment(text)
        if single is not None:
            return [single]
        return []

    def detect_query(self, text: str) -> Optional[PropertyQuery]:
        """
        Detect a property query about a specific entity.

        Matches patterns like:
            "How old is Leo?"
            "What colour is Rex?"
            "Where is Voron?"

        Args:
            text: The user's raw message.

        Returns:
            PropertyQuery if detected, None otherwise.
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        for pattern, fixed_key in _ATTRIBUTE_QUERY_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue

            # Most patterns: group(1) = entity, fixed_key = property
            # "What is X's Y?" pattern: group(1) = entity, group(2) = property
            if fixed_key is not None:
                subject = m.group(1).strip().lower()
                property_key = fixed_key
            else:
                # group(1) = entity, group(2) = property word
                try:
                    subject = m.group(1).strip().lower()
                    property_key = m.group(2).strip().lower()
                except IndexError:
                    continue

            if subject in _STOP_SUBJECTS:
                continue

            logger.info(
                "[PROPERTY] Query detected: subject=%r key=%r",
                subject, property_key,
            )

            return PropertyQuery(subject=subject, property_key=property_key)

        return None

    def detect_group_query(self, text: str) -> Optional[GroupPropertyQuery]:
        """
        Detect a group-property query.

        Matches patterns like:
            "Which printer is offline?"
            "Which dog is brown?"
            "Which child is 14?"

        Args:
            text: The user's raw message.

        Returns:
            GroupPropertyQuery if detected, None otherwise.
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        for pattern in _GROUP_QUERY_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue

            kind_hint = m.group(1).strip().lower()
            value_raw = m.group(2).strip().rstrip("?.")

            if kind_hint in _STOP_SUBJECTS:
                continue

            property_key = self._infer_property_key(value_raw)

            logger.info(
                "[PROPERTY] Group query detected: kind_hint=%r key=%r value=%r",
                kind_hint, property_key, value_raw,
            )

            return GroupPropertyQuery(
                kind_hint=kind_hint,
                property_key=property_key,
                value=value_raw,
            )

        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _infer_property_key(self, value: str) -> str:
        """
        Infer a canonical property key from a value string.

        Falls back to "property" if no pattern matches.

        Args:
            value: The raw value string (e.g. "14", "brown", "offline").

        Returns:
            A canonical property key string.
        """
        for pattern, key in _PROPERTY_VALUE_PATTERNS:
            if pattern.match(value.strip()):
                return key
        # Generic fallback — use the value itself as a hint if short
        if len(value.split()) == 1 and value.isalpha():
            return "property"
        return "property"