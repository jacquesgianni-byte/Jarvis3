"""
Knowledge Graph & Worker Intelligence — Engine
Genesis-039 Sprint-001

WorkerIntelligenceEngine answers routing questions using observed facts.
Infrastructure, not analytics. No dashboards. Just data + queries.

Key queries (Genesis-040 routing consumes these):
  best_worker_for(capability)         → WorkerProfile
  highest_confidence_for(capability)  → WorkerProfile
  reviewer_for(worker_id)             → WorkerProfile
  rank_workers_for(capability)        → list[WorkerProfile]

Observation (called after every worker execution):
  observe(worker_result, capability_used)

No AI. No inference. Only observed facts.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from core.worker_intelligence.models import WorkerProfile
from core.worker_intelligence.store import WorkerIntelligenceStore

logger = logging.getLogger(__name__)

_TRIGGERS: frozenset[str] = frozenset({
    "worker intelligence",
    "worker profiles",
    "show worker capabilities",
    "show worker profiles",
    "worker knowledge",
    "worker graph",
    "list workers",
    "worker stats",
    "worker statistics",
})

_WHO_IS_BEST_RE = re.compile(
    r"^who\s+is\s+best\s+(?:for|at)\s+(.+)$", re.IGNORECASE
)
_WHICH_WORKER_RE = re.compile(
    r"^which\s+worker\s+(?:for|handles?|does?)\s+(.+)$", re.IGNORECASE
)
_WORKER_PROFILE_RE = re.compile(
    r"^(?:show\s+)?(?:worker\s+)?profile\s+(?:for\s+)?(\w[\w_\-]*)$", re.IGNORECASE
)


class WorkerIntelligenceEngine:
    """
    Answers worker routing questions from observed execution facts.

    Public API:
        observe(worker_result, capability_used)  — record execution
        best_worker_for(capability)              — highest confidence worker
        highest_confidence_for(capability)       — same as best_worker_for
        reviewer_for(worker_id)                  — best reviewer (not self)
        rank_workers_for(capability)             — sorted by confidence
        profile(worker_id)                       — full WorkerProfile
        all_profiles()                           — all known profiles
        can_handle(utterance)                    — detect query
        handle(utterance)                        — render response
    """

    def __init__(self, knowledge_engine, worker_manager=None) -> None:
        self._store   = WorkerIntelligenceStore(knowledge_engine)
        self._manager = worker_manager

    # ── Observation ────────────────────────────────────────────────────────────

    def observe(self, worker_result, capability_used: str = "") -> None:
        """
        Record a WorkerResult as an observed fact.
        Called by agent AFTER every coordinator.run() call.
        This is the ONLY write path into the knowledge graph.
        """
        if worker_result is None:
            return

        worker_name = getattr(worker_result, "worker_name", "")
        if not worker_name:
            return

        success = getattr(worker_result, "success", False)

        # Resolve description from worker manager if available
        description = ""
        if self._manager:
            try:
                workers = self._manager.workers_for(capability_used)
                for w in workers:
                    if w.name == worker_name:
                        description = w.description
                        break
            except Exception:
                pass

        if not capability_used:
            # Try to infer from coordinator result data
            data = getattr(worker_result, "data", {}) or {}
            capability_used = data.get("capability_used", worker_name)

        try:
            self._store.record_execution(
                worker_name=worker_name,
                capability_used=capability_used,
                success=success,
                description=description,
            )
        except Exception:
            logger.exception("[WORKER_INTEL] observe() failed for %r", worker_name)

    # ── Queries ────────────────────────────────────────────────────────────────

    def best_worker_for(self, capability: str) -> Optional[WorkerProfile]:
        """
        Return the WorkerProfile with the highest confidence for a capability.
        Returns None if no worker has been observed for this capability.
        """
        profiles = self._store.profiles_for_capability(capability)
        if not profiles:
            return None
        return max(profiles, key=lambda p: p.confidence_for(capability))

    def highest_confidence_for(self, capability: str) -> Optional[WorkerProfile]:
        """Alias for best_worker_for — same semantics, different name."""
        return self.best_worker_for(capability)

    def reviewer_for(self, worker_id: str) -> Optional[WorkerProfile]:
        """
        Return the best available reviewer for a given worker's output.

        Strategy:
          1. Find workers with 'run_engineering_review' capability
          2. Exclude the worker itself (no self-review)
          3. Return highest confidence reviewer
          4. Fall back to any worker with review capability if no history
        """
        review_capability = "run_engineering_review"
        profiles = self._store.profiles_for_capability(review_capability)

        # Exclude self
        candidates = [p for p in profiles if p.worker_id != worker_id]

        if candidates:
            return max(candidates, key=lambda p: p.confidence_for(review_capability))

        # No history yet — check manager for registered review workers
        if self._manager:
            try:
                review_workers = self._manager.workers_for(review_capability)
                for w in review_workers:
                    if w.name != worker_id:
                        return WorkerProfile(
                            worker_id=w.name,
                            worker_name=w.name,
                            description=w.description,
                            capabilities=(),
                        )
            except Exception:
                pass

        return None

    def rank_workers_for(self, capability: str) -> list[WorkerProfile]:
        """
        Return all WorkerProfiles ranked by confidence for a capability.
        Highest confidence first. Workers with no data rank last.
        """
        profiles = self._store.profiles_for_capability(capability)
        return sorted(
            profiles,
            key=lambda p: p.confidence_for(capability),
            reverse=True,
        )

    def profile(self, worker_id: str) -> Optional[WorkerProfile]:
        """Return the full WorkerProfile for a worker, or None."""
        return self._store.get_profile(worker_id)

    def all_profiles(self) -> list[WorkerProfile]:
        """Return all known WorkerProfiles, sorted by overall confidence."""
        profiles = self._store.all_profiles()
        return sorted(profiles, key=lambda p: p.overall_confidence, reverse=True)

    # ── Agent interface ────────────────────────────────────────────────────────

    def can_handle(self, utterance: str) -> bool:
        lower = utterance.strip().lower().rstrip("?!.")
        if lower in _TRIGGERS:
            return True
        if _WHO_IS_BEST_RE.match(utterance.strip()):
            return True
        if _WHICH_WORKER_RE.match(utterance.strip()):
            return True
        if _WORKER_PROFILE_RE.match(utterance.strip()):
            return True
        return False

    def handle(self, utterance: str) -> str:
        text  = utterance.strip()
        lower = text.lower().rstrip("?!.")

        # "Who is best for X" / "Which worker for X"
        for pattern in [_WHO_IS_BEST_RE, _WHICH_WORKER_RE]:
            m = pattern.match(text)
            if m:
                capability = m.group(1).strip().rstrip("?!.,")
                profile    = self.best_worker_for(capability)
                if profile:
                    return (
                        f"Best worker for '{capability}': {profile.worker_name} "
                        f"({profile.confidence_for(capability):.0%} confidence, "
                        f"{profile.capability_record(capability).executions} runs)."  # type: ignore
                    )
                return f"No worker has been observed handling '{capability}' yet."

        # "Show profile for X"
        m = _WORKER_PROFILE_RE.match(text)
        if m:
            worker_id = m.group(1)
            p         = self.profile(worker_id)
            if p:
                return p.to_text()
            return f"No profile found for worker '{worker_id}'."

        # General intelligence overview
        profiles = self.all_profiles()
        if not profiles:
            return (
                "No worker intelligence data yet. "
                "Intelligence is collected automatically as workers execute."
            )

        lines = ["Worker Intelligence Summary", ""]
        for p in profiles:
            lines.append(
                f"  {p.worker_name:<40} "
                f"{p.overall_confidence:.0%} confidence  "
                f"{p.total_executions} runs"
            )
        lines.append("")
        lines.append(
            f"Total workers observed: {len(profiles)}"
        )
        return "\n".join(lines)
