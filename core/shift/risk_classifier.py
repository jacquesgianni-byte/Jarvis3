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

from __future__ import annotations

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
