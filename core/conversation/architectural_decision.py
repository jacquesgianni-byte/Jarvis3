"""
Jarvis Architectural Decision Model (Genesis-020 Sprint-004)

Defines the immutable ArchitecturalDecision dataclass and DecisionStatus enum.

Named `architectural_decision.py` to avoid collision with the existing
`core/conversation/decision.py` (ConversationDecision — behaviour layer).

Design constraints:
    - Frozen dataclass — never mutated after creation.
    - Versioned schema (version field) for replay compatibility.
    - Payload dict for supplementary machine-readable data.
    - Status transitions are expressed by creating NEW decisions
      that supersede old ones — never by mutating existing ones.
    - Fully independent of KnowledgeEngine, SessionContext, Timeline.

Decision lifecycle:
    PROPOSED     → decision is under consideration
    ACCEPTED     → decision is active and in effect
    SUPERSEDED   → replaced by a newer decision
    REJECTED     → considered and rejected with rationale
    EXPERIMENTAL → adopted on a trial basis

Replay contract:
    A DecisionProjection can reconstruct the full decision log
    by replaying Timeline events through the Projection interface.
    No independent storage required.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any


class DecisionStatus(Enum):
    """Lifecycle status of an architectural decision."""
    PROPOSED     = auto()
    ACCEPTED     = auto()
    SUPERSEDED   = auto()
    REJECTED     = auto()
    EXPERIMENTAL = auto()

    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def is_active(self) -> bool:
        """True if this decision is currently in effect."""
        return self in (DecisionStatus.ACCEPTED, DecisionStatus.EXPERIMENTAL)


@dataclass(frozen=True)
class ArchitecturalDecision:
    """
    A single immutable architectural decision.

    Attributes:
        id:              Unique identifier (UUID4 string).
        title:           Short human-readable title.
        decision:        The decision itself — what was decided.
        reason:          Why this decision was made (the rationale).
        status:          Current lifecycle status.
        source_turn:     Conversation turn when this decision was recorded.
        timestamp:       UTC datetime when this decision was recorded.
        alternatives:    Other options that were considered (may be empty).
        supersedes_id:   ID of the decision this one replaces (if any).
        confidence:      Confidence in this decision (0.0–1.0).
        tags:            Category tags for filtering.
        version:         Schema version for replay compatibility.
        payload:         Structured supplementary data.
    """
    title:          str
    decision:       str
    reason:         str
    status:         DecisionStatus = DecisionStatus.ACCEPTED
    source_turn:    int            = 0
    timestamp:      datetime       = field(default_factory=lambda: datetime.now(UTC))
    id:             str            = field(default_factory=lambda: str(uuid.uuid4()))
    alternatives:   tuple[str, ...]= field(default_factory=tuple)
    supersedes_id:  str            = ""
    confidence:     float          = 1.0
    tags:           tuple[str, ...]= field(default_factory=tuple)
    version:        int            = 1
    payload:        dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.status.label()}] {self.title}: {self.decision}"

    def date_str(self) -> str:
        """Return the decision date as YYYY-MM-DD in UTC."""
        return self.timestamp.strftime("%Y-%m-%d")

    def summary(self) -> str:
        """One-line summary for inspector display."""
        alts = f" | Alternatives: {len(self.alternatives)}" if self.alternatives else ""
        sup = " | SUPERSEDES previous" if self.supersedes_id else ""
        return (
            f"{self.title} [{self.status.label()}]"
            f" — Turn {self.source_turn}{alts}{sup}"
        )

    def explain(self) -> str:
        """
        Full explanation of this decision — the key Sprint-004 capability.

        Returns a human-readable paragraph explaining what was decided,
        why, and what alternatives were considered.
        """
        lines = [
            f"Decision: {self.title}",
            f"",
            f"What was decided: {self.decision}",
            f"",
            f"Why: {self.reason}",
        ]
        if self.alternatives:
            lines += ["", f"Alternatives considered:"]
            for alt in self.alternatives:
                lines.append(f"  - {alt}")
        if self.supersedes_id:
            lines += ["", f"This decision supersedes an earlier decision."]
        lines += [
            "",
            f"Status: {self.status.label()} | "
            f"Confidence: {self.confidence:.0%} | "
            f"Recorded: Turn {self.source_turn} ({self.date_str()})"
        ]
        return "\n".join(lines)

    def with_status(self, status: DecisionStatus) -> "ArchitecturalDecision":
        """
        Return a new decision with updated status.

        Because decisions are immutable, status changes produce new
        instances. The original decision is preserved in the Timeline.
        """
        return ArchitecturalDecision(
            id=self.id,
            title=self.title,
            decision=self.decision,
            reason=self.reason,
            status=status,
            source_turn=self.source_turn,
            timestamp=self.timestamp,
            alternatives=self.alternatives,
            supersedes_id=self.supersedes_id,
            confidence=self.confidence,
            tags=self.tags,
            version=self.version,
            payload=self.payload,
        )