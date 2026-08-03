"""
Executive Intelligence — Progress Store
Genesis-035 Sprint-001

Stores only progress state and blocker information via KnowledgeEngine.
All other entity data (names, tasks, lifecycle) lives in existing subsystems.

Storage convention:
  subject:   "progress_state"
  category:  "projects"
  attribute: "progress_{entity_type}_{entity_id}"
  value:     ProgressState value string
  tags:      ["progress_state", "entity_{entity_type}", "state_{state}",
               "blocker:{blocker}" if blocked]
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.progress.models import ProgressRecord, ProgressState

logger = logging.getLogger(__name__)

_SUBJECT  = "progress_state"
_CATEGORY = "projects"
_TAG_TYPE = "progress_state"


def _attr(entity_type: str, entity_id: str) -> str:
    return f"progress_{entity_type}_{entity_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgressStore:
    """
    Stores and retrieves progress state records via KnowledgeEngine.
    Only stores: state + blocker. Everything else reads from existing subsystems.
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ── Write ──────────────────────────────────────────────────────────────────

    def set_state(
        self,
        entity_type: str,
        entity_id:   str,
        entity_name: str,
        state:       ProgressState,
        blocker:     str = "",
    ) -> ProgressRecord:
        """Store or update progress state for an entity."""
        now  = _now()
        attr = _attr(entity_type, entity_id)

        tags = [
            _TAG_TYPE,
            f"entity_{entity_type}",
            f"state_{state.value}",
            f"updated:{now}",
        ]
        if blocker:
            tags.append(f"blocker:{blocker[:80]}")

        # Hard-delete then re-store to correctly update tags
        self._ke.forget_memory(_SUBJECT, attr, permanent=True)
        self._ke.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=attr,
            value=state.value,
            tags=tags,
        )

        logger.info(
            "[PROGRESS] %s/%s → %s%s",
            entity_type, entity_id, state.value,
            f" (blocker: {blocker})" if blocker else "",
        )

        return ProgressRecord(
            entity_id=entity_id,
            entity_type=entity_type,
            entity_name=entity_name,
            state=state,
            blocker=blocker,
            updated_at=now,
        )

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_state(
        self, entity_type: str, entity_id: str
    ) -> Optional[ProgressRecord]:
        """Return the progress record for an entity, or None."""
        attr   = _attr(entity_type, entity_id)
        record = self._ke.recall_memory(_SUBJECT, attr)
        if record is None:
            return None
        return self._record_to_progress(record, entity_type, entity_id)

    def all_records(self) -> list[ProgressRecord]:
        """Return all progress records."""
        records = [
            r for r in self._ke.list_memories(subject=_SUBJECT, limit=500)
            if _TAG_TYPE in r.tags
        ]
        result = []
        for r in records:
            attr  = r.attribute  # "progress_{type}_{id}"
            parts = attr[len("progress_"):].split("_", 1)
            if len(parts) == 2:
                entity_type, entity_id = parts
                result.append(self._record_to_progress(r, entity_type, entity_id))
        return result

    def records_by_state(self, state: ProgressState) -> list[ProgressRecord]:
        """Return all records with a given state."""
        return [r for r in self.all_records() if r.state == state]

    # ── Internal ───────────────────────────────────────────────────────────────

    def _record_to_progress(
        self, record, entity_type: str, entity_id: str
    ) -> ProgressRecord:
        try:
            state = ProgressState(record.value)
        except ValueError:
            state = ProgressState.IN_PROGRESS

        blocker    = ""
        updated_at = ""
        for tag in record.tags:
            if tag.startswith("blocker:"):
                blocker = tag[len("blocker:"):]
            elif tag.startswith("updated:"):
                updated_at = tag[len("updated:"):]

        return ProgressRecord(
            entity_id=entity_id,
            entity_type=entity_type,
            entity_name=entity_id.replace("_", " ").title(),
            state=state,
            blocker=blocker,
            updated_at=updated_at,
        )
