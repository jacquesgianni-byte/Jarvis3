"""
Engineering Academy JSON Repository.

Concrete implementation of AcademyRepository backed by principles.json.
Loads on construction. Returns immutable model objects. No writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .exceptions import PrincipleNotFoundError
from .loader import AcademyLoader
from .models import EngineeringPrinciple
from .repository import AcademyRepository


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
        Defaults to a standard ``AcademyLoader`` if not supplied.
    """

    def __init__(
        self,
        principles_path: Path,
        loader: Optional[AcademyLoader] = None,
    ) -> None:
        _loader = loader or AcademyLoader()
        raw = _loader.load(principles_path)

        # Store as an ordered dict keyed by id for O(1) lookup.
        # Sorted by id for deterministic list_all() order.
        self._index: Dict[str, EngineeringPrinciple] = {
            p.id: p for p in sorted(raw, key=lambda p: p.id)
        }

    # ------------------------------------------------------------------
    # AcademyRepository interface
    # ------------------------------------------------------------------

    def get_by_id(self, principle_id: str) -> Optional[EngineeringPrinciple]:
        """Return the principle with *principle_id*, or ``None``."""
        return self._index.get(principle_id)

    def list_all(self) -> List[EngineeringPrinciple]:
        """Return all principles sorted by id (stable, deterministic)."""
        return list(self._index.values())

    def filter_by_category(self, category: str) -> List[EngineeringPrinciple]:
        """Return principles whose category matches *category* (case-insensitive)."""
        target = category.strip().lower()
        return [
            p for p in self._index.values()
            if p.category.lower() == target
        ]

    def filter_by_tag(self, tag: str) -> List[EngineeringPrinciple]:
        """Return principles whose tags list contains *tag* (case-insensitive)."""
        target = tag.strip().lower()
        return [
            p for p in self._index.values()
            if target in [t.lower() for t in p.tags]
        ]
