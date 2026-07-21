"""
Jarvis Engineering Worker Models (Genesis-W001 Sprint-001)

Lightweight dataclasses for the EngineeringWorker output.

These models are read-only value objects. No AI calls, no side effects.
Consumers (CLI, UI, future workers) decide how to display or act on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"
    INFO   = "INFO"


class Category(str, Enum):
    ROUTING     = "ROUTING"
    MEMORY      = "MEMORY"
    PERFORMANCE = "PERFORMANCE"
    EXCEPTION   = "EXCEPTION"


@dataclass(frozen=True)
class EngineeringIssue:
    """
    A single issue detected during session analysis.

    Attributes:
        severity:       HIGH / MEDIUM / LOW / INFO
        category:       ROUTING / MEMORY / PERFORMANCE / EXCEPTION
        title:          One-line summary
        description:    What was observed
        evidence:       Raw log lines or values that triggered detection
        confidence:     0.0–1.0 — how certain the worker is
        likely_files:   Source files most likely responsible
        recommendation: Suggested next action (no code changes, just guidance)
    """
    severity:       Severity
    category:       Category
    title:          str
    description:    str
    evidence:       list[str]       = field(default_factory=list)
    confidence:     float           = 0.0
    likely_files:   list[str]       = field(default_factory=list)
    recommendation: str             = ""


@dataclass
class EngineeringReport:
    """
    The complete output of one EngineeringWorker.analyse_session() call.

    Attributes:
        health_score:   0–100 overall session health estimate
        session_turns:  Number of conversation turns analysed
        successes:      Things that worked correctly (short strings)
        issues:         Detected problems, ordered by severity
        summary:        One-paragraph human-readable summary
    """
    health_score:   int
    session_turns:  int
    successes:      list[str]            = field(default_factory=list)
    issues:         list[EngineeringIssue] = field(default_factory=list)
    summary:        str                  = ""

    def issues_by_severity(self, severity: Severity) -> list[EngineeringIssue]:
        """Return all issues at the given severity level."""
        return [i for i in self.issues if i.severity == severity]

    def has_issues(self) -> bool:
        return bool(self.issues)

    def formatted(self) -> str:
        """Human-readable report string for CLI or log output."""
        lines = [
            "=" * 60,
            "Engineering Worker Report",
            "=" * 60,
            f"Health Score : {self.health_score}/100",
            f"Turns        : {self.session_turns}",
            "",
        ]

        if self.successes:
            lines.append("Successes:")
            for s in self.successes:
                lines.append(f"  ✓ {s}")
            lines.append("")

        if self.issues:
            lines.append("Issues:")
            for issue in self.issues:
                lines.append(f"  [{issue.severity.value}] {issue.title}")
                lines.append(f"    Category   : {issue.category.value}")
                lines.append(f"    Confidence : {issue.confidence * 100:.0f}%")
                lines.append(f"    Description: {issue.description}")
                if issue.evidence:
                    lines.append(f"    Evidence   : {issue.evidence[0]}")
                if issue.likely_files:
                    lines.append(f"    Likely files: {', '.join(issue.likely_files)}")
                if issue.recommendation:
                    lines.append(f"    Recommend  : {issue.recommendation}")
                lines.append("")
        else:
            lines.append("No issues detected.")
            lines.append("")

        if self.summary:
            lines.append("Summary:")
            lines.append(f"  {self.summary}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)