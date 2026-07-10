"""
Knowledge Engine — Exceptions

Defines all exceptions raised by the Jarvis Knowledge Engine.

Centralising exceptions here ensures callers can catch engine-specific
errors without importing implementation details.
"""


class KnowledgeEngineError(Exception):
    """
    Base exception for all Knowledge Engine errors.

    All engine-specific exceptions inherit from this class,
    allowing callers to catch any engine error with a single except clause.
    """


class CategoryNotFoundError(KnowledgeEngineError):
    """
    Raised when a category id is not found in the category configuration.

    Attributes:
        category_id: The category id that was not found.
    """

    def __init__(self, category_id: str):
        self.category_id = category_id
        super().__init__(
            f"Category '{category_id}' is not defined in categories.json. "
            f"Add it to the configuration before using it."
        )


class MemoryNotFoundError(KnowledgeEngineError):
    """
    Raised when a required memory record cannot be found.

    Used in operations that require an existing record to proceed,
    such as a hard update where creation is not acceptable.

    Attributes:
        subject:   The subject that was searched.
        attribute: The attribute that was searched.
    """

    def __init__(self, subject: str, attribute: str):
        self.subject = subject
        self.attribute = attribute
        super().__init__(
            f"No memory found for subject='{subject}' attribute='{attribute}'."
        )


class StorageError(KnowledgeEngineError):
    """
    Raised when the storage layer fails to read or write data.

    Wraps lower-level IO errors so callers do not need to handle
    filesystem exceptions directly.
    """


class InvalidMemoryError(KnowledgeEngineError):
    """
    Raised when a MemoryRecord fails validation.

    Used when required fields are missing or values are out of range.

    Attributes:
        field:   The field that failed validation.
        reason:  A description of why validation failed.
    """

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(
            f"Invalid memory — field='{field}': {reason}"
        )


class DuplicateMemoryError(KnowledgeEngineError):
    """
    Raised when attempting to create a memory that already exists.

    The engine raises this when a StoreMemory call would create a duplicate
    subject + attribute record and the caller has not used the update path.

    The engine can then decide whether to update, reject or merge —
    but this exception ensures the conflict is never silently overwritten.

    Attributes:
        subject:   The subject of the duplicate memory.
        attribute: The attribute of the duplicate memory.
    """

    def __init__(self, subject: str, attribute: str):
        self.subject = subject
        self.attribute = attribute
        super().__init__(
            f"Memory already exists for subject='{subject}' attribute='{attribute}'."
        )