"""
Engineering Academy Models.

Immutable data models representing engineering principles.
No behaviour. No mutation. Pure data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# Required fields every principle record must supply.
REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "category",
    "summary",
    "rationale",
    "guidance",
    "violations",
    "tags",
)


@dataclass(frozen=True)
class EngineeringPrinciple:
    """
    An immutable record describing a single engineering principle.

    frozen=True ensures no code can mutate a principle after construction,
    satisfying the read-only contract of the Academy.

    Fields
    ------
    id          : Unique kebab-case identifier (e.g. ``"dry"``, ``"solid-srp"``).
    name        : Human-readable name.
    category    : High-level grouping (e.g. ``"core"``, ``"jarvis"``).
    summary     : One-sentence description.
    rationale   : Why this principle exists.
    guidance    : Actionable advice for applying the principle.
    violations  : Common ways the principle is broken.
    examples    : Optional concrete code or design examples.
    references  : Optional links or book citations.
    tags        : Keywords used for filtering and search.
    """

    id: str
    name: str
    category: str
    summary: str
    rationale: str
    guidance: str
    violations: List[str]
    tags: List[str]
    examples: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)

    # Allow unknown extra fields from the JSON to be stored without
    # breaking compatibility as the schema evolves.
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        # Enforce that list fields are actual lists (not None slipping through).
        for list_field in ("violations", "tags", "examples", "references"):
            value = getattr(self, list_field)
            if not isinstance(value, list):
                object.__setattr__(self, list_field, list(value))

    @classmethod
    def from_dict(cls, data: dict) -> "EngineeringPrinciple":
        """
        Construct an EngineeringPrinciple from a raw dictionary.

        Unknown keys are preserved in ``extra`` for forward compatibility.
        """
        known = {
            "id", "name", "category", "summary", "rationale",
            "guidance", "violations", "examples", "references", "tags",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            summary=data["summary"],
            rationale=data["rationale"],
            guidance=data["guidance"],
            violations=list(data.get("violations", [])),
            tags=list(data.get("tags", [])),
            examples=list(data.get("examples", [])),
            references=list(data.get("references", [])),
            extra=extra,
        )
