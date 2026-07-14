"""
Engineering Debugging Models (Genesis-017 Sprints 001–005)

Pure data carriers for engineering failure analysis.
Immutable once created — a debug report is a forensic record
of what happened. It never speculates about fixes.

Design philosophy:
    "What happened?" — not — "How should I fix it?"
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.engineering.debugging.root_cause import RootCause
    from core.engineering.debugging.correlation import CorrelationRecord
    from core.engineering.debugging.recommendation import Recommendation


class FailureType(Enum):
    """
    Classification of an engineering failure.

    Values are deliberately narrow — the debugger must never
    force a classification when evidence is insufficient.
    UNKNOWN is the honest answer when evidence is unclear.
    """
    COMPILE       = "Compile Error"
    IMPORT        = "Import Error"
    TEST          = "Test Failure"
    TIMEOUT       = "Timeout"
    CONFIGURATION = "Configuration Error"
    UNKNOWN       = "Unknown"


@dataclass(frozen=True)
class FailureEvidence:
    """
    Immutable container for structured forensic evidence.

    Sprint 001: raw command output (stdout, stderr, exit_code, timestamp).
    Sprint 002: structured extraction (stack_trace, failing_files,
                line_numbers, error_type, diagnostics).

    Kept separate from DebugReport so future sprints can enrich the
    evidence layer without changing the report contract.
    """
    # Sprint 001 — raw capture
    command:       str
    exit_code:     int
    stdout:        tuple   # lines of captured stdout
    stderr:        tuple   # lines of captured stderr
    timestamp:     str     # ISO-8601 UTC

    # Sprint 002 — structured extraction
    stack_trace:   tuple   # parsed stack frames (file, line, context)
    failing_files: tuple   # file paths mentioned in the output
    line_numbers:  tuple   # line numbers extracted from tracebacks
    error_type:    str     # exception class name (e.g. SyntaxError)
    diagnostics:   tuple   # compiler/linter diagnostic lines


@dataclass(frozen=True)
class DebugReport:
    """
    Immutable forensic record of an engineering failure.

    Produced by EngineeringDebugger.analyse(). Never modified
    after creation. Contains only observed evidence — no
    speculation, no fix suggestions.

    Fields
    ------
    failure_type    : Classified failure category.
    summary         : One-line human-readable description of the failure.
    confidence      : 0.0 (no evidence) → 1.0 (definitive classification).
    evidence        : Tuple of relevant lines extracted from output.
    command         : The command that was executed.
    exit_code       : Process exit code (0 = success, non-zero = failure).
    stdout          : Captured stdout (truncated to _MAX_OUTPUT chars).
    stderr          : Captured stderr (truncated to _MAX_OUTPUT chars).
    timestamp       : ISO-8601 UTC timestamp of when analysis was performed.
    """

    failure_type:  FailureType
    summary:       str
    confidence:    float           # 0.0 – 1.0
    clues:         tuple           # relevant lines extracted from output, max 20
    evidence:      FailureEvidence # raw forensic evidence
    root_cause:    RootCause       # Sprint 003 — deterministic root cause
    correlation:   CorrelationRecord  # Sprint 004 — failure correlation
    recommendations: tuple            # Sprint 005 — advisory recommendations

    def report(self) -> str:
        """Human-readable forensic report for Chief review."""
        lines = [
            "Engineering Debug Report",
            "=" * 50,
            "",
            f"Failure type:  {self.failure_type.value}",
            f"Confidence:    {self.confidence:.0%}",
            f"Command:       {self.evidence.command}",
            f"Exit code:     {self.evidence.exit_code}",
            f"Timestamp:     {self.evidence.timestamp}",
            "",
            "Root Cause:",
            f"    {self.root_cause.summary_line()}",
            "",
            f"Summary:",
            f"    {self.summary}",
            "",
            "Clues:",
        ]
        if self.clues:
            for line in self.clues:
                lines.append(f"    {line}")
        else:
            lines.append("    (no specific clues extracted)")

        if self.evidence.stack_trace:
            lines += ["", "Stack trace:"]
            for frame in self.evidence.stack_trace:
                lines.append(f"    {frame}")

        if self.evidence.failing_files:
            lines += ["", "Failing files:"]
            for f in self.evidence.failing_files:
                lines.append(f"    {f}")

        if self.evidence.diagnostics:
            lines += ["", "Diagnostics:"]
            for d in self.evidence.diagnostics:
                lines.append(f"    {d}")

        if self.root_cause.contributing_factors:
            lines += ["", "Contributing factors:"]
            for factor in self.root_cause.contributing_factors:
                lines.append(f"    • {factor}")

        if self.correlation.is_correlated:
            lines += ["", "Correlation:"]
            lines.append(f"    {self.correlation.summary_line()}")
            if self.correlation.related_files:
                lines.append(f"    Related files: {self.correlation.related_files}")
            if self.correlation.timeline:
                lines += ["", "    Timeline:"]
                for entry in self.correlation.timeline:
                    lines.append(f"        {entry}")

        if self.evidence.stderr:
            lines += ["", "Stderr (tail):"]
            for line in self.evidence.stderr[-5:]:
                lines.append(f"    {line}")

        if self.recommendations:
            lines += ["", "Recommendations:"]
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"    {i}. {rec.summary_line()}")

        lines += [
            "",
            "Note: This report describes what happened.",
            "      Recommendations are advisory only — no repairs proposed.",
        ]
        return "\n".join(lines)