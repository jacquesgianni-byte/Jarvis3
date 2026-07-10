"""
Jarvis Knowledge Engine

Public entry point for the core.knowledge_engine package.

Import from here rather than from submodules directly:

    from core.knowledge_engine import KnowledgeEngine
    from core.knowledge_engine import MemoryRecord, MemorySource, Visibility
    from core.knowledge_engine import KnowledgeRepository
    from core.knowledge_engine import KnowledgeEngineError, DuplicateMemoryError
"""

from core.knowledge_engine.engine import KnowledgeEngine
from core.knowledge_engine.models import MemoryRecord, MemorySource, Visibility
from core.knowledge_engine.repository import KnowledgeRepository
from core.knowledge_engine.exceptions import (
    KnowledgeEngineError,
    CategoryNotFoundError,
    MemoryNotFoundError,
    StorageError,
    InvalidMemoryError,
    DuplicateMemoryError,
)

__all__ = [
    "KnowledgeEngine",
    "MemoryRecord",
    "MemorySource",
    "Visibility",
    "KnowledgeRepository",
    "KnowledgeEngineError",
    "CategoryNotFoundError",
    "MemoryNotFoundError",
    "StorageError",
    "InvalidMemoryError",
    "DuplicateMemoryError",
]