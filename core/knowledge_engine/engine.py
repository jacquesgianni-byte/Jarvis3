"""
Knowledge Engine

The central business logic layer for the Jarvis Knowledge Engine.
Implements the public API defined in the Knowledge Engine Specification v1.1.

This class is the only entry point for all knowledge operations.
No other module accesses KnowledgeStorage directly.
"""

import math
import logging
from datetime import UTC, datetime
from typing import Optional

from core.knowledge_engine.categories import CategoryLoader
from core.knowledge_engine.exceptions import InvalidMemoryError
from core.knowledge_engine.json_storage import JsonKnowledgeRepository
from core.knowledge_engine.models import MemoryRecord, MemorySource, Visibility
from core.knowledge_engine.repository import KnowledgeRepository

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Enum normalisation helpers
# ------------------------------------------------------------------

def _normalise_source(value) -> MemorySource:
    """
    Normalise a source value to a MemorySource enum.

    Accepts either a MemorySource enum or a plain string.

    Args:
        value: A MemorySource enum or a string such as "user".

    Returns:
        A MemorySource enum instance.
    """
    if isinstance(value, MemorySource):
        return value
    return MemorySource(value)


def _normalise_visibility(value) -> Visibility:
    """
    Normalise a visibility value to a Visibility enum.

    Accepts either a Visibility enum or a plain string.

    Args:
        value: A Visibility enum or a string such as "private".

    Returns:
        A Visibility enum instance.
    """
    if isinstance(value, Visibility):
        return value
    return Visibility(value)


# ------------------------------------------------------------------
# Engine
# ------------------------------------------------------------------

