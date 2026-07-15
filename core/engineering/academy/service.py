"""
Engineering Academy Service.

Deterministic lookup and search over the principle repository.
No AI. No semantic search. No mutations. No autonomous decisions.
"""

from __future__ import annotations

from typing import List, Optional

from .exceptions import PrincipleNotFoundError
from .models import EngineeringPrinciple
from .repository import AcademyRepository


class AcademyService:
    """
    Business-logic layer for the Engineering Academy.

    Provides deterministic access to engineering principles.
    All search is keyword / substring-based — no AI, no fuzzy matching.

    Parameters
    ----------
    repository:
        Any ``AcademyRepository`` implementation.
    """

    def __init__(self, repository: AcademyRepository) -> None:
        self._repository = repository

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def find_by_category(self, category: str) -> List[EngineeringPrinciple]:
        """
        Return principles that belong to *category* (case-insensitive).

        Returns an empty list if the category is not found — never raises.
        """
        return self._repository.filter_by_category(category)

    def find_by_tag(self, tag: str) -> List[EngineeringPrinciple]:
        """
        Return principles tagged with *tag* (case-insensitive).

        Returns an empty list if no match — never raises.
        """
        return self._repository.filter_by_tag(tag)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[EngineeringPrinciple]:
        """
        Return principles whose text fields contain *query* as a substring.

        Search is case-insensitive and deterministic.
        Fields searched (in priority order, but all results returned):
        ``id``, ``name``, ``summary``, ``rationale``, ``guidance``, ``tags``.

        No AI. No semantic matching. No fuzzy matching.
        Results are sorted by id for deterministic ordering.

        Parameters
        ----------
        query:
            The substring to search for. Whitespace is stripped.

        Returns
        -------
        List of matching principles, sorted by id. Empty list if no match.
        """
        needle = query.strip().lower()
        if not needle:
            return []

        results: List[EngineeringPrinciple] = []
        for principle in self._repository.list_all():
            if self._matches(principle, needle):
                results.append(principle)

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _matches(self, principle: EngineeringPrinciple, needle: str) -> bool:
        """Return True if *needle* appears in any searchable field."""
        searchable_strings = [
            principle.id,
            principle.name,
            principle.summary,
            principle.rationale,
            principle.guidance,
            *principle.tags,
            *principle.violations,
            *principle.examples,
        ]
        return any(needle in s.lower() for s in searchable_strings)
