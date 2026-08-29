"""Jarvis OS - SprintStateStore + SprintStateMachine - Genesis-064 Sprint-003a

Persistent sprint approval state machine.

Design invariants:
    - SprintState is an explicit enum. No implicit states.
    - All transitions are declared. No state is reachable except through
      the declared transition table.
    - State is persisted to disk before any transition is confirmed.
    - Server restart never advances state. The persisted state is the
      authoritative state. If execution was in progress, the restart
      produces INTERRUPTED_BEFORE_COMPLETION -- never EXECUTING or beyond.
    - Only explicit Chief actions may advance from PROPOSED to APPROVED
      and from APPROVED to EXECUTING. Never automatic.
    - COMPLETED, REJECTED, and FAILED are terminal. No transitions out.
    - Every transition is logged with timestamp and reason.
    - The audit trail is append-only. No entry is ever deleted.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SprintState(Enum):
    """Explicit sprint approval states. No implicit states exist."""
    PROPOSED                  = "proposed"
    APPROVED                  = "approved"
    EXECUTING                 = "executing"
    VALIDATING                = "validating"
    AWAITING_RESULT_REVIEW    = "awaiting_result_review"
    COMPLETED                 = "completed"
    REJECTED                  = "rejected"
    FAILED                    = "failed"
    INTERRUPTED               = "interrupted"


# ---------------------------------------------------------------------------
# Declared transition table -- the ONLY valid transitions
# ---------------------------------------------------------------------------

_TRANSITIONS: Dict[SprintState, Tuple[SprintState, ...]] = {
    SprintState.PROPOSED:               (SprintState.APPROVED, SprintState.REJECTED),
    SprintState.APPROVED:               (SprintState.EXECUTING, SprintState.REJECTED),
    SprintState.EXECUTING:              (SprintState.VALIDATING, SprintState.FAILED, SprintState.INTERRUPTED),
    SprintState.VALIDATING:             (SprintState.AWAITING_RESULT_REVIEW, SprintState.FAILED, SprintState.INTERRUPTED),
    SprintState.AWAITING_RESULT_REVIEW: (SprintState.COMPLETED, SprintState.REJECTED),
    SprintState.COMPLETED:              (),
    SprintState.REJECTED:               (),
    SprintState.FAILED:                 (),
    SprintState.INTERRUPTED:            (),
}


# ---------------------------------------------------------------------------
# States that require explicit Chief action to advance
# ---------------------------------------------------------------------------

_CHIEF_REQUIRED: Tuple[SprintState, ...] = (
    SprintState.PROPOSED,             # Layer 1: Chief approves plan
    SprintState.APPROVED,             # Layer 2: Chief authorises execution
    SprintState.AWAITING_RESULT_REVIEW, # Layer 3: Chief reviews result
)


@dataclass
class SprintTransitionRecord:
    """One recorded state transition in the audit trail."""
    from_state:  str
    to_state:    str
    timestamp:   str
    reason:      str
    chief_action: bool  # True when this transition required Chief action

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SprintStateRecord:
    """Persistent state record for one sprint proposal."""
    proposal_id:   str
    current_state: str
    created_at:    str
    updated_at:    str
    transitions:   List[dict] = field(default_factory=list)
    execution_trace: List[dict] = field(default_factory=list)
    validation_result: Optional[dict] = None
    result_summary:    Optional[str]  = None
    stored_proposal:   Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "proposal_id":      self.proposal_id,
            "current_state":    self.current_state,
            "created_at":       self.created_at,
            "updated_at":       self.updated_at,
            "transitions":      self.transitions,
            "execution_trace":  self.execution_trace,
            "validation_result": self.validation_result,
            "result_summary":    self.result_summary,
            "stored_proposal":   self.stored_proposal,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SprintStateRecord":
        return cls(
            proposal_id      = d["proposal_id"],
            current_state    = d["current_state"],
            created_at       = d["created_at"],
            updated_at       = d["updated_at"],
            transitions      = d.get("transitions", []),
            execution_trace  = d.get("execution_trace", []),
            validation_result= d.get("validation_result"),
            result_summary   = d.get("result_summary"),
            stored_proposal  = d.get("stored_proposal"),
        )

    @property
    def state(self) -> SprintState:
        return SprintState(self.current_state)

    @property
    def is_terminal(self) -> bool:
        return self.state in (SprintState.COMPLETED, SprintState.REJECTED,
                              SprintState.FAILED, SprintState.INTERRUPTED)

    @property
    def requires_chief_action(self) -> bool:
        return self.state in _CHIEF_REQUIRED


# ---------------------------------------------------------------------------
# TransitionResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransitionResult:
    success:    bool
    from_state: str
    to_state:   str
    reason:     str
    error:      str = ""


# ---------------------------------------------------------------------------
# SprintStateMachine
# ---------------------------------------------------------------------------

class SprintStateMachine:
    """
    Validates and applies state transitions.

    Never persists state itself -- SprintStateStore handles persistence.
    Never advances state automatically -- all transitions are explicit.
    Never allows a transition not in _TRANSITIONS.
    """

    def can_transition(self, record: SprintStateRecord, to_state: SprintState) -> bool:
        current = record.state
        return to_state in _TRANSITIONS.get(current, ())

    def transition(
        self,
        record:    SprintStateRecord,
        to_state:  SprintState,
        reason:    str,
        chief_action: bool = False,
    ) -> TransitionResult:
        """
        Attempt a state transition.

        Returns TransitionResult(success=True) if transition is valid.
        Returns TransitionResult(success=False) if transition is invalid.
        Mutates record.current_state and appends to record.transitions
        ONLY if the transition is valid.

        Chief-required states enforce chief_action=True.
        """
        current = record.state

        if not self.can_transition(record, to_state):
            return TransitionResult(
                success=False,
                from_state=current.value,
                to_state=to_state.value,
                reason=reason,
                error=f"Invalid transition {current.value!r} -> {to_state.value!r}. "
                      f"Allowed from {current.value!r}: "
                      f"{[s.value for s in _TRANSITIONS.get(current, ())]}")

        # Enforce Chief action for protected states
        if current in _CHIEF_REQUIRED and not chief_action:
            return TransitionResult(
                success=False,
                from_state=current.value,
                to_state=to_state.value,
                reason=reason,
                error=f"Transition from {current.value!r} requires explicit Chief action.")

        now = datetime.now(timezone.utc).isoformat()
        tr  = SprintTransitionRecord(
            from_state   = current.value,
            to_state     = to_state.value,
            timestamp    = now,
            reason       = reason,
            chief_action = chief_action,
        )
        record.current_state = to_state.value
        record.updated_at    = now
        record.transitions.append(tr.to_dict())

        logger.info(
            "[SprintStateMachine] %s -> %s (chief=%s) reason=%r",
            current.value, to_state.value, chief_action, reason,
        )

        return TransitionResult(
            success    = True,
            from_state = current.value,
            to_state   = to_state.value,
            reason     = reason,
        )


# ---------------------------------------------------------------------------
# SprintStateStore
# ---------------------------------------------------------------------------

class SprintStateStore:
    """
    Persistent store for SprintStateRecord objects.

    One JSON file per proposal_id in data/sprint_states/.
    State is written to disk before any transition is confirmed.
    On server restart, the persisted state is the authoritative state.

    Restart safety rule:
        If a sprint was in EXECUTING when the server stopped, it is
        loaded as INTERRUPTED on restart. Execution never resumes
        automatically. Chief must explicitly restart the sprint.
        PROPOSED and APPROVED states survive restart unchanged --
        they are waiting states that do not require recovery.
    """

    # States that become INTERRUPTED on restart (were mid-execution)
    _INTERRUPT_ON_RESTART: Tuple[SprintState, ...] = (
        SprintState.EXECUTING,
        SprintState.VALIDATING,
    )

    def __init__(self, data_dir: Path) -> None:
        self._dir     = data_dir / "sprint_states"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._machine = SprintStateMachine()
        # In-memory cache: tracks records loaded in this process session.
        # Restart safety (EXECUTING->INTERRUPTED) only applies on first load
        # from disk, not on subsequent same-session loads.
        self._session_cache: dict = {}

    def create(self, proposal_id: str) -> SprintStateRecord:
        """Create a new SprintStateRecord in PROPOSED state."""
        now    = datetime.now(timezone.utc).isoformat()
        record = SprintStateRecord(
            proposal_id   = proposal_id,
            current_state = SprintState.PROPOSED.value,
            created_at    = now,
            updated_at    = now,
        )
        self._persist(record)
        self._session_cache[proposal_id] = record
        logger.info("[SprintStateStore] Created %s in PROPOSED.", proposal_id)
        return record

    def load(self, proposal_id: str) -> Optional[SprintStateRecord]:
        """
        Load a SprintStateRecord from disk.
        Applies restart recovery: EXECUTING/VALIDATING -> INTERRUPTED.
        Restart safety only applies on first load (not cached in this session).
        """
        # Return cached record if already loaded in this session
        if proposal_id in self._session_cache:
            return self._session_cache[proposal_id]

        path = self._path_for(proposal_id)
        if not path.exists():
            return None
        try:
            data   = json.loads(path.read_text(encoding="utf-8"))
            record = SprintStateRecord.from_dict(data)

            # Restart safety: interrupt mid-execution states (first load only)
            if record.state in self._INTERRUPT_ON_RESTART:
                logger.warning(
                    "[SprintStateStore] %s was %s on restart -- marking INTERRUPTED.",
                    proposal_id, record.current_state,
                )
                result = self._machine.transition(
                    record    = record,
                    to_state  = SprintState.INTERRUPTED,
                    reason    = "Server restarted during execution -- automatic recovery prevention.",
                    chief_action = False,
                )
                if result.success:
                    self._persist(record)

            self._session_cache[proposal_id] = record
            return record
        except Exception as e:
            logger.warning("[SprintStateStore] Could not load %s: %s", proposal_id, e)
            return None

    def transition(
        self,
        proposal_id:  str,
        to_state:     SprintState,
        reason:       str,
        chief_action: bool = False,
    ) -> TransitionResult:
        """
        Attempt a state transition and persist the result.

        State is written to disk before returning success.
        If the persist fails, the transition is reported as failed.
        """
        record = self.load(proposal_id)
        if record is None:
            return TransitionResult(
                success=False, from_state="unknown", to_state=to_state.value,
                reason=reason, error=f"No record found for {proposal_id!r}")

        result = self._machine.transition(record, to_state, reason, chief_action)
        if not result.success:
            return result

        try:
            self._persist(record)
        except Exception as e:
            return TransitionResult(
                success=False, from_state=result.from_state, to_state=to_state.value,
                reason=reason, error=f"Persist failed: {e}")

        return result

    def all_active(self) -> List[SprintStateRecord]:
        """Return all non-terminal sprint state records."""
        result = []
        for p in self._dir.glob("*.json"):
            try:
                # Read from disk directly (not cache) to get current file state
                data   = json.loads(p.read_text(encoding="utf-8"))
                record = SprintStateRecord.from_dict(data)
                if not record.is_terminal:
                    result.append(record)
            except Exception:
                pass
        return result

    def all_records(self) -> List[SprintStateRecord]:
        """Return all sprint state records including terminal ones."""
        result = []
        for path in self._dir.glob("*.json"):
            try:
                data   = json.loads(path.read_text(encoding="utf-8"))
                record = SprintStateRecord.from_dict(data)
                result.append(record)
            except Exception:
                pass
        return result

    def _persist(self, record: SprintStateRecord) -> None:
        """Write record to disk. Raises on failure."""
        path = self._path_for(record.proposal_id)
        path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")

    def _path_for(self, proposal_id: str) -> Path:
        safe = "".join(c for c in proposal_id if c.isalnum() or c in "-_")
        return self._dir / f"{safe}.json"