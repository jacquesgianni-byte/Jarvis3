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


# Required fields every architecture pattern record must supply.
REQUIRED_ARCHITECTURE_PATTERN_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "category",
    "description",
    "intent",
    "structure",
    "components",
    "advantages",
    "disadvantages",
    "when_to_use",
    "when_not_to_use",
    "tags",
)


@dataclass(frozen=True)
class ArchitecturePattern:
    """
    An immutable record describing a software architecture pattern.
    (Genesis-019 Sprint 004)

    frozen=True enforces the read-only contract of the Academy.

    Fields
    ------
    id                    : Unique kebab-case identifier.
    name                  : Human-readable name.
    category              : Architecture category (e.g. "structural",
                            "distributed", "presentation", "data-flow",
                            "extensibility").
    description           : What the pattern is and how it manifests.
    intent                : The goal the pattern achieves.
    structure             : How the pattern is organised.
    components            : The named parts of the pattern and their roles.
    advantages            : Benefits of the pattern.
    disadvantages         : Trade-offs and costs.
    when_to_use           : Conditions under which the pattern is appropriate.
    when_not_to_use       : Conditions under which the pattern should be avoided.
    related_principles    : IDs of principles this pattern embodies.
    related_patterns      : IDs of design patterns used within this architecture.
    related_anti_patterns : IDs of anti-patterns this architecture guards against.
    examples              : Concrete examples, including Jarvis-specific ones.
    references            : Book or article citations.
    tags                  : Keywords for filtering and search.
    """

    id: str
    name: str
    category: str
    description: str
    intent: str
    structure: str
    components: List[str]
    advantages: List[str]
    disadvantages: List[str]
    when_to_use: List[str]
    when_not_to_use: List[str]
    tags: List[str]
    related_principles: List[str] = field(default_factory=list)
    related_patterns: List[str] = field(default_factory=list)
    related_anti_patterns: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        list_fields = (
            "components", "advantages", "disadvantages",
            "when_to_use", "when_not_to_use", "tags",
            "related_principles", "related_patterns",
            "related_anti_patterns", "examples", "references",
        )
        for lf in list_fields:
            value = getattr(self, lf)
            if not isinstance(value, list):
                object.__setattr__(self, lf, list(value))

    @classmethod
    def from_dict(cls, data: dict) -> "ArchitecturePattern":
        """Construct an ArchitecturePattern from a raw dictionary."""
        known = {
            "id", "name", "category", "description", "intent",
            "structure", "components", "advantages", "disadvantages",
            "when_to_use", "when_not_to_use", "related_principles",
            "related_patterns", "related_anti_patterns",
            "examples", "references", "tags",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            description=data["description"],
            intent=data["intent"],
            structure=data["structure"],
            components=list(data.get("components", [])),
            advantages=list(data.get("advantages", [])),
            disadvantages=list(data.get("disadvantages", [])),
            when_to_use=list(data.get("when_to_use", [])),
            when_not_to_use=list(data.get("when_not_to_use", [])),
            tags=list(data.get("tags", [])),
            related_principles=list(data.get("related_principles", [])),
            related_patterns=list(data.get("related_patterns", [])),
            related_anti_patterns=list(data.get("related_anti_patterns", [])),
            examples=list(data.get("examples", [])),
            references=list(data.get("references", [])),
            extra=extra,
        )


# Required fields every best practice record must supply.
REQUIRED_BEST_PRACTICE_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "category",
    "description",
    "rationale",
    "implementation_guidance",
    "benefits",
    "common_mistakes",
    "tags",
)


