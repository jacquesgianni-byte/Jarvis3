"""
Jarvis Decision Engine (Genesis-020 Sprint-004)

Records, manages, and explains architectural decisions.

Architecture position:
    Knowledge  → "What do I know?"      (KnowledgeEngine — persisted)
    Context    → "What now?"            (SessionContext — RAM)
    Timeline   → "What happened?"       (ConversationTimeline — append-only)
    Decisions  → "Why did we do that?"  (DecisionEngine — projects from Timeline)

Design:
    The Decision Engine is a Projection over the Timeline.
    It has NO independent storage — all decisions are derived
    from Timeline events via replay().

    DecisionEngine implements Projection so it can be rebuilt
    entirely from the Timeline at any point.

Constitutional constraints:
    - No AI calls. All decision recording and querying is deterministic.
    - No independent storage. Timeline is the source of truth.
    - Immutable decisions. Status changes produce new instances.
    - Errors caught and logged — never crash the pipeline.

Integration:
    Agent creates one DecisionEngine instance.
    ConversationObserver publishes DECISION_* events to Timeline.
    Agent calls decision_engine.replay(timeline) on startup.
    Users record decisions via: "We decided to use Event Sourcing because..."
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Optional

from core.conversation.architectural_decision import (
    ArchitecturalDecision, DecisionStatus
)
from core.conversation.projection import Projection
from core.conversation.timeline_event import EventType, TimelineEvent

logger = logging.getLogger(__name__)


class DecisionEngine(Projection):
    """
    Records and manages architectural decisions.

    Implements Projection so it can be rebuilt from Timeline replay.
    In-memory only — no persistence layer.

    Public API:
        record(decision)              — add a new decision
        supersede(old_id, new)        — replace a decision
        reject(decision_id, reason)   — mark a decision rejected
        get(decision_id)              — fetch by ID
        all_decisions()               — all decisions ordered by turn
        active()                      — only ACCEPTED + EXPERIMENTAL
        superseded()                  — only SUPERSEDED
        rejected()                    — only REJECTED
        by_status(status)             — filter by status
        search(query)                 — full-text search
        explain(decision_id)          — full explanation string
        latest(n)                     — most recent N decisions
        on_date(date_str)             — decisions from YYYY-MM-DD
        summary()                     — inspector-ready dict
    """

    def __init__(self) -> None:
        self._decisions: dict[str, ArchitecturalDecision] = {}
        self._order: list[str] = []   # insertion order of IDs

    # ------------------------------------------------------------------
    # Projection interface — rebuild from Timeline
    # ------------------------------------------------------------------

    def apply(self, event: TimelineEvent) -> None:
        """
        Process a single Timeline event.

        Called by ConversationTimeline.replay(). Reconstructs decision
        state from DECISION_* timeline events.
        """
        try:
            self._apply_event(event)
        except Exception:
            logger.exception("[DECISIONS] Error applying event: %s", event)

    def on_replay_complete(self) -> None:
        logger.info(
            "[DECISIONS] Replay complete — %d decisions loaded.",
            len(self._decisions)
        )

    def _apply_event(self, event: TimelineEvent) -> None:
        """Map a timeline event to a decision state change."""
        if event.event_type == EventType.DECISION_PROPOSED:
            decision = self._event_to_decision(event, DecisionStatus.PROPOSED)
            if decision:
                self._store(decision)

        elif event.event_type == EventType.DECISION_ACCEPTED:
            decision = self._event_to_decision(event, DecisionStatus.ACCEPTED)
            if decision:
                self._store(decision)

        elif event.event_type == EventType.DECISION_SUPERSEDED:
            # payload["superseded_id"] holds the old decision's ID
            old_id = event.payload.get("superseded_id", "")
            if old_id and old_id in self._decisions:
                old = self._decisions[old_id]
                self._decisions[old_id] = old.with_status(DecisionStatus.SUPERSEDED)
            decision = self._event_to_decision(event, DecisionStatus.ACCEPTED)
            if decision:
                self._store(decision)

        elif event.event_type == EventType.DECISION_REJECTED:
            decision = self._event_to_decision(event, DecisionStatus.REJECTED)
            if decision:
                self._store(decision)

        # Legacy DECISION events (from fact extractor) stored as ACCEPTED
        elif event.event_type == EventType.DECISION:
            decision = self._event_to_decision(event, DecisionStatus.ACCEPTED)
            if decision:
                self._store(decision)

    def _event_to_decision(
        self, event: TimelineEvent, status: DecisionStatus
    ) -> Optional[ArchitecturalDecision]:
        """Convert a TimelineEvent into an ArchitecturalDecision."""
        if not event.value or len(event.value.strip()) < 2:
            return None
        payload = event.payload or {}
        return ArchitecturalDecision(
            id=payload.get("decision_id", str(event.turn) + "_" + event.value[:8]),
            title=payload.get("title", event.value),
            decision=payload.get("decision", event.value),
            reason=payload.get("reason", event.notes or ""),
            status=status,
            source_turn=event.turn,
            timestamp=event.timestamp,
            alternatives=tuple(payload.get("alternatives", [])),
            supersedes_id=payload.get("supersedes_id", ""),
            confidence=payload.get("confidence", 1.0),
            tags=tuple(payload.get("tags", [])),
        )

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def record(self, decision: ArchitecturalDecision) -> None:
        """
        Record a new decision.

        Args:
            decision: The ArchitecturalDecision to record.
        """
        try:
            self._store(decision)
            logger.info("[DECISIONS] Recorded: %s", decision.summary())
        except Exception:
            logger.exception("[DECISIONS] Failed to record decision.")

    def supersede(
        self,
        old_id: str,
        new_decision: ArchitecturalDecision,
    ) -> None:
        """
        Replace an existing decision with a new one.

        The old decision is marked SUPERSEDED. The new decision
        is recorded with ACCEPTED status.

        Args:
            old_id:       ID of the decision being replaced.
            new_decision: The replacement ArchitecturalDecision.
        """
        if old_id in self._decisions:
            old = self._decisions[old_id]
            self._decisions[old_id] = old.with_status(DecisionStatus.SUPERSEDED)
            logger.info("[DECISIONS] Superseded: %s", old.title)
        self._store(new_decision)
        logger.info("[DECISIONS] New decision: %s", new_decision.summary())

    def reject(self, decision_id: str, reason: str = "") -> None:
        """
        Mark a decision as rejected.

        Args:
            decision_id: ID of the decision to reject.
            reason:      Optional rejection rationale.
        """
        if decision_id not in self._decisions:
            return
        decision = self._decisions[decision_id]
        updated = ArchitecturalDecision(
            id=decision.id,
            title=decision.title,
            decision=decision.decision,
            reason=reason or decision.reason,
            status=DecisionStatus.REJECTED,
            source_turn=decision.source_turn,
            timestamp=decision.timestamp,
            alternatives=decision.alternatives,
            supersedes_id=decision.supersedes_id,
            confidence=decision.confidence,
            tags=decision.tags,
            version=decision.version,
            payload=decision.payload,
        )
        self._decisions[decision_id] = updated
        logger.info("[DECISIONS] Rejected: %s", decision.title)

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get(self, decision_id: str) -> Optional[ArchitecturalDecision]:
        """Fetch a decision by ID. Returns None if not found."""
        return self._decisions.get(decision_id)

    def all_decisions(self) -> list[ArchitecturalDecision]:
        """All decisions in insertion (turn) order."""
        return [self._decisions[id_] for id_ in self._order
                if id_ in self._decisions]

    def active(self) -> list[ArchitecturalDecision]:
        """Decisions currently in effect (ACCEPTED + EXPERIMENTAL)."""
        return [d for d in self.all_decisions() if d.status.is_active]

    def superseded(self) -> list[ArchitecturalDecision]:
        """Decisions that have been replaced."""
        return [d for d in self.all_decisions()
                if d.status == DecisionStatus.SUPERSEDED]

    def rejected(self) -> list[ArchitecturalDecision]:
        """Decisions that were rejected."""
        return [d for d in self.all_decisions()
                if d.status == DecisionStatus.REJECTED]

    def proposed(self) -> list[ArchitecturalDecision]:
        """Decisions under consideration."""
        return [d for d in self.all_decisions()
                if d.status == DecisionStatus.PROPOSED]

    def by_status(self, status: DecisionStatus) -> list[ArchitecturalDecision]:
        """Filter decisions by status."""
        return [d for d in self.all_decisions() if d.status == status]

    def search(self, query: str) -> list[ArchitecturalDecision]:
        """
        Full-text search across title, decision, reason, and tags.

        Case-insensitive substring match. Returns matches in turn order.
        """
        q = query.lower().strip()
        results = []
        for d in self.all_decisions():
            searchable = " ".join([
                d.title, d.decision, d.reason,
                " ".join(d.tags),
                " ".join(d.alternatives),
            ]).lower()
            if q in searchable:
                results.append(d)
        return results

    def explain(self, decision_id: str) -> str:
        """
        Return a full human-readable explanation of a decision.

        This is the core Sprint-004 capability:
        "Why did we adopt Event Sourcing?" → full rationale.
        """
        decision = self._decisions.get(decision_id)
        if not decision:
            return f"No decision found with ID {decision_id!r}, sir."
        return decision.explain()

    def latest(self, n: int = 5) -> list[ArchitecturalDecision]:
        """Return the most recent N decisions."""
        return self.all_decisions()[-n:]

    def on_date(self, date_str: str) -> list[ArchitecturalDecision]:
        """Return decisions recorded on a given date (YYYY-MM-DD)."""
        return [d for d in self.all_decisions() if d.date_str() == date_str]

    def today(self) -> list[ArchitecturalDecision]:
        """Return decisions recorded today."""
        return self.on_date(datetime.now(UTC).strftime("%Y-%m-%d"))

    def yesterday(self) -> list[ArchitecturalDecision]:
        """Return decisions recorded yesterday."""
        return self.on_date(
            (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        )

    def count(self, status: Optional[DecisionStatus] = None) -> int:
        """Count decisions, optionally filtered by status."""
        if status is None:
            return len(self._decisions)
        return len(self.by_status(status))

    def summary(self) -> dict:
        """Inspector-ready summary dict."""
        latest = self.latest(3)
        return {
            "total":        len(self._decisions),
            "active":       self.count(DecisionStatus.ACCEPTED) +
                            self.count(DecisionStatus.EXPERIMENTAL),
            "superseded":   self.count(DecisionStatus.SUPERSEDED),
            "rejected":     self.count(DecisionStatus.REJECTED),
            "proposed":     self.count(DecisionStatus.PROPOSED),
            "experimental": self.count(DecisionStatus.EXPERIMENTAL),
            "latest":       [d.title for d in latest],
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _store(self, decision: ArchitecturalDecision) -> None:
        """Store a decision, maintaining insertion order."""
        if decision.id not in self._decisions:
            self._order.append(decision.id)
        self._decisions[decision.id] = decision