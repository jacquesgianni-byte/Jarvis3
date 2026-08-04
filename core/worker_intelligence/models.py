"""
Knowledge Graph & Worker Intelligence — Models
Genesis-039 Sprint-001

Immutable data models representing observed worker intelligence.
Only observed facts — no inference, no AI, no estimates.

CapabilityRecord: per-capability execution statistics
WorkerProfile: complete intelligence profile for one worker

These models are the infrastructure Genesis-040 routes on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class CapabilityRecord:
    """
    Observed execution statistics for a single capability on a single worker.
    confidence = successes / executions (0.0 if no executions recorded).
    """
    capability:  str
    executions:  int   = 0
    successes:   int   = 0
    failures:    int   = 0

    @property
    def confidence(self) -> float:
        if self.executions == 0:
            return 0.0
        return round(self.successes / self.executions, 4)

    @property
    def has_data(self) -> bool:
        return self.executions > 0

    def with_execution(self, success: bool) -> "CapabilityRecord":
        """Return a new record with one more execution recorded."""
        return CapabilityRecord(
            capability=self.capability,
            executions=self.executions + 1,
            successes=self.successes + (1 if success else 0),
            failures=self.failures + (0 if success else 1),
        )


@dataclass(frozen=True)
class WorkerProfile:
    """
    Complete intelligence profile for a single worker.
    Built entirely from observed WorkerResult facts.

    Genesis-040: routing decisions consume this directly.
    No worker needs to know it exists.
    """
    worker_id:          str
    worker_name:        str
    description:        str                        = ""
    capabilities:       tuple[CapabilityRecord, ...] = field(default_factory=tuple)
    total_executions:   int                        = 0
    total_successes:    int                        = 0
    total_failures:     int                        = 0
    last_seen:          str                        = ""   # ISO datetime

    @property
    def overall_confidence(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return round(self.total_successes / self.total_executions, 4)

    def confidence_for(self, capability: str) -> float:
        """Return confidence score for a specific capability."""
        for cap in self.capabilities:
            if cap.capability == capability:
                return cap.confidence
        return 0.0

    def best_capability(self) -> str:
        """Return the capability with the highest confidence score."""
        if not self.capabilities:
            return ""
        best = max(self.capabilities, key=lambda c: c.confidence)
        return best.capability

    def capability_record(self, capability: str) -> Optional[CapabilityRecord]:
        """Return the CapabilityRecord for a capability, or None."""
        for cap in self.capabilities:
            if cap.capability == capability:
                return cap
        return None

    def has_capability(self, capability: str) -> bool:
        return any(c.capability == capability for c in self.capabilities)

    def to_text(self) -> str:
        """Render profile as human-readable text."""
        lines = [
            f"Worker:      {self.worker_name}",
            f"Confidence:  {self.overall_confidence:.0%}",
            f"Executions:  {self.total_executions} "
            f"({self.total_successes} ✓, {self.total_failures} ✗)",
        ]
        if self.last_seen:
            lines.append(f"Last seen:   {self.last_seen[:19].replace('T', ' ')} UTC")
        if self.description:
            lines.append(f"Description: {self.description}")
        lines.append("")
        lines.append("Capabilities:")
        for cap in sorted(self.capabilities, key=lambda c: c.confidence, reverse=True):
            bar = "█" * int(cap.confidence * 10) + "░" * (10 - int(cap.confidence * 10))
            lines.append(
                f"  {cap.capability:<35} [{bar}] "
                f"{cap.confidence:.0%} ({cap.executions} runs)"
            )
        return "\n".join(lines)
