"""
Property Recall Engine (Genesis-028 Sprint-001)

Resolves property queries and assignments against KnowledgeEngine.

Responsibilities:
    - Store entity properties via KnowledgeEngine.store_memory()
    - Retrieve entity properties via KnowledgeEngine.recall_memory()
    - Scan entity groups for group-property queries ("Which printer is offline?")
    - Resolve entity names to known group members before storing/querying
    - Return structured results for Agent to render as responses

Design constraints:
    - Single source of truth: KnowledgeEngine only (no parallel storage)
    - No hardcoded entity types or property names
    - Graceful failure — unknown entity returns None, not a crash
    - All properties stored with category="entity_property" for easy retrieval

Architecture position:
    Agent._route()
        └── PropertyRecallEngine.store()    ← after PropertyAssigner.detect_assignment()
        └── PropertyRecallEngine.retrieve() ← after PropertyAssigner.detect_query()
        └── PropertyRecallEngine.scan_group() ← after PropertyAssigner.detect_group_query()
                └── KnowledgeEngine

Genesis-028 Sprint-001.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.knowledge_engine.engine import KnowledgeEngine

from core.conversation.property_assigner import (
    PropertyAssignment,
    PropertyQuery,
    GroupPropertyQuery,
)

logger = logging.getLogger(__name__)

# KnowledgeEngine category used for all entity properties
_PROPERTY_CATEGORY = "entity_property"

# Attribute prefix — stored as "prop:age", "prop:colour", etc.
# Keeps property attributes distinct from other memory records.
_ATTR_PREFIX = "prop:"


@dataclass(frozen=True)
class StoreResult:
    """Result of storing a property assignment."""
    success:      bool
    subject:      str
    property_key: str
    value:        str
    message:      str


@dataclass(frozen=True)
class RetrieveResult:
    """Result of retrieving a property value."""
    found:        bool
    subject:      str
    property_key: str
    value:        Optional[str]
    message:      str


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning a group for a matching property value."""
    found:        bool
    matches:      list[str]       # entity names that matched
    kind_hint:    str
    property_key: str
    value:        str
    message:      str


