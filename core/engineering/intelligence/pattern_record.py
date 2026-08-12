"""
Pattern Record â€” Genesis-045 Sprint-002 / Sprint-003

PatternRecord: recurring observation across multiple analysis cycles.
RejectionRecord: structured human decision on a proposal.
RejectionReasonCode: 7 structured reason codes.

Sprint-003 additions to RejectionRecord:
  components_at_rejection  â€” snapshot of PatternRecord.affected_components
                             taken at rejection time (evidence immutability)
  suppression_cycles       â€” computed from RejectionReasonCode at rejection
                             time; stored explicitly so the selector reads it
                             without recalculating
  recorded_genesis         â€” Genesis sprint tag for future version-awareness
                             (Sprint-004); zero cost to store now

Key design invariants:
  - PatternRecord evidence is IMMUTABLE â€” never modified by a rejection.
  - external_flag is RESERVED â€” never set by any Sprint-002/003 operation.
  - Differentiated suppression is fully deterministic; no AI involved.
  - A rejection is a decision about a proposal, not a change to the pattern.
  - Evidence novelty (new component) may permit early re-eligibility, but
    frequency growth alone does NOT override a human rejection window.
  - ACCEPTABLE_TRADEOFF suppressions are window-only; evidence novelty does
    NOT trigger early re-eligibility for this code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class RejectionReasonCode(Enum):
    """
    Structured reason for rejecting an ImprovementProposal.

    Sprint-003 introduces differentiated suppression windows per code.
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
        A new component appearing does not fundamentally change that position.
        Only window expiry governs for this code.
        """
        return self == RejectionReasonCode.ACCEPTABLE_TRADEOFF


@dataclass
class RejectionRecord:
    """
    Structured record of a human rejection decision.

    Persisted to PatternStore. Does NOT modify PatternRecord.
    The pattern evidence remains immutable after any rejection.

    Sprint-003 additions:
        components_at_rejection  Snapshot of PatternRecord.affected_components
                                 at the moment of rejection.  Used to detect
                                 evidence novelty (new component) without
                                 mutating the live PatternRecord.
        suppression_cycles       Pre-computed suppression window for this
                                 reason code.  Stored explicitly so the
                                 selector does not need to recalculate and
                                 the audit trail is self-describing.
        recorded_genesis         Genesis sprint tag at rejection time.
                                 Reserved for Sprint-004 version-awareness.

    Attributes:
        proposal_id:              The rejected proposal's ID
        pattern_signature:        Which pattern this proposal was about
        reason_code:              Structured rejection reason
        reason_text:              Optional free-text explanation
        cycle:                    Analysis cycle when rejected
        recorded_at:              ISO timestamp
        components_at_rejection:  Snapshot of affected_components (Sprint-003)
        suppression_cycles:       Computed window for this reason (Sprint-003)
        recorded_genesis:         Genesis tag e.g. "Genesis-045" (Sprint-003)
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
    suppression_cycles:       int  = 5    # default; overwritten by engine
    recorded_genesis:         str  = "Genesis-045"

    def __post_init__(self):
        # Defensive copy — components_at_rejection is independent of caller's list.
        # Evidence immutability invariant enforced at the dataclass level.
        object.__setattr__(self, "components_at_rejection",
                           list(self.components_at_rejection))


@dataclass
class PatternRecord:
    """
    A recurring observation across multiple analysis cycles.

    Created when the same issue signature appears in 2+ distinct cycles.
    Evidence (session history) is immutable â€” never modified by rejections.

    Attributes:
        signature:             Normalised pattern key: "CATEGORY:normalised_title"
        category:              ROUTING / MEMORY / PERFORMANCE / EXCEPTION
        display_title:         Human-readable title from first observation
        first_cycle:           Cycle when first observed
        last_cycle:            Most recent cycle when observed
        total_occurrences:     Lifetime raw count (never decreases)
        affected_components:   Union of likely_files across all observations
        external_flag:         RESERVED â€” never set in Sprint-002/003
        proposals:             proposal_ids linked to this pattern
    """
    signature:            str
    category:             str
    display_title:        str
    first_cycle:          int
    last_cycle:           int
    total_occurrences:    int
    affected_components:  list = field(default_factory=list)
    external_flag:        bool = False   # RESERVED â€” Sprint-003+ only
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

