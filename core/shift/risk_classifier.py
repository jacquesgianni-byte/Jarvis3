"""
Jarvis ShiftController — Risk Classifier (Sprint A)

DETERMINISTIC — no LLM involvement.
DiagnosisHypothesis is never an input to this module.

Classification tiers:
    LOW      — autonomous repair permitted (all conditions met)
    MEDIUM   — Chief approval required via Four-Way
    HIGH     — Chief approval required; structural or architectural change
    CRITICAL — no repair attempted; HARD STOP

An AUTONOMOUSLY_PROTECTED file always produces AUTONOMOUSLY_PROTECTED
(not a risk tier — a separate classification that bypasses risk entirely).
A GOVERNED_HIGH_RISK file always produces GOVERNED_HIGH_RISK.
"""

from dataclasses import dataclass
from enum import Enum, auto

from core.shift.evidence import EvidenceStrength
from core.shift.source_clean import classify_file


class RiskTier(Enum):
    LOW                  = auto()
    MEDIUM               = auto()
    HIGH                 = auto()
    CRITICAL             = auto()
    AUTONOMOUSLY_PROTECTED = auto()   # not a repair tier — finding is surfaced only
    GOVERNED_HIGH_RISK   = auto()     # finding surfaced to Chief, manual sprint required


@dataclass(frozen=True)
class ClassificationResult:
    tier: RiskTier
    reason: str

    @property
    def allows_autonomous_repair(self) -> bool:
        return self.tier == RiskTier.LOW

    @property
    def requires_chief_approval(self) -> bool:
        return self.tier in (RiskTier.MEDIUM, RiskTier.HIGH)

    @property
    def is_hard_stop(self) -> bool:
        return self.tier == RiskTier.CRITICAL

    @property
    def is_surface_only(self) -> bool:
        """Finding is logged/surfaced to Chief; no autonomous repair attempted."""
        return self.tier in (
            RiskTier.AUTONOMOUSLY_PROTECTED,
            RiskTier.GOVERNED_HIGH_RISK,
        )


class RiskClassifier:
    """
    Deterministic risk classifier.

    Inputs:
        affected_file     — repo-relative path identified in EvidenceBundle
        evidence_strength — from EvidenceBundle (HIGH / MEDIUM / LOW)
        is_new_architecture — True if the proposed fix introduces new
                              modules, classes, or structural patterns
        is_additive_only  — True if the fix only adds within an existing,
                            well-understood module (no new architecture)

    Decision tree (evaluated top to bottom, first match wins):
        1. affected_file in AUTONOMOUSLY_PROTECTED → AUTONOMOUSLY_PROTECTED
        2. affected_file in GOVERNED_HIGH_RISK → GOVERNED_HIGH_RISK
        3. evidence_strength == LOW → MEDIUM minimum (cannot be LOW risk)
        4. is_new_architecture → HIGH
        5. not is_additive_only → MEDIUM
        6. All LOW conditions met → LOW

    RUNTIME_DATA_PATHS expansion attempt → CRITICAL (caller must check)
    """

    def classify(
        self,
        affected_file: str | None,
        evidence_strength: EvidenceStrength,
        is_new_architecture: bool = False,
        is_additive_only: bool = True,
    ) -> ClassificationResult:
        """
        Classify a finding into a risk tier.

        Args:
            affected_file:       Repo-relative path. None → treated as MEDIUM.
            evidence_strength:   Deterministic strength from EvidenceBundle.
            is_new_architecture: True if fix introduces new structural elements.
            is_additive_only:    True if fix is corrective within existing module.

        Returns:
            ClassificationResult with tier and reason.
        """
        # No affected file — cannot confirm scope → MEDIUM minimum
        if affected_file is None:
            return ClassificationResult(
                tier=RiskTier.MEDIUM,
                reason="No affected file identified; cannot confirm repair scope.",
            )

        # Step 1: AUTONOMOUSLY_PROTECTED
        file_class = classify_file(affected_file)
        if file_class == "AUTONOMOUSLY_PROTECTED":
            return ClassificationResult(
                tier=RiskTier.AUTONOMOUSLY_PROTECTED,
                reason=f"File is autonomously protected: {affected_file}",
            )

        # Step 2: GOVERNED_HIGH_RISK
        if file_class == "GOVERNED_HIGH_RISK":
            return ClassificationResult(
                tier=RiskTier.GOVERNED_HIGH_RISK,
                reason=f"File requires separate governed sprint: {affected_file}",
            )

        # Step 3: LOW evidence → MEDIUM minimum
        if evidence_strength == EvidenceStrength.LOW:
            return ClassificationResult(
                tier=RiskTier.MEDIUM,
                reason="Evidence strength is LOW; minimum risk tier is MEDIUM.",
            )

        # Step 4: New architecture → HIGH
        if is_new_architecture:
            return ClassificationResult(
                tier=RiskTier.HIGH,
                reason="Proposed fix introduces new architecture.",
            )

        # Step 5: Not purely additive → MEDIUM
        if not is_additive_only:
            return ClassificationResult(
                tier=RiskTier.MEDIUM,
                reason="Proposed fix is not purely additive within existing module.",
            )

        # Step 6: All LOW conditions met
        return ClassificationResult(
            tier=RiskTier.LOW,
            reason=(
                f"Evidence strength {evidence_strength.label()}, "
                f"additive fix in standard file: {affected_file}"
            ),
        )

    def classify_runtime_path_expansion(self) -> ClassificationResult:
        """
        Any attempt to expand RUNTIME_DATA_PATHS is classified CRITICAL.
        This is a separate entry point to make the intent explicit.
        """
        return ClassificationResult(
            tier=RiskTier.CRITICAL,
            reason="RUNTIME_DATA_PATHS expansion attempted — HARD STOP.",
        )


