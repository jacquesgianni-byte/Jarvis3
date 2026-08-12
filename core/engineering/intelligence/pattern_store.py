"""
Pattern Store — Genesis-045 Sprint-001 / Sprint-002 / Sprint-003

Thin persistence adapter over KnowledgeEngine.
Stores issue frequency, rejection history, session records, patterns,
and proposal history across analysis cycles.

Sprint-003 additions:
  REJECTION_SIG_SUBJECT  — secondary index keyed by pattern_signature;
                           stores the most-recent RejectionRecord for fast
                           lookup without chained reads (Option B from review)
  save_rejection_record  — updated to also write the sig-indexed entry
  get_rejection_record_by_signature — new; primary suppression-check path
  Legacy fallback        — get_rejection_cycle() retained for data written
                           by Sprint-002; new path takes precedence

Does NOT modify KnowledgeEngine architecture.
Uses standard store_memory / recall_memory / update_memory API.

Subjects used:
  "eng_pattern_freq"    — issue frequency by category+title key
                          (also legacy rejection suppression key)
  "eng_proposal"        — serialised ImprovementProposal state
  "eng_session"         — SessionRecord per cycle
  "eng_pattern"         — PatternRecord per signature
  "eng_rejection"       — RejectionRecord keyed by proposal_id (audit trail)
  "eng_rejection_sig"   — RejectionRecord keyed by pattern_signature
                          (Sprint-003; most-recent rejection per pattern)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Optional

logger = logging.getLogger(__name__)

FREQ_SUBJECT      = "eng_pattern_freq"
PROPOSAL_SUBJECT  = "eng_proposal"
CATEGORY          = "engineering"


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
        get_rejection_cycle(category, title) -> int  (0 = not rejected; legacy)
        record_rejection(category, title, cycle, reason)  (legacy write)
        save_rejection_record(record)        -> None  (Sprint-002+)
        get_rejection_record_by_signature(signature) -> Optional[RejectionRecord]
        save_proposal(proposal)
        load_proposal()                      -> Optional[ImprovementProposal]
        clear_proposal()
        save_session_record(record)
        get_session_records(n)               -> list
        get_last_cycle()                     -> int
        get_window_occurrences(sig, cycle, window) -> int
        update_pattern(signature, ...)
        get_active_patterns(window, min_occurrences) -> list
        link_proposal_to_pattern(signature, proposal_id)
    """

    # Sprint-002 subjects (class-level so subclasses can read them)
    SESSION_SUBJECT    = "eng_session"
    PATTERN_SUBJECT    = "eng_pattern"
    REJECTION_SUBJECT  = "eng_rejection"
    # Sprint-003: secondary index for signature-based lookup
    REJECTION_SIG_SUBJECT = "eng_rejection_sig"

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ------------------------------------------------------------------
    # Issue frequency
    # ------------------------------------------------------------------

    def _freq_key(self, category: str, title: str) -> str:
        """Stable key for a category+title pair."""
        return f"{category}:{title[:40]}"

    def increment_frequency(self, category: str, title: str) -> int:
        """Increment the seen-count for this issue type. Returns new count."""
        key = self._freq_key(category, title)
        try:
            record = self._ke.recall_memory(FREQ_SUBJECT, key)
            if record is None:
                data = {"count": 1, "last_seen": datetime.now(UTC).isoformat()}
                self._ke.store_memory(
                    subject=FREQ_SUBJECT, category=CATEGORY,
                    attribute=key, value=json.dumps(data), source="system",
                )
                return 1
            else:
                existing = json.loads(record.value)
                new_count = existing.get("count", 0) + 1
                data = {"count": new_count, "last_seen": datetime.now(UTC).isoformat()}
                self._ke.update_memory(
                    subject=FREQ_SUBJECT, attribute=key,
                    value=json.dumps(data), source="system",
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
    # Legacy rejection history (Sprint-001 / Sprint-002 path)
    # Retained for backward-compatibility with data written before Sprint-003.
    # ------------------------------------------------------------------

    def _rejection_key(self, category: str, title: str) -> str:
        return f"reject:{self._freq_key(category, title)}"

    def record_rejection(
        self, category: str, title: str, cycle: int, reason: str = ""
    ) -> None:
        """
        Record that this issue type was rejected at the given cycle.

        Legacy path — retained for backward-compatibility.
        Sprint-003 callers also invoke save_rejection_record() for the
        richer structured record.
        """
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
                    subject=FREQ_SUBJECT, category=CATEGORY,
                    attribute=key, value=json.dumps(data), source="system",
                )
            else:
                self._ke.update_memory(
                    subject=FREQ_SUBJECT, attribute=key,
                    value=json.dumps(data), source="system",
                )
        except Exception as e:
            raise PatternStoreError(f"record_rejection failed: {e}") from e

    def get_rejection_cycle(self, category: str, title: str) -> int:
        """
        Return the cycle number when this issue was last rejected (legacy).
        Returns -1 if never rejected via the legacy path.

        Sprint-003 selector uses get_rejection_record_by_signature() first
        and falls back to this only when no structured RejectionRecord exists.
        """
        key = self._rejection_key(category, title)
        try:
            record = self._ke.recall_memory(FREQ_SUBJECT, key)
            if record is None:
                return -1
            data = json.loads(record.value)
            return data.get("rejected_at_cycle", 0)
        except Exception:
            return -1

    # ------------------------------------------------------------------
    # Structured rejection records (Sprint-002+)
    # ------------------------------------------------------------------

    def save_rejection_record(self, record) -> None:
        """
        Persist a RejectionRecord.

        Sprint-003: writes two entries —
          (a) audit trail keyed by proposal_id under REJECTION_SUBJECT
          (b) signature index keyed by pattern_signature under
              REJECTION_SIG_SUBJECT (most-recent rejection per pattern;
              overwrites previous entry for the same signature)

        The signature index (b) is what the selector reads at proposal
        time for O(1) suppression lookup without chained reads.
        """
        key_by_id  = record.proposal_id
        key_by_sig = record.pattern_signature

        data = {
            "proposal_id":              record.proposal_id,
            "pattern_signature":        record.pattern_signature,
            "reason_code":              record.reason_code.value,
            "reason_text":              record.reason_text,
            "cycle":                    record.cycle,
            "recorded_at":              record.recorded_at,
            # Sprint-003 fields
            "components_at_rejection":  list(getattr(record, "components_at_rejection", [])),
            "suppression_cycles":       getattr(record, "suppression_cycles", 5),
            "recorded_genesis":         getattr(record, "recorded_genesis", ""),
        }
        serialised = json.dumps(data)

        try:
            # (a) audit entry keyed by proposal_id
            existing = self._ke.recall_memory(self.REJECTION_SUBJECT, key_by_id)
            if existing is None:
                self._ke.store_memory(
                    subject=self.REJECTION_SUBJECT, category=CATEGORY,
                    attribute=key_by_id, value=serialised, source="system",
                )
            else:
                self._ke.update_memory(
                    subject=self.REJECTION_SUBJECT,
                    attribute=key_by_id, value=serialised, source="system",
                )

            # (b) signature index — always overwrite with most recent rejection
            existing_sig = self._ke.recall_memory(self.REJECTION_SIG_SUBJECT, key_by_sig)
            if existing_sig is None:
                self._ke.store_memory(
                    subject=self.REJECTION_SIG_SUBJECT, category=CATEGORY,
                    attribute=key_by_sig, value=serialised, source="system",
                )
            else:
                self._ke.update_memory(
                    subject=self.REJECTION_SIG_SUBJECT,
                    attribute=key_by_sig, value=serialised, source="system",
                )

            logger.info(
                "[PATTERN_STORE] RejectionRecord saved: %s (%s) window=%d",
                record.proposal_id, record.reason_code.value,
                getattr(record, "suppression_cycles", 5),
            )
        except Exception as e:
            raise PatternStoreError(f"save_rejection_record failed: {e}") from e

    def get_rejection_record_by_signature(self, signature: str):
        """
        Return the most-recent RejectionRecord for a pattern_signature.

        Returns None if the pattern has never been rejected (Sprint-003 path)
        or if no structured record exists (fall back to legacy path in selector).

        This is the primary suppression-check path for Sprint-003.
        """
        from core.engineering.intelligence.pattern_record import (
            RejectionRecord, RejectionReasonCode,
        )
        try:
            rec = self._ke.recall_memory(self.REJECTION_SIG_SUBJECT, signature)
            if rec is None:
                return None
            d = json.loads(rec.value)
            return RejectionRecord(
                proposal_id             = d["proposal_id"],
                pattern_signature       = d["pattern_signature"],
                reason_code             = RejectionReasonCode(d["reason_code"]),
                reason_text             = d.get("reason_text", ""),
                cycle                   = d.get("cycle", 0),
                recorded_at             = d.get("recorded_at", ""),
                components_at_rejection = d.get("components_at_rejection", []),
                suppression_cycles      = d.get("suppression_cycles", 5),
                recorded_genesis        = d.get("recorded_genesis", ""),
            )
        except Exception as e:
            logger.warning(
                "[PATTERN_STORE] get_rejection_record_by_signature failed for %s: %s",
                signature, e,
            )
            return None

    # ------------------------------------------------------------------
    # Proposal persistence
    # ------------------------------------------------------------------

    def save_proposal(self, proposal) -> None:
        """Persist the current proposal to KnowledgeEngine."""
        from core.engineering.intelligence.models import ProposalStatus
        try:
            data = {
                "proposal_id":        proposal.proposal_id,
                "status":             proposal.status.name,
                "confidence":         proposal.confidence,
                "session_id":         proposal.session_id,
                "pattern_signature":  getattr(proposal, "pattern_signature", ""),
                "created_at":         proposal.created_at.isoformat(),
                "stale_cycles":       proposal.stale_cycles,
                "rejection_reason":   proposal.rejection_reason,
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
                    "inference":         proposal.diagnosis.inference,
                    "confidence":        proposal.diagnosis.confidence,
                    "uncertainty":       proposal.diagnosis.uncertainty,
                    "likely_components": list(proposal.diagnosis.likely_components),
                    "cfr_reference":     proposal.diagnosis.cfr_reference,
                },
                "recommendation": {
                    "proposed_change":      proposal.recommendation.proposed_change,
                    "expected_benefit":     proposal.recommendation.expected_benefit,
                    "affected_components":  list(proposal.recommendation.affected_components),
                    "validation_plan":      proposal.recommendation.validation_plan,
                },
            }
            serialised = json.dumps(data)
            record = self._ke.recall_memory(PROPOSAL_SUBJECT, "active")
            if record is None:
                self._ke.store_memory(
                    subject=PROPOSAL_SUBJECT, category=CATEGORY,
                    attribute="active", value=serialised, source="system",
                )
            else:
                self._ke.update_memory(
                    subject=PROPOSAL_SUBJECT,
                    attribute="active", value=serialised, source="system",
                )
            logger.info("[PATTERN_STORE] Proposal saved: %s", proposal.proposal_id)
        except Exception as e:
            raise PatternStoreError(f"save_proposal failed: {e}") from e

    def load_proposal(self):
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
            status   = ProposalStatus[data["status"]]
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
                proposed_change     = r["proposed_change"],
                expected_benefit    = r["expected_benefit"],
                affected_components = tuple(r.get("affected_components", [])),
                validation_plan     = r.get("validation_plan", ""),
            )
            return ImprovementProposal(
                proposal_id       = data["proposal_id"],
                status            = status,
                evidence          = evidence,
                diagnosis         = diagnosis,
                recommendation    = recommendation,
                confidence        = data["confidence"],
                session_id        = data.get("session_id", ""),
                pattern_signature = data.get("pattern_signature", ""),
                stale_cycles      = data.get("stale_cycles", 0),
                rejection_reason  = data.get("rejection_reason", ""),
            )
        except Exception as e:
            logger.warning("[PATTERN_STORE] load_proposal failed: %s", e)
            return None

    def clear_proposal(self) -> None:
        """Remove the active proposal from KnowledgeEngine."""
        try:
            self._ke.update_memory(
                subject=PROPOSAL_SUBJECT, attribute="active",
                value="", source="system",
            )
            logger.info("[PATTERN_STORE] Active proposal cleared.")
        except Exception:
            pass  # No proposal to clear is not an error

    # ------------------------------------------------------------------
    # Genesis-045 Sprint-002: Session records, patterns
    # ------------------------------------------------------------------

    def _session_key(self, cycle: int) -> str:
        return f"cycle-{cycle}"

    def save_session_record(self, record) -> None:
        """Persist a SessionRecord for this analysis cycle."""
        key = self._session_key(record.cycle)
        data = {
            "cycle":               record.cycle,
            "timestamp":           record.timestamp,
            "total_turns":         record.total_turns,
            "deterministic_turns": record.deterministic_turns,
            "ai_called_turns":     record.ai_called_turns,
            "error_turns":         record.error_turns,
            "issues_found":        record.issues_found,
        }
        try:
            existing = self._ke.recall_memory(self.SESSION_SUBJECT, key)
            if existing is None:
                self._ke.store_memory(
                    subject=self.SESSION_SUBJECT, category=CATEGORY,
                    attribute=key, value=json.dumps(data), source="system",
                )
            else:
                self._ke.update_memory(
                    subject=self.SESSION_SUBJECT,
                    attribute=key, value=json.dumps(data), source="system",
                )
            logger.info("[PATTERN_STORE] SessionRecord saved: cycle=%d", record.cycle)
        except Exception as e:
            raise PatternStoreError(f"save_session_record failed: {e}") from e

    def get_session_records(self, n: int = 10) -> list:
        """Return last N SessionRecord objects, oldest first."""
        from core.engineering.intelligence.session_record import SessionRecord
        try:
            all_records = self._ke.list_memories(subject=self.SESSION_SUBJECT)
            parsed = []
            for rec in all_records:
                try:
                    d = json.loads(rec.value)
                    parsed.append(SessionRecord(
                        cycle=d["cycle"], timestamp=d["timestamp"],
                        total_turns=d["total_turns"],
                        deterministic_turns=d["deterministic_turns"],
                        ai_called_turns=d["ai_called_turns"],
                        error_turns=d["error_turns"],
                        issues_found=d.get("issues_found", []),
                    ))
                except Exception:
                    pass
            parsed.sort(key=lambda r: r.cycle)
            return parsed[-n:] if len(parsed) > n else parsed
        except Exception:
            return []

    def get_last_cycle(self) -> int:
        """Return the highest persisted cycle number. 0 if none."""
        records = self.get_session_records(n=1000)
        if not records:
            return 0
        return max(r.cycle for r in records)

    def get_window_occurrences(
        self, signature: str, current_cycle: int, window: int = 20
    ) -> int:
        """Count how many of the last `window` cycles contained this signature."""
        records = self.get_session_records(n=window)
        cutoff  = current_cycle - window
        count   = 0
        for rec in records:
            if rec.cycle <= cutoff:
                continue
            for issue in rec.issues_found:
                if issue.get("signature") == signature:
                    count += 1
                    break
        return count

    def update_pattern(
        self, signature: str, category: str,
        display_title: str, cycle: int, likely_files: list = None,
    ) -> None:
        """Create or update a PatternRecord for this signature."""
        try:
            existing_rec = self._ke.recall_memory(self.PATTERN_SUBJECT, signature)
            if existing_rec is None:
                data = {
                    "signature":           signature,
                    "category":            category,
                    "display_title":       display_title,
                    "first_cycle":         cycle,
                    "last_cycle":          cycle,
                    "total_occurrences":   1,
                    "affected_components": likely_files or [],
                    "external_flag":       False,
                    "proposals":           [],
                }
                self._ke.store_memory(
                    subject=self.PATTERN_SUBJECT, category=CATEGORY,
                    attribute=signature, value=json.dumps(data), source="system",
                )
            else:
                data = json.loads(existing_rec.value)
                data["last_cycle"]        = cycle
                data["total_occurrences"] = data.get("total_occurrences", 0) + 1
                existing_comps = set(data.get("affected_components", []))
                existing_comps.update(likely_files or [])
                data["affected_components"] = sorted(existing_comps)
                self._ke.update_memory(
                    subject=self.PATTERN_SUBJECT,
                    attribute=signature, value=json.dumps(data), source="system",
                )
            logger.info("[PATTERN_STORE] Pattern updated: %s (cycle=%d)", signature, cycle)
        except Exception as e:
            logger.warning("[PATTERN_STORE] update_pattern failed: %s", e)

    def get_active_patterns(self, window: int = 20, min_occurrences: int = 2) -> list:
        """Return PatternRecords with window_occurrences >= min_occurrences."""
        from core.engineering.intelligence.pattern_record import PatternRecord
        current_cycle = self.get_last_cycle()
        try:
            all_recs = self._ke.list_memories(subject=self.PATTERN_SUBJECT)
            result   = []
            for rec in all_recs:
                try:
                    d            = json.loads(rec.value)
                    sig          = d["signature"]
                    window_occ   = self.get_window_occurrences(sig, current_cycle, window)
                    if window_occ >= min_occurrences:
                        result.append(PatternRecord(
                            signature           = sig,
                            category            = d["category"],
                            display_title       = d["display_title"],
                            first_cycle         = d["first_cycle"],
                            last_cycle          = d["last_cycle"],
                            total_occurrences   = d["total_occurrences"],
                            affected_components = d.get("affected_components", []),
                            external_flag       = d.get("external_flag", False),
                            proposals           = d.get("proposals", []),
                        ))
                except Exception:
                    pass
            return result
        except Exception:
            return []

    def get_pattern(self, signature: str):
        """Return the PatternRecord for this signature, or None."""
        from core.engineering.intelligence.pattern_record import PatternRecord
        try:
            rec = self._ke.recall_memory(self.PATTERN_SUBJECT, signature)
            if rec is None:
                return None
            d = json.loads(rec.value)
            return PatternRecord(
                signature           = d["signature"],
                category            = d["category"],
                display_title       = d["display_title"],
                first_cycle         = d["first_cycle"],
                last_cycle          = d["last_cycle"],
                total_occurrences   = d["total_occurrences"],
                affected_components = d.get("affected_components", []),
                external_flag       = d.get("external_flag", False),
                proposals           = d.get("proposals", []),
            )
        except Exception as e:
            logger.warning("[PATTERN_STORE] get_pattern failed for %s: %s", signature, e)
            return None

    def link_proposal_to_pattern(self, signature: str, proposal_id: str) -> None:
        """Record that a proposal was generated from this pattern."""
        try:
            rec = self._ke.recall_memory(self.PATTERN_SUBJECT, signature)
            if rec is None:
                return
            data = json.loads(rec.value)
            proposals = data.get("proposals", [])
            if proposal_id not in proposals:
                proposals.append(proposal_id)
                data["proposals"] = proposals
                self._ke.update_memory(
                    subject=self.PATTERN_SUBJECT,
                    attribute=signature, value=json.dumps(data), source="system",
                )
        except Exception as e:
            logger.warning("[PATTERN_STORE] link_proposal_to_pattern failed: %s", e)
