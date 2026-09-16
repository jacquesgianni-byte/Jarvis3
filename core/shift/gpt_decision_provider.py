"""
Jarvis GPT Decision Provider (Governance Sprint)

Routes governance decision requests to the designated GPT provider
(OpenAIProvider) using the project's existing AI abstraction.

DESIGN CONSTRAINTS:
    - Uses OpenAIProvider.ask() — the existing blocking call
    - Uses Settings() — the existing credential mechanism
    - Does NOT call Claude / Anthropic
    - Does NOT create a second provider mechanism
    - Does NOT hardcode credentials
    - Requires structured JSON response — free-form text is rejected
    - Validates decision against strict schema before returning
    - Any validation failure → decision treated as REJECTED (fail-safe)

SEPARATION OF ROLES:
    - Proposer:           Jarvis (builds EvidenceBundle, classifies risk)
    - Decision authority: GPT (this module delivers the request and response)
    - Executor:           Jarvis (executes if decision is APPROVED)
    GPT does NOT propose. GPT does NOT execute. GPT does NOT classify risk.

RISK CLASSIFICATION IMMUTABILITY:
    - risk_level in the request is set by RiskClassifier BEFORE this
      module is called. It is passed READ-ONLY to GPT for information.
    - The response is validated to confirm risk_level matches the
      immutable classification. Any mismatch → REJECTED.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from core.ai.providers.openai_provider import OpenAIProvider
from core.ai.streaming import StreamCallbacks
from core.shift.risk_classifier import ApprovalRecord
from core.shift.source_clean import AUTONOMOUSLY_PROTECTED

logger = logging.getLogger(__name__)

# Valid decision values — anything else is rejected
_VALID_DECISIONS = {"APPROVED", "REJECTED"}

# System prompt for GPT governance decisions
_DECISION_SYSTEM_PROMPT = """You are the designated engineering governance authority for the Jarvis autonomous shift.

Your role is DECISION AUTHORITY ONLY. You:
- Review evidence of a failing test and a proposed repair
- Approve or reject the repair based on the evidence
- Do NOT propose alternative repairs
- Do NOT reclassify the risk level
- Do NOT modify the affected_files list
- Do NOT approve repairs to autonomously protected components

You must respond with ONLY a JSON object in this exact format:
{
  "decision": "APPROVED" or "REJECTED",
  "decision_reason": "one or two sentences explaining your decision",
  "finding_id": "<echo the finding_id from the request>",
  "risk_level": "<echo the risk_level from the request — do not change it>"
}