@dataclass(frozen=True)
class BestPractice:
    """
    An immutable record describing an engineering best practice.
    (Genesis-019 Sprint 005)

    frozen=True enforces the read-only contract of the Academy.

    Fields
    ------
    id                           : Unique kebab-case identifier.
    name                         : Human-readable name.
    category                     : Practice category (e.g. "design",
                                   "reliability", "quality", "process",
                                   "operations", "communication", "readability").
    description                  : What the practice is and why it matters.
    rationale                    : The engineering reasoning behind the practice.
    implementation_guidance      : Actionable steps for applying the practice.
    benefits                     : The outcomes of applying the practice consistently.
    common_mistakes              : Typical ways this practice is applied incorrectly.
    related_principles           : IDs of principles that underpin this practice.
    related_patterns             : IDs of design patterns that support this practice.
    related_anti_patterns        : IDs of anti-patterns this practice guards against.
    related_architecture_patterns: IDs of architecture patterns where this applies.
    examples                     : Concrete examples, including Jarvis-specific ones.
    references                   : Book or article citations.
    tags                         : Keywords for filtering and search.
    """

    id: str
    name: str
    category: str
    description: str
    rationale: str
    implementation_guidance: List[str]
    benefits: List[str]
    common_mistakes: List[str]
    tags: List[str]
    related_principles: List[str] = field(default_factory=list)
    related_patterns: List[str] = field(default_factory=list)
    related_anti_patterns: List[str] = field(default_factory=list)
    related_architecture_patterns: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        list_fields = (
            "implementation_guidance", "benefits", "common_mistakes", "tags",
            "related_principles", "related_patterns", "related_anti_patterns",
            "related_architecture_patterns", "examples", "references",
        )
        for lf in list_fields:
            value = getattr(self, lf)
            if not isinstance(value, list):
                object.__setattr__(self, lf, list(value))

    @classmethod
    def from_dict(cls, data: dict) -> "BestPractice":
        """Construct a BestPractice from a raw dictionary."""
        known = {
            "id", "name", "category", "description", "rationale",
            "implementation_guidance", "benefits", "common_mistakes",
            "related_principles", "related_patterns", "related_anti_patterns",
            "related_architecture_patterns", "examples", "references", "tags",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            description=data["description"],
            rationale=data["rationale"],
            implementation_guidance=list(data.get("implementation_guidance", [])),
            benefits=list(data.get("benefits", [])),
            common_mistakes=list(data.get("common_mistakes", [])),
            tags=list(data.get("tags", [])),
            related_principles=list(data.get("related_principles", [])),
            related_patterns=list(data.get("related_patterns", [])),
            related_anti_patterns=list(data.get("related_anti_patterns", [])),
            related_architecture_patterns=list(data.get("related_architecture_patterns", [])),
            examples=list(data.get("examples", [])),
            references=list(data.get("references", [])),
            extra=extra,
        )


# Required fields every engineering decision record must supply.
REQUIRED_ENGINEERING_DECISION_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "category",
    "situation",
    "indicators",
    "recommended_action",
    "trade_offs",
    "risks",
    "benefits",
    "decision_questions",
    "tags",
)


@dataclass(frozen=True)
class EngineeringDecision:
    """
    An immutable record describing an engineering decision framework.
    (Genesis-019 Sprint 006)

    frozen=True enforces the read-only contract of the Academy.

    Fields
    ------
    id                           : Unique kebab-case identifier.
    name                         : Human-readable decision name.
    category                     : Decision category.
    situation                    : When this decision arises.
    indicators                   : Signals that suggest each option.
    recommended_action           : The default recommended approach.
    trade_offs                   : What each option gains and loses.
    risks                        : Risks associated with each option.
    benefits                     : Benefits of the recommended action.
    decision_questions           : Questions to ask before deciding.
    related_principles           : Principle IDs relevant to this decision.
    related_patterns             : Pattern IDs relevant to this decision.
    related_anti_patterns        : Anti-pattern IDs relevant to this decision.
    related_architecture_patterns: Architecture pattern IDs relevant.
    related_best_practices       : Best practice IDs relevant to this decision.
    jarvis_example               : A Jarvis-specific concrete example.
    references                   : Book or article citations.
    tags                         : Keywords for filtering and search.
    """

    id: str
    name: str
    category: str
    situation: str
    recommended_action: str
    jarvis_example: str
    indicators: List[str]
    trade_offs: List[str]
    risks: List[str]
    benefits: List[str]
    decision_questions: List[str]
    tags: List[str]
    related_principles: List[str] = field(default_factory=list)
    related_patterns: List[str] = field(default_factory=list)
    related_anti_patterns: List[str] = field(default_factory=list)
    related_architecture_patterns: List[str] = field(default_factory=list)
    related_best_practices: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        list_fields = (
            "indicators", "trade_offs", "risks", "benefits",
            "decision_questions", "tags", "related_principles",
            "related_patterns", "related_anti_patterns",
            "related_architecture_patterns", "related_best_practices",
            "references",
        )
        for lf in list_fields:
            value = getattr(self, lf)
            if not isinstance(value, list):
                object.__setattr__(self, lf, list(value))

    @classmethod
    def from_dict(cls, data: dict) -> "EngineeringDecision":
        """Construct an EngineeringDecision from a raw dictionary."""
        known = {
            "id", "name", "category", "situation", "indicators",
            "recommended_action", "trade_offs", "risks", "benefits",
            "decision_questions", "related_principles", "related_patterns",
            "related_anti_patterns", "related_architecture_patterns",
            "related_best_practices", "jarvis_example", "references", "tags",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            situation=data["situation"],
            recommended_action=data["recommended_action"],
            jarvis_example=data["jarvis_example"],
            indicators=list(data.get("indicators", [])),
            trade_offs=list(data.get("trade_offs", [])),
            risks=list(data.get("risks", [])),
            benefits=list(data.get("benefits", [])),
            decision_questions=list(data.get("decision_questions", [])),
            tags=list(data.get("tags", [])),
            related_principles=list(data.get("related_principles", [])),
            related_patterns=list(data.get("related_patterns", [])),
            related_anti_patterns=list(data.get("related_anti_patterns", [])),
            related_architecture_patterns=list(data.get("related_architecture_patterns", [])),
            related_best_practices=list(data.get("related_best_practices", [])),
            references=list(data.get("references", [])),
            extra=extra,
        )