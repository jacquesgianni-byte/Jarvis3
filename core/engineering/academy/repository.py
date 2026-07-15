"""
Engineering Academy Repository.

Abstract read-only interfaces for principle and pattern storage.
No write operations. No mutation. No caching requirements.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import DesignPattern, EngineeringPrinciple


class AcademyRepository(ABC):
    """
    Abstract base class for the Engineering Academy principle data layer.

    Contract
    --------
    * All operations are read-only.
    * Implementations must never mutate stored principles.
    * Result ordering must be stable and deterministic (sorted by id).
    """

    @abstractmethod
    def get_by_id(self, principle_id: str) -> Optional[EngineeringPrinciple]:
        """Return the principle with *principle_id*, or ``None`` if not found."""

    @abstractmethod
    def list_all(self) -> List[EngineeringPrinciple]:
        """Return all principles sorted by id (stable, deterministic)."""

    @abstractmethod
    def filter_by_category(self, category: str) -> List[EngineeringPrinciple]:
        """
        Return all principles whose category matches *category* (case-insensitive).
        Returns an empty list if no match — never raises.
        """

    @abstractmethod
    def filter_by_tag(self, tag: str) -> List[EngineeringPrinciple]:
        """
        Return all principles whose tags list contains *tag* (case-insensitive).
        Returns an empty list if no match — never raises.
        """


class PatternRepository(ABC):
    """
    Abstract base class for the Engineering Academy pattern data layer.

    Contract
    --------
    * All operations are read-only.
    * Implementations must never mutate stored patterns.
    * Result ordering must be stable and deterministic (sorted by id).
    """

    @abstractmethod
    def get_by_id(self, pattern_id: str) -> Optional[DesignPattern]:
        """Return the pattern with *pattern_id*, or ``None`` if not found."""

    @abstractmethod
    def list_all(self) -> List[DesignPattern]:
        """Return all patterns sorted by id (stable, deterministic)."""

    @abstractmethod
    def filter_by_category(self, category: str) -> List[DesignPattern]:
        """
        Return all patterns whose category matches *category* (case-insensitive).
        Returns an empty list if no match — never raises.
        """

    @abstractmethod
    def filter_by_tag(self, tag: str) -> List[DesignPattern]:
        """
        Return all patterns whose tags list contains *tag* (case-insensitive).
        Returns an empty list if no match — never raises.
        """