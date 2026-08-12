"""
Session Record — Genesis-045 Sprint-002

TurnType taxonomy, SessionRecord, and DRRTrend.

TurnType is emitted by Agent as [TURN_TYPE] structured telemetry.
SessionRecord persists raw turn counts per analysis cycle.
DRRTrend computed from last 6 SessionRecords — never stored.

DeterministicResolutionRate is computed on demand:
    DRR = deterministic_turns / total_turns
It is NEVER stored as a derived value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Optional


class TurnType(Enum):
    """
    Authoritative taxonomy of conversation turn types.

    Emitted by Agent at every response exit point as:
        logger.info("[TURN_TYPE] type=%s", turn_type.value)

    DRR denominator: CONVERSATION + CONVERSATION_AI + CONVERSATION_ERROR
                     + TOOL_LOCAL + TOOL_EXTERNAL
    DRR numerator:   CONVERSATION + TOOL_LOCAL

    Excluded from both: CONVERSATION_AI_INTENTIONAL, CONVERSATION_INTERRUPTED,
                        SYSTEM_CMD, EMPTY_INPUT
    """
    CONVERSATION                = "CONVERSATION"
    CONVERSATION_AI             = "CONVERSATION_AI"
    CONVERSATION_AI_INTENTIONAL = "CONVERSATION_AI_INTENTIONAL"
    CONVERSATION_ERROR          = "CONVERSATION_ERROR"
    CONVERSATION_INTERRUPTED    = "CONVERSATION_INTERRUPTED"
    SYSTEM_CMD                  = "SYSTEM_CMD"
    EMPTY_INPUT                 = "EMPTY_INPUT"
    TOOL_LOCAL                  = "TOOL_LOCAL"
    TOOL_EXTERNAL               = "TOOL_EXTERNAL"

    # Types that count in DRR denominator
    @classmethod
    def denominator_types(cls) -> frozenset:
        return frozenset({
            cls.CONVERSATION,
            cls.CONVERSATION_AI,
            cls.CONVERSATION_ERROR,
            cls.TOOL_LOCAL,
            cls.TOOL_EXTERNAL,
        })

    # Types that count in DRR numerator (deterministic)
    @classmethod
    def numerator_types(cls) -> frozenset:
        return frozenset({
            cls.CONVERSATION,
            cls.TOOL_LOCAL,
        })


@dataclass
class SessionRecord:
    """
    Raw turn counts for one analysis cycle.

    Persisted to PatternStore after each cycle.
    DRR computed on demand from these fields — never stored.

    Attributes:
        cycle:                Analysis cycle number (monotonically increasing)
        timestamp:            ISO timestamp when this record was created
        total_turns:          Turns in DRR denominator
        deterministic_turns:  Turns in DRR numerator
        ai_called_turns:      CONVERSATION_AI turns
        error_turns:          CONVERSATION_ERROR turns
        issues_found:         Issues detected by SessionAnalysisWorker
    """
    cycle:               int
    timestamp:           str
    total_turns:         int
    deterministic_turns: int
    ai_called_turns:     int
    error_turns:         int
    issues_found:        list  = field(default_factory=list)
    # issues_found: list of {signature: str, category: str, confidence: float}

    @property
    def drr(self) -> float:
        """DeterministicResolutionRate for this cycle. 0.0 if no turns."""
        if self.total_turns == 0:
            return 0.0
        return self.deterministic_turns / self.total_turns

    @classmethod
    def empty(cls, cycle: int) -> "SessionRecord":
        return cls(
            cycle=cycle,
            timestamp=datetime.now(UTC).isoformat(),
            total_turns=0,
            deterministic_turns=0,
            ai_called_turns=0,
            error_turns=0,
            issues_found=[],
        )


class DRRTrend(Enum):
    """
    Trend direction of DeterministicResolutionRate over last 6 cycles.

    Requires exactly 6 cycles for non-overlapping 3+3 comparison:
        previous window: cycles[0:3]
        latest window:   cycles[3:6]

    Threshold: > 5% difference = DECLINING or IMPROVING
    """
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # fewer than 6 cycles
    DECLINING         = "DECLINING"          # DRR falling > 5%
    IMPROVING         = "IMPROVING"          # DRR rising > 5%
    STABLE            = "STABLE"             # difference <= 5%

    def label(self) -> str:
        return self.value.replace("_", " ").title()


def compute_drr_trend(session_records: list) -> DRRTrend:
    """
    Compute DRRTrend from a list of SessionRecord objects.

    Requires at least 6 records (the most recent 6 are used).
    Uses non-overlapping 3+3 windows:
        previous = mean DRR of records[0:3]
        latest   = mean DRR of records[3:6]

    Args:
        session_records: List of SessionRecord, oldest first.

    Returns:
        DRRTrend enum value.
    """
    if len(session_records) < 6:
        return DRRTrend.INSUFFICIENT_DATA

    recent = session_records[-6:]  # last 6
    previous_drr = sum(r.drr for r in recent[:3]) / 3
    latest_drr   = sum(r.drr for r in recent[3:]) / 3

    diff = latest_drr - previous_drr

    if diff < -0.05:
        return DRRTrend.DECLINING
    if diff > 0.05:
        return DRRTrend.IMPROVING
    return DRRTrend.STABLE