Do not include any text outside the JSON object.
Do not include markdown formatting or code fences.
If you are uncertain or the evidence is insufficient, respond with REJECTED."""


@dataclass
class GptDecisionResult:
    """Validated result from a GPT governance decision."""
    decision:        str    # "APPROVED" | "REJECTED" | "VALIDATION_FAILED"
    decision_reason: str
    finding_id:      str
    risk_level:      str    # as returned by GPT — validated against original
    raw_response:    str    # for audit purposes


class GptDecisionProvider:
    """
    Delivers governance decision requests to GPT and validates responses.

    Uses the project's existing OpenAIProvider.ask() — no new mechanism.
    Credentials come from Settings() — no hardcoding.
    """

    def __init__(self) -> None:
        self._provider = OpenAIProvider()

    def request_decision(
        self,
        finding_id:      str,
        risk_level:      str,          # locked, immutable
        evidence_bundle: dict,         # raw EvidenceBundle.to_dict()
        proposed_action: str,
        affected_files:  list[str],
        protected_component_check: bool,  # True = screened against AUTONOMOUSLY_PROTECTED
    ) -> GptDecisionResult:
        """
        Send a governance decision request to GPT.

        The risk_level is included READ-ONLY for GPT's information.
        GPT's response is validated against the original risk_level —
        any mismatch produces VALIDATION_FAILED (treated as REJECTED).

        Args:
            finding_id:                UUID of the FindingRecord
            risk_level:                RiskTier.name — locked before this call
            evidence_bundle:           EvidenceBundle.to_dict()
            proposed_action:           Description of the proposed repair
            affected_files:            Files the repair would modify
            protected_component_check: True if screened against AUTONOMOUSLY_PROTECTED

        Returns:
            GptDecisionResult with validated decision
        """
        request_payload = {
            "finding_id":               finding_id,
            "risk_level":               risk_level,
            "evidence":                 evidence_bundle,
            "proposed_action":          proposed_action,
            "affected_files":           affected_files,
            "protected_component_check": protected_component_check,
            "instructions": (
                "Review the evidence and proposed repair. "
                "Respond with APPROVED if the repair is well-evidenced, "
                "targeted, and appropriate for the risk level. "
                "Respond with REJECTED otherwise. "
                "Do not change the risk_level. "
                "Do not approve repairs to autonomously protected components."
            ),
        }

        prompt = (
            f"{_DECISION_SYSTEM_PROMPT}\n\n"
            f"GOVERNANCE DECISION REQUEST:\n"
            f"{json.dumps(request_payload, indent=2)}"
        )

        logger.info(
            "[GPT_DECISION] Requesting decision for finding=%s risk=%s",
            finding_id, risk_level,
        )

        # Use existing provider abstraction — no new mechanism
        # StreamCallbacks with no-op handlers for blocking ask()
        callbacks = _NoOpCallbacks()
        response = self._provider.ask(prompt)

        if not response.success:
            logger.error(
                "[GPT_DECISION] Provider call failed: %s", response.message
            )
            return GptDecisionResult(
                decision="VALIDATION_FAILED",
                decision_reason=f"GPT provider call failed: {response.message}",
                finding_id=finding_id,
                risk_level=risk_level,
                raw_response="",
            )

        return self._validate_response(
            raw=response.message,
            expected_finding_id=finding_id,
            expected_risk_level=risk_level,
        )

    def _validate_response(
        self,
        raw: str,
        expected_finding_id: str,
        expected_risk_level: str,
    ) -> GptDecisionResult:
        """
        Strict schema validation of GPT's response.

        Validation chain:
            1. Parse as JSON
            2. Required fields present
            3. decision ∈ {APPROVED, REJECTED}
            4. finding_id matches
            5. risk_level matches (immutability check)

        Any failure → VALIDATION_FAILED (treated as REJECTED by caller).
        """
        # Strip markdown fences if GPT included them despite instructions
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            clean = "\n".join(
                l for l in lines
                if not l.startswith("```")
            ).strip()

        # Step 1: Parse JSON
        try:
            parsed = json.loads(clean)
        except json.JSONDecodeError as exc:
            logger.error("[GPT_DECISION] JSON parse failed: %s | raw=%r", exc, raw[:200])
            return GptDecisionResult(
                decision="VALIDATION_FAILED",
                decision_reason=f"Response is not valid JSON: {exc}",
                finding_id=expected_finding_id,
                risk_level=expected_risk_level,
                raw_response=raw,
            )

        # Step 2: Required fields
        required = {"decision", "decision_reason", "finding_id", "risk_level"}
        missing = required - set(parsed.keys())
        if missing:
            logger.error("[GPT_DECISION] Missing fields: %s", missing)
            return GptDecisionResult(
                decision="VALIDATION_FAILED",
                decision_reason=f"Response missing required fields: {missing}",
                finding_id=expected_finding_id,
                risk_level=expected_risk_level,
                raw_response=raw,
            )

        # Step 3: decision value
        decision = str(parsed["decision"]).upper().strip()
        if decision not in _VALID_DECISIONS:
            logger.error("[GPT_DECISION] Invalid decision value: %r", decision)
            return GptDecisionResult(
                decision="VALIDATION_FAILED",
                decision_reason=f"Decision value {decision!r} not in {_VALID_DECISIONS}",
                finding_id=expected_finding_id,
                risk_level=expected_risk_level,
                raw_response=raw,
            )

        # Step 4: finding_id matches
        returned_id = str(parsed.get("finding_id", "")).strip()
        if returned_id != expected_finding_id:
            logger.error(
                "[GPT_DECISION] finding_id mismatch: expected=%s got=%s",
                expected_finding_id, returned_id,
            )
            return GptDecisionResult(
                decision="VALIDATION_FAILED",
                decision_reason=(
                    f"finding_id mismatch: expected {expected_finding_id!r}, "
                    f"got {returned_id!r}"
                ),
                finding_id=expected_finding_id,
                risk_level=expected_risk_level,
                raw_response=raw,
            )

        # Step 5: risk_level immutability check
        returned_risk = str(parsed.get("risk_level", "")).strip().upper()
        if returned_risk != expected_risk_level.upper():
            logger.error(
                "[GPT_DECISION] risk_level mismatch: expected=%s got=%s — HARD STOP",
                expected_risk_level, returned_risk,
            )
            return GptDecisionResult(
                decision="VALIDATION_FAILED",
                decision_reason=(
                    f"risk_level mismatch — classification manipulation attempt: "
                    f"expected {expected_risk_level!r}, got {returned_risk!r}"
                ),
                finding_id=expected_finding_id,
                risk_level=expected_risk_level,
                raw_response=raw,
            )

        logger.info(
            "[GPT_DECISION] Validated: finding=%s decision=%s reason=%s",
            expected_finding_id, decision, parsed["decision_reason"][:100],
        )

        return GptDecisionResult(
            decision=decision,
            decision_reason=str(parsed["decision_reason"]),
            finding_id=expected_finding_id,
            risk_level=expected_risk_level,
            raw_response=raw,
        )


class _NoOpCallbacks(StreamCallbacks):
    """No-op StreamCallbacks for blocking ask() calls."""
    def emit_token(self, token: str) -> None: pass
    def emit_complete(self, text: str) -> None: pass
    def emit_error(self, error: Exception) -> None: pass
