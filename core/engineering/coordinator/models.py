"""
Genesis-018 Sprint 002 — Engineering Coordinator Models
Immutable data models for the Engineering Coordinator pipeline.

Sprint 001: EngineeringStatus, EngineeringRequest, EngineeringResult
Sprint 002: EngineeringStage, CoordinatorEventLog, EngineeringSession
            + EngineeringResult expanded (backwards compatible)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# EngineeringStatus  (Sprint 001 — unchanged)
# ---------------------------------------------------------------------------

class EngineeringStatus(Enum):
    """Lifecycle states for an engineering request moving through the coordinator."""

    PENDING    = "PENDING"
    PLANNING   = "PLANNING"
    VALIDATING = "VALIDATING"
    DEBUGGING  = "DEBUGGING"
    COMPLETE   = "COMPLETE"
    FAILED     = "FAILED"

    def is_terminal(self) -> bool:
        """Return True if this status represents a final state."""
        return self in (EngineeringStatus.COMPLETE, EngineeringStatus.FAILED)

    def is_active(self) -> bool:
        """Return True if this status represents work in progress."""
        return self in (
            EngineeringStatus.PENDING,
            EngineeringStatus.PLANNING,
            EngineeringStatus.VALIDATING,
            EngineeringStatus.DEBUGGING,
        )


# ---------------------------------------------------------------------------
# EngineeringStage  (Sprint 002 — new)
# ---------------------------------------------------------------------------

class EngineeringStage(Enum):
    """
    Fine-grained pipeline stages tracked inside an EngineeringSession.

    Ordered to reflect natural pipeline progression:
        INITIALISING → PLANNING → GUARDRAILS → VALIDATION
            → DEBUGGING → REPAIR_PLANNING → COMPLETE | FAILED
    """

    INITIALISING   = "INITIALISING"
    PLANNING       = "PLANNING"
    GUARDRAILS     = "GUARDRAILS"
    VALIDATION     = "VALIDATION"
    DEBUGGING      = "DEBUGGING"
    REPAIR_PLANNING = "REPAIR_PLANNING"
    COMPLETE       = "COMPLETE"
    FAILED         = "FAILED"

    def is_terminal(self) -> bool:
        """Return True if this stage ends the session."""
        return self in (EngineeringStage.COMPLETE, EngineeringStage.FAILED)

    def is_active(self) -> bool:
        """Return True if this stage represents ongoing work."""
        return not self.is_terminal()

    def is_failure_path(self) -> bool:
        """Return True if this stage only appears on the failure path."""
        return self in (EngineeringStage.DEBUGGING, EngineeringStage.REPAIR_PLANNING)


# ---------------------------------------------------------------------------
# EngineeringRequest  (Sprint 001 — unchanged)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineeringRequest:
    """
    Immutable model representing a single engineering request submitted
    to the EngineeringCoordinator.
    """

    request:  str
    context:  str            = ""
    priority: int            = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, str):
            raise TypeError(
                f"EngineeringRequest.request must be str, "
                f"got {type(self.request).__name__}"
            )
        if not self.request.strip():
            raise ValueError("EngineeringRequest.request must not be blank")
        if not isinstance(self.context, str):
            raise TypeError(
                f"EngineeringRequest.context must be str, "
                f"got {type(self.context).__name__}"
            )
        if not isinstance(self.priority, int):
            raise TypeError(
                f"EngineeringRequest.priority must be int, "
                f"got {type(self.priority).__name__}"
            )
        if not isinstance(self.metadata, dict):
            raise TypeError(
                f"EngineeringRequest.metadata must be dict, "
                f"got {type(self.metadata).__name__}"
            )

    @property
    def has_context(self) -> bool:
        return bool(self.context.strip())

    @property
    def is_high_priority(self) -> bool:
        return self.priority > 0

    def with_metadata(self, **kwargs: Any) -> "EngineeringRequest":
        merged = {**self.metadata, **kwargs}
        return EngineeringRequest(
            request=self.request,
            context=self.context,
            priority=self.priority,
            metadata=merged,
        )

    def __repr__(self) -> str:
        preview = (self.request[:60] + "…") if len(self.request) > 60 else self.request
        return (
            f"EngineeringRequest("
            f"request={preview!r}, "
            f"priority={self.priority}, "
            f"has_context={self.has_context}"
            f")"
        )


# ---------------------------------------------------------------------------
# SessionEvent  (Sprint 002 — new, internal building block)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionEvent:
    """
    A single immutable event recorded in a CoordinatorEventLog.

    Once created, a SessionEvent cannot be modified.
    """

    stage:       EngineeringStage
    description: str
    timestamp_ms: int                    # monotonic milliseconds since epoch
    detail:      str                     = ""
    duration_ms: Optional[int]           = None   # set when stage completes

    def __post_init__(self) -> None:
        if not isinstance(self.stage, EngineeringStage):
            raise TypeError(
                f"SessionEvent.stage must be EngineeringStage, "
                f"got {type(self.stage).__name__}"
            )
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("SessionEvent.description must be a non-blank string")
        if not isinstance(self.timestamp_ms, int):
            raise TypeError(
                f"SessionEvent.timestamp_ms must be int, "
                f"got {type(self.timestamp_ms).__name__}"
            )

    @property
    def has_duration(self) -> bool:
        return self.duration_ms is not None

    def __repr__(self) -> str:
        dur = f", {self.duration_ms}ms" if self.has_duration else ""
        return (
            f"SessionEvent("
            f"stage={self.stage.value}, "
            f"description={self.description!r}"
            f"{dur}"
            f")"
        )


# ---------------------------------------------------------------------------
# CoordinatorEventLog  (Sprint 002 — new)
# ---------------------------------------------------------------------------

class CoordinatorEventLog:
    """
    Chronological, append-only log of events recorded during an
    EngineeringSession.

    Events are immutable once recorded.
    The log itself accepts new entries during pipeline execution
    but is sealed when the session completes.
    """

    def __init__(self) -> None:
        self._events: List[SessionEvent] = []
        self._sealed: bool = False

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        stage:       EngineeringStage,
        description: str,
        *,
        detail:      str          = "",
        duration_ms: Optional[int] = None,
    ) -> SessionEvent:
        """
        Append a new immutable event to the log.

        Raises RuntimeError if the log has been sealed.
        """
        if self._sealed:
            raise RuntimeError(
                "CoordinatorEventLog is sealed — no further events may be recorded"
            )
        event = SessionEvent(
            stage=stage,
            description=description,
            timestamp_ms=int(time.monotonic() * 1000),
            detail=detail,
            duration_ms=duration_ms,
        )
        self._events.append(event)
        return event

    def seal(self) -> None:
        """Prevent any further events from being recorded."""
        self._sealed = True

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def is_empty(self) -> bool:
        return len(self._events) == 0

    def events(self) -> List[SessionEvent]:
        """Return a snapshot of all recorded events (read-only copy)."""
        return list(self._events)

    def events_for_stage(self, stage: EngineeringStage) -> List[SessionEvent]:
        """Return all events recorded for a specific stage."""
        return [e for e in self._events if e.stage == stage]

    def stages_visited(self) -> List[EngineeringStage]:
        """Return ordered list of unique stages that appear in the log."""
        seen: List[EngineeringStage] = []
        for e in self._events:
            if e.stage not in seen:
                seen.append(e.stage)
        return seen

    def total_duration_ms(self) -> Optional[int]:
        """
        Return the wall-clock span from first to last event in milliseconds.
        Returns None if fewer than two events exist.
        """
        if len(self._events) < 2:
            return None
        return self._events[-1].timestamp_ms - self._events[0].timestamp_ms

    def timeline(self) -> List[str]:
        """
        Return a human-readable ordered list of event descriptions.
        Suitable for display or logging.
        """
        lines = []
        for e in self._events:
            dur_part = f" [{e.duration_ms}ms]" if e.has_duration else ""
            detail_part = f" — {e.detail}" if e.detail else ""
            lines.append(f"[{e.stage.value}]{dur_part} {e.description}{detail_part}")
        return lines

    def __repr__(self) -> str:
        return (
            f"CoordinatorEventLog("
            f"events={self.event_count}, "
            f"sealed={self._sealed}"
            f")"
        )


# ---------------------------------------------------------------------------
# EngineeringSession  (Sprint 002 — new)
# ---------------------------------------------------------------------------

@dataclass
class EngineeringSession:
    """
    Mutable lifecycle record for one engineering request, from receipt
    through final result.

    The session is the single source of truth for what happened, when
    it happened, how long it took, and what the outcome was.

    A completed session is fully replayable from the session object alone.
    """

    session_id:    str
    request:       EngineeringRequest
    status:        EngineeringStatus
    started_at:    int                        # monotonic ms
    completed_at:  Optional[int]              = None
    events:        CoordinatorEventLog        = field(default_factory=CoordinatorEventLog)
    current_stage: EngineeringStage           = EngineeringStage.INITIALISING
    result:        Optional["EngineeringResult"] = None

    @classmethod
    def create(cls, request: EngineeringRequest) -> "EngineeringSession":
        """Factory: create a new session for the given request."""
        return cls(
            session_id=str(uuid.uuid4()),
            request=request,
            status=EngineeringStatus.PENDING,
            started_at=int(time.monotonic() * 1000),
        )

    # ------------------------------------------------------------------
    # Stage transitions
    # ------------------------------------------------------------------

    def advance_to(self, stage: EngineeringStage, description: str, **log_kwargs) -> None:
        """Advance the current stage and record the transition."""
        self.current_stage = stage
        self.events.record(stage, description, **log_kwargs)

    def complete(self, result: "EngineeringResult") -> None:
        """Mark the session as complete and seal the event log."""
        self.result       = result
        self.completed_at = int(time.monotonic() * 1000)
        self.status       = result.status
        self.events.seal()

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    @property
    def duration_ms(self) -> Optional[int]:
        if self.completed_at is None:
            return None
        return self.completed_at - self.started_at

    @property
    def stages_visited(self) -> List[EngineeringStage]:
        return self.events.stages_visited()

    @property
    def stage_count(self) -> int:
        return len(self.stages_visited)

    def stage_durations(self) -> Dict[str, Optional[int]]:
        """
        Return a mapping of stage name → total recorded duration (ms).
        Stages with no duration-tagged events map to None.
        """
        durations: Dict[str, Optional[int]] = {}
        for stage in self.stages_visited:
            stage_events = self.events.events_for_stage(stage)
            timed = [e.duration_ms for e in stage_events if e.has_duration]
            durations[stage.value] = sum(timed) if timed else None
        return durations

    def replay(self) -> List[str]:
        """
        Return a complete human-readable replay of the session.

        Given only this session object, answers:
          - what happened
          - when it happened (relative ms from session start)
          - how long each stage took
          - why it stopped
          - what the outcome was
        """
        lines = [
            f"Session: {self.session_id}",
            f"Request: {self.request.request!r}",
            f"Priority: {self.request.priority}",
            f"Started:  t+0ms",
        ]

        origin = self.started_at
        for event in self.events.events():
            elapsed = event.timestamp_ms - origin
            dur_part    = f" [{event.duration_ms}ms]" if event.has_duration else ""
            detail_part = f" — {event.detail}" if event.detail else ""
            lines.append(
                f"  t+{elapsed}ms  [{event.stage.value}]{dur_part} "
                f"{event.description}{detail_part}"
            )

        if self.is_complete:
            lines.append(f"Completed: t+{self.duration_ms}ms")
            lines.append(f"Outcome:   {self.status.value}")
        else:
            lines.append(f"Status:    {self.status.value} (in progress)")

        return lines

    def __repr__(self) -> str:
        return (
            f"EngineeringSession("
            f"id={self.session_id[:8]}…, "
            f"status={self.status.value}, "
            f"stage={self.current_stage.value}, "
            f"events={self.events.event_count}"
            f")"
        )


# ---------------------------------------------------------------------------
# EngineeringResult  (Sprint 002 — expanded, backwards compatible)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineeringResult:
    """
    Immutable model representing the unified outcome of an engineering request.

    Sprint 001 fields: status, plan, validation, debug_report, repair_plan,
                       completed, duration_ms, errors, warnings
    Sprint 002 fields: session, timeline, stage_durations  (all optional,
                       default None/empty — zero breaking changes)
    """

    # ── Sprint 001 fields ──────────────────────────────────────────────
    status:       EngineeringStatus
    plan:         Optional[str]              = None
    validation:   Optional[str]             = None
    debug_report: Optional[str]             = None
    repair_plan:  Optional[str]             = None
    completed:    bool                      = False
    duration_ms:  Optional[int]             = None
    errors:       List[str]                 = field(default_factory=list)
    warnings:     List[str]                 = field(default_factory=list)

    # ── Sprint 002 fields ──────────────────────────────────────────────
    session:         Optional[EngineeringSession]  = None
    timeline:        List[str]                     = field(default_factory=list)
    stage_durations: Dict[str, Optional[int]]      = field(default_factory=dict)

    # ── Sprint 003 fields ──────────────────────────────────────────────
    queue_position:  Optional[int]                 = None   # 1-based position when enqueued
    queue_snapshot:  Optional["QueueSnapshot"]     = None   # snapshot at time of completion

    # ── Sprint 004 fields ──────────────────────────────────────────────
    dispatch_record:      Optional["DispatchRecord"] = None  # full dispatch lifecycle
    dispatch_duration_ms: Optional[int]              = None  # dispatch-to-complete duration

    def __post_init__(self) -> None:
        if not isinstance(self.status, EngineeringStatus):
            raise TypeError(
                f"EngineeringResult.status must be EngineeringStatus, "
                f"got {type(self.status).__name__}"
            )
        if self.duration_ms is not None and not isinstance(self.duration_ms, int):
            raise TypeError(
                f"EngineeringResult.duration_ms must be int or None, "
                f"got {type(self.duration_ms).__name__}"
            )
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError(
                f"EngineeringResult.duration_ms must be >= 0, "
                f"got {self.duration_ms}"
            )

    # ── Sprint 001 properties (unchanged) ─────────────────────────────

    @property
    def succeeded(self) -> bool:
        return self.status == EngineeringStatus.COMPLETE and self.completed

    @property
    def failed(self) -> bool:
        return self.status == EngineeringStatus.FAILED

    @property
    def required_debugging(self) -> bool:
        return self.debug_report is not None

    @property
    def has_repair_plan(self) -> bool:
        return self.repair_plan is not None

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    # ── Sprint 002 properties ──────────────────────────────────────────

    @property
    def has_session(self) -> bool:
        """Return True if a full EngineeringSession is attached."""
        return self.session is not None

    @property
    def has_timeline(self) -> bool:
        """Return True if a non-empty timeline was recorded."""
        return bool(self.timeline)

    @property
    def has_stage_durations(self) -> bool:
        return bool(self.stage_durations)

    @property
    def session_id(self) -> Optional[str]:
        """Convenience accessor for the attached session's ID."""
        return self.session.session_id if self.session is not None else None

    def stages_visited(self) -> List[str]:
        """Return ordered stage names from the attached session, or empty list."""
        if self.session is None:
            return []
        return [s.value for s in self.session.stages_visited]

    # ── Sprint 003 properties ──────────────────────────────────────────

    @property
    def has_queue_position(self) -> bool:
        return self.queue_position is not None

    @property
    def has_queue_snapshot(self) -> bool:
        return self.queue_snapshot is not None

    # ── Sprint 004 properties ──────────────────────────────────────────

    @property
    def has_dispatch_record(self) -> bool:
        return self.dispatch_record is not None

    @property
    def dispatch_id(self) -> Optional[str]:
        return self.dispatch_record.dispatch_id if self.dispatch_record is not None else None

    # ── Summary ───────────────────────────────────────────────────────

    def summary(self) -> str:
        parts = [f"status={self.status.value}"]
        if self.duration_ms is not None:
            parts.append(f"duration={self.duration_ms}ms")
        if self.has_errors:
            parts.append(f"errors={self.error_count}")
        if self.has_warnings:
            parts.append(f"warnings={self.warning_count}")
        if self.required_debugging:
            parts.append("debugged=True")
        if self.has_repair_plan:
            parts.append("repaired=True")
        if self.has_session:
            parts.append(f"session={self.session_id[:8]}…")
        if self.has_queue_position:
            parts.append(f"queue_pos={self.queue_position}")
        if self.has_dispatch_record:
            parts.append(f"dispatch={self.dispatch_id[:8]}…")
        return f"EngineeringResult({', '.join(parts)})"

    def __repr__(self) -> str:
        return self.summary()


