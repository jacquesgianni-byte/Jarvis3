"""
Engineering Lifecycle Manager — State Store
Genesis-034 Sprint-001

Persists Genesis lifecycle records via KnowledgeEngine.
No new storage layer. Uses existing 'projects' category.

Storage convention:
  subject:   "genesis_lifecycle"
  category:  "projects"
  attribute: "genesis_{number}"
  value:     status ("active" | "closed")
  tags:      ["genesis_lifecycle", "genesis_{number}",
               "active"|"closed", "opened:{iso}", "closed:{iso}"]
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.engineering.lifecycle.models import GenesisLifecycleStatus, GenesisRecord

logger = logging.getLogger(__name__)

_SUBJECT  = "genesis_lifecycle"
_CATEGORY = "projects"
_TAG_TYPE = "genesis_lifecycle"


def _attr(genesis: str) -> str:
    return f"genesis_{genesis}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LifecycleStore:
    """
    Persists and retrieves Genesis lifecycle records via KnowledgeEngine.
    One responsibility: lifecycle state persistence.
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ── Write ──────────────────────────────────────────────────────────────────

    def open_genesis(self, genesis: str) -> GenesisRecord:
        """Record a Genesis as ACTIVE."""
        now = _now_iso()
        tags = [_TAG_TYPE, f"genesis_{genesis}",
                GenesisLifecycleStatus.ACTIVE.value, f"opened:{now}"]

        # Hard-delete any existing record then re-store
        self._ke.forget_memory(_SUBJECT, _attr(genesis), permanent=True)
        self._ke.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=_attr(genesis),
            value=GenesisLifecycleStatus.ACTIVE.value,
            tags=tags,
        )
        logger.info("[LIFECYCLE] Opened Genesis-%s", genesis)
        return GenesisRecord(
            genesis=genesis,
            status=GenesisLifecycleStatus.ACTIVE,
            opened_at=now,
            closed_at="",
        )

    def close_genesis(self, genesis: str) -> GenesisRecord:
        """Record a Genesis as CLOSED."""
        now      = _now_iso()
        existing = self._get_record(genesis)
        opened_at = existing.opened_at if existing else ""

        tags = [_TAG_TYPE, f"genesis_{genesis}",
                GenesisLifecycleStatus.CLOSED.value,
                f"closed:{now}"]
        if opened_at:
            tags.append(f"opened:{opened_at}")

        self._ke.forget_memory(_SUBJECT, _attr(genesis), permanent=True)
        self._ke.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=_attr(genesis),
            value=GenesisLifecycleStatus.CLOSED.value,
            tags=tags,
        )
        logger.info("[LIFECYCLE] Closed Genesis-%s", genesis)
        return GenesisRecord(
            genesis=genesis,
            status=GenesisLifecycleStatus.CLOSED,
            opened_at=opened_at,
            closed_at=now,
        )

    # ── Read ───────────────────────────────────────────────────────────────────

    def get(self, genesis: str) -> Optional[GenesisRecord]:
        """Return the lifecycle record for a genesis, or None."""
        return self._get_record(genesis)

    def active_genesis(self) -> Optional[GenesisRecord]:
        """Return the currently active Genesis, or None."""
        for record in self._all_records():
            if GenesisLifecycleStatus.ACTIVE.value in record.tags:
                return self._to_genesis_record(record)
        return None

    def all_records(self) -> list[GenesisRecord]:
        """Return all lifecycle records."""
        return [self._to_genesis_record(r) for r in self._all_records()]

    # ── Internal ───────────────────────────────────────────────────────────────

    def _all_records(self):
        return [
            r for r in self._ke.list_memories(subject=_SUBJECT, limit=200)
            if _TAG_TYPE in r.tags
        ]

    def _get_record(self, genesis: str) -> Optional[GenesisRecord]:
        record = self._ke.recall_memory(_SUBJECT, _attr(genesis))
        if record is None:
            return None
        return self._to_genesis_record(record)

    def _to_genesis_record(self, record) -> GenesisRecord:
        genesis = record.attribute[len("genesis_"):] if record.attribute.startswith("genesis_") else record.attribute
        status  = (GenesisLifecycleStatus.CLOSED
                   if GenesisLifecycleStatus.CLOSED.value in record.tags
                   else GenesisLifecycleStatus.ACTIVE)
        opened_at = ""
        closed_at = ""
        for tag in record.tags:
            if tag.startswith("opened:"):
                opened_at = tag[len("opened:"):]
            elif tag.startswith("closed:"):
                closed_at = tag[len("closed:"):]
        return GenesisRecord(
            genesis=genesis,
            status=status,
            opened_at=opened_at,
            closed_at=closed_at,
        )
