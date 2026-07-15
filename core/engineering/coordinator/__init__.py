"""
Genesis-018 Sprint 003 — Engineering Coordinator Package

Public API:
    EngineeringCoordinator  — central orchestrator
    EngineeringRequest      — immutable input model
    EngineeringResult       — immutable output model
    EngineeringStatus       — pipeline lifecycle enum
    EngineeringStage        — fine-grained pipeline stage enum    (Sprint 002)
    EngineeringSession      — full session lifecycle record        (Sprint 002)
    CoordinatorEventLog     — chronological event timeline         (Sprint 002)
    SessionEvent            — single immutable log entry           (Sprint 002)
    EngineeringQueue        — FIFO request queue                   (Sprint 003)
    QueueStatus             — queue operational state enum         (Sprint 003)
    QueueSnapshot           — immutable point-in-time queue state  (Sprint 003)
    CoordinatorConfig       — coordinator configuration
    CoordinatorEvent        — external observer event
"""

from .coordinator import CoordinatorConfig, CoordinatorEvent, EngineeringCoordinator
from .models import (
    CoordinatorEventLog,
    EngineeringRequest,
    EngineeringResult,
    EngineeringSession,
    EngineeringStage,
    EngineeringStatus,
    QueueSnapshot,
    QueueStatus,
    SessionEvent,
)
from .queue import EngineeringQueue

__all__ = [
    # Sprint 001
    "EngineeringCoordinator",
    "EngineeringRequest",
    "EngineeringResult",
    "EngineeringStatus",
    "CoordinatorConfig",
    "CoordinatorEvent",
    # Sprint 002
    "EngineeringStage",
    "EngineeringSession",
    "CoordinatorEventLog",
    "SessionEvent",
    # Sprint 003
    "EngineeringQueue",
    "QueueStatus",
    "QueueSnapshot",
]