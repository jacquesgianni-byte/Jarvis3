"""
Engineering Intelligence — Data Models
Genesis-033 Sprint-001

Structured data models for the Engineering Review subsystem.
All models use dataclasses and enums. No raw dicts as primary types.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Enums ──────────────────────────────────────────────────────────────────────

class GenesisStatus(str, Enum):
    COMPLETE      = "complete"
    IN_PROGRESS   = "in_progress"
    ABANDONED     = "abandoned"
    STABILISING   = "stabilising"


class Recommendation(str, Enum):
    CONTINUE_GENESIS    = "CONTINUE_GENESIS"
    BEGIN_NEXT_GENESIS  = "BEGIN_NEXT_GENESIS"
    ENTER_STABILISATION = "ENTER_STABILISATION"
    ARCHITECTURE_REVIEW = "ARCHITECTURE_REVIEW"
    REFACTOR            = "REFACTOR"


# ── Core sub-models ────────────────────────────────────────────────────────────

@dataclass
class TestResults:
    passed:   int
    skipped:  int
    failed:   int
    warnings: int = 0

    @property
    def is_green(self) -> bool:
        """True when there are zero failed tests."""
        return self.failed == 0


@dataclass
class DesktopValidation:
    status:    str                    # "passed" | "failed" | "partial"
    scenarios: list[str] = field(default_factory=list)
    notes:     Optional[str] = None


@dataclass
class ArchitectureDecision:
    decision:     str
    rationale:    str
    alternatives: list[str] = field(default_factory=list)


# ── Primary review record ──────────────────────────────────────────────────────

@dataclass
class EngineeringReview:
    genesis:                str
    sprint:                 str
    status:                 GenesisStatus
    completed_at:           str                        # ISO date string
    commits:                list[str] = field(default_factory=list)
    files_added:            list[str] = field(default_factory=list)
    files_modified:         list[str] = field(default_factory=list)
    architecture_decisions: list[ArchitectureDecision] = field(default_factory=list)
    tests_added:            int = 0
    test_results:           TestResults = field(default_factory=lambda: TestResults(0, 0, 0))
    desktop_validation:     DesktopValidation = field(default_factory=lambda: DesktopValidation("unknown"))
    technical_debt:         list[str] = field(default_factory=list)
    risks:                  list[str] = field(default_factory=list)
    future_improvements:    list[str] = field(default_factory=list)
    recommendation:         Recommendation = Recommendation.CONTINUE_GENESIS
    recommendation_reason:  str = ""


# ── R&D evidence ───────────────────────────────────────────────────────────────

@dataclass
class RDEvidenceRecord:
    """
    Structured engineering evidence record.

    Note: This record documents technical work only.
    It makes no claim about tax eligibility or grant outcomes.
    That is the responsibility of qualified advisers who consume this data.
    """
    genesis:               str
    technical_problem:     str = ""
    technical_uncertainty: str = ""
    hypothesis:            str = ""
    approach:              str = ""
    experiments:           list[str] = field(default_factory=list)
    results:               str = ""
    validation:            str = ""
    remaining_unknowns:    list[str] = field(default_factory=list)


# ── Future improvement backlog item ───────────────────────────────────────────

@dataclass
class FutureImprovement:
    genesis:     str
    title:       str
    description: str
    priority:    str = "medium"    # "low" | "medium" | "high"
    category:    str = "general"


# ── Top-level report ──────────────────────────────────────────────────────────


@dataclass
class ExecutionMetadata:
    """
    Execution provenance — who produced this report and when.
    Stamped by EngineeringReviewOSWorker before persistence.
    """
    worker:          str = "EngineeringReviewOSWorker"
    worker_id:       str = "engineering_review_worker"
    worker_version:  str = "1.0"
    planner:         str = "TaskPlanner"
    coordinator:     str = "WorkerCoordinator"
    duration_ms:     float = 0.0
    generated_at:    str = ""    # ISO datetime string


@dataclass
class GenesisReport:
    review:       EngineeringReview
    rd_evidence:  RDEvidenceRecord
    improvements: list[FutureImprovement]
    rendered_at:  str                    # ISO datetime string
    metadata:     "ExecutionMetadata | None" = None
