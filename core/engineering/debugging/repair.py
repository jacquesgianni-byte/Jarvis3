"""
Repair Planning Models (Genesis-017 Sprint 006)

Immutable data carriers for engineering repair plans.

Design philosophy:
    "What repair plan should an engineer follow?"

    A RepairPlan is an engineering workflow, not code.
    It describes what steps to take, in what order, and why —
    without ever executing, modifying, or generating anything.

    Every step must be:
        * deterministic,
        * explainable,
        * supported by prior investigation evidence.

    Execution belongs to a future Genesis after explicit approval
    mechanisms and worker orchestration are mature.
"""

from dataclasses import dataclass
from enum import Enum


class RepairRisk(Enum):
    """
    Estimated risk level of executing a repair plan.
    Derived deterministically from root cause and correlation evidence.
    """
    LOW      = "Low"
    MEDIUM   = "Medium"
    HIGH     = "High"
    CRITICAL = "Critical"


class RepairEffort(Enum):
    """
    Estimated engineering effort to execute a repair plan.
    Derived deterministically from the number and type of steps.
    """
    MINOR    = "Minor"      # < 15 minutes
    SMALL    = "Small"      # 15–60 minutes
    MODERATE = "Moderate"   # 1–4 hours
    LARGE    = "Large"      # 4–8 hours
    MAJOR    = "Major"      # > 1 day


@dataclass(frozen=True)
class RepairStep:
    """
    One immutable step in a repair plan.

    Describes what to do and why — never executes it.

    Fields
    ------
    order       : Position in the plan (1-based).
    title       : Short action title (verb phrase).
    description : What to do and why, referencing evidence.
    depends_on  : Tuple of step order numbers this step depends on.
    """
    order:       int
    title:       str
    description: str
    depends_on:  tuple          # tuple of int step order numbers


@dataclass(frozen=True)
class RepairPlan:
    """
    Immutable engineering repair plan.

    Produced by RepairPlanner. Never modified after creation.
    Describes what an engineer should do to address a failure —
    without executing, modifying, or generating anything.

    Fields
    ------
    title                    : Human-readable plan title.
    summary                  : One-paragraph description of the plan.
    confidence               : 0.0 → 1.0 confidence in the plan.
    steps                    : Ordered tuple of RepairStep objects.
    validation_steps         : Tuple of validation actions after repair.
    estimated_risk           : RepairRisk — risk of executing this plan.
    estimated_effort         : RepairEffort — effort to execute this plan.
    supporting_recommendations: Tuple of recommendation titles that
                                informed this plan.
    """

    title:                     str
    summary:                   str
    confidence:                float
    steps:                     tuple       # tuple of RepairStep
    validation_steps:          tuple       # tuple of str
    estimated_risk:            RepairRisk
    estimated_effort:          RepairEffort
    supporting_recommendations: tuple      # tuple of str (rec titles)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def has_plan(self) -> bool:
        """True when the plan contains actionable steps."""
        return len(self.steps) > 0

    def report(self) -> str:
        """Human-readable repair plan for Chief review."""
        lines = [
            "Repair Plan",
            "=" * 50,
            "",
            f"Title:            {self.title}",
            f"Confidence:       {self.confidence:.0%}",
            f"Estimated risk:   {self.estimated_risk.value}",
            f"Estimated effort: {self.estimated_effort.value}",
            "",
            "Summary:",
            f"    {self.summary}",
            "",
            "Steps:",
        ]

        if self.steps:
            for step in self.steps:
                deps = (f" (after step {', '.join(str(d) for d in step.depends_on)})"
                        if step.depends_on else "")
                lines.append(f"    {step.order}. {step.title}{deps}")
                lines.append(f"       {step.description}")
        else:
            lines.append("    No repair steps identified.")

        if self.validation_steps:
            lines += ["", "Validation after repair:"]
            for v in self.validation_steps:
                lines.append(f"    ✓ {v}")

        if self.supporting_recommendations:
            lines += ["", "Based on recommendations:"]
            for r in self.supporting_recommendations:
                lines.append(f"    • {r}")

        lines += [
            "",
            "⚠  This plan requires Chief approval before execution.",
            "   No files have been modified. No code has been generated.",
        ]
        return "\n".join(lines)