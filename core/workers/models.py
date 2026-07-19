"""
Jarvis Worker Models (Genesis-021 Sprint-001)

Clean immutable dataclasses for worker tasks and results.

Design constraints:
    - WorkerTask is immutable (frozen). Tasks never change once created.
    - WorkerResult is immutable (frozen). Results are final.
    - WorkerStatus is a mutable enum — it tracks the worker lifecycle.
    - No AI calls, no repository modification, no memory writes.

WorkerTask:
    Represents a unit of work to be executed by a Worker.
    Contains the task type, payload, and metadata.

WorkerResult:
    The output of a completed Worker execution.
    Contains observations, recommendations, and whether approval
    is required before any action is taken.

WorkerStatus:
    The current lifecycle state of a Worker.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, Optional


class WorkerStatus(Enum):
    """Lifecycle state of a Worker."""
    IDLE       = auto()   # ready to accept a task
    RUNNING    = auto()   # currently executing a task
    COMPLETED  = auto()   # last task completed successfully
    FAILED     = auto()   # last task failed
    CANCELLED  = auto()   # last task was cancelled

    def label(self) -> str:
        return self.name.title()

    @property
    def is_busy(self) -> bool:
        return self == WorkerStatus.RUNNING

    @property
    def is_available(self) -> bool:
        """True if the worker can accept a new task."""
        return self in (WorkerStatus.IDLE, WorkerStatus.COMPLETED,
                        WorkerStatus.FAILED, WorkerStatus.CANCELLED)


@dataclass(frozen=True)
class WorkerTask:
    """
    An immutable unit of work to be executed by a Worker.

    Attributes:
        task_type:   Short identifier for the kind of task.
                     e.g. "analyse_code", "plan_sprint", "review_pr"
        payload:     Task-specific data dict. Worker interprets this.
        task_id:     Unique identifier (auto-generated UUID4).
        created_at:  UTC timestamp when this task was created.
        requester:   Who or what created this task.
        priority:    Integer priority (1=highest). Default 5.
        metadata:    Optional supplementary data.
    """
    task_type:  str
    payload:    dict[str, Any]     = field(default_factory=dict)
    task_id:    str                = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime           = field(default_factory=lambda: datetime.now(UTC))
    requester:  str                = "system"
    priority:   int                = 5
    metadata:   dict[str, Any]     = field(default_factory=dict)

    def __str__(self) -> str:
        return f"WorkerTask(type={self.task_type!r}, id={self.task_id[:8]})"


@dataclass(frozen=True)
class WorkerResult:
    """
    The immutable result of a completed Worker execution.

    Workers produce observations and recommendations.
    They never produce direct actions — human approval is always
    required before anything is executed.

    Attributes:
        task_id:          ID of the task that produced this result.
        worker_name:      Name of the worker that produced this result.
        success:          True if the task completed without error.
        observations:     What the worker found (list of strings).
        recommendations:  What the worker suggests (list of strings).
        requires_approval: True if a human must approve before action.
        completed_at:     UTC timestamp when the result was produced.
        error:            Error message if success=False.
        data:             Structured result data for downstream use.
    """
    task_id:           str
    worker_name:       str
    success:           bool
    observations:      tuple[str, ...]     = field(default_factory=tuple)
    recommendations:   tuple[str, ...]     = field(default_factory=tuple)
    requires_approval: bool                = True
    completed_at:      datetime            = field(default_factory=lambda: datetime.now(UTC))
    error:             str                 = ""
    data:              dict[str, Any]      = field(default_factory=dict)

    def __str__(self) -> str:
        status = "OK" if self.success else f"FAILED: {self.error}"
        return f"WorkerResult(worker={self.worker_name!r}, {status})"

    @classmethod
    def failure(
        cls,
        task_id: str,
        worker_name: str,
        error: str,
    ) -> "WorkerResult":
        """Convenience constructor for failed results."""
        return cls(
            task_id=task_id,
            worker_name=worker_name,
            success=False,
            error=error,
            requires_approval=False,
        )