# ---------------------------------------------------------------------------
# QueueStatus  (Sprint 003 — new)
# ---------------------------------------------------------------------------

class QueueStatus(Enum):
    """
    Represents the operational state of the EngineeringQueue.

    EMPTY      — no requests present, nothing active
    WAITING    — one or more requests pending, nothing currently active
    PROCESSING — one request is active; others may be waiting
    COMPLETE   — all submitted requests have been processed
    """

    EMPTY      = "EMPTY"
    WAITING    = "WAITING"
    PROCESSING = "PROCESSING"
    COMPLETE   = "COMPLETE"

    def is_idle(self) -> bool:
        """Return True if the queue is not actively processing."""
        return self in (QueueStatus.EMPTY, QueueStatus.COMPLETE)

    def is_busy(self) -> bool:
        """Return True if the queue is actively processing or has work pending."""
        return self in (QueueStatus.WAITING, QueueStatus.PROCESSING)

    def has_pending(self) -> bool:
        """Return True if there are requests waiting to be processed."""
        return self in (QueueStatus.WAITING, QueueStatus.PROCESSING)


# ---------------------------------------------------------------------------
# QueueSnapshot  (Sprint 003 — new)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QueueSnapshot:
    """
    Immutable point-in-time representation of the EngineeringQueue state.

    Snapshots are safe to pass around, store, and compare without fear
    of the underlying queue changing underneath them.
    """

    queue_size:          int
    status:              QueueStatus
    timestamp_ms:        int
    active_session_id:   Optional[str]            = None
    pending_session_ids: Tuple[str, ...]           = field(default_factory=tuple)
    completed_count:     int                       = 0
    total_submitted:     int                       = 0

    def __post_init__(self) -> None:
        if not isinstance(self.queue_size, int) or self.queue_size < 0:
            raise ValueError(
                f"QueueSnapshot.queue_size must be a non-negative int, "
                f"got {self.queue_size!r}"
            )
        if not isinstance(self.status, QueueStatus):
            raise TypeError(
                f"QueueSnapshot.status must be QueueStatus, "
                f"got {type(self.status).__name__}"
            )
        if not isinstance(self.timestamp_ms, int):
            raise TypeError(
                f"QueueSnapshot.timestamp_ms must be int, "
                f"got {type(self.timestamp_ms).__name__}"
            )
        if not isinstance(self.completed_count, int) or self.completed_count < 0:
            raise ValueError(
                f"QueueSnapshot.completed_count must be a non-negative int, "
                f"got {self.completed_count!r}"
            )
        if not isinstance(self.total_submitted, int) or self.total_submitted < 0:
            raise ValueError(
                f"QueueSnapshot.total_submitted must be a non-negative int, "
                f"got {self.total_submitted!r}"
            )

    @property
    def is_empty(self) -> bool:
        return self.queue_size == 0

    @property
    def has_active(self) -> bool:
        return self.active_session_id is not None

    @property
    def pending_count(self) -> int:
        return len(self.pending_session_ids)

    @property
    def remaining(self) -> int:
        """Requests not yet completed (active + pending)."""
        active = 1 if self.has_active else 0
        return active + self.pending_count

    def __repr__(self) -> str:
        return (
            f"QueueSnapshot("
            f"status={self.status.value}, "
            f"size={self.queue_size}, "
            f"active={self.active_session_id is not None}, "
            f"pending={self.pending_count}, "
            f"completed={self.completed_count}"
            f")"
        )


