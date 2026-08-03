"""
Executive Intelligence — Dashboard Models
Genesis-035 Sprint-002

Structured models for the Executive Dashboard.
Read-only aggregation layer — owns no data, stores nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecutiveSection:
    """A named section of the executive dashboard."""
    title:  str
    lines:  list[str] = field(default_factory=list)
    empty:  bool      = False

    def to_text(self) -> str:
        if self.empty or not self.lines:
            return f"── {self.title}\n   (none)"
        body = "\n".join(f"   {line}" for line in self.lines)
        return f"── {self.title}\n{body}"


@dataclass
class ExecutiveDashboard:
    """
    Complete engineering dashboard.
    Assembled entirely from existing subsystems — stores nothing.
    """
    sections:       list[ExecutiveSection] = field(default_factory=list)
    recommendation: str                    = ""
    generated_at:   str                    = ""

    def to_text(self) -> str:
        sep  = "=" * 56
        lines = [
            sep,
            "ENGINEERING BRIEFING",
            sep,
            "",
        ]

        for section in self.sections:
            lines.append(section.to_text())
            lines.append("")

        if self.recommendation:
            lines.append("── RECOMMENDATION")
            lines.append(f"   {self.recommendation}")
            lines.append("")

        if self.generated_at:
            lines.append(f"   Generated: {self.generated_at[:19].replace('T', ' ')} UTC")

        return "\n".join(lines)