# ---------------------------------------------------------------------------
# GPT Authority Delegation additions (Governance Sprint)
# ---------------------------------------------------------------------------
# Additions to core/shift/risk_classifier.py
# These are the NEW symbols — appended after existing RiskTier/RiskClassifier

"""
GPT Decision Authority additions (Governance Sprint)

DecisionAuthority  — who must approve a finding of each RiskTier
authority_for()    — pure deterministic mapping, no side effects
ApprovalRecord     — mandatory audit trail for every GPT decision
"""


class DecisionAuthority(Enum):
    """
    Who must approve a repair proposal of this risk tier.

    GPT_APPROVAL_REQUIRED — LOW, MEDIUM, HIGH, GOVERNED_HIGH_RISK
    JOINT_HARD_STOP       — CRITICAL (Chief + GPT + Claude joint decision)
    BLOCKED               — AUTONOMOUSLY_PROTECTED (no approval path exists)
    """
    GPT_APPROVAL_REQUIRED = auto()
    JOINT_HARD_STOP       = auto()
    BLOCKED               = auto()


# Exhaustive, explicit mapping — every RiskTier has exactly one authority.
# Adding a new RiskTier without updating this table raises KeyError at runtime.
_AUTHORITY_MAP: dict[str, DecisionAuthority] = {
    "LOW":                  DecisionAuthority.GPT_APPROVAL_REQUIRED,
    "MEDIUM":               DecisionAuthority.GPT_APPROVAL_REQUIRED,
    "HIGH":                 DecisionAuthority.GPT_APPROVAL_REQUIRED,
    "CRITICAL":             DecisionAuthority.JOINT_HARD_STOP,
    "AUTONOMOUSLY_PROTECTED": DecisionAuthority.BLOCKED,
    "GOVERNED_HIGH_RISK":   DecisionAuthority.GPT_APPROVAL_REQUIRED,
}


def authority_for(risk_tier: "RiskTier") -> DecisionAuthority:
    """
    Pure deterministic mapping from RiskTier to DecisionAuthority.

    No side effects. Cannot be influenced by the proposed repair or
    by any agent. Called after RiskClassifier.classify() completes —
    the tier is already locked.

    Raises:
        KeyError: if a RiskTier has no entry in _AUTHORITY_MAP
                  (programming error, not a runtime condition).
    """
    return _AUTHORITY_MAP[risk_tier.name]


from datetime import UTC as _UTC, datetime as _datetime

@dataclass
class ApprovalRecord:
    """
    Mandatory audit trail for every GPT decision — approval AND rejection.

    Written to ShiftManifest.approval_records on every decision outcome.
    Never omitted — a REJECTED finding produces an ApprovalRecord with
    decision="REJECTED". A BLOCKED finding produces decision="BLOCKED".

    Fields are immutable after creation: the risk_level recorded here
    is the classification computed by RiskClassifier BEFORE the decision
    request was built. It cannot be changed by GPT's response.
    """
    finding_id:      str
    risk_level:      str            # RiskTier.name — locked at classification time
    evidence_ref:    str            # EvidenceBundle.test_id
    decision:        str            # "APPROVED" | "REJECTED" | "PENDING" | "BLOCKED"
    decision_reason: str
    timestamp:       str            # ISO-8601 UTC
    affected_files:  list[str]      # from EvidenceBundle.affected_file
    proposed_action: str
    authority:       str            # "GPT" | "JOINT" | "BLOCKED"

    def to_dict(self) -> dict:
        return {
            "finding_id":      self.finding_id,
            "risk_level":      self.risk_level,
            "evidence_ref":    self.evidence_ref,
            "decision":        self.decision,
            "decision_reason": self.decision_reason,
            "timestamp":       self.timestamp,
            "affected_files":  self.affected_files,
            "proposed_action": self.proposed_action,
            "authority":       self.authority,
        }

    @classmethod
    def pending(
        cls,
        finding_id: str,
        risk_level: str,
        evidence_ref: str,
        affected_files: list[str],
        proposed_action: str,
    ) -> "ApprovalRecord":
        return cls(
            finding_id=finding_id,
            risk_level=risk_level,
            evidence_ref=evidence_ref,
            decision="PENDING",
            decision_reason="Awaiting GPT decision.",
            timestamp=_datetime.now(_UTC).isoformat(),
            affected_files=affected_files,
            proposed_action=proposed_action,
            authority="GPT",
        )

    @classmethod
    def blocked(
        cls,
        finding_id: str,
        risk_level: str,
        evidence_ref: str,
        affected_files: list[str],
    ) -> "ApprovalRecord":
        return cls(
            finding_id=finding_id,
            risk_level=risk_level,
            evidence_ref=evidence_ref,
            decision="BLOCKED",
            decision_reason="AUTONOMOUSLY_PROTECTED component — no approval path exists.",
            timestamp=_datetime.now(_UTC).isoformat(),
            affected_files=affected_files,
            proposed_action="N/A",
            authority="BLOCKED",
        )
