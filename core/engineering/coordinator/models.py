"""
Genesis-018 Sprint 001 — Engineering Coordinator Models
Immutable data models for the Engineering Coordinator pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# EngineeringStatus
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
# EngineeringRequest
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineeringRequest:
    """
    Immutable model representing a single engineering request submitted
    to the EngineeringCoordinator.

    Callers construct this once and pass it to the coordinator.
    The coordinator must not mutate it.
    """

    request:  str
    context:  str                    = ""
    priority: int                    = 0          # Higher = more urgent
    metadata: Dict[str, Any]         = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate types on construction so bad inputs fail fast.
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
        """Return True if a non-empty context was provided."""
        return bool(self.context.strip())

    @property
    def is_high_priority(self) -> bool:
        """Return True if priority is above the default baseline."""
        return self.priority > 0

    def with_metadata(self, **kwargs: Any) -> "EngineeringRequest":
        """
        Return a new EngineeringRequest with additional metadata merged in.
        Original request is unchanged (immutable).
        """
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
# EngineeringResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineeringResult:
    """
    Immutable model representing the unified outcome of an engineering request
    after it has passed through the full coordinator pipeline.

    This is the public API surface returned by EngineeringCoordinator.
    """

    status:      EngineeringStatus
    plan:        Optional[str]             = None
    validation:  Optional[str]             = None
    debug_report: Optional[str]            = None
    repair_plan: Optional[str]             = None
    completed:   bool                      = False
    duration_ms: Optional[int]             = None
    errors:      List[str]                 = field(default_factory=list)
    warnings:    List[str]                 = field(default_factory=list)

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

    @property
    def succeeded(self) -> bool:
        """Return True if the pipeline completed successfully."""
        return self.status == EngineeringStatus.COMPLETE and self.completed

    @property
    def failed(self) -> bool:
        """Return True if the pipeline ended in failure."""
        return self.status == EngineeringStatus.FAILED

    @property
    def required_debugging(self) -> bool:
        """Return True if the debugger was invoked during this request."""
        return self.debug_report is not None

    @property
    def has_repair_plan(self) -> bool:
        """Return True if a repair plan was produced."""
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

    def summary(self) -> str:
        """Return a human-readable one-line summary of the result."""
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
        return f"EngineeringResult({', '.join(parts)})"

    def __repr__(self) -> str:
        return self.summary()