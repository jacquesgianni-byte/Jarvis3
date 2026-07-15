"""
Genesis-018 Sprint 001 — Engineering Coordinator Package

Public API:
    EngineeringCoordinator  — central orchestrator
    EngineeringRequest      — immutable input model
    EngineeringResult       — immutable output model
    EngineeringStatus       — pipeline lifecycle enum
    CoordinatorConfig       — coordinator configuration
    CoordinatorEvent        — observer event model
"""

from .coordinator import CoordinatorConfig, CoordinatorEvent, EngineeringCoordinator
from .models import EngineeringRequest, EngineeringResult, EngineeringStatus

__all__ = [
    "EngineeringCoordinator",
    "EngineeringRequest",
    "EngineeringResult",
    "EngineeringStatus",
    "CoordinatorConfig",
    "CoordinatorEvent",
]