class PropertyRecallEngine:
    """
    Stores and retrieves entity properties via KnowledgeEngine.

    Takes KnowledgeEngine as a dependency — injected by the Agent.
    No direct storage access.

    Public API:
        store(assignment)            -> StoreResult
        retrieve(query)              -> RetrieveResult
        scan_group(group_query, members) -> ScanResult
    """

    def __init__(self, knowledge: "KnowledgeEngine") -> None:
        self._knowledge = knowledge

    def store(self, assignment: PropertyAssignment) -> StoreResult:
        """
        Store a property assignment in KnowledgeEngine.

        Uses subject as the memory subject and "prop:{key}" as the attribute.
        Calls store_memory() which handles duplicate detection automatically.

        Args:
            assignment: A PropertyAssignment from PropertyAssigner.

        Returns:
            StoreResult indicating success or failure.
        """
        attribute = f"{_ATTR_PREFIX}{assignment.property_key}"

        try:
            self._knowledge.store_memory(
                subject=assignment.subject,
                category=_PROPERTY_CATEGORY,
                attribute=attribute,
                value=assignment.value,
                tags=["entity_property", f"prop_key:{assignment.property_key}"],
            )
            msg = (
                f"Got it — {assignment.subject.title()} "
                f"{self._verb_for(assignment.property_key)} {assignment.value}."
            )
            logger.info(
                "[PROPERTY_ENGINE] Stored: subject=%r attr=%r value=%r",
                assignment.subject, attribute, assignment.value,
            )
            return StoreResult(
                success=True,
                subject=assignment.subject,
                property_key=assignment.property_key,
                value=assignment.value,
                message=msg,
            )
        except Exception as exc:
            logger.warning(
                "[PROPERTY_ENGINE] Store failed: subject=%r attr=%r error=%s",
                assignment.subject, attribute, exc,
            )
            return StoreResult(
                success=False,
                subject=assignment.subject,
                property_key=assignment.property_key,
                value=assignment.value,
                message="I wasn't able to store that property.",
            )

    def retrieve(self, query: PropertyQuery) -> RetrieveResult:
        """
        Retrieve a stored property from KnowledgeEngine.

        Args:
            query: A PropertyQuery from PropertyAssigner.

        Returns:
            RetrieveResult with the value if found.
        """
        attribute = f"{_ATTR_PREFIX}{query.property_key}"

        record = self._knowledge.recall_memory(
            subject=query.subject,
            attribute=attribute,
        )

        if record is None:
            logger.debug(
                "[PROPERTY_ENGINE] Not found: subject=%r attr=%r",
                query.subject, attribute,
            )
            return RetrieveResult(
                found=False,
                subject=query.subject,
                property_key=query.property_key,
                value=None,
                message=f"I don't have {query.property_key} information for {query.subject.title()}.",
            )

        msg = self._format_retrieve_response(query.subject, query.property_key, record.value)
        logger.info(
            "[PROPERTY_ENGINE] Retrieved: subject=%r attr=%r value=%r",
            query.subject, attribute, record.value,
        )
        return RetrieveResult(
            found=True,
            subject=query.subject,
            property_key=query.property_key,
            value=record.value,
            message=msg,
        )

    def scan_group(
        self,
        group_query: GroupPropertyQuery,
        members: list[str],
    ) -> ScanResult:
        """
        Scan a list of entity members for a matching property value.

        Used for "Which printer is offline?" — iterates known members
        of the relevant group and checks each for the queried property/value.

        Args:
            group_query: A GroupPropertyQuery from PropertyAssigner.
            members:     List of known entity names in the group (lowercased).

        Returns:
            ScanResult with matching entity names.
        """
        attribute = f"{_ATTR_PREFIX}{group_query.property_key}"
        matches: list[str] = []

        for member in members:
            record = self._knowledge.recall_memory(
                subject=member.lower(),
                attribute=attribute,
            )
            if record is not None:
                if record.value.lower() == group_query.value.lower():
                    matches.append(member)

        if not matches:
            # Also try a generic search if exact match fails
            search_results = self._knowledge.search_memory(
                query=group_query.value,
                category=_PROPERTY_CATEGORY,
            )
            for r in search_results:
                if r.value.lower() == group_query.value.lower():
                    if r.subject not in [m.lower() for m in matches]:
                        matches.append(r.subject.title())

        if matches:
            names = ", ".join(m.title() for m in matches)
            msg = f"{names} {'is' if len(matches) == 1 else 'are'} {group_query.value}."
        else:
            msg = f"I don't have any {group_query.kind_hint} recorded as {group_query.value}."

        logger.info(
            "[PROPERTY_ENGINE] Group scan: kind=%r key=%r value=%r matches=%r",
            group_query.kind_hint, group_query.property_key, group_query.value, matches,
        )

        return ScanResult(
            found=bool(matches),
            matches=matches,
            kind_hint=group_query.kind_hint,
            property_key=group_query.property_key,
            value=group_query.value,
            message=msg,
        )

    def retrieve_all_properties(self, subject: str) -> dict[str, str]:
        """
        Retrieve all stored properties for an entity.

        Useful for "Tell me everything about Rex."

        Args:
            subject: Entity name (lowercased).

        Returns:
            Dict of property_key → value.
        """
        records = self._knowledge.list_memories(
            subject=subject.lower(),
            category=_PROPERTY_CATEGORY,
        )
        result = {}
        for r in records:
            if r.attribute.startswith(_ATTR_PREFIX):
                key = r.attribute[len(_ATTR_PREFIX):]
                result[key] = r.value
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _verb_for(self, property_key: str) -> str:
        """Return a natural verb phrase for a property key."""
        _VERBS = {
            "age":      "is",
            "colour":   "is",
            "color":    "is",
            "weight":   "weighs",
            "status":   "is",
            "location": "is located in",
            "priority": "has priority",
            "interest": "likes",
        }
        return _VERBS.get(property_key, "is")

    def _format_retrieve_response(
        self,
        subject: str,
        property_key: str,
        value: str,
    ) -> str:
        """Format a natural response for a property retrieval."""
        name = subject.title()
        _TEMPLATES = {
            "age":      f"{name} is {value}.",
            "colour":   f"{name} is {value}.",
            "color":    f"{name} is {value}.",
            "weight":   f"{name} weighs {value}.",
            "status":   f"{name} is {value}.",
            "location": f"{name} is located in {value}.",
            "priority": f"{name} has {value} priority.",
            "interest": f"{name} likes {value}.",
        }
        return _TEMPLATES.get(property_key, f"{name} is {value}.")