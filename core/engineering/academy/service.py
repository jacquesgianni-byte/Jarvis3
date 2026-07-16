"""
Engineering Academy Services.

Deterministic lookup and search over principle, pattern, and
anti-pattern repositories.
No AI. No semantic search. No mutations. No autonomous decisions.
"""

from __future__ import annotations

from typing import List, Optional

from .exceptions import PrincipleNotFoundError
from .models import AntiPattern, ArchitecturePattern, BestPractice, DesignPattern, EngineeringPrinciple
from .repository import (
    AcademyRepository,
    AntiPatternRepository,
    ArchitecturePatternRepository,
    BestPracticeRepository,
    PatternRepository,
)


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


class AntiPatternService:
    """
    Business-logic layer for engineering anti-patterns.
    (Genesis-019 Sprint 003)

    Provides deterministic access to anti-patterns.
    All search is keyword/substring-based — no AI, no fuzzy matching.
    """

    def __init__(self, repository: AntiPatternRepository) -> None:
        self._repository = repository

    def get_anti_pattern(self, anti_pattern_id: str) -> AntiPattern:
        """
        Return the anti-pattern with *anti_pattern_id*.

        Raises
        ------
        PrincipleNotFoundError
            If no anti-pattern with that ID exists.
        """
        result = self._repository.get_by_id(anti_pattern_id)
        if result is None:
            raise PrincipleNotFoundError(anti_pattern_id)
        return result

    def list_anti_patterns(self) -> List[AntiPattern]:
        """Return all anti-patterns in stable, deterministic order (sorted by id)."""
        return self._repository.list_all()

    def find_by_category(self, category: str) -> List[AntiPattern]:
        """Return anti-patterns in *category* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_category(category)

    def find_by_tag(self, tag: str) -> List[AntiPattern]:
        """Return anti-patterns tagged with *tag* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_tag(tag)

    def search(self, query: str) -> List[AntiPattern]:
        """
        Return anti-patterns whose text fields contain *query* as a substring.

        Case-insensitive. Deterministic. Results sorted by id.
        No AI. No semantic matching. No fuzzy matching.
        """
        needle = query.strip().lower()
        if not needle:
            return []
        return [
            ap for ap in self._repository.list_all()
            if self._anti_pattern_matches(ap, needle)
        ]

    def _anti_pattern_matches(self, ap: AntiPattern, needle: str) -> bool:
        searchable = [
            ap.id, ap.name, ap.category, ap.description,
            ap.recommended_solution,
            *ap.tags, *ap.symptoms, *ap.consequences,
            *ap.detection, *ap.examples,
        ]
        return any(needle in s.lower() for s in searchable)


class ArchitecturePatternService:
    """
    Business-logic layer for engineering architecture patterns.
    (Genesis-019 Sprint 004)

    Provides deterministic access to architecture patterns.
    All search is keyword/substring-based — no AI, no fuzzy matching.
    """

    def __init__(self, repository: ArchitecturePatternRepository) -> None:
        self._repository = repository

    def get_architecture_pattern(self, architecture_pattern_id: str) -> ArchitecturePattern:
        """
        Return the architecture pattern with *architecture_pattern_id*.

        Raises
        ------
        PrincipleNotFoundError
            If no architecture pattern with that ID exists.
        """
        result = self._repository.get_by_id(architecture_pattern_id)
        if result is None:
            raise PrincipleNotFoundError(architecture_pattern_id)
        return result

    def list_architecture_patterns(self) -> list:
        """Return all architecture patterns in stable, deterministic order (sorted by id)."""
        return self._repository.list_all()

    def find_by_category(self, category: str) -> list:
        """Return architecture patterns in *category* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_category(category)

    def find_by_tag(self, tag: str) -> list:
        """Return architecture patterns tagged with *tag* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_tag(tag)

    def search(self, query: str) -> list:
        """
        Return architecture patterns whose text fields contain *query* as a substring.

        Case-insensitive. Deterministic. Results sorted by id.
        No AI. No semantic matching. No fuzzy matching.
        """
        needle = query.strip().lower()
        if not needle:
            return []
        return [
            ap for ap in self._repository.list_all()
            if self._architecture_pattern_matches(ap, needle)
        ]

    def _architecture_pattern_matches(self, ap: ArchitecturePattern, needle: str) -> bool:
        searchable = [
            ap.id, ap.name, ap.category, ap.description,
            ap.intent, ap.structure,
            *ap.tags, *ap.components, *ap.advantages,
            *ap.disadvantages, *ap.when_to_use,
            *ap.when_not_to_use, *ap.examples,
        ]
        return any(needle in s.lower() for s in searchable)


class BestPracticeService:
    """
    Business-logic layer for engineering best practices.
    (Genesis-019 Sprint 005)

    Provides deterministic access to best practices.
    All search is keyword/substring-based — no AI, no fuzzy matching.
    """

    def __init__(self, repository: BestPracticeRepository) -> None:
        self._repository = repository

    def get_best_practice(self, best_practice_id: str) -> BestPractice:
        """
        Return the best practice with *best_practice_id*.

        Raises
        ------
        PrincipleNotFoundError
            If no best practice with that ID exists.
        """
        result = self._repository.get_by_id(best_practice_id)
        if result is None:
            raise PrincipleNotFoundError(best_practice_id)
        return result

    def list_best_practices(self) -> list:
        """Return all best practices in stable, deterministic order (sorted by id)."""
        return self._repository.list_all()

    def find_by_category(self, category: str) -> list:
        """Return best practices in *category* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_category(category)

    def find_by_tag(self, tag: str) -> list:
        """Return best practices tagged with *tag* (case-insensitive). Empty list if none."""
        return self._repository.filter_by_tag(tag)

    def search(self, query: str) -> list:
        """
        Return best practices whose text fields contain *query* as a substring.

        Case-insensitive. Deterministic. Results sorted by id.
        No AI. No semantic matching. No fuzzy matching.
        """
        needle = query.strip().lower()
        if not needle:
            return []
        return [
            bp for bp in self._repository.list_all()
            if self._best_practice_matches(bp, needle)
        ]

    def _best_practice_matches(self, bp: BestPractice, needle: str) -> bool:
        searchable = [
            bp.id, bp.name, bp.category, bp.description, bp.rationale,
            *bp.tags, *bp.implementation_guidance, *bp.benefits,
            *bp.common_mistakes, *bp.examples,
        ]
        return any(needle in s.lower() for s in searchable)