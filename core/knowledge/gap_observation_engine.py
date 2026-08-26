"""
Jarvis OS - GapObservationEngine - Genesis-060 Sprint-002

Observes pipeline outcomes and records genuine capability-gap evidence.

Design invariants:
    - Observational only: never modifies the MissionResponse.
    - Never reruns the pipeline or triggers a new decision loop.
    - Never interprets the question beyond the four evidence signals.
    - Fires only when all four conditions are simultaneously true:
        1. intent == "unknown"
        2. knowledge_match == False  (state["knowledge_query"] is None)
        3. investigation_match == False  (state.get("investigation_terminal") not set
           by a successful investigation)
        4. boundary_violation == False  (MissionResponse.boundary_violation is False)
    - Observation failures are logged and swallowed - never surface to the user.
    - The original MissionResponse is always returned unchanged.

Called inside MissionPipeline.process() after ResponseStage has produced
the final MissionResponse. Both state and response are available at that point.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from core.knowledge.capability_gap import (
    CapabilityGapObservation,
    GapObservationStore,
    CAPABILITY_GAP_SIGNATURE,
)

if TYPE_CHECKING:
    from core.mission.pipeline import MissionRequest, MissionResponse

logger = logging.getLogger(__name__)


class GapObservationEngine:
    """
    Observes pipeline outcomes and records genuine capability-gap evidence.

    Constructed with a GapObservationStore and a project_root for the store path.
    Called via observe() after ResponseStage produces the final MissionResponse.

    The engine evaluates four evidence signals from state and response.
    If all four indicate a genuine capability gap, it records an observation.
    It never modifies the response. It never reruns the pipeline.
    """

    def __init__(self, store: GapObservationStore) -> None:
        self._store = store

    def observe(
        self,
        request: "MissionRequest",
        state: dict,
        response: "MissionResponse",
    ) -> None:
        """
        Observe the pipeline outcome. Record a gap observation if warranted.

        This method never raises. Observation failures are logged and swallowed.
        The caller's response is never affected.

        Four conditions must ALL be true to record:
            1. intent == "unknown"
            2. knowledge_query is None (no knowledge path matched)
            3. investigation_terminal not set (no investigation matched and ran)
            4. boundary_violation is False (not a policy block)
        """
        try:
            self._observe(request, state, response)
        except Exception as e:
            logger.warning(
                "[GapObservationEngine] Observation failed (response unchanged): %s", e
            )

    def _observe(
        self,
        request: "MissionRequest",
        state: dict,
        response: "MissionResponse",
    ) -> None:
        """Internal observation logic. May raise - caller swallows."""

        # Signal 1: intent must be unknown
        intent = state.get("intent", "")
        if intent != "unknown":
            return

        # Signal 2: no knowledge path matched
        knowledge_query = state.get("knowledge_query")
        knowledge_match = knowledge_query is not None
        if knowledge_match:
            return

        # Signal 3: no investigation matched and ran to a result
        # investigation_terminal is only set when InvestigationStage ran successfully
        investigation_terminal = state.get("investigation_terminal", False)
        investigation_match = bool(investigation_terminal)
        if investigation_match:
            return

        # Signal 4: not a boundary violation
        if response.boundary_violation:
            return

        # All four conditions met - derive and record the observation
        sig = CapabilityGapObservation.derive_failure_signature(
            intent_result       = intent,
            knowledge_match     = knowledge_match,
            investigation_match = investigation_match,
            boundary_violation  = response.boundary_violation,
        )

        observation = CapabilityGapObservation(
            observation_id      = f"OBS-{uuid.uuid4().hex[:6].upper()}",
            observed_at         = datetime.now(timezone.utc).isoformat(),
            question            = request.message,
            intent_result       = intent,
            knowledge_match     = knowledge_match,
            investigation_match = investigation_match,
            boundary_violation  = response.boundary_violation,
            failure_signature   = sig,
            session_id          = request.session_id,
        )

        self._store.record(observation)
        logger.info(
            "[GapObservationEngine] Capability gap observed: %s | question=%r",
            observation.observation_id,
            request.message[:80],
        )
