"""
Engineering Intelligence Models — Genesis-045 Sprint-001 / Sprint-004

Structured proposal model with explicit epistemological layers:

  Evidence      — raw observations from SessionAnalysisWorker (never inferred)
  Diagnosis     — inferences drawn from evidence (explicitly labelled)
  Recommendation — proposed change with expected benefit and validation plan

These layers are separate types so an inference cannot accidentally
appear in the evidence layer.

Sprint-004 additions to ProposalStatus:
  IMPLEMENTED     — engineering action physically applied (COMMIT_PENDING reached)
  VALIDATED       — expected improvement observed in subsequent cycles
                    (outcome observation, NOT proof of causation)
  FAILED_VALIDATION — expected improvement not observed within window
                    (cause uncertain; evidence intact; pattern still eligible)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Optional


class ProposalStatus(Enum):
    """Lifecycle state of an ImprovementProposal."""
    PENDING           = auto()   # awaiting human decision
    STALE             = auto()   # issue has not recurred; human should close or dismiss
    APPROVED          = auto()   # human approved; handed to CollaborationRunner
    REJECTED          = auto()   # human rejected; suppressed for N cycles
    DEFERRED          = auto()   # human deferred; remains pending
    EXPIRED           = auto()   # STALE for too long; auto-closed
    # Sprint-004: post-approval outcome states
    IMPLEMENTED       = auto()   # execution pipeline reached COMMIT_PENDING
    VALIDATED         = auto()   # expected improvement observed (not proven causal)
    FAILED_VALIDATION = auto()   # expected improvement not observed within window

    def label(self) -> str:
        return self.name.title()


@dataclass(frozen=True)
class Observation:
    """
    A single raw observation from SessionAnalysisWorker.

    Contains ONLY facts derived directly from log lines.
    No inference, no judgment. Source is always SessionAnalysisWorker.
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
    """
    inference:          str
    confidence:         float
    uncertainty:        str
    likely_components:  tuple[str, ...] = field(default_factory=tuple)
    cfr_reference:      str             = ""


@dataclass(frozen=True)
class Recommendation:
    """
    A proposed change with expected benefit and validation plan.

    Explicitly labelled as a suggestion, not a decision.
    Human approval is always required before any action.
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
      evidence       — list[Observation]  (facts, never inferences)
      diagnosis      — Diagnosis          (inferences, explicitly labelled)
      recommendation — Recommendation    (proposed change, needs approval)

    One active proposal at a time. Human must decide before next is formed.
    """
    proposal_id:       str
    status:            ProposalStatus
    evidence:          list[Observation]
    diagnosis:         Diagnosis
    recommendation:    Recommendation
    confidence:        float
    session_id:        str              = ""
    pattern_signature: str             = ""
    created_at:        datetime        = field(default_factory=lambda: datetime.now(UTC))
    decided_at:        Optional[datetime] = None
    rejection_reason:  str             = ""
    stale_cycles:      int             = 0

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

        # Sprint-004: show outcome status if past approval
        if self.status in (
            ProposalStatus.IMPLEMENTED,
            ProposalStatus.VALIDATED,
            ProposalStatus.FAILED_VALIDATION,
        ):
            lines += [
                "",
                "OUTCOME",
                "-" * 40,
            ]
            if self.status == ProposalStatus.IMPLEMENTED:
                lines.append("  Engineering action applied. Observing subsequent cycles.")
            elif self.status == ProposalStatus.VALIDATED:
                lines.append(
                    "  Expected improvement observed in subsequent cycles. "
                    "Note: observation does not establish causation."
                )
            elif self.status == ProposalStatus.FAILED_VALIDATION:
                lines.append(
                    "  Expected improvement was not observed within the observation window. "
                    "Cause is uncertain. Pattern remains eligible for future proposals."
                )

        lines += [
            "",
            "=" * 60,
            "Type /engineering approve | reject [reason] | defer",
            "=" * 60,
        ]
        return "\n".join(lines)
