"""
Knowledge Graph & Worker Intelligence — Store
Genesis-039 Sprint-001

Persists WorkerProfiles via KnowledgeEngine.
No new storage layer. Uses existing 'projects' category.

Storage convention:
  subject:   "worker_intelligence"
  category:  "projects"
  attribute: "profile_{worker_name}"
  value:     JSON-serialised profile dict
  tags:      ["worker_intelligence", "worker_{name}",
               "capability_{cap}" for each capability]

Each profile is stored as one record — all capability data
serialised together. Avoids N+1 reads per capability.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from core.worker_intelligence.models import CapabilityRecord, WorkerProfile

logger = logging.getLogger(__name__)

_SUBJECT  = "worker_intelligence"
_CATEGORY = "projects"
_TAG_TYPE = "worker_intelligence"


def _attr(worker_name: str) -> str:
    return f"profile_{worker_name}"


class WorkerIntelligenceStore:
    """
    Persists and retrieves WorkerProfiles via KnowledgeEngine.
    One responsibility: worker intelligence persistence.
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ── Write ──────────────────────────────────────────────────────────────────

    def record_execution(
        self,
        worker_name:     str,
        capability_used: str,
        success:         bool,
        description:     str = "",
    ) -> WorkerProfile:
        """
        Record one execution fact and return the updated WorkerProfile.
        This is the ONLY way intelligence data enters the knowledge graph.
        """
        existing = self.get_profile(worker_name)
        now      = datetime.now(timezone.utc).isoformat()

        if existing is None:
            # First time we've seen this worker
            cap_rec  = CapabilityRecord(capability=capability_used).with_execution(success)
            profile  = WorkerProfile(
                worker_id=worker_name,
                worker_name=worker_name,
                description=description,
                capabilities=(cap_rec,),
                total_executions=1,
                total_successes=1 if success else 0,
                total_failures=0 if success else 1,
                last_seen=now,
            )
        else:
            # Update existing profile
            caps     = dict((c.capability, c) for c in existing.capabilities)
            prev_rec = caps.get(capability_used, CapabilityRecord(capability=capability_used))
            caps[capability_used] = prev_rec.with_execution(success)

            profile = WorkerProfile(
                worker_id=existing.worker_id,
                worker_name=existing.worker_name,
                description=description or existing.description,
                capabilities=tuple(caps.values()),
                total_executions=existing.total_executions + 1,
                total_successes=existing.total_successes + (1 if success else 0),
                total_failures=existing.total_failures + (0 if success else 1),
                last_seen=now,
            )

        self._persist(profile)
        logger.info(
            "[WORKER_INTEL] Recorded: %s %s %s → conf=%.0f%%",
            worker_name, capability_used,
            "✓" if success else "✗",
            profile.confidence_for(capability_used) * 100,
        )
        return profile

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_profile(self, worker_name: str) -> Optional[WorkerProfile]:
        """Return a WorkerProfile, or None if never observed."""
        record = self._ke.recall_memory(_SUBJECT, _attr(worker_name))
        if record is None:
            return None
        return self._deserialise(record.value, worker_name)

    def all_profiles(self) -> list[WorkerProfile]:
        """Return all known WorkerProfiles."""
        records = [
            r for r in self._ke.list_memories(subject=_SUBJECT, limit=500)
            if _TAG_TYPE in r.tags
        ]
        profiles = []
        for r in records:
            name = r.attribute[len("profile_"):] if r.attribute.startswith("profile_") else r.attribute
            try:
                profiles.append(self._deserialise(r.value, name))
            except Exception:
                logger.debug("[WORKER_INTEL] Failed to deserialise profile for %r", name)
        return profiles

    def profiles_for_capability(self, capability: str) -> list[WorkerProfile]:
        """Return all profiles that have data for a given capability."""
        return [
            p for p in self.all_profiles()
            if p.has_capability(capability) and p.capability_record(capability).has_data  # type: ignore
        ]

    def has_profile(self, worker_name: str) -> bool:
        return self._ke.recall_memory(_SUBJECT, _attr(worker_name)) is not None

    # ── Internal ───────────────────────────────────────────────────────────────

    def _persist(self, profile: WorkerProfile) -> None:
        """Serialise and store a WorkerProfile."""
        data = {
            "worker_id":        profile.worker_id,
            "worker_name":      profile.worker_name,
            "description":      profile.description,
            "total_executions": profile.total_executions,
            "total_successes":  profile.total_successes,
            "total_failures":   profile.total_failures,
            "last_seen":        profile.last_seen,
            "capabilities": [
                {
                    "capability": c.capability,
                    "executions": c.executions,
                    "successes":  c.successes,
                    "failures":   c.failures,
                }
                for c in profile.capabilities
            ],
        }
        tags = [_TAG_TYPE, f"worker_{profile.worker_name}"]
        for cap in profile.capabilities:
            tags.append(f"capability_{cap.capability}")

        # Hard-delete then re-store to correctly update
        self._ke.forget_memory(_SUBJECT, _attr(profile.worker_name), permanent=True)
        self._ke.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=_attr(profile.worker_name),
            value=json.dumps(data),
            tags=tags,
        )

    def _deserialise(self, value: str, worker_name: str) -> WorkerProfile:
        """Deserialise a stored JSON profile."""
        data = json.loads(value)
        caps = tuple(
            CapabilityRecord(
                capability=c["capability"],
                executions=c["executions"],
                successes=c["successes"],
                failures=c["failures"],
            )
            for c in data.get("capabilities", [])
        )
        return WorkerProfile(
            worker_id=data.get("worker_id", worker_name),
            worker_name=data.get("worker_name", worker_name),
            description=data.get("description", ""),
            capabilities=caps,
            total_executions=data.get("total_executions", 0),
            total_successes=data.get("total_successes", 0),
            total_failures=data.get("total_failures", 0),
            last_seen=data.get("last_seen", ""),
        )
