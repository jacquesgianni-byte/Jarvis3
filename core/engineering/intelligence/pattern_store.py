"""
Pattern Store — Genesis-045 Sprint-001

Thin persistence adapter over KnowledgeEngine.
Stores issue frequency and proposal history across analysis cycles.

Does NOT modify KnowledgeEngine architecture.
Uses standard store_memory / recall_memory / update_memory API.

Subjects used:
  "eng_pattern_freq"    — issue frequency by category+title key
  "eng_proposal"        — serialised ImprovementProposal state

If KnowledgeEngine cannot support a required operation,
PatternStore raises PatternStoreError and Sprint-001 stops.
It never silently redesigns the persistence layer.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Optional

logger = logging.getLogger(__name__)

FREQ_SUBJECT    = "eng_pattern_freq"
PROPOSAL_SUBJECT = "eng_proposal"
CATEGORY        = "engineering"


class PatternStoreError(Exception):
    """Raised when PatternStore cannot complete a required operation."""


class PatternStore:
    """
    Persistence for engineering intelligence pattern data.

    Thin adapter over KnowledgeEngine. All reads/writes use
    the standard KnowledgeEngine public API. Architecture unchanged.

    Public API:
        increment_frequency(category, title) -> int
        get_frequency(category, title)       -> int
        get_rejection_cycle(category, title) -> int  (0 = not rejected)
        record_rejection(category, title, cycle, reason)
        save_proposal(proposal)
        load_proposal()                      -> Optional[ImprovementProposal]
        clear_proposal()
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ------------------------------------------------------------------
    # Issue frequency
    # ------------------------------------------------------------------

    def _freq_key(self, category: str, title: str) -> str:
        """Stable key for a category+title pair."""
        return f"{category}:{title[:40]}"

    def increment_frequency(self, category: str, title: str) -> int:
        """
        Increment the seen-count for this issue type.
        Returns the new count.
        """
        key = self._freq_key(category, title)
        try:
            record = self._ke.recall_memory(FREQ_SUBJECT, key)
            if record is None:
                data = {"count": 1, "last_seen": datetime.now(UTC).isoformat()}
                self._ke.store_memory(
                    subject=FREQ_SUBJECT,
                    category=CATEGORY,
                    attribute=key,
                    value=json.dumps(data),
                    source="system",
                )
                return 1
            else:
                existing = json.loads(record.value)
                new_count = existing.get("count", 0) + 1
                data = {"count": new_count, "last_seen": datetime.now(UTC).isoformat()}
                self._ke.update_memory(
                    subject=FREQ_SUBJECT,
                    attribute=key,
                    value=json.dumps(data),
                    source="system",
                )
                return new_count
        except Exception as e:
            raise PatternStoreError(f"increment_frequency failed: {e}") from e

    def get_frequency(self, category: str, title: str) -> int:
        """Return the number of times this issue has been seen. 0 if never."""
        key = self._freq_key(category, title)
        try:
            record = self._ke.recall_memory(FREQ_SUBJECT, key)
            if record is None:
                return 0
            data = json.loads(record.value)
            return data.get("count", 0)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Rejection history
    # ------------------------------------------------------------------

    def _rejection_key(self, category: str, title: str) -> str:
        return f"reject:{self._freq_key(category, title)}"

    def record_rejection(
        self, category: str, title: str, cycle: int, reason: str = ""
    ) -> None:
        """Record that this issue type was rejected at the given cycle."""
        key = self._rejection_key(category, title)
        data = {
            "rejected_at_cycle": cycle,
            "reason": reason,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        try:
            record = self._ke.recall_memory(FREQ_SUBJECT, key)
            if record is None:
                self._ke.store_memory(
                    subject=FREQ_SUBJECT,
                    category=CATEGORY,
                    attribute=key,
                    value=json.dumps(data),
                    source="system",
                )
            else:
                self._ke.update_memory(
                    subject=FREQ_SUBJECT,
                    attribute=key,
                    value=json.dumps(data),
                    source="system",
                )
        except Exception as e:
            raise PatternStoreError(f"record_rejection failed: {e}") from e

    def get_rejection_cycle(self, category: str, title: str) -> int:
        """
        Return the cycle number when this issue was last rejected.
        Returns 0 if never rejected.
        """
        key = self._rejection_key(category, title)
        try:
            record = self._ke.recall_memory(FREQ_SUBJECT, key)
            if record is None:
                return 0
            data = json.loads(record.value)
            return data.get("rejected_at_cycle", 0)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Proposal persistence
    # ------------------------------------------------------------------

    def save_proposal(self, proposal: "ImprovementProposal") -> None:
        """Persist the current proposal to KnowledgeEngine."""
        from core.engineering.intelligence.models import ProposalStatus
        try:
            data = {
                "proposal_id":      proposal.proposal_id,
                "status":           proposal.status.name,
                "confidence":       proposal.confidence,
                "session_id":       proposal.session_id,
                "created_at":       proposal.created_at.isoformat(),
                "stale_cycles":     proposal.stale_cycles,
                "rejection_reason": proposal.rejection_reason,
                # Store evidence as list of dicts
                "evidence": [
                    {
                        "category":   e.category,
                        "title":      e.title,
                        "detail":     e.detail,
                        "evidence":   list(e.evidence),
                        "confidence": e.confidence,
                    }
                    for e in proposal.evidence
                ],
                "diagnosis": {
                    "inference":          proposal.diagnosis.inference,
                    "confidence":         proposal.diagnosis.confidence,
                    "uncertainty":        proposal.diagnosis.uncertainty,
                    "likely_components":  list(proposal.diagnosis.likely_components),
                    "cfr_reference":      proposal.diagnosis.cfr_reference,
                },
                "recommendation": {
                    "proposed_change":     proposal.recommendation.proposed_change,
                    "expected_benefit":    proposal.recommendation.expected_benefit,
                    "affected_components": list(proposal.recommendation.affected_components),
                    "validation_plan":     proposal.recommendation.validation_plan,
                },
            }
            serialised = json.dumps(data)
            record = self._ke.recall_memory(PROPOSAL_SUBJECT, "active")
            if record is None:
                self._ke.store_memory(
                    subject=PROPOSAL_SUBJECT,
                    category=CATEGORY,
                    attribute="active",
                    value=serialised,
                    source="system",
                )
            else:
                self._ke.update_memory(
                    subject=PROPOSAL_SUBJECT,
                    attribute="active",
                    value=serialised,
                    source="system",
                )
            logger.info("[PATTERN_STORE] Proposal saved: %s", proposal.proposal_id)
        except Exception as e:
            raise PatternStoreError(f"save_proposal failed: {e}") from e

    def load_proposal(self) -> "Optional[ImprovementProposal]":
        """Load the active proposal from KnowledgeEngine. None if none."""
        from core.engineering.intelligence.models import (
            Diagnosis, ImprovementProposal, Observation,
            ProposalStatus, Recommendation,
        )
        try:
            record = self._ke.recall_memory(PROPOSAL_SUBJECT, "active")
            if record is None:
                return None
            data = json.loads(record.value)

            status = ProposalStatus[data["status"]]
            evidence = [
                Observation(
                    category   = e["category"],
                    title      = e["title"],
                    detail     = e["detail"],
                    evidence   = tuple(e.get("evidence", [])),
                    confidence = e.get("confidence", 0.0),
                )
                for e in data.get("evidence", [])
            ]
            d = data["diagnosis"]
            diagnosis = Diagnosis(
                inference         = d["inference"],
                confidence        = d["confidence"],
                uncertainty       = d["uncertainty"],
                likely_components = tuple(d.get("likely_components", [])),
                cfr_reference     = d.get("cfr_reference", ""),
            )
            r = data["recommendation"]
            recommendation = Recommendation(
                proposed_change      = r["proposed_change"],
                expected_benefit     = r["expected_benefit"],
                affected_components  = tuple(r.get("affected_components", [])),
                validation_plan      = r.get("validation_plan", ""),
            )
            return ImprovementProposal(
                proposal_id      = data["proposal_id"],
                status           = status,
                evidence         = evidence,
                diagnosis        = diagnosis,
                recommendation   = recommendation,
                confidence       = data["confidence"],
                session_id       = data.get("session_id", ""),
                stale_cycles     = data.get("stale_cycles", 0),
                rejection_reason = data.get("rejection_reason", ""),
            )
        except Exception as e:
            logger.warning("[PATTERN_STORE] load_proposal failed: %s", e)
            return None

    def clear_proposal(self) -> None:
        """Remove the active proposal from KnowledgeEngine."""
        try:
            self._ke.update_memory(
                subject   = PROPOSAL_SUBJECT,
                attribute = "active",
                value     = "",
                source    = "system",
            )
            logger.info("[PATTERN_STORE] Active proposal cleared.")
        except Exception:
            pass  # No proposal to clear is not an error