# ---------------------------------------------------------------------------
# DispatchStatus  (Sprint 004 — new)
# ---------------------------------------------------------------------------

class DispatchStatus(Enum):
    """
    Lifecycle state of a single dispatch operation.

    IDLE        — dispatcher has no pending work
    READY       — a session is selected and ready to be dispatched
    DISPATCHING — a session is currently being executed
    COMPLETE    — the dispatched session has finished
    """

    IDLE        = "IDLE"
    READY       = "READY"
    DISPATCHING = "DISPATCHING"
    COMPLETE    = "COMPLETE"

    def is_terminal(self) -> bool:
        return self == DispatchStatus.COMPLETE

    def is_active(self) -> bool:
        return self in (DispatchStatus.READY, DispatchStatus.DISPATCHING)

    def is_idle(self) -> bool:
        return self == DispatchStatus.IDLE


# ---------------------------------------------------------------------------
# DispatchRecord  (Sprint 004 — new)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DispatchRecord:
    """
    Immutable record of one dispatch operation — from selection through completion.

    Every dispatch, successful or not, becomes part of the permanent
    engineering history.
    """

    dispatch_id:   str
    session_id:    str
    queued_at:     int                    # monotonic ms — when session entered the queue
    dispatched_at: int                    # monotonic ms — when dispatcher selected it
    status:        DispatchStatus
    completed_at:  Optional[int]  = None  # monotonic ms — when session finished
    duration_ms:   Optional[int]  = None  # total dispatch lifecycle duration

    def __post_init__(self) -> None:
        if not isinstance(self.dispatch_id, str) or not self.dispatch_id.strip():
            raise ValueError("DispatchRecord.dispatch_id must be a non-blank string")
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("DispatchRecord.session_id must be a non-blank string")
        if not isinstance(self.queued_at, int):
            raise TypeError(
                f"DispatchRecord.queued_at must be int, "
                f"got {type(self.queued_at).__name__}"
            )
        if not isinstance(self.dispatched_at, int):
            raise TypeError(
                f"DispatchRecord.dispatched_at must be int, "
                f"got {type(self.dispatched_at).__name__}"
            )
        if not isinstance(self.status, DispatchStatus):
            raise TypeError(
                f"DispatchRecord.status must be DispatchStatus, "
                f"got {type(self.status).__name__}"
            )
        if self.duration_ms is not None:
            if not isinstance(self.duration_ms, int):
                raise TypeError(
                    f"DispatchRecord.duration_ms must be int or None, "
                    f"got {type(self.duration_ms).__name__}"
                )
            if self.duration_ms < 0:
                raise ValueError(
                    f"DispatchRecord.duration_ms must be >= 0, "
                    f"got {self.duration_ms}"
                )

    @property
    def wait_ms(self) -> int:
        """Time between enqueue and dispatch (scheduling latency)."""
        return self.dispatched_at - self.queued_at

    @property
    def is_complete(self) -> bool:
        return self.status == DispatchStatus.COMPLETE

    @property
    def has_duration(self) -> bool:
        return self.duration_ms is not None

    def complete(self, completed_at: int) -> "DispatchRecord":
        """
        Return a new DispatchRecord marked as COMPLETE.
        Original is unchanged (immutable).
        """
        return DispatchRecord(
            dispatch_id=self.dispatch_id,
            session_id=self.session_id,
            queued_at=self.queued_at,
            dispatched_at=self.dispatched_at,
            status=DispatchStatus.COMPLETE,
            completed_at=completed_at,
            duration_ms=completed_at - self.queued_at,
        )

    def __repr__(self) -> str:
        dur = f", {self.duration_ms}ms" if self.has_duration else ""
        return (
            f"DispatchRecord("
            f"id={self.dispatch_id[:8]}…, "
            f"session={self.session_id[:8]}…, "
            f"status={self.status.value}"
            f"{dur}"
            f")"
        )