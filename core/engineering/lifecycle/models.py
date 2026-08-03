"""
Engineering Lifecycle Manager — Models
Genesis-034 Sprint-001

Immutable data models for Genesis lifecycle state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GenesisLifecycleStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class LifecycleCommandKind(Enum):
    OPEN_GENESIS  = "open_genesis"
    CLOSE_GENESIS = "close_genesis"


@dataclass(frozen=True)
class LifecycleCommand:
    """A detected lifecycle command with its genesis number."""
    kind:    LifecycleCommandKind
    genesis: str                   # e.g. "034"
    raw:     str                   # original utterance


@dataclass
class GenesisRecord:
    """
    Lifecycle record for a single Genesis.
    Stored in KnowledgeEngine under subject="genesis_lifecycle".
    """
    genesis:    str
    status:     GenesisLifecycleStatus
    opened_at:  str   # ISO datetime string
    closed_at:  str   # ISO datetime string, empty if still active
