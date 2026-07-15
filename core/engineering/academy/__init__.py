"""
Engineering Academy subsystem.

A deterministic, read-only engineering knowledge base.
Future Engineering Workers consult this before making engineering decisions.

Public API
----------
EngineeringPrinciple   — immutable principle model
AcademyRepository      — abstract read-only repository
JsonAcademyRepository  — JSON-backed repository implementation
AcademyLoader          — JSON loader and schema validator
AcademyService         — deterministic lookup and search service
AcademyError           — base exception
PrincipleNotFoundError — raised when a principle ID is not found
InvalidPrincipleError  — raised when a record fails validation
AcademySchemaError     — raised when the data file fails schema validation
"""

from .exceptions import (
    AcademyError,
    AcademySchemaError,
    InvalidPrincipleError,
    PrincipleNotFoundError,
)
from .json_repository import JsonAcademyRepository
from .loader import AcademyLoader
from .models import EngineeringPrinciple
from .repository import AcademyRepository
from .service import AcademyService

__all__ = [
    "EngineeringPrinciple",
    "AcademyRepository",
    "JsonAcademyRepository",
    "AcademyLoader",
    "AcademyService",
    "AcademyError",
    "PrincipleNotFoundError",
    "InvalidPrincipleError",
    "AcademySchemaError",
]