class KnowledgeEngine:
    """
    The Jarvis Knowledge Engine.

    Implements six public methods as defined in the approved specification:
        store_memory()
        recall_memory()
        search_memory()
        update_memory()
        forget_memory()
        list_memories()

    Enforces:
        - Duplicate detection (subject + attribute uniqueness)
        - Update rules with provenance notes
        - Soft and hard delete
        - Expiration handling
        - Importance and visibility inheritance from category defaults
        - Confidence rules per source

    This class has no knowledge of the UI, voice pipeline, or AI providers.
    """

    _CONFIDENCE_BY_SOURCE = {
        MemorySource.USER:     1.0,
        MemorySource.INFERRED: 0.7,
        MemorySource.SYSTEM:   0.9,
    }

    def __init__(
        self,
        storage: Optional[KnowledgeRepository] = None,
        categories: Optional[CategoryLoader] = None
    ):
        """
        Initialise the KnowledgeEngine.

        Args:
            storage:    Optional KnowledgeRepository instance.
                        Defaults to the standard JSON storage.
            categories: Optional CategoryLoader instance.
                        Defaults to loading from data/categories.json.
        """
        self._storage = storage or JsonKnowledgeRepository()
        self._categories = categories or CategoryLoader()

        logger.info(
            "KnowledgeEngine initialised. Records in store: %d",
            self._storage.count()
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_memory(
        self,
        subject: str,
        category: str,
        attribute: str,
        value: str,
        confidence: Optional[float] = None,
        source=MemorySource.USER,
        tags: Optional[list] = None,
        expires_at: Optional[datetime] = None,
        importance: Optional[float] = None,
        visibility=None,
        data_type: str = "str",
    ) -> MemoryRecord:
        """
        Store a new memory or update an existing one.

        If a memory with the same subject and attribute already exists,
        update_memory() is called instead of creating a duplicate.

        Accepts source and visibility as either enum instances or plain
        strings — both are normalised before constructing MemoryRecord.

        Args:
            subject:    Who or what this fact is about.
            category:   The category id. Must exist in categories.json.
            attribute:  The property being described.
            value:      The value of the attribute.
            confidence: How certain Jarvis is. Defaults to source default.
            source:     Who provided this memory. MemorySource enum or string.
            tags:       Searchable labels.
            expires_at: Optional expiry date.
            importance: How significant this memory is. Inherits from category.
            visibility: Access control. Visibility enum or string.
            data_type:  The value type for future typed memory support.

        Returns:
            The stored or updated MemoryRecord.
        """
        # Normalise enums immediately — before any logic runs.
        # MemoryRecord requires typed enums, never raw strings.
        source = _normalise_source(source)

        # Check for existing record — avoid duplicates.
        existing = self._storage.find_by_subject_and_attribute(subject, attribute)
        if existing is not None:
            logger.debug(
                "store_memory: duplicate detected for subject=%r attribute=%r — updating.",
                subject, attribute
            )
            resolved_confidence = confidence if confidence is not None else self._confidence_for(source)
            return self.update_memory(
                subject=subject,
                attribute=attribute,
                value=value,
                confidence=resolved_confidence,
                source=source
            )

        # Resolve importance and visibility from category defaults.
        cat_def = self._categories.get_or_general(category)
        resolved_importance = importance if importance is not None else cat_def.default_importance
        resolved_visibility = _normalise_visibility(
            visibility if visibility is not None else cat_def.default_visibility
        )
        resolved_confidence = confidence if confidence is not None else self._confidence_for(source)

        record = MemoryRecord(
            subject=subject.lower().strip(),
            category=category,
            attribute=attribute.lower().strip(),
            value=value.strip(),
            data_type=data_type,
            confidence=resolved_confidence,
            importance=resolved_importance,
            visibility=resolved_visibility,
            source=source,
            tags=[t.lower().strip() for t in (tags or [])],
            expires_at=expires_at,
        )

        self._storage.save(record)

        logger.info(
            "store_memory: stored subject=%r attribute=%r value=%r",
            record.subject, record.attribute, record.value
        )

        return record

    def recall_memory(
        self,
        subject: str,
        attribute: str,
        category: Optional[str] = None
    ) -> Optional[MemoryRecord]:
        """
        Retrieve a specific memory by subject and attribute.

        Args:
            subject:   The subject to look up.
            attribute: The attribute to look up.
            category:  Optional category filter (reserved for future use).

        Returns:
            The MemoryRecord if found and not expired, otherwise None.
        """
        record = self._storage.find_by_subject_and_attribute(subject, attribute)

        if record is None:
            logger.debug(
                "recall_memory: not found — subject=%r attribute=%r",
                subject, attribute
            )
            return None

        if record.is_expired():
            logger.debug(
                "recall_memory: found but expired — subject=%r attribute=%r",
                subject, attribute
            )
            return None

        return record

    def search_memory(
        self,
        query: str,
        subject: Optional[str] = None,
        category: Optional[str] = None,
        min_importance: float = 0.0,
        limit: int = 10
    ) -> list[MemoryRecord]:
        """
        Search for memories matching a query string.

        Applies a five-tier priority order per the specification:
            1. Exact subject + attribute match
            2. Tag match
            3. Category match
            4. Attribute substring match
            5. Value substring match

        Results are ranked by score × sqrt(confidence) × sqrt(importance).
        Expired memories and confidence < 0.3 are excluded.

        Args:
            query:          The search string.
            subject:        Optional subject filter.
            category:       Optional category filter.
            min_importance: Minimum importance threshold.
            limit:          Maximum number of results to return.

        Returns:
            A ranked list of matching MemoryRecord objects.
        """
        query_lower = query.lower().strip()
        query_words = set(query_lower.split()) if query_lower else set()

        scored: list[tuple[float, MemoryRecord]] = []

        for record in self._storage.list_all():
            if record.is_expired():
                continue
            if record.confidence < 0.3:
                continue
            if record.importance < min_importance:
                continue
            if subject and record.subject.lower() != subject.lower():
                continue
            if category and record.category != category:
                continue

            score = self._score_record(record, query_lower, query_words)
            if score > 0:
                weighted = score * math.sqrt(record.confidence) * math.sqrt(record.importance)
                scored.append((weighted, record))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = [record for _, record in scored[:limit]]

        logger.debug(
            "search_memory: query=%r returned %d results",
            query, len(results)
        )

        return results

    def update_memory(
        self,
        subject: str,
        attribute: str,
        value: str,
        confidence: float = 1.0,
        source=MemorySource.USER,
        category: Optional[str] = None
    ) -> Optional[MemoryRecord]:
        """
        Update the value of an existing memory.

        Preserves created_at. Records the previous value in notes.
        User-provided updates always win over inferred values.

        Args:
            subject:    The subject of the memory to update.
            attribute:  The attribute to update.
            value:      The new value.
            confidence: Confidence of the new value.
            source:     Source of the update. MemorySource enum or string.
            category:   Optional category hint for disambiguation.

        Returns:
            The updated MemoryRecord, or None if not found.
        """
        source = _normalise_source(source)

        record = self._storage.find_by_subject_and_attribute(subject, attribute)

        if record is None:
            logger.debug(
                "update_memory: no existing record for subject=%r attribute=%r",
                subject, attribute
            )
            return None

        # Conflict resolution — lower confidence source cannot overwrite user fact.
        if (source == MemorySource.INFERRED
                and record.source == MemorySource.USER
                and record.confidence >= confidence):
            logger.debug(
                "update_memory: inferred value rejected — existing user fact has higher confidence."
            )
            return record

        # Record provenance in notes.
        timestamp = datetime.now(UTC).isoformat()
        note = f"[{timestamp}] Updated from '{record.value}' to '{value}' by {source.value}."
        record.notes = (record.notes + "\n" + note) if record.notes else note

        record.value = value.strip()
        record.confidence = confidence
        record.source = source
        record.updated_at = datetime.now(UTC)

        # DEFECT FIX (MP-003 validation, 2026-07-10): a re-stated fact
        # is a living fact. Without clearing expires_at, updating a
        # soft-deleted record left it dead forever — "forget my colour"
        # followed by "my colour is black" wrote the new value onto a
        # tombstone and recall kept returning None.
        record.expires_at = None

        self._storage.save(record)

        logger.info(
            "update_memory: updated subject=%r attribute=%r value=%r",
            record.subject, record.attribute, record.value
        )

        return record

    def forget_memory(
        self,
        subject: str,
        attribute: str,
        category: Optional[str] = None,
        permanent: bool = False
    ) -> bool:
        """
        Forget a memory by soft or hard delete.

        Soft delete (default): sets expires_at to now.
        Hard delete: permanently removes the record.

        Args:
            subject:    The subject of the memory to forget.
            attribute:  The attribute to forget.
            category:   Optional category hint.
            permanent:  If True, permanently deletes the record.

        Returns:
            True if the memory was found and forgotten, False otherwise.
        """
        record = self._storage.find_by_subject_and_attribute(subject, attribute)

        if record is None:
            logger.debug(
                "forget_memory: not found — subject=%r attribute=%r",
                subject, attribute
            )
            return False

        if permanent:
            self._storage.delete(record.id)
            logger.info(
                "forget_memory: permanently deleted subject=%r attribute=%r",
                subject, attribute
            )
        else:
            record.expires_at = datetime.now(UTC)
            record.updated_at = datetime.now(UTC)
            self._storage.save(record)
            logger.info(
                "forget_memory: soft deleted subject=%r attribute=%r",
                subject, attribute
            )

        return True

    def list_memories(
        self,
        subject: Optional[str] = None,
        category: Optional[str] = None,
        min_importance: float = 0.0,
        include_expired: bool = False,
        limit: int = 100
    ) -> list[MemoryRecord]:
        """
        Return a filtered list of stored memories.

        Args:
            subject:          Optional subject filter.
            category:         Optional category filter.
            min_importance:   Minimum importance threshold.
            include_expired:  If True, includes expired memories.
            limit:            Maximum number of records to return.

        Returns:
            A list of matching MemoryRecord objects ordered by importance desc.
        """
        results = []

        for record in self._storage.list_all():
            if not include_expired and record.is_expired():
                continue
            if subject and record.subject.lower() != subject.lower():
                continue
            if category and record.category != category:
                continue
            if record.importance < min_importance:
                continue
            results.append(record)

        results.sort(key=lambda r: r.importance, reverse=True)

        return results[:limit]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _confidence_for(self, source: MemorySource) -> float:
        """Return the default confidence value for a given source."""
        return self._CONFIDENCE_BY_SOURCE.get(source, 0.5)

    def _score_record(
        self,
        record: MemoryRecord,
        query_lower: str,
        query_words: set
    ) -> float:
        """
        Score a single record against a search query.

        Applies the five-tier priority from the specification.

        Returns:
            A float score >= 0. Zero means no match.
        """
        if not query_lower:
            return 0.0

        # Tier 1 — exact subject + attribute match
        if (record.subject.lower() == query_lower
                or record.attribute.lower() == query_lower):
            return 1.0

        score = 0.0

        # Tier 2 — tag match
        record_tags = {t.lower() for t in record.tags}
        tag_matches = query_words & record_tags
        if tag_matches:
            score = max(score, 0.8 * len(tag_matches) / max(len(query_words), 1))

        # Tier 3 — category match
        if record.category.lower() in query_lower:
            score = max(score, 0.6)

        # Tier 4 — attribute substring
        if query_lower in record.attribute.lower() or record.attribute.lower() in query_lower:
            score = max(score, 0.5)

        # Tier 5 — value substring
        if query_lower in record.value.lower():
            score = max(score, 0.3)

        return score