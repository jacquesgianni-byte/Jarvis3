"""
Engineering Academy Services.

Deterministic lookup and search over principle and pattern repositories.
No AI. No semantic search. No mutations. No autonomous decisions.
"""

from __future__ import annotations

from typing import List, Optional

from .exceptions import PrincipleNotFoundError
from .models import DesignPattern, EngineeringPrinciple
from .repository import AcademyRepository, PatternRepository


class AcademyService:
    """
    Business-logic layer for engineering principles.

    Provides deterministic access to engineering principles.
    All search is keyword/substring-based — no AI, no fuzzy matching.
    """

    def __init__(self, repository: AcademyRepository) -> None:
        self._repository = repository

    def get_principle(self, principle_id: str) -> EngineeringPrinciple:
        """
        Return the principle with *principle_id*.

        Raises
        ------
        PrincipleNotFoundError
            If no principle with that ID exists.
        """
        result = self._repository.get_by_id(principle_id)
        if result is None:
            raise PrincipleNotFoundError(principle_id)
        return result

    def list_principles(self) -> List[EngineeringPrinciple]:
        """Return all principles in stable, deterministic order (sorted by id)."""
        return self._repository.list_all()

    def find_by_category(self, category: str) -> List[EngineeringPrinciple]:
        """Return principles in *category* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_category(category)

    def find_by_tag(self, tag: str) -> List[EngineeringPrinciple]:
        """Return principles tagged with *tag* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_tag(tag)

    def search(self, query: str) -> List[EngineeringPrinciple]:
        """
        Return principles whose text fields contain *query* as a substring.

        Case-insensitive. Deterministic. Results sorted by id.
        No AI. No semantic matching. No fuzzy matching.
        """
        needle = query.strip().lower()
        if not needle:
            return []
        return [
            p for p in self._repository.list_all()
            if self._principle_matches(p, needle)
        ]

    def _principle_matches(self, principle: EngineeringPrinciple, needle: str) -> bool:
        searchable = [
            principle.id, principle.name, principle.summary,
            principle.rationale, principle.guidance,
            *principle.tags, *principle.violations, *principle.examples,
        ]
        return any(needle in s.lower() for s in searchable)


class PatternService:
    """
    Business-logic layer for engineering design patterns.

    Provides deterministic access to design patterns.
    All search is keyword/substring-based — no AI, no fuzzy matching.
    """

    def __init__(self, repository: PatternRepository) -> None:
        self._repository = repository

    def get_pattern(self, pattern_id: str) -> DesignPattern:
        """
        Return the pattern with *pattern_id*.

        Raises
        ------
        PrincipleNotFoundError
            If no pattern with that ID exists.
        """
        result = self._repository.get_by_id(pattern_id)
        if result is None:
            raise PrincipleNotFoundError(pattern_id)
        return result

    def list_patterns(self) -> List[DesignPattern]:
        """Return all patterns in stable, deterministic order (sorted by id)."""
        return self._repository.list_all()

    def find_by_category(self, category: str) -> List[DesignPattern]:
        """Return patterns in *category* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_category(category)

    def find_by_tag(self, tag: str) -> List[DesignPattern]:
        """Return patterns tagged with *tag* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_tag(tag)

    def search(self, query: str) -> List[DesignPattern]:
        """
        Return patterns whose text fields contain *query* as a substring.

        Case-insensitive. Deterministic. Results sorted by id.
        No AI. No semantic matching. No fuzzy matching.
        """
        needle = query.strip().lower()
        if not needle:
            return []
        return [
            p for p in self._repository.list_all()
            if self._pattern_matches(p, needle)
        ]

    def _pattern_matches(self, pattern: DesignPattern, needle: str) -> bool:
        searchable = [
            pattern.id, pattern.name, pattern.intent,
            pattern.problem, pattern.solution,
            *pattern.tags, *pattern.advantages,
            *pattern.disadvantages, *pattern.examples,
            *pattern.when_to_use, *pattern.when_not_to_use,
        ]
        return any(needle in s.lower() for s in searchable)
