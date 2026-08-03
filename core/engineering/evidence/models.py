"""
Engineering Evidence Manager — Models
Genesis-034 Sprint-002

Structured evidence accumulated during a Genesis session.
All fields map directly to EngineeringReview evidence dict fields
so the snapshot can be passed directly to EngineeringReviewOSWorker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvidenceSnapshot:
    """
    Immutable-style snapshot of accumulated Genesis evidence.
    Produced by EvidenceStore.snapshot() and consumed by
    EngineeringReviewOSWorker as its evidence dict.

    Field names match the EngineeringReviewWorker evidence contract exactly.
    """
    genesis:               str
    sprint:                str = ""
    status:                str = "in_progress"
    commits:               list[str] = field(default_factory=list)
    files_added:           list[str] = field(default_factory=list)
    files_modified:        list[str] = field(default_factory=list)
    architecture_decisions: list[dict] = field(default_factory=list)
    tests_added:           int = 0
    test_results:          dict = field(default_factory=lambda: {
        "passed": 0, "skipped": 0, "failed": 0, "warnings": 0
    })
    desktop_validation:    dict = field(default_factory=lambda: {
        "status": "pending", "scenarios": [], "notes": None
    })
    technical_debt:        list[str] = field(default_factory=list)
    risks:                 list[str] = field(default_factory=list)
    future_improvements:   list[dict] = field(default_factory=list)
    technical_problem:     str = ""
    technical_uncertainty: str = ""
    hypothesis:            str = ""
    approach:              str = ""
    experiments:           list[str] = field(default_factory=list)
    results:               str = ""
    validation:            str = ""
    remaining_unknowns:    list[str] = field(default_factory=list)
    recommendation:        str = "CONTINUE_GENESIS"
    recommendation_reason: str = ""

    def to_dict(self) -> dict:
        """Convert to the evidence dict format expected by EngineeringReviewOSWorker."""
        import dataclasses
        return dataclasses.asdict(self)

    def is_reviewable(self) -> bool:
        """
        True if enough evidence has been collected to produce a meaningful review.
        Minimum: genesis number and recommendation_reason must be set.
        """
        return bool(self.genesis and self.recommendation_reason)
