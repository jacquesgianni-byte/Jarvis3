"""
Engineering Academy Models.

Immutable data models representing engineering principles, design patterns,
and anti-patterns.
No behaviour. No mutation. Pure data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


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

# Required fields every pattern record must supply.
REQUIRED_PATTERN_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "category",
    "intent",
    "problem",
    "solution",
    "when_to_use",
    "when_not_to_use",
    "advantages",
    "disadvantages",
    "tags",
)

# Required fields every anti-pattern record must supply.
REQUIRED_ANTI_PATTERN_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "category",
    "description",
    "symptoms",
    "consequences",
    "detection",
    "recommended_solution",
    "tags",
)


@dataclass(frozen=True)
class EngineeringPrinciple:
    """
    An immutable record describing a single engineering principle.

    frozen=True ensures no code can mutate a principle after construction,
    satisfying the read-only contract of the Academy.
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
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        for list_field in ("violations", "tags", "examples", "references"):
            value = getattr(self, list_field)
            if not isinstance(value, list):
                object.__setattr__(self, list_field, list(value))

    @classmethod
    def from_dict(cls, data: dict) -> "EngineeringPrinciple":
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


@dataclass(frozen=True)
class DesignPattern:
    """
    An immutable record describing a single software design pattern.

    frozen=True enforces the read-only contract of the Academy.
    """

    id: str
    name: str
    category: str
    intent: str
    problem: str
    solution: str
    when_to_use: List[str]
    when_not_to_use: List[str]
    advantages: List[str]
    disadvantages: List[str]
    tags: List[str]
    related_principles: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        list_fields = (
            "when_to_use", "when_not_to_use", "advantages",
            "disadvantages", "tags", "related_principles",
            "examples", "references",
        )
        for lf in list_fields:
            value = getattr(self, lf)
            if not isinstance(value, list):
                object.__setattr__(self, lf, list(value))

    @classmethod
    def from_dict(cls, data: dict) -> "DesignPattern":
        known = {
            "id", "name", "category", "intent", "problem", "solution",
            "when_to_use", "when_not_to_use", "advantages", "disadvantages",
            "related_principles", "examples", "references", "tags",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            intent=data["intent"],
            problem=data["problem"],
            solution=data["solution"],
            when_to_use=list(data.get("when_to_use", [])),
            when_not_to_use=list(data.get("when_not_to_use", [])),
            advantages=list(data.get("advantages", [])),
            disadvantages=list(data.get("disadvantages", [])),
            tags=list(data.get("tags", [])),
            related_principles=list(data.get("related_principles", [])),
            examples=list(data.get("examples", [])),
            references=list(data.get("references", [])),
            extra=extra,
        )


@dataclass(frozen=True)
class AntiPattern:
    """
    An immutable record describing a single software anti-pattern.

    frozen=True enforces the read-only contract of the Academy.

    Fields
    ------
    id                   : Unique kebab-case identifier (e.g. ``"god-object"``).
    name                 : Human-readable name.
    category             : Anti-pattern category (e.g. ``"object-oriented"``,
                           ``"structural"``, ``"maintenance"``, ``"process"``).
    description          : What the anti-pattern is and how it manifests.
    symptoms             : Observable signs that the anti-pattern is present.
    consequences         : Problems that result from the anti-pattern.
    detection            : How to identify the anti-pattern in a codebase.
    recommended_solution : How to refactor away from the anti-pattern.
    related_principles   : IDs of principles violated by this anti-pattern.
    related_patterns     : IDs of design patterns that address this anti-pattern.
    examples             : Concrete examples, including Jarvis-specific ones.
    references           : Book or article citations.
    tags                 : Keywords for filtering and search.
    """

    id: str
    name: str
    category: str
    description: str
    symptoms: List[str]
    consequences: List[str]
    detection: List[str]
    recommended_solution: str
    tags: List[str]
    related_principles: List[str] = field(default_factory=list)
    related_patterns: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        list_fields = (
            "symptoms", "consequences", "detection", "tags",
            "related_principles", "related_patterns",
            "examples", "references",
        )
        for lf in list_fields:
            value = getattr(self, lf)
            if not isinstance(value, list):
                object.__setattr__(self, lf, list(value))

    @classmethod
    def from_dict(cls, data: dict) -> "AntiPattern":
        """Construct an AntiPattern from a raw dictionary."""
        known = {
            "id", "name", "category", "description", "symptoms",
            "consequences", "detection", "recommended_solution",
            "related_principles", "related_patterns",
            "examples", "references", "tags",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            description=data["description"],
            symptoms=list(data.get("symptoms", [])),
            consequences=list(data.get("consequences", [])),
            detection=list(data.get("detection", [])),
            recommended_solution=data["recommended_solution"],
            tags=list(data.get("tags", [])),
            related_principles=list(data.get("related_principles", [])),
            related_patterns=list(data.get("related_patterns", [])),
            examples=list(data.get("examples", [])),
            references=list(data.get("references", [])),
            extra=extra,
        )