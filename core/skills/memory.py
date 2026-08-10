"""
Memory Skill (Genesis-031 Sprint-002)

Minimal extension of original MemorySkill.
Only change: remember() accepts optional temporal_tags,
encoded as additional tags in store_memory().

All original private/public methods preserved exactly.
"""

from __future__ import annotations

import re
from typing import Optional

from core.knowledge_engine.engine import KnowledgeEngine
from core.knowledge_engine.models import MemorySource
from core.models.response import Response
from core.skills.base import Skill


# ---------------------------------------------------------------------------
# Canonicalisation (GC-008)
# ---------------------------------------------------------------------------

_ALIASES: dict[str, str] = {
    "colour":       "favourite colour",
    "color":        "favourite colour",
    "drink":        "favourite drink",
    "food":         "favourite food",
    "sport":        "favourite sport",
    "movie":        "favourite movie",
    "film":         "favourite movie",
    "song":         "favourite song",
    "book":         "favourite book",
}

_PET_NAME_RE = re.compile(
    r"\b(?:dogs?|cats?|pets?|animals?|birds?|fish|rabbits?|hamsters?)'?\s*names?\b",
    re.IGNORECASE,
)


def _canonicalise(key: str) -> str:
    key_stripped = key.strip().rstrip(".")
    if _PET_NAME_RE.search(key_stripped):
        return "pet names"
    lower = key_stripped.lower()
    return _ALIASES.get(lower, key_stripped)


