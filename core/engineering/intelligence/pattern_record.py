"""
Pattern Record — Genesis-045 Sprint-002

PatternRecord: recurring observation across multiple analysis cycles.
RejectionRecord: structured human decision on a proposal.
RejectionReasonCode: 7 structured reason codes.

Key design invariants:
  - PatternRecord evidence is IMMUTABLE — never modified by a rejection.
  - external_flag is RESERVED — never set by any Sprint-002 operation.
  - All rejection reason codes produce the same 5-cycle suppression in Sprint-002.
  - Differentiated suppression is Sprint-003.
  - A rejection is a decision about a proposal, not a change to the pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class RejectionReasonCode(Enum):
    """
    Structured reason for rejecting an ImprovementProposal.

    All codes produce the same 5-cycle suppression in Sprint-002.
    Sprint-003 will introduce differentiated behaviour per code.
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


@dataclass
class RejectionRecord:
    """
    Structured record of a human rejection decision.

    Persisted to PatternStore. Does NOT modify PatternRecord.
    The pattern evidence remains immutable after any rejection.

    Attributes:
        proposal_id:       The rejected proposal's ID
        pattern_signature: Which pattern this proposal was about
        reason_code:       Structured rejection reason
        reason_text:       Optional free-text explanation
        cycle:             Analysis cycle when rejected
        recorded_at:       ISO timestamp
    """
    proposal_id:       str
    pattern_signature: str
    reason_code:       RejectionReasonCode
    reason_text:       str = ""
    cycle:             int = 0
    recorded_at:       str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


@dataclass
class PatternRecord:
    """
    A recurring observation across multiple analysis cycles.

    Created when the same issue signature appears in 2+ distinct cycles.
    Evidence (session history) is immutable — never modified by rejections.

    Attributes:
        signature:             Normalised pattern key: "CATEGORY:normalised_title"
        category:              ROUTING / MEMORY / PERFORMANCE / EXCEPTION
        display_title:         Human-readable title from first observation
        first_cycle:           Cycle when first observed
        last_cycle:            Most recent cycle when observed
        total_occurrences:     Lifetime raw count (never decreases)
        affected_components:   Union of likely_files across all observations
        external_flag:         RESERVED — never set in Sprint-002
                               Will be set by /engineering flag-external in Sprint-003
        proposals:             proposal_ids linked to this pattern
    """
    signature:            str
    category:             str
    display_title:        str
    first_cycle:          int
    last_cycle:           int
    total_occurrences:    int
    affected_components:  list = field(default_factory=list)
    external_flag:        bool = False   # RESERVED — Sprint-003 only
    proposals:            list = field(default_factory=list)  # list[str]

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
