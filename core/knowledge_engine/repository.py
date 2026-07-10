"""
Knowledge Engine — Storage Repository Interface

Defines the abstract base class for all storage backends.
The KnowledgeEngine depends on this interface — never on a concrete implementation.

This separation ensures the JSON backend can be replaced with SQLite,
a remote API, or any other storage mechanism without changing the engine.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from core.knowledge_engine.models import MemoryRecord

logger = logging.getLogger(__name__)


class KnowledgeRepository(ABC):
    """
    Abstract base class for Knowledge Engine storage backends.

    All storage implementations must inherit from this class
    and implement every abstract method.

    The KnowledgeEngine interacts only with this interface.
    It never imports or instantiates a concrete backend directly.
    """

    @abstractmethod
    def save(self, record: MemoryRecord) -> None:
        """
        Insert or update a MemoryRecord.

        If a record with the same id already exists, it is replaced.

        Args:
            record: The MemoryRecord to store.
        """

    @abstractmethod
    def delete(self, record_id: str) -> bool:
        """
        Remove a record by its UUID.

        Args:
            record_id: The UUID of the record to delete.

        Returns:
            True if found and deleted, False otherwise.
        """

    @abstractmethod
    def find_by_id(self, record_id: str) -> Optional[MemoryRecord]:
        """
        Retrieve a single record by its UUID.

        Args:
            record_id: The UUID to look up.

        Returns:
            The MemoryRecord, or None if not found.
        """

    @abstractmethod
    def find_by_subject_and_attribute(
        self,
        subject: str,
        attribute: str
    ) -> Optional[MemoryRecord]:
        """
        Find a record matching the given subject and attribute.

        Args:
            subject:   The subject to match.
            attribute: The attribute to match.

        Returns:
            The first matching MemoryRecord, or None.
        """

    @abstractmethod
    def list_all(self) -> list[MemoryRecord]:
        """
        Return all stored MemoryRecord objects.

        Returns:
            A list of all records in no guaranteed order.
        """


    @abstractmethod
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

        All parameters are keyword-only and optional.
        Passing no arguments returns all non-expired records.

        Args:
            subject:         Filter by subject. Example: "user", "wife".
            category:        Filter by category id. Example: "preferences".
            attribute:       Filter by attribute. Example: "favourite_colour".
            tags:            Filter by tags — records matching any tag are included.
            include_expired: If True, includes expired records in results.

        Returns:
            A list of matching MemoryRecord objects in no guaranteed order.

        Examples:
            search(subject="user")
            search(category="preferences")
            search(tags=["python"])
            search(subject="wife", attribute="name")
        """

    @abstractmethod
    def count(self) -> int:
        """
        Return the total number of stored records.

        Returns:
            Integer count of all records.
        """