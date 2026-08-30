"""
Jarvis OS - CapabilityGapObservation + GapObservationStore - Genesis-060 Sprint-001

Immutable, append-only evidence journal of capability-gap observations.

A capability-gap observation is recorded when the pipeline produces all four
signals simultaneously:
    - intent = "unknown"          (IntentStage could not classify the request)
    - knowledge_match = False     (KnowledgePreclassificationStage found nothing)
    - investigation_match = False (InvestigationSelector found no match)
    - boundary_violation = False  (this was NOT a policy block)

Design invariants:
    - CapabilityGapObservation is frozen - immutable after creation.
    - GapObservationStore is append-only - observations are never deleted or rewritten.
    - The store persists to disk across server restarts (Option B).
    - Only raw observations are persisted - never developer-written conclusions.
    - Conclusions are derived at report time from the evidence, not stored.
    - A single observation does not constitute a reportable gap (recurrence threshold).
    - Boundary violations (Type 3 failures) are never stored as gap observations.
    - Knowledge gaps (Type 1: capability path exists, record missing) are not stored here.

This is an evidence journal, not a capability registry.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CapabilityGapObservation - immutable evidence record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapabilityGapObservation:
    """
    Immutable record of one capability-gap event.

    Fields are set at observation time from real pipeline evidence.
    frozen=True: any attempted mutation raises FrozenInstanceError.

    observation_id:       unique identifier for this observation
    observed_at:          ISO 8601 UTC timestamp
    question:             exact question asked by the user
    intent_result:        what IntentStage assigned (always "unknown" for gap)
    knowledge_match:      True if KnowledgePreclassificationStage found a query
    investigation_match:  True if InvestigationSelector found a match
    boundary_violation:   True if MissionCapabilityPolicy blocked the request
    failure_signature:    canonical string describing the failure pattern
    session_id:           the session that produced this observation
    """
    observation_id:      str
    observed_at:         str
    question:            str
    intent_result:       str
    knowledge_match:     bool
    investigation_match: bool
    boundary_violation:  bool
    failure_signature:   str
    session_id:          str = ""

    @classmethod
    def derive_failure_signature(
        cls,
        intent_result: str,
        knowledge_match: bool,
        investigation_match: bool,
        boundary_violation: bool,
    ) -> str:
        """
        Derive the canonical failure signature from pipeline signals.
        This is the basis for recurrence matching - not the question text.
        """
        parts = []
        parts.append(f"intent={intent_result}")
        parts.append(f"knowledge={'yes' if knowledge_match else 'no'}")
        parts.append(f"investigation={'yes' if investigation_match else 'no'}")
        parts.append(f"boundary={'yes' if boundary_violation else 'no'}")
        return "+".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CapabilityGapObservation":
        return cls(**data)

    def is_genuine_capability_gap(self) -> bool:
        """
        True only when this observation represents a Type 2 capability gap:
        - Intent unknown (not classified)
        - No knowledge path matched
        - No investigation matched
        - NOT a boundary violation
        """
        return (
            self.intent_result == "unknown"
            and not self.knowledge_match
            and not self.investigation_match
            and not self.boundary_violation
        )


# ---------------------------------------------------------------------------
# GapObservationStore - append-only evidence journal
# ---------------------------------------------------------------------------

# Canonical failure signature for a genuine capability gap
CAPABILITY_GAP_SIGNATURE = "intent=unknown+knowledge=no+investigation=no+boundary=no"

# Minimum number of matching observations before a gap is reportable
RECURRENCE_THRESHOLD = 2

# Maximum age in days for an observation to count as active evidence
RECENCY_WINDOW_DAYS = 30


@dataclass(frozen=True)
class GapCluster:
    """
    Genesis-066 Sprint-001: A group of observations sharing a normalised question.

    Represents one recurring capability gap family. Evaluated independently
    from other clusters -- one resolved cluster cannot poison another.

    normalised_question: lowercased, stripped, punctuation-removed question
    observations:        all observations in this cluster (sorted by observed_at)
    recurring_question:  the most frequent raw question text in the cluster
    latest_observed_at:  ISO timestamp of the most recent observation
    is_active:           True if size >= threshold and within recency window
    """
    normalised_question: str
    observations:        tuple          # tuple of CapabilityGapObservation
    recurring_question:  str
    latest_observed_at:  str
    is_active:           bool


class GapObservationStore:
    """
    Append-only persistent journal of capability-gap observations.

    Persists to a JSON lines file - one observation per line.
    Append-only: observations are never deleted or overwritten.
    Safe if the file is missing or corrupt - starts fresh.
    Schema-controlled: only CapabilityGapObservation fields are written.
    No developer-written conclusions are stored.

    Conclusions are derived at report time from the stored observations.
    """

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "capability_gap_observations.jsonl"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._observations: List[CapabilityGapObservation] = []
        self._load()

    def _load(self) -> None:
        """Load existing observations from disk. Safe if file is missing or corrupt."""
        if not self._path.exists():
            logger.info("[GapObservationStore] No existing journal at %s ? starting fresh.", self._path)
            return
        loaded = 0
        skipped = 0
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    obs = CapabilityGapObservation.from_dict(data)
                    self._observations.append(obs)
                    loaded += 1
                except Exception as e:
                    logger.warning("[GapObservationStore] Skipping corrupt line: %s", e)
                    skipped += 1
        except Exception as e:
            logger.warning("[GapObservationStore] Could not read journal: %s ? starting fresh.", e)
            self._observations = []
        logger.info(
            "[GapObservationStore] Loaded %d observations (%d skipped).",
            loaded, skipped,
        )

    def record(self, observation: CapabilityGapObservation) -> None:
        """
        Append one observation to the journal.
        Only genuine capability gaps (Type 2) are accepted.
        Boundary violations and knowledge gaps are rejected.
        """
        if not observation.is_genuine_capability_gap():
            logger.info(
                "[GapObservationStore] Observation %s is not a genuine capability gap "
                "(signature=%s) ? not recorded.",
                observation.observation_id,
                observation.failure_signature,
            )
            return

        self._observations.append(observation)
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(observation.to_dict()) + "\n")
            logger.info(
                "[GapObservationStore] Recorded observation %s (total=%d).",
                observation.observation_id,
                len(self._observations),
            )
        except Exception as e:
            logger.warning("[GapObservationStore] Could not persist observation: %s", e)

    @staticmethod
    def _normalise_question(question: str) -> str:
        """
        Normalise a question for clustering.
        Lowercased, stripped, punctuation removed, whitespace collapsed.
        Deterministic and auditable.
        """
        import re as _re
        q = question.lower().strip()
        q = _re.sub(r"[^a-z0-9\s]", "", q)
        q = _re.sub(r"\s+", " ", q).strip()
        return q

    def active_clusters(
        self,
        inv_registry=None,
        min_observations: int = RECURRENCE_THRESHOLD,
        recency_days: int = RECENCY_WINDOW_DAYS,
    ) -> List["GapCluster"]:
        """
        Genesis-066 Sprint-001: Group genuine capability gaps into clusters.

        Each cluster groups observations by normalised question text.
        A cluster is ACTIVE if:
          1. It has >= min_observations observations
          2. Its most recent observation is within recency_days
          3. If inv_registry is provided: the cluster's recurring question
             scores 0 (ISOLATED) against all registered descriptors

        Clusters are returned sorted by size descending (largest first).
        Each cluster is evaluated independently -- one non-isolated cluster
        does not affect eligibility of other clusters.

        inv_registry: optional InvestigationRegistry for isolation check.
                      If None, isolation is not checked.
        """
        from datetime import datetime, timezone, timedelta
        from collections import Counter

        cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)

        # Group genuine gaps by normalised question
        groups: dict = {}
        for obs in self._observations:
            if not obs.is_genuine_capability_gap():
                continue
            key = self._normalise_question(obs.question)
            if key not in groups:
                groups[key] = []
            groups[key].append(obs)

        clusters: List[GapCluster] = []
        for norm_q, obs_list in groups.items():
            obs_list_sorted = sorted(obs_list, key=lambda o: o.observed_at)
            latest_at = obs_list_sorted[-1].observed_at

            # Recency check
            try:
                latest_dt = datetime.fromisoformat(latest_at)
                if latest_dt.tzinfo is None:
                    latest_dt = latest_dt.replace(tzinfo=timezone.utc)
                recent_enough = latest_dt >= cutoff
            except Exception:
                recent_enough = True  # if parse fails, don't exclude

            # Size check
            large_enough = len(obs_list) >= min_observations

            is_active = large_enough and recent_enough

            # Isolation check (only if registry provided and cluster passes other checks)
            if is_active and inv_registry is not None:
                try:
                    from core.knowledge.proximity import CapabilityProximityAnalyser
                    analyser = CapabilityProximityAnalyser()
                    # Use the most frequent raw question as representative
                    counts = Counter(o.question for o in obs_list)
                    rep_question = counts.most_common(1)[0][0]
                    rep_id = obs_list_sorted[-1].observation_id
                    result = analyser.analyse(rep_question, rep_id, inv_registry)
                    if result.closest_score >= 2:  # suppress only on strong match (>= 2 keywords)
                        is_active = False   # cluster is covered by an existing descriptor
                except Exception:
                    pass   # if proximity check fails, keep cluster active (conservative)

            counts2 = Counter(o.question for o in obs_list)
            recurring = counts2.most_common(1)[0][0]

            clusters.append(GapCluster(
                normalised_question = norm_q,
                observations        = tuple(obs_list_sorted),
                recurring_question  = recurring,
                latest_observed_at  = latest_at,
                is_active           = is_active,
            ))

        # Sort by cluster size descending
        clusters.sort(key=lambda c: len(c.observations), reverse=True)
        return clusters

    def active_eligible_clusters(self, inv_registry=None) -> List["GapCluster"]:
        """Return only clusters that are active (is_active=True)."""
        return [c for c in self.active_clusters(inv_registry=inv_registry) if c.is_active]

    def all_observations(self) -> List[CapabilityGapObservation]:
        """Return all recorded observations. Read-only view."""
        return list(self._observations)

    def observations_by_signature(self, signature: str) -> List[CapabilityGapObservation]:
        """Return all observations matching a failure signature."""
        return [o for o in self._observations if o.failure_signature == signature]

    def capability_gap_count(self) -> int:
        """Return the number of genuine capability-gap observations."""
        return len([o for o in self._observations if o.is_genuine_capability_gap()])

    def is_reportable_gap(self, signature: str) -> bool:
        """
        True if the recurrence threshold has been met for this signature.
        A single observation is noted but not yet a reportable gap.
        """
        return len(self.observations_by_signature(signature)) >= RECURRENCE_THRESHOLD

    def recent_capability_gaps(self, n: int = 5) -> List[CapabilityGapObservation]:
        """Return the N most recent genuine capability-gap observations."""
        gaps = [o for o in self._observations if o.is_genuine_capability_gap()]
        return gaps[-n:]
