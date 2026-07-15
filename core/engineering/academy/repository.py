"""
Engineering Academy Repository.

Abstract read-only interface for principle storage.
No write operations. No mutation. No caching requirements.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import EngineeringPrinciple


class AcademyRepository(ABC):
    """
    Abstract base class for the Engineering Academy data layer.

    Contract
    --------
    * All operations are read-only.
    * Implementations must never mutate stored principles.
    * Result ordering must be stable and deterministic.
    """

    @abstractmethod
    def get_by_id(self, principle_id: str) -> Optional[EngineeringPrinciple]:
        """
        Return the principle with *principle_id*, or ``None`` if not found.

        Parameters
        ----------
        principle_id:
            The unique kebab-case identifier (e.g. ``"dry"``).
        """

    @abstractmethod
    def list_all(self) -> List[EngineeringPrinciple]:
        """
        Return all principles in stable, deterministic order.

        Order is sorted by ``id`` ascending.
        """

    @abstractmethod
    def filter_by_category(self, category: str) -> List[EngineeringPrinciple]:
        """
        Return all principles whose ``category`` matches *category* (case-insensitive).

        Returns an empty list if no match is found — never raises.
        """

    @abstractmethod
    def filter_by_tag(self, tag: str) -> List[EngineeringPrinciple]:
        """
        Return all principles whose ``tags`` list contains *tag* (case-insensitive).

        Returns an empty list if no match is found — never raises.
        """
