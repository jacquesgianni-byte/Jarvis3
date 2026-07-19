"""
Jarvis Worker Exceptions (Genesis-021 Sprint-001)

All worker exceptions inherit from WorkerError so callers
can catch the entire family with a single except clause.
"""


class WorkerError(Exception):
    """Base class for all worker errors."""


class WorkerNotFoundError(WorkerError):
    """Raised when a worker is looked up by name but does not exist."""


class WorkerAlreadyRegisteredError(WorkerError):
    """Raised when a worker name is registered more than once."""


class WorkerNotReadyError(WorkerError):
    """Raised when execute() is called on a worker that is not IDLE."""


class WorkerCancelledError(WorkerError):
    """Raised when a task is cancelled before completion."""


class InvalidTaskError(WorkerError):
    """Raised when validate() determines a task is malformed."""