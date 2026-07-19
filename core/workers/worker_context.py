"""
Jarvis Worker Context (Genesis-021 Sprint-006)

Shared context store for multi-worker workflows.

WorkerContext is entirely internal to the WorkerCoordinator.
Workers remain completely unaware of its existence.

Responsibilities:
    - Store WorkerResults keyed by worker name and payload hash
    - Reuse previous results when still valid (TTL-based)
    - Share context (data) across workers in a workflow
    - Support explicit invalidation
    - Track workflow metadata (which workers ran, when, how long)

Design constraints:
    - In-memory only (no persistence)
    - Workers never receive or reference WorkerContext directly
    - Coordinator is the only consumer
    - Deterministic: same inputs → same cache key
    - Thread-safe reads (single-threaded for now; lock-ready structure)

Architecture position:
    WorkerCoordinator
        └── WorkerContext   ← Sprint-006
                ├── stores WorkerResult per worker+payload
                ├── shares data across workflow steps
                └── invalidates on demand

Future:
    - Persistent context (survive restarts)
    - Cross-session context sharing
    - Context namespacing per workflow
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

from core.workers.models import WorkerResult

logger = logging.getLogger(__name__)

# Default TTL for stored results (seconds)
DEFAULT_TTL: int = 300   # 5 minutes


# ---------------------------------------------------------------------------
# Context entry — internal storage unit
# ---------------------------------------------------------------------------

@dataclass
class ContextEntry:
    """
    A single stored result with metadata.

    Attributes:
        result:      The stored WorkerResult.
        stored_at:   When this entry was stored.
        ttl_seconds: How long before this entry expires (0 = never).
        hits:        How many times this entry has been retrieved.
    """
    result:      WorkerResult
    stored_at:   datetime     = field(default_factory=lambda: datetime.now(UTC))
    ttl_seconds: int          = DEFAULT_TTL
    hits:        int          = 0

    def is_valid(self, now: Optional[datetime] = None) -> bool:
        """True if this entry has not exceeded its TTL."""
        if self.ttl_seconds == 0:
            return True
        reference = now or datetime.now(UTC)
        elapsed = (reference - self.stored_at).total_seconds()
        return elapsed <= self.ttl_seconds

    def age_seconds(self, now: Optional[datetime] = None) -> float:
        """Return how old this entry is in seconds."""
        reference = now or datetime.now(UTC)
        return (reference - self.stored_at).total_seconds()


# ---------------------------------------------------------------------------
# WorkerContext
# ---------------------------------------------------------------------------

class WorkerContext:
    """
    Shared context store for multi-worker workflows.

    Stores WorkerResults keyed by (worker_name, payload_hash).
    Reuses valid results to avoid redundant worker execution.
    Shares structured data across workflow steps via get_data().

    Entirely internal to WorkerCoordinator — workers are unaware.

    Public API:
        store(worker_name, task_payload, result, ttl)
        get(worker_name, task_payload)      → WorkerResult or None
        has(worker_name, task_payload)      → bool
        invalidate(worker_name)             → clears all entries for worker
        invalidate_all()                    → clears everything
        get_data(worker_name)               → data dict or {}
        set_shared(key, value)              → store arbitrary shared data
        get_shared(key)                     → retrieve shared data
        entry_count()                       → number of stored entries
        summary()                           → debug dict
    """

    def __init__(self, default_ttl: int = DEFAULT_TTL) -> None:
        self._default_ttl = default_ttl
        self._entries: dict[str, ContextEntry] = {}
        self._shared: dict[str, Any] = {}   # arbitrary cross-worker data
        self._created_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Result storage and retrieval
    # ------------------------------------------------------------------

    def store(
        self,
        worker_name: str,
        task_payload: dict,
        result: WorkerResult,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Store a WorkerResult keyed by worker name and payload hash.

        Args:
            worker_name:  The worker that produced this result.
            task_payload: The payload that produced this result.
                          Used to generate the cache key.
            result:       The WorkerResult to store.
            ttl_seconds:  Override TTL. Defaults to context default_ttl.
        """
        key = self._make_key(worker_name, task_payload)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        self._entries[key] = ContextEntry(
            result=result,
            stored_at=datetime.now(UTC),
            ttl_seconds=ttl,
        )
        logger.debug(
            "[CONTEXT] Stored result for worker=%r key=%s ttl=%ds",
            worker_name, key[:12], ttl,
        )

    def get(
        self, worker_name: str, task_payload: dict
    ) -> Optional[WorkerResult]:
        """
        Retrieve a stored result if it exists and is still valid.

        Returns None if not found or expired (expired entries are
        automatically removed on access).

        Args:
            worker_name:  The worker name.
            task_payload: The payload used to generate the cache key.

        Returns:
            WorkerResult if a valid entry exists, otherwise None.
        """
        key = self._make_key(worker_name, task_payload)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if not entry.is_valid():
            del self._entries[key]
            logger.debug(
                "[CONTEXT] Expired entry removed: worker=%r", worker_name
            )
            return None
        entry.hits += 1
        logger.debug(
            "[CONTEXT] Cache hit: worker=%r (age=%.1fs hits=%d)",
            worker_name, entry.age_seconds(), entry.hits,
        )
        return entry.result

    def has(self, worker_name: str, task_payload: dict) -> bool:
        """
        Return True if a valid result exists for this worker + payload.

        Expired entries are automatically cleared.
        """
        return self.get(worker_name, task_payload) is not None

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(self, worker_name: str) -> int:
        """
        Remove all stored entries for a specific worker.

        Args:
            worker_name: The worker whose entries to remove.

        Returns:
            Number of entries removed.
        """
        prefix = f"{worker_name}:"
        to_remove = [k for k in self._entries if k.startswith(prefix)]
        for key in to_remove:
            del self._entries[key]
        if to_remove:
            logger.info(
                "[CONTEXT] Invalidated %d entries for worker=%r",
                len(to_remove), worker_name,
            )
        return len(to_remove)

    def invalidate_all(self) -> int:
        """
        Remove all stored entries and shared data.

        Returns:
            Number of entries removed.
        """
        count = len(self._entries)
        self._entries.clear()
        self._shared.clear()
        logger.info("[CONTEXT] Invalidated all entries (%d).", count)
        return count

    # ------------------------------------------------------------------
    # Shared data — arbitrary cross-worker key/value store
    # ------------------------------------------------------------------

    def set_shared(self, key: str, value: Any) -> None:
        """
        Store an arbitrary value in shared context.

        Use for data that doesn't fit neatly into a WorkerResult
        but needs to be accessible across workflow steps.

        Args:
            key:   Unique string key.
            value: Any serialisable value.
        """
        self._shared[key] = value
        logger.debug("[CONTEXT] set_shared: key=%r", key)

    def get_shared(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a shared value by key.

        Args:
            key:     The key to look up.
            default: Value to return if key is not found.
        """
        return self._shared.get(key, default)

    def has_shared(self, key: str) -> bool:
        """True if a shared value exists for this key."""
        return key in self._shared

    # ------------------------------------------------------------------
    # Convenience: access structured data from a stored result
    # ------------------------------------------------------------------

    def get_data(self, worker_name: str, task_payload: dict = None) -> dict:
        """
        Return the data dict from the most recently stored result
        for a worker, or {} if no valid result exists.

        When task_payload is None, searches all entries for this worker
        and returns the data from the most recently stored valid one.

        Args:
            worker_name:  The worker name.
            task_payload: Optional payload for exact key lookup.
        """
        if task_payload is not None:
            result = self.get(worker_name, task_payload)
            return result.data if result else {}

        # Search all entries for this worker (most recent first)
        prefix = f"{worker_name}:"
        candidates = [
            (k, e) for k, e in self._entries.items()
            if k.startswith(prefix) and e.is_valid()
        ]
        if not candidates:
            return {}
        # Return data from the most recently stored entry
        _, latest = max(candidates, key=lambda x: x[1].stored_at)
        return latest.result.data

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def entry_count(self) -> int:
        """Return the number of stored (including possibly expired) entries."""
        return len(self._entries)

    def valid_entry_count(self) -> int:
        """Return the number of currently valid (non-expired) entries."""
        return sum(1 for e in self._entries.values() if e.is_valid())

    def summary(self) -> dict:
        """Human-readable context summary for debugging."""
        now = datetime.now(UTC)
        entries = []
        for key, entry in self._entries.items():
            worker = key.split(":")[0]
            entries.append({
                "worker":    worker,
                "valid":     entry.is_valid(now),
                "age_s":     round(entry.age_seconds(now), 1),
                "hits":      entry.hits,
                "ttl_s":     entry.ttl_seconds,
            })
        return {
            "total_entries":  len(self._entries),
            "valid_entries":  self.valid_entry_count(),
            "shared_keys":    list(self._shared.keys()),
            "default_ttl":    self._default_ttl,
            "created_at":     self._created_at.isoformat(),
            "entries":        entries,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(worker_name: str, task_payload: dict) -> str:
        """
        Generate a deterministic cache key from worker name and payload.

        Uses SHA-256 of the JSON-serialised payload (sorted keys)
        so the same payload always produces the same key regardless
        of dict insertion order.
        """
        try:
            payload_str = json.dumps(task_payload, sort_keys=True, default=str)
        except (TypeError, ValueError):
            payload_str = str(task_payload)
        payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:16]
        return f"{worker_name}:{payload_hash}"