class MemorySkill(Skill):

    name = "memory"

    def __init__(self, knowledge: KnowledgeEngine):
        self.knowledge = knowledge

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def remember(
        self,
        key: str,
        value: str,
        temporal_tags: Optional[list[str]] = None,
        temporal_metadata: Optional[dict] = None,
    ) -> Response:
        """
        Store a memory. Genesis-031: temporal_tags appended if provided.
        temporal_metadata is accepted for API compatibility and encoded as tags.
        """
        tags = ["user_fact"]
        if temporal_tags:
            tags = tags + [t for t in temporal_tags if t not in tags]
        if temporal_metadata:
            if "resolved_date" in temporal_metadata:
                tags.append(f"resolved:{temporal_metadata['resolved_date']}")
            if "temporal_expression" in temporal_metadata:
                tags.append(f"expr:{temporal_metadata['temporal_expression']}")

        self.knowledge.store_memory(
            subject="user",
            category="personal",
            attribute=_canonicalise(key),
            value=value,
            tags=tags,
        )
        return Response(success=True, message="Got it, I'll remember that.")

    def execute(self, request: str) -> Response:
        req_lower = request.lower().strip()

        # Store: "remember my X is Y" / "my X is Y" / "remember X is Y"
        if any(w in req_lower for w in ["remember", "note", "store", "save"]):
            m = re.search(
                r"(?:remember|note|store|save)\s+(?:that\s+)?(?:my\s+)?(.+?)\s+is\s+(.+)",
                req_lower,
            )
            if m:
                key = m.group(1).strip().rstrip(".")
                value = m.group(2).strip().rstrip(".")
                # JTI-001 Fix 1 (P1): route corrections to entity records
                return self._remember_entity_aware(key, value)

        # Forget / delete
        if any(w in req_lower for w in ["forget", "delete", "remove", "clear"]):
            m = re.search(
                r"(?:forget|delete|remove|clear)\s+(?:my\s+)?(.+)", req_lower
            )
            if m:
                key = m.group(1).strip().rstrip(".")
                return self._forget(key)

        # Recall: "what is my X" / "what's my X" / "tell me my X"
        if any(w in req_lower for w in ["what is", "what's", "tell me", "remind me"]):
            m = re.search(
                r"(?:what(?:\s+is|'s)|tell me|remind me)(?:\s+(?:my|about))?\s+(.+)",
                req_lower,
            )
            if m:
                key = m.group(1).strip().rstrip("?.")
                return self._recall(key)

        return Response(
            success=False,
            message="I'm not sure what you'd like me to remember.",
        )


    # ------------------------------------------------------------------
    # JTI-001 Fix 1 (P1): Entity-aware correction routing
    # ------------------------------------------------------------------

    # Property key inference patterns — ordered most specific first.
    # Used ONLY as fallback when no existing prop: record exists for entity.
    _PROP_KEY_PATTERNS: list = []  # populated after class definition

    def _remember_entity_aware(self, key: str, value: str) -> Response:
        """
        Route a correction to the right record.

        If key is a known entity subject (has entity_property records),
        update that entity's existing prop: attribute rather than creating
        a new user fact. Prefers existing prop relationship over value inference.

        Args:
            key:   The subject extracted from "remember that X is Y"
            value: The value extracted from "remember that X is Y"

        Returns:
            Response with confirmation message.
        """
        entity_records = self.knowledge.list_memories(
            subject=key.lower(), category="entity_property"
        )
        if entity_records:
            # Entity is known — find the most relevant existing prop: attribute.
            # Prefer value-inferred key match, then fall back to first record.
            inferred_key = self._infer_prop_key(value)
            target_attr = f"prop:{inferred_key}"

            # Check if entity already has a record for this prop key
            existing = self.knowledge.recall_memory(
                subject=key.lower(), attribute=target_attr
            )
            if existing is None:
                # No existing record for inferred key — use the first prop: record
                # (most common case: entity has one property, e.g. prop:age)
                prop_records = [
                    r for r in entity_records
                    if r.attribute.startswith("prop:")
                ]
                if prop_records:
                    target_attr = prop_records[0].attribute

            self.knowledge.store_memory(
                subject=key.lower(),
                category="entity_property",
                attribute=target_attr,
                value=value,
                tags=["entity_property", f"prop_key:{target_attr[len('prop:'):]}"],
            )
            name = key.title()
            prop_label = target_attr[len("prop:"):]
            return Response(
                success=True,
                message=f"Got it — I've updated {name}'s {prop_label} to {value}.",
            )

        # Not a known entity — store as normal user fact
        return self.remember(key, value)

    def _infer_prop_key(self, value: str) -> str:
        """
        Infer a canonical property key from a value string.
        Used as fallback when no existing prop: record exists.
        Falls back to "property" if no pattern matches.
        """
        _patterns = [
            (re.compile(r"^\d+\s*(?:years?\s*old|yrs?\.?\s*old|years?)?$", re.IGNORECASE), "age"),
            (re.compile(
                r"^(?:red|orange|yellow|green|blue|purple|pink|brown|black|white|"
                r"grey|gray|golden|silver|cream|beige|tan|teal|navy|maroon|violet|indigo)"
                r"(?:\s+and\s+\w+)?$", re.IGNORECASE), "colour"),
            (re.compile(
                r"^(?:online|offline|active|inactive|enabled|disabled|running|stopped|"
                r"pending|complete|completed|done|open|closed|available|unavailable)$",
                re.IGNORECASE), "status"),
            (re.compile(
                r"^\d+(?:\.\d+)?\s*(?:kg|kgs?|lbs?|pounds?|tonnes?|grams?|g)\b",
                re.IGNORECASE), "weight"),
        ]
        for pattern, key in _patterns:
            if pattern.match(value.strip()):
                return key
        return "property"

    # ------------------------------------------------------------------
    # Private helpers (used by execute and existing tests)
    # ------------------------------------------------------------------

    def _forget(self, key: str) -> Response:
        canonical = _canonicalise(key)
        self.knowledge.forget_memory("user", canonical)
        return Response(success=True, message="Done, I've forgotten that.")

    def _recall(self, key: str) -> Response:
        canonical = _canonicalise(key)
        record = self.knowledge.recall_memory(subject="user", attribute=canonical)
        if record:
            return Response(
                success=True,
                message=f"Your {canonical} is {record.value}.",
                data={"value": record.value},
            )
        # Fuzzy search, excluding derived records
        results = self.knowledge.search_memory(canonical, subject="user")
        canonical_results = [r for r in results if "derived" not in r.tags]
        if canonical_results:
            r = canonical_results[0]
            return Response(
                success=True,
                message=f"Your {r.attribute} is {r.value}.",
                data={"value": r.value},
            )
        return Response(
            success=False,
            message=f"I don't have your {canonical} stored yet.",
            data={"memory_miss": True, "attribute": canonical},
        )

    # Public aliases for _forget and _recall
    def forget(self, key: str) -> Response:
        return self._forget(key)

    def recall(self, key: str) -> Response:
        return self._recall(key)
