"""
Engineering Academy Exceptions.

All exceptions raised by the Engineering Academy subsystem.
No business logic — only exception definitions.
"""


class AcademyError(Exception):
    """Base exception for all Engineering Academy errors."""


class PrincipleNotFoundError(AcademyError):
    """Raised when a requested principle does not exist in the Academy."""

    def __init__(self, principle_id: str) -> None:
        self.principle_id = principle_id
        super().__init__(f"Principle not found: '{principle_id}'")


class InvalidPrincipleError(AcademyError):
    """Raised when a principle record fails validation."""

    def __init__(self, principle_id: str, reason: str) -> None:
        self.principle_id = principle_id
        self.reason = reason
        super().__init__(f"Invalid principle '{principle_id}': {reason}")


class AcademySchemaError(AcademyError):
    """Raised when the principles data file fails schema validation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Academy schema error: {reason}")
