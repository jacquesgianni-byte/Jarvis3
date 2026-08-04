"""
Decision Intelligence — Models
Genesis-036 Sprint-001

Structured data models for engineering decisions.
DecisionResult is data first — the UI renders it into English.
Workers consume DecisionResult directly (Genesis-040 readiness).

No AI. No prose generation. Only structured facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DecisionSeverity(str, Enum):
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class DecisionResult:
    """
    A structured engineering decision.

    Data-first: all fields are typed and structured.
    to_text() renders for humans. Workers consume the fields directly.

    Genesis-040 note: can_delegate signals whether this decision
    could be executed by an AI worker without human intervention.
    """
    recommendation:  str                  # e.g. "Close Genesis-036"
    confidence:      float                # 0.0 – 1.0
    reasons:         tuple[str, ...]      # why this recommendation
    blockers:        tuple[str, ...]      # what's currently blocking
    prerequisites:   tuple[str, ...]      # what must be done before acting
    severity:        DecisionSeverity
    next_action:     str                  # single concrete next step
    can_delegate:    bool = False         # Genesis-040: can a worker handle this?
    ready_to_close:  bool = False         # shortcut: is genesis closeable now?

    def to_text(self) -> str:
        """Render decision as human-readable text."""
        lines: list[str] = []

        lines.append(f"Recommendation: {self.recommendation}")
        lines.append(f"Confidence:     {self.confidence:.0%}")
        lines.append(f"Severity:       {self.severity.value.title()}")
        lines.append("")

        if self.reasons:
            lines.append("Reasons:")
            for r in self.reasons:
                lines.append(f"  • {r}")
            lines.append("")

        if self.blockers:
            lines.append("Blockers:")
            for b in self.blockers:
                lines.append(f"  ✗ {b}")
            lines.append("")

        if self.prerequisites:
            lines.append("Prerequisites:")
            for p in self.prerequisites:
                lines.append(f"  → {p}")
            lines.append("")

        lines.append(f"Next action: {self.next_action}")

        if self.ready_to_close:
            lines.append("")
            lines.append("✅ Ready to close this Genesis.")

        return "\n".join(lines)


@dataclass
class DecisionContext:
    """
    Engineering context assembled from all subsystems.
    Passed to each DecisionRule for evaluation.
    Immutable after construction — rules read it, never modify it.
    """
    genesis:                str
    lifecycle_status:       str           = ""  # "active" | "closed" | ""
    progress_state:         str           = ""  # ProgressState value or ""
    blockers:               list[str]     = field(default_factory=list)
    tests_passed:           int           = 0
    tests_failed:           int           = 0
    tests_skipped:          int           = 0
    desktop_status:         str           = ""   # "passed"|"failed"|"pending"|""
    review_recommendation:  str           = ""   # from latest review JSON
    has_active_genesis:     bool          = False
    has_evidence:           bool          = False

    @property
    def tests_green(self) -> bool:
        return self.tests_failed == 0 and self.tests_passed > 0

    @property
    def desktop_passed(self) -> bool:
        return self.desktop_status == "passed"

    @property
    def has_blockers(self) -> bool:
        return len(self.blockers) > 0

    @property
    def is_closeable(self) -> bool:
        """True if all preconditions for closing are met."""
        return (
            self.tests_green
            and self.desktop_passed
            and not self.has_blockers
            and self.has_active_genesis
        )
