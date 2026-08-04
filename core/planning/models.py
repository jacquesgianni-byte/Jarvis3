"""
Planning Intelligence — Models
Genesis-037 Sprint-001

Immutable, structured planning data.
WorkPackage is designed to be consumed by Worker OS workers
and future external AI workers (Genesis-040) without modification.

No prose. No AI. Pure engineering data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


@dataclass(frozen=True)
class WorkPackage:
    """
    An immutable, self-contained unit of engineering work.

    Designed to be consumed by:
      - Internal Worker OS workers (today)
      - External AI workers (Genesis-040)

    capability_required maps directly to a Worker OS capability string
    (e.g. "run_tests", "plan_implementation", "run_engineering_review").

    can_delegate: True means an external AI worker could execute this
    autonomously after human approval.
    """
    id:                  str
    objective:           str              # what must be achieved
    capability_required: str              # Worker OS capability string
    priority:            int              # 1 = highest
    estimated_scope:     str              # "small" | "medium" | "large"
    affected_subsystems: tuple[str, ...]  # e.g. ("core/progress", "core/decision")
    affected_files:      tuple[str, ...]  # specific files if known
    constraints:         tuple[str, ...]  # must not do X
    dependencies:        tuple[str, ...]  # must complete Y first
    acceptance_tests:    tuple[str, ...]  # how to verify completion
    definition_of_done:  tuple[str, ...]  # completion checklist
    review_requirements: tuple[str, ...]  # what review is needed
    can_delegate:        bool             # Genesis-040: external AI eligible?
    created_at:          str              # ISO datetime
    source_decision:     str              # which DecisionResult drove this
    genesis:             str = ""         # which Genesis this belongs to

    def to_text(self) -> str:
        """Render work package as human-readable text."""
        lines: list[str] = [
            f"Work Package: {self.id[:8]}",
            f"Objective:    {self.objective}",
            f"Capability:   {self.capability_required}",
            f"Priority:     {self.priority}",
            f"Scope:        {self.estimated_scope}",
            f"Delegate:     {'Yes' if self.can_delegate else 'No'}",
            "",
        ]

        if self.affected_subsystems:
            lines.append("Affected Subsystems:")
            for s in self.affected_subsystems:
                lines.append(f"  • {s}")
            lines.append("")

        if self.dependencies:
            lines.append("Dependencies:")
            for d in self.dependencies:
                lines.append(f"  → {d}")
            lines.append("")

        if self.constraints:
            lines.append("Constraints:")
            for c in self.constraints:
                lines.append(f"  ✗ {c}")
            lines.append("")

        if self.acceptance_tests:
            lines.append("Acceptance Tests:")
            for t in self.acceptance_tests:
                lines.append(f"  ✓ {t}")
            lines.append("")

        if self.definition_of_done:
            lines.append("Definition of Done:")
            for d in self.definition_of_done:
                lines.append(f"  □ {d}")
            lines.append("")

        if self.review_requirements:
            lines.append("Review Requirements:")
            for r in self.review_requirements:
                lines.append(f"  · {r}")

        return "\n".join(lines)


@dataclass(frozen=True)
class PlanningResult:
    """
    The output of a PlanningEngine run.
    Contains one or more WorkPackages in priority order.
    """
    packages:   tuple[WorkPackage, ...]
    total:      int
    genesis:    str
    planned_at: str

    def to_text(self) -> str:
        """Render the full planning result for humans."""
        sep   = "=" * 56
        lines = [
            sep,
            "ENGINEERING WORK PLAN",
            sep,
            f"Genesis:   {self.genesis}",
            f"Packages:  {self.total}",
            f"Planned:   {self.planned_at[:19].replace('T', ' ')} UTC",
            "",
        ]

        for i, pkg in enumerate(self.packages, 1):
            lines.append(f"─── Package {i} of {self.total} ───")
            lines.append(pkg.to_text())
            if i < self.total:
                lines.append("")

        return "\n".join(lines)


def make_work_package(
    objective:           str,
    capability_required: str,
    priority:            int            = 5,
    estimated_scope:     str            = "medium",
    affected_subsystems: tuple[str, ...] = (),
    affected_files:      tuple[str, ...] = (),
    constraints:         tuple[str, ...] = (),
    dependencies:        tuple[str, ...] = (),
    acceptance_tests:    tuple[str, ...] = (),
    definition_of_done:  tuple[str, ...] = (),
    review_requirements: tuple[str, ...] = (),
    can_delegate:        bool            = False,
    source_decision:     str             = "",
    genesis:             str             = "",
) -> WorkPackage:
    """Factory function for creating WorkPackage instances."""
    return WorkPackage(
        id=str(uuid4()),
        objective=objective,
        capability_required=capability_required,
        priority=priority,
        estimated_scope=estimated_scope,
        affected_subsystems=affected_subsystems,
        affected_files=affected_files,
        constraints=constraints,
        dependencies=dependencies,
        acceptance_tests=acceptance_tests,
        definition_of_done=definition_of_done,
        review_requirements=review_requirements,
        can_delegate=can_delegate,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_decision=source_decision,
        genesis=genesis,
    )
