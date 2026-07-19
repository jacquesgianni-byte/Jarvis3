"""
Jarvis Workers Package (Genesis-021 Sprint-001)

The operating system for future autonomous agents.

Workers are specialised, independently registerable units that
delegate engineering tasks. They produce observations, plans, and
recommendations — they never directly modify the repository.
Human approval is always required before execution.

Public API:
    from core.workers.base import Worker
    from core.workers.manager import WorkerManager
    from core.workers.registry import WorkerRegistry
    from core.workers.models import WorkerTask, WorkerResult, WorkerStatus
    from core.workers.exceptions import WorkerError
"""