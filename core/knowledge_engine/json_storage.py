"""
Knowledge Engine — JSON Storage Implementation

Implements the KnowledgeRepository interface using a local JSON file.

This is the Phase 1 storage backend.
It will be replaced by SQLite when record counts exceed ~1,000
without any changes to the KnowledgeEngine or its callers.
"""

import json
from datetime import UTC, datetime
import logging
import os
from typing import Optional

from core.knowledge_engine.exceptions import StorageError
from core.knowledge_engine.models import MemoryRecord
from core.knowledge_engine.repository import KnowledgeRepository

logger = logging.getLogger(__name__)

_DEFAULT_STORAGE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "knowledge.json"
)


class JsonKnowledgeRepository(KnowledgeRepository):
    """
    JSON-backed implementation of KnowledgeRepository.

    Loads all records into memory at construction time.
    Writes the full record set to disk on every mutation.

    This class has no business logic. It only handles:
        - Loading records from disk
        - Saving records to disk
        - Serialisation (MemoryRecord → dict)
        - Deserialisation (dict → MemoryRecord)

    Example usage:
        repository = JsonKnowledgeRepository()
        repository.save(record)
        record = repository.find_by_id("some-uuid")
    """

    def __init__(self, path: Optional[str] = None):
        """
        Initialise the JSON repository.

        Args:
            path: Optional path to the knowledge.json file.
                  Defaults to data/knowledge.json relative to project root.
        """
        self._path = path or _DEFAULT_STORAGE_PATH
        self._records: dict[str, MemoryRecord] = {}
        self._load()

    def _load(self) -> None:
        """
        Load all records from the JSON file into memory.

        Creates an empty file if none exists.
        Logs and continues if individual records fail to deserialise.
        """
        if not os.path.exists(self._path):
            logger.info(
                "JsonKnowledgeRepository: no file at %s — starting with empty store.",
                self._path
            )
            self._ensure_file()
            return

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            for entry in raw:
                try:
                    record = MemoryRecord.from_dict(entry)
                    self._records[record.id] = record
                except Exception as e:
                    logger.exception(
                        "JsonKnowledgeRepository: failed to deserialise record %s: %s",
                        entry.get("id", "unknown"),
                        e
                    )

            logger.info(
                "JsonKnowledgeRepository: loaded %d records from %s",
                len(self._records),
                self._path
            )

        except Exception:
            logger.exception(
                "JsonKnowledgeRepository: failed to load %s — starting with empty store.",
                self._path
            )

    def _persist(self) -> None:
        """
        Write all records to the JSON file atomically.

        Writes to a temporary file first then replaces the target with
        os.replace(). This ensures the knowledge store is never left in
        a corrupt state if the process is interrupted mid-write.
        """
        try:
            self._ensure_file()
            tmp_path = self._path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(
                    [record.to_dict() for record in self._records.values()],
                    f,
                    indent=2,
                    ensure_ascii=False
                )
            os.replace(tmp_path, self._path)
        except Exception as e:
            raise StorageError(f"Failed to persist knowledge store: {e}") from e

    def _ensure_file(self) -> None:
        """Create the storage file and parent directories if they do not exist."""
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        if not os.path.exists(self._path):
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump([], f)

    # ------------------------------------------------------------------
    # KnowledgeRepository implementation
    # ------------------------------------------------------------------

    def save(self, record: MemoryRecord) -> None:
        """Insert or update a MemoryRecord. Persists to disk immediately."""
        self._records[record.id] = record
        self._persist()

    def delete(self, record_id: str) -> bool:
        """Remove a record by UUID. Returns True if found and deleted."""
        if record_id in self._records:
            del self._records[record_id]
            self._persist()
            return True
        return False

    def find_by_id(self, record_id: str) -> Optional[MemoryRecord]:
        """Retrieve a single record by UUID."""
        return self._records.get(record_id)

    def find_by_subject_and_attribute(
        self,
        subject: str,
        attribute: str
    ) -> Optional[MemoryRecord]:
        """Find a record by subject and attribute. Used for duplicate detection."""
        subject_lower = subject.lower()
        attribute_lower = attribute.lower()

        for record in self._records.values():
            if (record.subject.lower() == subject_lower
                    and record.attribute.lower() == attribute_lower):
                return record

        return None

    def list_all(self) -> list[MemoryRecord]:
        """
        Return copies of all stored records.

        Returns copies rather than references to prevent callers from
        mutating records without going through save().
        """
        from copy import deepcopy
        return [deepcopy(record) for record in self._records.values()]

    def search(
        self,
        *,
        subject: str | None = None,
        category: str | None = None,
        attribute: str | None = None,
        tags: list[str] | None = None,
        include_expired: bool = False,
    ) -> list[MemoryRecord]:
        """
        Search memories using one or more optional criteria.

        Each provided criterion is applied as an AND filter.
        Tag filtering uses OR — a record matches if it contains any of the given tags.

        Args:
            subject:         Optional subject filter.
            category:        Optional category filter.
            attribute:       Optional attribute filter.
            tags:            Optional tag list. Matches records containing any tag.
            include_expired: If True, includes expired records.

        Returns:
            A list of matching MemoryRecord objects.
        """
        results = []
        tag_set = {t.lower() for t in tags} if tags else None

        for record in self._records.values():
            if not include_expired and record.is_expired():
                continue
            if subject and record.subject.lower() != subject.lower():
                continue
            if category and record.category != category:
                continue
            if attribute and record.attribute.lower() != attribute.lower():
                continue
            if tag_set and not tag_set.intersection({t.lower() for t in record.tags}):
                continue
            results.append(record)

        return results

    def count(self) -> int:
        """Return the total number of stored records."""
        return len(self._records)