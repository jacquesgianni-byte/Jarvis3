"""
Pattern Record — Genesis-045 Sprint-002 / Sprint-003 / Sprint-004

PatternRecord: recurring observation across multiple analysis cycles.
RejectionRecord: structured human decision on a proposal.
RejectionReasonCode: 7 structured reason codes.
OutcomeStatus: lifecycle state after a proposal is approved (Sprint-004).
ProposalOutcomeRecord: minimal outcome model linking proposal to execution
                       result and subsequent validation observation (Sprint-004).

Sprint-003 additions to RejectionRecord:
  components_at_rejection  — snapshot of affected_components at rejection
  suppression_cycles       — computed window from RejectionReasonCode
  recorded_genesis         — Genesis tag for future version-awareness

Sprint-004 additions:
  OutcomeStatus enum: IMPLEMENTED / VALIDATED / FAILED_VALIDATION
  ProposalOutcomeRecord dataclass

Key design invariants:
  - PatternRecord evidence is IMMUTABLE — never modified by any outcome.
  - IMPLEMENTED ≠ diagnosis correct ≠ recommendation optimal ≠ problem solved.
  - VALIDATED = expected improvement observed; causation is NOT established.
  - FAILED_VALIDATION = expected improvement not observed within window;
    cause is uncertain; original evidence intact; pattern remains eligible.
  - No outcome triggers autonomous engineering action.
  - Every new engineering action requires human approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Optional


class RejectionReasonCode(Enum):
    """
    Structured reason for rejecting an ImprovementProposal.

    Sprint-003 introduced differentiated suppression windows per code.
    See SUPPRESSION_BY_REASON in selector.py for the definitive table.
    """
    NOT_A_PROBLEM        = "NOT_A_PROBLEM"
    WRONG_DIAGNOSIS      = "WRONG_DIAGNOSIS"
    WRONG_RECOMMENDATION = "WRONG_RECOMMENDATION"
    TOO_RISKY            = "TOO_RISKY"
    NOT_NOW              = "NOT_NOW"
    ACCEPTABLE_TRADEOFF  = "ACCEPTABLE_TRADEOFF"
    OTHER                = "OTHER"

    @classmethod
    def from_string(cls, s: str) -> "RejectionReasonCode":
        """Parse a reason code string. Falls back to OTHER."""
        try:
            return cls(s.upper().replace(" ", "_"))
        except ValueError:
            return cls.OTHER

    def label(self) -> str:
        return self.value.replace("_", " ").title()

    def is_novelty_exempt(self) -> bool:
        """
        Return True if evidence novelty does NOT bypass the suppression window.

        ACCEPTABLE_TRADEOFF represents a considered architectural position.
        A new component appearing does not change that position.
        Only window expiry governs for this code.
        """
        return self == RejectionReasonCode.ACCEPTABLE_TRADEOFF


@dataclass
class RejectionRecord:
    """
    Structured record of a human rejection decision.

    Persisted to PatternStore. Does NOT modify PatternRecord.
    The pattern evidence remains immutable after any rejection.
    """
    proposal_id:              str
    pattern_signature:        str
    reason_code:              RejectionReasonCode
    reason_text:              str  = ""
    cycle:                    int  = 0
    recorded_at:              str  = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    # Sprint-003 additions
    components_at_rejection:  list = field(default_factory=list)
    suppression_cycles:       int  = 5
    recorded_genesis:         str  = "Genesis-045"

    def __post_init__(self):
        # Defensive copy — components_at_rejection is independent of caller's list.
        object.__setattr__(self, "components_at_rejection",
                           list(self.components_at_rejection))


# ---------------------------------------------------------------------------
# Sprint-004: Outcome tracking
# ---------------------------------------------------------------------------

class OutcomeStatus(Enum):
    """
    Lifecycle state of a proposal after it has been approved and executed.

    IMPLEMENTED     — ExecutionRunner reached COMMIT_PENDING for a session
                      linked to this proposal. A physical engineering change
                      was applied. Does NOT imply the change worked.

    VALIDATED       — After IMPLEMENTED, the pattern that triggered this
                      proposal did not recur for VALIDATION_CYCLES consecutive
                      analysis cycles. This is outcome observation, NOT proof
                      of causation. Jarvis does not claim the implementation
                      caused the improvement.

    FAILED_VALIDATION — After IMPLEMENTED, the pattern recurred within the
                      observation window. The expected improvement was NOT
                      observed. Cause is uncertain. Original evidence intact.
                      Pattern remains fully eligible for future proposals.
    """
    IMPLEMENTED      = "IMPLEMENTED"
    VALIDATED        = "VALIDATED"
    FAILED_VALIDATION = "FAILED_VALIDATION"

    def label(self) -> str:
        return self.value.replace("_", " ").title()


@dataclass
class ProposalOutcomeRecord:
    """
    Minimal outcome record linking a proposal to its execution result
    and subsequent validation observation.

    Persisted to PatternStore under subject 'eng_outcome'.
    Does NOT mutate PatternRecord or the original ImprovementProposal.

    Chronology fields:
        approved_at_cycle      — cycle when human approved the proposal
        implemented_at_cycle   — cycle when COMMIT_PENDING was reached
        validated_at_cycle     — cycle when VALIDATED or FAILED_VALIDATION
                                 was set; None until that transition

    Invariants:
        approved_at_cycle <= implemented_at_cycle
        implemented_at_cycle <= validated_at_cycle (when set)
        VALIDATED/FAILED_VALIDATION require IMPLEMENTED first
        No outcome triggers autonomous engineering action

    Epistemic notes (preserved in record):
        IMPLEMENTED ≠ diagnosis correct
        VALIDATED ≠ problem permanently solved; causation not established
        FAILED_VALIDATION ≠ implementation failure; cause uncertain
    """
    proposal_id:           str
    pattern_signature:     str
    status:                OutcomeStatus
    approved_at_cycle:     int
    implemented_at_cycle:  int
    validated_at_cycle:    Optional[int]  = None
    tests_run:             int            = 0
    files_changed:         int            = 0
    snapshot_sha:          str            = ""
    recorded_genesis:      str            = "Genesis-045"


@dataclass
class PatternRecord:
    """
    A recurring observation across multiple analysis cycles.

    Created when the same issue signature appears in 2+ distinct cycles.
    Evidence (session history) is immutable — never modified by rejections
    or outcomes.

    Attributes:
        signature:             Normalised pattern key: "CATEGORY:normalised_title"
        category:              ROUTING / MEMORY / PERFORMANCE / EXCEPTION
        display_title:         Human-readable title from first observation
        first_cycle:           Cycle when first observed
        last_cycle:            Most recent cycle when observed
        total_occurrences:     Lifetime raw count (never decreases)
        affected_components:   Union of likely_files across all observations
        external_flag:         RESERVED — never set in Sprint-002/003/004
        proposals:             proposal_ids linked to this pattern
    """
    signature:            str
    category:             str
    display_title:        str
    first_cycle:          int
    last_cycle:           int
    total_occurrences:    int
    affected_components:  list = field(default_factory=list)
    external_flag:        bool = False
    proposals:            list = field(default_factory=list)

    @classmethod
    def normalise_signature(cls, category: str, title: str) -> str:
        """
        Build a stable normalised signature from category and title.

        Strips numeric specifics to keep the same issue type stable
        even when counts change (e.g. "3 turns" vs "7 turns").
        """
        import re
        normalised = re.sub(r'\d+', 'N', title.lower().strip())
        normalised = re.sub(r'[^a-z0-9_: ]+', '', normalised)
        normalised = normalised[:60]
        return f"{category.upper()}:{normalised}"
