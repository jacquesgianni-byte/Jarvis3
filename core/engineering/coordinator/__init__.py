"""
Genesis-018 Sprint 002 — Engineering Coordinator Package

Public API:
    EngineeringCoordinator  — central orchestrator
    EngineeringRequest      — immutable input model
    EngineeringResult       — immutable output model  (Sprint 002: +session, +timeline, +stage_durations)
    EngineeringStatus       — pipeline lifecycle enum
    EngineeringStage        — fine-grained pipeline stage enum  (Sprint 002)
    EngineeringSession      — full session lifecycle record       (Sprint 002)
    CoordinatorEventLog     — chronological event timeline        (Sprint 002)
    SessionEvent            — single immutable log entry          (Sprint 002)
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
    SessionEvent,
)

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
]