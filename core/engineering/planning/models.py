"""
Engineering Planner Models (Genesis-016 Sprint 004)

Pure data carriers for engineering plans.
Immutable once created — a plan is a point-in-time record
of what would be required. Nothing is ever executed.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Complexity(Enum):
    """Estimated complexity of an engineering task."""
    LOW    = "Low"
    MEDIUM = "Medium"
    HIGH   = "High"


@dataclass(frozen=True)
class EngineeringPlan:
    """
    A complete engineering plan for a proposed task.

    Immutable once created. Produced by EngineeringPlanner;
    evaluated by EngineeringGuardrails; approved by the Chief.

    This object answers: "What would be required to complete
    this engineering task?" — without modifying a single file.
    """

    # Core identity
    objective: str                      # what the task aims to achieve
    request: str                        # original request text

    # File analysis
    candidate_files: tuple              # files likely to change
    layers_involved: tuple              # architectural layers touched
    dependencies: tuple                 # related files/modules to be aware of

    # Estimates
    complexity: Complexity
    estimated_file_count: int

    # Guidance
    validation_steps: tuple             # abstract validation recommendations
                                        # Testing Engine maps these to commands in Sprint 005
    risks: tuple                        # potential issues to watch for

    # Summary
    summary: str                        # human-readable narrative

    def report(self) -> str:
        """Human-readable engineering plan for Chief review."""
        lines = [
            "Engineering Plan",
            "=" * 50,
            "",
            f"Objective:      {self.objective}",
            f"Complexity:     {self.complexity.value}",
            f"Files affected: {self.estimated_file_count}",
            "",
            "Candidate files:",
        ]
        for f in self.candidate_files:
            lines.append(f"    {f}")
        if not self.candidate_files:
            lines.append("    none identified")

        lines += ["", "Architectural layers:"]
        for layer in self.layers_involved:
            lines.append(f"    {layer}")
        if not self.layers_involved:
            lines.append("    none identified")

        lines += ["", "Dependencies to be aware of:"]
        for dep in self.dependencies:
            lines.append(f"    {dep}")
        if not self.dependencies:
            lines.append("    none identified")

        lines += ["", "Recommended validation steps:"]
        for step in self.validation_steps:
            lines.append(f"    - {step}")

        if self.risks:
            lines += ["", "Risks:"]
            for risk in self.risks:
                lines.append(f"    ⚠  {risk}")

        lines += [
            "",
            "Summary:",
            f"    {self.summary}",
            "",
            "Status: Awaiting Chief approval.",
        ]
        return "\n".join(lines)