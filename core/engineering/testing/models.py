"""
Engineering Testing Models (Genesis-016 Sprint 005)

Pure data carriers for engineering test results.
Immutable once created — a result is a point-in-time record
of what was validated and what was found.
"""

from dataclasses import dataclass, field
from enum import Enum


class ValidationStatus(Enum):
    """Overall status of a validation run."""
    PASSED  = "Passed"
    FAILED  = "Failed"
    PARTIAL = "Partial"   # some checks passed, some failed
    SKIPPED = "Skipped"   # no validations were applicable


@dataclass(frozen=True)
class StepResult:
    """Result of one individual validation step."""

    name: str           # human-readable step name
    command: str        # command that was executed (or attempted)
    passed: bool
    duration_ms: float
    output: str         # captured stdout/stderr (truncated if long)
    error: str = ""     # non-empty if the step raised an exception


@dataclass(frozen=True)
class EngineeringTestResult:
    """
    Immutable record of a complete validation run against an
    EngineeringPlan.

    Answers: "Has this engineering work been successfully validated?"
    using real evidence — not assumptions.
    """

    plan_objective: str             # from the EngineeringPlan
    steps: tuple                    # tuple of StepResult
    status: ValidationStatus
    total_duration_ms: float
    started_at: str          # ISO-8601 UTC timestamp
    finished_at: str         # ISO-8601 UTC timestamp

    @property
    def steps_passed(self) -> int:
        return sum(1 for s in self.steps if s.passed)

    @property
    def steps_failed(self) -> int:
        return sum(1 for s in self.steps if not s.passed)

    @property
    def steps_total(self) -> int:
        return len(self.steps)

    @property
    def success(self) -> bool:
        return self.status == ValidationStatus.PASSED

    def report(self) -> str:
        """Human-readable validation report for Chief review."""
        lines = [
            "Engineering Validation Report",
            "=" * 50,
            "",
            f"Objective:  {self.plan_objective}",
            f"Status:     {self.status.value}",
            f"Duration:   {self.total_duration_ms:.0f} ms",
            f"Started:    {self.started_at}",
            f"Finished:   {self.finished_at}",
            f"Steps:      {self.steps_passed}/{self.steps_total} passed",
            "",
            "Validation steps:",
        ]
        for step in self.steps:
            icon = "✓" if step.passed else "✗"
            lines.append(
                f"  {icon}  {step.name} ({step.duration_ms:.0f} ms)"
            )
            if not step.passed and step.error:
                lines.append(f"       Error: {step.error[:120]}")
            if not step.passed and step.output:
                # Show last 3 lines of output for failed steps
                tail = "\n".join(step.output.splitlines()[-3:])
                lines.append(f"       Output: {tail[:200]}")

        if self.status == ValidationStatus.PASSED:
            lines += ["", "All validation steps passed. Ready for Chief review."]
        elif self.status == ValidationStatus.FAILED:
            lines += ["", f"{self.steps_failed} step(s) failed. "
                         "Review output above before proceeding."]
        elif self.status == ValidationStatus.PARTIAL:
            lines += ["", f"{self.steps_passed} passed, {self.steps_failed} failed. "
                         "Chief should review failures before proceeding."]
        else:
            lines += ["", "No validation steps were executed."]

        return "\n".join(lines)