"""
Reasoning models (Genesis-013 Task 001).

Data carriers for the Thought & Reasoning Engine. These classes hold
the results of reasoning — they never reason, never store knowledge,
and never touch the Knowledge Engine.

An Inference is NOT a MemoryRecord and is never stored in
knowledge.json.
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Optional


class ReasonType(Enum):
    """How a conclusion was reached. [R3]

    DERIVED, CHAINED and MULTI_PREMISE are the Version 1 set.
    AI_ASSISTED and OBSERVED are reserved for later versions and are
    never produced by this engine.
    """

    DERIVED = "derived"              # single rule, stored premises only
    CHAINED = "chained"              # at least one premise was inferred
    MULTI_PREMISE = "multi_premise"  # single rule, several stored premises
    AI_ASSISTED = "ai_assisted"      # reserved (V2+)
    OBSERVED = "observed"            # reserved (V2+)


class Outcome(Enum):
    """What became of an inference attempt (thresholds per design §6)."""

    ASSERTED = "asserted"      # confidence >= 0.75 — may be spoken plainly
    HEDGED = "hedged"          # 0.50–0.74 — spoken with hedging
    SUPPRESSED = "suppressed"  # < 0.50 — never spoken; history only
    NO_PATH = "no_path"        # no rule chain could conclude anything


# Confidence thresholds and cap (design §6). The cap guarantees that an
# inferred value can never tie or beat a user-stated fact (1.0):
# "User facts prevail" — numerically, not just structurally.
CONFIDENCE_CAP = 0.9
ASSERT_THRESHOLD = 0.75
SUPPRESS_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class Premise:
    """One condition of a rule."""

    attribute: str
    kind: str                       # "equals" | "in_set" | "exists"
    operand: object = None          # value for equals, set name for in_set


@dataclass(frozen=True, slots=True)
class Rule:
    """A declarative reasoning rule, loaded from data — never hardcoded."""

    id: str
    premises: tuple                 # tuple[Premise, ...]
    conclusion_attribute: str
    conclusion_value: str
    confidence: float
    source_file: str = ""


@dataclass(frozen=True, slots=True)
class PremiseSnapshot:
    """A premise fact as it was at inference time.

    Snapshots make explanations honest forever: if the fact later
    changes, the explanation still shows what the conclusion was
    actually based on.
    """

    attribute: str
    value: str
    confidence: float
    source: str                     # "user", "inferred", ...


@dataclass(slots=True)
class Inference:
    """A conclusion produced by the ReasoningEngine."""

    subject: str
    attribute: str
    value: str
    confidence: float
    reason_type: ReasonType
    rule_ids: tuple                 # full chain, outermost rule first
    premises: tuple                 # tuple[PremiseSnapshot, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def outcome(self) -> Outcome:
        if self.confidence >= ASSERT_THRESHOLD:
            return Outcome.ASSERTED
        if self.confidence >= SUPPRESS_THRESHOLD:
            return Outcome.HEDGED
        return Outcome.SUPPRESSED


@dataclass(frozen=True, slots=True)
class Explanation:
    """Human-readable trace answering: what facts produced this?"""

    inference: Inference
    lines: tuple                    # tuple[str, ...]

    def summary(self) -> str:
        return "\n".join(self.lines)


@dataclass(slots=True)
class ReasoningStats:
    """Session counters exposed via ReasoningEngine.stats()."""

    inferences: int = 0
    asserted: int = 0
    hedged: int = 0
    suppressed: int = 0
    no_path: int = 0
    derived: int = 0
    chained: int = 0
    multi_premise: int = 0
    rules_loaded: int = 0
    ai_consults: int = 0            # pinned 0 in V1 by design