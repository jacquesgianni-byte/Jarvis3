"""
Engineering Academy JSON Repositories.

Concrete implementations of AcademyRepository and PatternRepository
backed by principles.json and patterns.json respectively.
Loads on construction. Returns immutable model objects. No writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .loader import AcademyLoader
from .models import DesignPattern, EngineeringPrinciple
from .repository import AcademyRepository, PatternRepository


class JsonAcademyRepository(AcademyRepository):
    """
    Read-only repository that loads engineering principles from a JSON file.

    All data is loaded once at construction time.
    No runtime writes. No mutations. No network access.

    Parameters
    ----------
    principles_path:
        Path to the ``principles.json`` data file.
    loader:
        Optional ``AcademyLoader`` instance (injected for testability).
    """

    def __init__(
        self,
        principles_path: Path,
        loader: Optional[AcademyLoader] = None,
    ) -> None:
        _loader = loader or AcademyLoader()
        raw = _loader.load(principles_path)
        self._index: Dict[str, EngineeringPrinciple] = {
            p.id: p for p in sorted(raw, key=lambda p: p.id)
        }

    def get_by_id(self, principle_id: str) -> Optional[EngineeringPrinciple]:
        return self._index.get(principle_id)

    def list_all(self) -> List[EngineeringPrinciple]:
        return list(self._index.values())

    def filter_by_category(self, category: str) -> List[EngineeringPrinciple]:
        target = category.strip().lower()
        return [p for p in self._index.values() if p.category.lower() == target]

    def filter_by_tag(self, tag: str) -> List[EngineeringPrinciple]:
        target = tag.strip().lower()
        return [
            p for p in self._index.values()
            if target in [t.lower() for t in p.tags]
        ]


class JsonPatternRepository(PatternRepository):
    """
    Read-only repository that loads design patterns from a JSON file.

    All data is loaded once at construction time.
    No runtime writes. No mutations. No network access.

    Parameters
    ----------
    patterns_path:
        Path to the ``patterns.json`` data file.
    loader:
        Optional ``AcademyLoader`` instance (injected for testability).
    """

    def __init__(
        self,
        patterns_path: Path,
        loader: Optional[AcademyLoader] = None,
    ) -> None:
        _loader = loader or AcademyLoader()
        raw = _loader.load_patterns(patterns_path)
        self._index: Dict[str, DesignPattern] = {
            p.id: p for p in sorted(raw, key=lambda p: p.id)
        }

    def get_by_id(self, pattern_id: str) -> Optional[DesignPattern]:
        return self._index.get(pattern_id)

    def list_all(self) -> List[DesignPattern]:
        return list(self._index.values())

    def filter_by_category(self, category: str) -> List[DesignPattern]:
        target = category.strip().lower()
        return [p for p in self._index.values() if p.category.lower() == target]

    def filter_by_tag(self, tag: str) -> List[DesignPattern]:
        target = tag.strip().lower()
        return [
            p for p in self._index.values()
            if target in [t.lower() for t in p.tags]
        ]