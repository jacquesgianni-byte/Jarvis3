"""
Engineering Intelligence Models — Genesis-045 Sprint-001

Structured proposal model with explicit epistemological layers:
  Evidence   → raw observations from SessionAnalysisWorker (never inferred)
  Diagnosis  → inferences drawn from evidence (explicitly labelled)
  Recommendation → proposed change with expected benefit and validation plan

These layers are separate types so an inference cannot accidentally
appear in the evidence layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Optional


class ProposalStatus(Enum):
    """Lifecycle state of an ImprovementProposal."""
    PENDING  = auto()   # awaiting human decision
    STALE    = auto()   # issue has not recurred; human should close or dismiss
    APPROVED = auto()   # human approved; handed to CollaborationRunner
    REJECTED = auto()   # human rejected; suppressed for N cycles
    DEFERRED = auto()   # human deferred; remains pending
    EXPIRED  = auto()   # STALE for too long; auto-closed

    def label(self) -> str:
        return self.name.title()


@dataclass(frozen=True)
class Observation:
    """
    A single raw observation from SessionAnalysisWorker.

    Contains ONLY facts derived directly from log lines.
    No inference, no judgment. Source is always SessionAnalysisWorker.

    Attributes:
        category:     Issue category (ROUTING / MEMORY / PERFORMANCE / EXCEPTION)
        title:        One-line summary of what was observed
        detail:       What specifically was seen
        evidence:     Raw log evidence lines
        turn_count:   How many session turns exhibited this
        confidence:   SessionAnalysisWorker confidence in this observation
    """
    category:   str
    title:      str
    detail:     str
    evidence:   tuple[str, ...]  = field(default_factory=tuple)
    turn_count: int              = 0
    confidence: float            = 0.0

    @classmethod
    def from_issue(cls, issue) -> "Observation":
        """Build an Observation from an EngineeringIssue."""
        return cls(
            category   = issue.category.value if hasattr(issue.category, "value") else str(issue.category),
            title      = issue.title,
            detail     = issue.description,
            evidence   = tuple(issue.evidence or []),
            turn_count = 0,
            confidence = issue.confidence,
        )


@dataclass(frozen=True)
class Diagnosis:
    """
    An inference drawn from one or more Observations.

    Explicitly labelled as inference — not fact.
    Always carries an uncertainty statement.

    Attributes:
        inference:   What the evidence suggests (explicitly an inference)
        confidence:  How confident this inference is (0.0-1.0)
        uncertainty: What could make this inference wrong
        likely_components: Which components are likely involved
        cfr_reference: Related open CFR entry if one exists (read-only)
    """
    inference:          str
    confidence:         float
    uncertainty:        str
    likely_components:  tuple[str, ...] = field(default_factory=tuple)
    cfr_reference:      str             = ""  # e.g. "CFR-001" — read-only link


@dataclass(frozen=True)
class Recommendation:
    """
    A proposed change with expected benefit and validation plan.

    Explicitly labelled as a suggestion, not a decision.
    Human approval is always required before any action.

    Attributes:
        proposed_change:     What should change
        expected_benefit:    Why it would help
        affected_components: Which files/components would change
        validation_plan:     How to know if it worked
    """
    proposed_change:      str
    expected_benefit:     str
    affected_components:  tuple[str, ...] = field(default_factory=tuple)
    validation_plan:      str             = ""


@dataclass
class ImprovementProposal:
    """
    A single structured improvement proposal.

    Three explicit epistemological layers:
      evidence       → list[Observation]  (facts, never inferences)
      diagnosis      → Diagnosis          (inferences, explicitly labelled)
      recommendation → Recommendation    (proposed change, needs approval)

    One active proposal at a time. Human must decide before next is formed.

    Attributes:
        proposal_id:     Unique identifier (session_id + issue category)
        status:          ProposalStatus lifecycle state
        evidence:        Raw observations — source only, never inferred
        diagnosis:       What the evidence suggests (inference layer)
        recommendation:  What to do about it (proposal layer)
        confidence:      Overall proposal confidence
        session_id:      Which analysis cycle produced this
        created_at:      When this proposal was formed
        decided_at:      When the human made a decision (None if pending)
        rejection_reason: Human's reason for rejection (if rejected)
        stale_cycles:    How many cycles have passed without the issue recurring
    """
    proposal_id:      str
    status:           ProposalStatus
    evidence:         list[Observation]
    diagnosis:        Diagnosis
    recommendation:   Recommendation
    confidence:       float
    session_id:       str             = ""
    created_at:       datetime        = field(default_factory=lambda: datetime.now(UTC))
    decided_at:       Optional[datetime] = None
    rejection_reason: str             = ""
    stale_cycles:     int             = 0

    def is_pending(self) -> bool:
        return self.status == ProposalStatus.PENDING

    def is_stale(self) -> bool:
        return self.status == ProposalStatus.STALE

    def formatted_for_user(self) -> str:
        """Human-readable proposal for display via /engineering or chat."""
        lines = [
            "=" * 60,
            "Engineering Improvement Proposal",
            f"Status: {self.status.label()}",
            f"Confidence: {self.confidence * 100:.0f}%",
            "",
            "WHAT I OBSERVED",
            "-" * 40,
        ]
        for obs in self.evidence:
            lines.append(f"  [{obs.category}] {obs.title}")
            lines.append(f"  {obs.detail}")
            if obs.evidence:
                lines.append(f"  Evidence: {obs.evidence[0]}")
            lines.append("")

        lines += [
            "WHAT I THINK IT MEANS  (inference — not fact)",
            "-" * 40,
            f"  {self.diagnosis.inference}",
            f"  Confidence: {self.diagnosis.confidence * 100:.0f}%",
            f"  Uncertainty: {self.diagnosis.uncertainty}",
        ]
        if self.diagnosis.cfr_reference:
            lines.append(f"  Related: {self.diagnosis.cfr_reference}")
        if self.diagnosis.likely_components:
            lines.append(f"  Components: {', '.join(self.diagnosis.likely_components)}")
        lines.append("")

        lines += [
            "WHAT I SUGGEST",
            "-" * 40,
            f"  {self.recommendation.proposed_change}",
            "",
            "WHY",
            f"  {self.recommendation.expected_benefit}",
        ]
        if self.recommendation.affected_components:
            lines.append(f"  Affected: {', '.join(self.recommendation.affected_components)}")
        if self.recommendation.validation_plan:
            lines.append(f"  Validation: {self.recommendation.validation_plan}")
        lines += [
            "",
            "=" * 60,
            "Type /engineering approve | reject [reason] | defer",
            "=" * 60,
        ]
        return "\n".join(lines)
