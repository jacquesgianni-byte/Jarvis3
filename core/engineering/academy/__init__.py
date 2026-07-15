"""
Engineering Academy subsystem.

A deterministic, read-only engineering knowledge base.
Future Engineering Workers consult this before making engineering decisions.

Public API
----------
EngineeringPrinciple   — immutable principle model
DesignPattern          — immutable design pattern model
AcademyRepository      — abstract read-only principle repository
PatternRepository      — abstract read-only pattern repository
JsonAcademyRepository  — JSON-backed principle repository implementation
JsonPatternRepository  — JSON-backed pattern repository implementation
AcademyLoader          — JSON loader and schema validator (principles + patterns)
AcademyService         — deterministic principle lookup and search
PatternService         — deterministic pattern lookup and search
AcademyError           — base exception
PrincipleNotFoundError — raised when a principle or pattern ID is not found
InvalidPrincipleError  — raised when a record fails validation
AcademySchemaError     — raised when a data file fails schema validation
"""

from .exceptions import (
    AcademyError,
    AcademySchemaError,
    InvalidPrincipleError,
    PrincipleNotFoundError,
)
from .json_repository import JsonAcademyRepository, JsonPatternRepository
from .loader import AcademyLoader
from .models import DesignPattern, EngineeringPrinciple
from .repository import AcademyRepository, PatternRepository
from .service import AcademyService, PatternService

__all__ = [
    "EngineeringPrinciple",
    "DesignPattern",
    "AcademyRepository",
    "PatternRepository",
    "JsonAcademyRepository",
    "JsonPatternRepository",
    "AcademyLoader",
    "AcademyService",
    "PatternService",
    "AcademyError",
    "PrincipleNotFoundError",
    "InvalidPrincipleError",
    "AcademySchemaError",
]
