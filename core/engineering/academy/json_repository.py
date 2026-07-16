"""
Engineering Academy JSON Repositories.

Concrete implementations of AcademyRepository, PatternRepository,
and AntiPatternRepository backed by JSON files.

Loads on construction. Returns immutable model objects. No writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .loader import AcademyLoader
from .models import AntiPattern, ArchitecturePattern, BestPractice, DesignPattern, EngineeringDecision, EngineeringPrinciple
from .repository import AcademyRepository, AntiPatternRepository, ArchitecturePatternRepository, BestPracticeRepository, EngineeringDecisionRepository, PatternRepository


class JsonAcademyRepository(AcademyRepository):
    """
    Read-only repository that loads engineering principles from a JSON file.

    All data is loaded once at construction time.
    No runtime writes. No mutations. No network access.
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


class JsonAntiPatternRepository(AntiPatternRepository):
    """
    Read-only repository that loads anti-patterns from a JSON file.
    (Genesis-019 Sprint 003)

    All data is loaded once at construction time.
    No runtime writes. No mutations. No network access.

    Parameters
    ----------
    anti_patterns_path:
        Path to the ``anti_patterns.json`` data file.
    loader:
        Optional ``AcademyLoader`` instance (injected for testability).
    """

    def __init__(
        self,
        anti_patterns_path: Path,
        loader: Optional[AcademyLoader] = None,
    ) -> None:
        _loader = loader or AcademyLoader()
        raw = _loader.load_anti_patterns(anti_patterns_path)
        self._index: Dict[str, AntiPattern] = {
            ap.id: ap for ap in sorted(raw, key=lambda ap: ap.id)
        }

    def get_by_id(self, anti_pattern_id: str) -> Optional[AntiPattern]:
        return self._index.get(anti_pattern_id)

    def list_all(self) -> List[AntiPattern]:
        return list(self._index.values())

    def filter_by_category(self, category: str) -> List[AntiPattern]:
        target = category.strip().lower()
        return [
            ap for ap in self._index.values()
            if ap.category.lower() == target
        ]

    def filter_by_tag(self, tag: str) -> List[AntiPattern]:
        target = tag.strip().lower()
        return [
            ap for ap in self._index.values()
            if target in [t.lower() for t in ap.tags]
        ]


class JsonArchitecturePatternRepository(ArchitecturePatternRepository):
    """
    Read-only repository that loads architecture patterns from a JSON file.
    (Genesis-019 Sprint 004)

    All data is loaded once at construction time.
    No runtime writes. No mutations. No network access.

    Parameters
    ----------
    architecture_patterns_path:
        Path to the ``architecture_patterns.json`` data file.
    loader:
        Optional ``AcademyLoader`` instance (injected for testability).
    """

    def __init__(
        self,
        architecture_patterns_path: Path,
        loader=None,
    ) -> None:
        _loader = loader or AcademyLoader()
        raw = _loader.load_architecture_patterns(architecture_patterns_path)
        self._index: Dict[str, ArchitecturePattern] = {
            ap.id: ap for ap in sorted(raw, key=lambda ap: ap.id)
        }

    def get_by_id(self, architecture_pattern_id: str):
        return self._index.get(architecture_pattern_id)

    def list_all(self) -> list:
        return list(self._index.values())

    def filter_by_category(self, category: str) -> list:
        target = category.strip().lower()
        return [
            ap for ap in self._index.values()
            if ap.category.lower() == target
        ]

    def filter_by_tag(self, tag: str) -> list:
        target = tag.strip().lower()
        return [
            ap for ap in self._index.values()
            if target in [t.lower() for t in ap.tags]
        ]


class JsonBestPracticeRepository(BestPracticeRepository):
    """
    Read-only repository that loads best practices from a JSON file.
    (Genesis-019 Sprint 005)

    All data is loaded once at construction time.
    No runtime writes. No mutations. No network access.
    """

    def __init__(self, best_practices_path, loader=None) -> None:
        _loader = loader or AcademyLoader()
        raw = _loader.load_best_practices(best_practices_path)
        self._index: Dict[str, BestPractice] = {
            bp.id: bp for bp in sorted(raw, key=lambda bp: bp.id)
        }

    def get_by_id(self, best_practice_id: str):
        return self._index.get(best_practice_id)

    def list_all(self) -> list:
        return list(self._index.values())

    def filter_by_category(self, category: str) -> list:
        target = category.strip().lower()
        return [bp for bp in self._index.values() if bp.category.lower() == target]

    def filter_by_tag(self, tag: str) -> list:
        target = tag.strip().lower()
        return [bp for bp in self._index.values()
                if target in [t.lower() for t in bp.tags]]


class JsonEngineeringDecisionRepository(EngineeringDecisionRepository):
    """
    Read-only repository that loads engineering decisions from a JSON file.
    (Genesis-019 Sprint 006)

    All data is loaded once at construction time.
    No runtime writes. No mutations. No network access.
    """

    def __init__(self, decisions_path, loader=None) -> None:
        _loader = loader or AcademyLoader()
        raw = _loader.load_engineering_decisions(decisions_path)
        self._index: Dict[str, EngineeringDecision] = {
            d.id: d for d in sorted(raw, key=lambda d: d.id)
        }

    def get_by_id(self, decision_id: str):
        return self._index.get(decision_id)

    def list_all(self) -> list:
        return list(self._index.values())

    def filter_by_category(self, category: str) -> list:
        target = category.strip().lower()
        return [d for d in self._index.values() if d.category.lower() == target]

    def filter_by_tag(self, tag: str) -> list:
        target = tag.strip().lower()
        return [d for d in self._index.values()
                if target in [t.lower() for t in d.tags]]