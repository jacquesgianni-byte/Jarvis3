"""
Genesis-018 Sprint 006 — Engineering Coordinator Package (FINAL SPRINT)

Public API:
    EngineeringCoordinator       — central orchestrator
    EngineeringRequest           — immutable input model
    EngineeringResult            — immutable output model
    EngineeringStatus            — pipeline lifecycle enum
    EngineeringStage             — fine-grained stage enum           (Sprint 002)
    EngineeringSession           — full session lifecycle record      (Sprint 002)
    CoordinatorEventLog          — chronological event timeline       (Sprint 002)
    SessionEvent                 — single immutable log entry         (Sprint 002)
    EngineeringQueue             — FIFO request queue                 (Sprint 003)
    QueueStatus                  — queue operational state enum       (Sprint 003)
    QueueSnapshot                — immutable queue state snapshot     (Sprint 003)
    EngineeringDispatcher        — selects next session               (Sprint 004)
    DispatchStatus               — dispatch lifecycle enum            (Sprint 004)
    DispatchRecord               — immutable dispatch history entry   (Sprint 004)
    EngineeringWorker            — abstract worker interface          (Sprint 005)
    LocalEngineeringWorker       — local single-threaded worker       (Sprint 005)
    DefaultEngineeringWorker     — alias for LocalEngineeringWorker   (Sprint 005)
    WorkerStatus                 — worker operational state enum      (Sprint 005)
    WorkerRecord                 — immutable worker state snapshot    (Sprint 005)
    EngineeringWorkerRegistry    — authoritative worker registry      (Sprint 006)
    RegistryStatus               — registry operational state enum    (Sprint 006)
    RegistrySnapshot             — immutable registry state snapshot  (Sprint 006)
    CoordinatorConfig            — coordinator configuration
    CoordinatorEvent             — external observer event
"""

from .coordinator import CoordinatorConfig, CoordinatorEvent, EngineeringCoordinator
from .dispatcher import DispatchPolicy, EngineeringDispatcher
from .models import (
    CoordinatorEventLog,
    DispatchRecord,
    DispatchStatus,
    EngineeringRequest,
    EngineeringResult,
    EngineeringSession,
    EngineeringStage,
    EngineeringStatus,
    QueueSnapshot,
    QueueStatus,
    RegistrySnapshot,
    RegistryStatus,
    SessionEvent,
    WorkerRecord,
    WorkerStatus,
)
from .queue import EngineeringQueue
from .registry import EngineeringWorkerRegistry
from .worker import DefaultEngineeringWorker, EngineeringWorker, LocalEngineeringWorker

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
    # Sprint 004
    "EngineeringDispatcher",
    "DispatchStatus",
    "DispatchRecord",
    "DispatchPolicy",
    # Sprint 005
    "EngineeringWorker",
    "LocalEngineeringWorker",
    "DefaultEngineeringWorker",
    "WorkerStatus",
    "WorkerRecord",
    # Sprint 006
    "EngineeringWorkerRegistry",
    "RegistryStatus",
    "RegistrySnapshot",
]