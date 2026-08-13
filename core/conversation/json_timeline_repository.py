"""
JSON Timeline Repository — Genesis-047 Sprint-001

Stores persisted timeline events in data/conversations/timeline.json.

Storage strategy:
    - Single JSON file (list of event dicts).
    - Atomic write: write to .tmp then os.replace() — crash-safe.
    - Backup: copy .json to .bak before each write — one generation rollback.
    - Idempotency: event_id lookup before write — duplicates silently ignored.
    - Corruption recovery: timeline.json -> .bak -> empty. Never raises on load.
    - Per-event validation on load: corrupt records skipped and logged.

Thread safety:
    threading.Lock protects in-process concurrent access.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from core.conversation.timeline_repository import (
    PersistedTimelineEvent,
    TimelineRepository,
)

logger = logging.getLogger(__name__)

# Default: data/conversations/timeline.json (matches CONVERSATIONS_DIR in config)
_DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "conversations" / "timeline.json"
)


class JsonTimelineRepository(TimelineRepository):
    """
    JSON-file implementation of TimelineRepository.

    Args:
        path: Path to the timeline.json file.
              Defaults to data/conversations/timeline.json.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else _DEFAULT_PATH
        self._tmp  = self._path.with_suffix(".json.tmp")
        self._bak  = self._path.with_suffix(".json.bak")
        self._lock = threading.Lock()

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._events: dict[str, PersistedTimelineEvent] = {}
        self._load()

        logger.info(
            "[TIMELINE REPO] Initialised. path=%s events=%d",
            self._path, len(self._events),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, event: PersistedTimelineEvent) -> None:
        with self._lock:
            if event.event_id in self._events:
                logger.debug(
                    "[TIMELINE REPO] Duplicate event_id=%s — ignored.", event.event_id,
                )
                return
            self._events[event.event_id] = event
            self._write()
        logger.debug(
            "[TIMELINE REPO] Saved event_id=%s type=%s session=%s",
            event.event_id, event.event_type, event.session_id,
        )

    def load_by_session(self, session_id: str) -> list[PersistedTimelineEvent]:
        with self._lock:
            results = [e for e in self._events.values() if e.session_id == session_id]
        results.sort(key=lambda e: (e.turn, e.timestamp))
        return results

    def load_by_date(self, date_str: str) -> list[PersistedTimelineEvent]:
        with self._lock:
            results = [
                e for e in self._events.values()
                if e.timestamp.startswith(date_str)
            ]
        results.sort(key=lambda e: e.timestamp)
        return results

    def load_by_type(
        self, event_type: str, limit: int = 100,
    ) -> list[PersistedTimelineEvent]:
        with self._lock:
            results = [
                e for e in self._events.values() if e.event_type == event_type
            ]
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    def load_recent(
        self, days: int = 7, limit: int = 500,
    ) -> list[PersistedTimelineEvent]:
        cutoff = (
            datetime.now(UTC) - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            results = [e for e in self._events.values() if e.timestamp >= cutoff]
        results.sort(key=lambda e: e.timestamp)
        return results[:limit]

    def purge_before(self, cutoff_date: str) -> int:
        with self._lock:
            before = len(self._events)
            self._events = {
                eid: e for eid, e in self._events.items()
                if e.timestamp[:10] >= cutoff_date
            }
            deleted = before - len(self._events)
            if deleted:
                self._write()
        logger.info(
            "[TIMELINE REPO] Purged %d events older than %s.", deleted, cutoff_date,
        )
        return deleted

    def count(self) -> int:
        with self._lock:
            return len(self._events)

    # ------------------------------------------------------------------
    # Internal — load
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """
        Load events from disk. Never raises — worst case starts empty.
        Attempt order: .json -> .bak -> empty.
        """
        for candidate in (self._path, self._bak):
            if not candidate.exists():
                continue
            try:
                raw = candidate.read_text(encoding="utf-8")
                records = json.loads(raw)
                if not isinstance(records, list):
                    raise ValueError("Expected JSON array at root.")
                loaded = skipped = 0
                for item in records:
                    try:
                        event = PersistedTimelineEvent.from_dict(item)
                        self._events[event.event_id] = event
                        loaded += 1
                    except Exception as exc:
                        logger.warning(
                            "[TIMELINE REPO] Skipped corrupt record: %s — %s",
                            item, exc,
                        )
                        skipped += 1
                logger.info(
                    "[TIMELINE REPO] Loaded from %s: %d events, %d skipped.",
                    candidate.name, loaded, skipped,
                )
                return
            except Exception as exc:
                logger.error(
                    "[TIMELINE REPO] Failed to load %s: %s — trying next.",
                    candidate.name, exc,
                )
        logger.info("[TIMELINE REPO] Starting with empty timeline.")

    # ------------------------------------------------------------------
    # Internal — write
    # ------------------------------------------------------------------

    def _write(self) -> None:
        """
        Atomically write all events to disk.
        Caller must hold self._lock. Raises on I/O failure.
        Steps: serialise -> write .tmp -> copy .json to .bak -> replace .json
        """
        records = [e.to_dict() for e in self._events.values()]
        payload = json.dumps(records, indent=2, ensure_ascii=False)
        self._tmp.write_text(payload, encoding="utf-8")
        if self._path.exists():
            shutil.copy2(self._path, self._bak)
        os.replace(self._tmp, self._path)
