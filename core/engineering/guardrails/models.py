"""
Engineering Guardrails Models (Genesis-016 Sprint 003)

Pure data carriers for engineering plan validation.
No behaviour, no file modification, no Git operations.
"""

from dataclasses import dataclass, field
from enum import Enum


class ApprovalStatus(Enum):
    """The outcome of a guardrail evaluation."""

    APPROVED = "approved"               # within limits, no protected files
    REQUIRES_APPROVAL = "requires_approval"  # Chief must explicitly sign off
    REJECTED = "rejected"               # exceeds hard limits


@dataclass(frozen=True)
class EngineeringPlan:
    """
    A proposed engineering task, evaluated against guardrail rules.

    Immutable once created — the plan is a point-in-time record of
    what was proposed and what the guardrails decided. Nothing is
    executed or written.
    """

    task: str                           # human-readable task description
    files_to_modify: tuple              # files the task intends to change
    protected_files_encountered: tuple  # subset that match protected paths
    total_files: int                    # len(files_to_modify)
    max_files_allowed: int              # the configured limit
    status: ApprovalStatus
    reason: str                         # plain-English explanation of status

    @property
    def safe(self) -> bool:
        """True only when status is APPROVED."""
        return self.status == ApprovalStatus.APPROVED

    def report(self) -> str:
        """
        Human-readable engineering plan — suitable for the coordinator
        to present to the Chief before any action is taken.
        """
        lines = ["Engineering Plan", ""]

        lines.append("Files to modify:")
        if self.files_to_modify:
            for f in self.files_to_modify:
                lines.append(f"    {f}")
        else:
            lines.append("    none")

        lines.append("")
        lines.append("Protected files:")
        if self.protected_files_encountered:
            for f in self.protected_files_encountered:
                lines.append(f"    {f}  ← PROTECTED")
        else:
            lines.append("    none")

        lines += [
            "",
            f"Estimated changes:  {self.total_files}",
            f"Limit:              {self.max_files_allowed}",
            "",
            f"Status:             {self.status.value.replace('_', ' ').title()}",
            f"Reason:             {self.reason}",
        ]

        if self.status == ApprovalStatus.REQUIRES_APPROVAL:
            lines += ["", "    Waiting for Chief approval."]
        elif self.status == ApprovalStatus.REJECTED:
            lines += ["", "    Task rejected. Revise scope before proceeding."]

        return "\n".join(lines)