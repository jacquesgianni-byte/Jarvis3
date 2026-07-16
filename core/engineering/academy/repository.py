"""
Engineering Academy Repository.

Abstract read-only interfaces for principle, pattern, anti-pattern,
and architecture pattern storage.
No write operations. No mutation. No caching requirements.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from .models import AntiPattern, ArchitecturePattern, BestPractice, DesignPattern, EngineeringPrinciple


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


class AntiPatternRepository(ABC):
    """
    Abstract base class for the Engineering Academy anti-pattern data layer.
    (Genesis-019 Sprint 003)

    Contract
    --------
    * All operations are read-only.
    * Implementations must never mutate stored anti-patterns.
    * Result ordering must be stable and deterministic (sorted by id).
    """

    @abstractmethod
    def get_by_id(self, anti_pattern_id: str) -> Optional[AntiPattern]:
        """Return the anti-pattern with *anti_pattern_id*, or ``None`` if not found."""

    @abstractmethod
    def list_all(self) -> List[AntiPattern]:
        """Return all anti-patterns sorted by id (stable, deterministic)."""

    @abstractmethod
    def filter_by_category(self, category: str) -> List[AntiPattern]:
        """
        Return all anti-patterns whose category matches *category*
        (case-insensitive). Returns an empty list if no match — never raises.
        """

    @abstractmethod
    def filter_by_tag(self, tag: str) -> List[AntiPattern]:
        """
        Return all anti-patterns whose tags list contains *tag*
        (case-insensitive). Returns an empty list if no match — never raises.
        """


class ArchitecturePatternRepository(ABC):
    """
    Abstract base class for the Engineering Academy architecture pattern data layer.
    (Genesis-019 Sprint 004)

    Contract
    --------
    * All operations are read-only.
    * Implementations must never mutate stored architecture patterns.
    * Result ordering must be stable and deterministic (sorted by id).
    """

    @abstractmethod
    def get_by_id(self, architecture_pattern_id: str) -> Optional[ArchitecturePattern]:
        """Return the architecture pattern with *architecture_pattern_id*, or None."""

    @abstractmethod
    def list_all(self) -> List[ArchitecturePattern]:
        """Return all architecture patterns sorted by id (stable, deterministic)."""

    @abstractmethod
    def filter_by_category(self, category: str) -> List[ArchitecturePattern]:
        """
        Return all architecture patterns whose category matches *category*
        (case-insensitive). Returns an empty list if no match — never raises.
        """

    @abstractmethod
    def filter_by_tag(self, tag: str) -> List[ArchitecturePattern]:
        """
        Return all architecture patterns whose tags list contains *tag*
        (case-insensitive). Returns an empty list if no match — never raises.
        """


class BestPracticeRepository(ABC):
    """
    Abstract base class for the Engineering Academy best practice data layer.
    (Genesis-019 Sprint 005)

    Contract
    --------
    * All operations are read-only.
    * Implementations must never mutate stored best practices.
    * Result ordering must be stable and deterministic (sorted by id).
    """

    @abstractmethod
    def get_by_id(self, best_practice_id: str) -> Optional[BestPractice]:
        """Return the best practice with *best_practice_id*, or None."""

    @abstractmethod
    def list_all(self) -> List[BestPractice]:
        """Return all best practices sorted by id (stable, deterministic)."""

    @abstractmethod
    def filter_by_category(self, category: str) -> List[BestPractice]:
        """
        Return all best practices whose category matches *category*
        (case-insensitive). Returns an empty list if no match.
        """

    @abstractmethod
    def filter_by_tag(self, tag: str) -> List[BestPractice]:
        """
        Return all best practices whose tags list contains *tag*
        (case-insensitive). Returns an empty list if no match.
        """