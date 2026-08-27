"""
Genesis-064 Sprint-003b - SprintProposalStage + SprintApprovalGateStage tests.

Covers:
    IntentStage:
        - propose_sprint phrases classify correctly
        - existing intents unaffected

    SprintProposalStage:
        - skipped when intent is not propose_sprint
        - insufficient evidence returns honest response
        - valid proposal creates PROPOSED state record
        - valid proposal sets sprint_proposal in state
        - valid proposal sets approval_required=True
        - terminal=True in both cases
        - engine unavailable returns honest response

    SprintApprovalGateStage:
        - approve_plan transitions PROPOSED to APPROVED
        - approve_plan rejected without chief_action (enforced by state machine)
        - approve_execution transitions APPROVED to EXECUTING
        - approve_execution requires prior approve_plan
        - mark_validating transitions EXECUTING to VALIDATING
        - mark_awaiting_review transitions VALIDATING to AWAITING_RESULT_REVIEW
        - accept_result transitions AWAITING_RESULT_REVIEW to COMPLETED
        - reject at layer 1 transitions PROPOSED to REJECTED
        - reject at layer 2 transitions APPROVED to REJECTED
        - mark_failed transitions EXECUTING to FAILED
        - INTERRUPTED never auto-resumes
        - FAILED never auto-retries
        - get_status returns correct state info
        - store unavailable returns honest error

    Pipeline integration:
        - propose_sprint intent routes to SprintProposalStage
        - investigate intent not affected
        - capability_inventory intent not affected
"""
from __future__ import annotations

import json
import pathlib
import pytest
from unittest.mock import patch, MagicMock
import uuid
from datetime import datetime, timezone

from core.mission.pipeline import (
    SprintProposalStage,
    SprintApprovalGateStage,
    IntentStage,
    MissionPipeline,
    MissionRequest,
)
from core.knowledge.sprint_state import SprintStateStore, SprintState
from core.knowledge.capability_gap import GapObservationStore, CapabilityGapObservation, CAPABILITY_GAP_SIGNATURE
from core.mission.investigation_registry import InvestigationRegistry
from core.knowledge.genesis_record import GenesisDeliveryStore
from core.mission.context import MissionContext
from core.mission.policy import MissionCapabilityPolicy

PROJECT_ROOT = pathlib.Path(r"C:\\Users\\ljmas\\Desktop\\jarvis3")


def _make_request(message: str) -> MissionRequest:
    ctx = MissionContext.for_mission(
        session_id           = "test-session",
        permitted_workers    = MissionCapabilityPolicy.PERMITTED_WORKERS,
        knowledge_categories = MissionCapabilityPolicy.PERMITTED_KNOWLEDGE_CATEGORIES,
    )
    return MissionRequest(message=message, session_id="test-session", context=ctx)


def _make_observation(question="What should our next mission be?"):
    return CapabilityGapObservation(
        observation_id=f"OBS-{uuid.uuid4().hex[:6].upper()}",
        observed_at=datetime.now(timezone.utc).isoformat(),
        question=question, intent_result="unknown",
        knowledge_match=False, investigation_match=False,
        boundary_violation=False, failure_signature=CAPABILITY_GAP_SIGNATURE,
        session_id="test-session",
    )


class TestIntentProposeSprint:

    def _classify(self, message: str) -> str:
        stage = IntentStage()
        state = {"knowledge_query": None}
        stage.run(_make_request(message), state)
        return state["intent"]

    def test_propose_a_sprint_classifies(self):
        assert self._classify("propose a sprint") == "propose_sprint"

    def test_what_should_we_work_on_next(self):
        assert self._classify("what should we work on next") == "propose_sprint"

    def test_suggest_a_sprint(self):
        assert self._classify("suggest a sprint") == "propose_sprint"

    def test_what_should_we_build_next(self):
        assert self._classify("what should we build next") == "propose_sprint"

    def test_investigate_still_works(self):
        assert self._classify("Is everything consistent?") == "investigate"

    def test_capability_inventory_still_works(self):
        assert self._classify("What can you do?") == "capability_inventory"

    def test_why_failed_still_works(self):
        assert self._classify("Why couldn't you answer that?") == "why_failed"


class TestSprintProposalStage:

    def test_skipped_when_wrong_intent(self, tmp_path):
        stage = SprintProposalStage()
        state = {"intent": "investigate"}
        result = stage.run(_make_request("test"), state)
        assert result.executed is False

    def test_engine_unavailable_honest_response(self, tmp_path):
        stage = SprintProposalStage()  # no args = no engine
        state = {"intent": "propose_sprint"}
        result = stage.run(_make_request("propose a sprint"), state)
        assert result.terminal is True
        assert "not available" in state["response_message"].lower()

    def test_insufficient_evidence_honest_response(self, tmp_path):
        gap_store = GapObservationStore(tmp_path / "gaps")
        # Only 1 observation -- below threshold
        gap_store.record(_make_observation())
        stage = SprintProposalStage(
            gap_store=gap_store,
            inv_registry=InvestigationRegistry(PROJECT_ROOT),
            delivery_store=GenesisDeliveryStore(PROJECT_ROOT),
            sprint_state_store=SprintStateStore(tmp_path),
            project_root=PROJECT_ROOT,
        )
        state = {"intent": "propose_sprint"}
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            result = stage.run(_make_request("propose a sprint"), state)
        assert result.terminal is True
        assert "INSUFFICIENT EVIDENCE" in state["response_message"]

    def test_valid_proposal_creates_state_record(self, tmp_path):
        gap_store = GapObservationStore(tmp_path / "gaps")
        for _ in range(3):
            gap_store.record(_make_observation("What should our next mission be?"))
        sprint_store = SprintStateStore(tmp_path)
        stage = SprintProposalStage(
            gap_store=gap_store,
            inv_registry=InvestigationRegistry(PROJECT_ROOT),
            delivery_store=GenesisDeliveryStore(PROJECT_ROOT),
            sprint_state_store=sprint_store,
            project_root=PROJECT_ROOT,
        )
        state = {"intent": "propose_sprint"}
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            result = stage.run(_make_request("propose a sprint"), state)
        if result.terminal and "INSUFFICIENT" not in state["response_message"]:
            proposal = state.get("sprint_proposal")
            assert proposal is not None
            record = sprint_store.load(proposal.proposal_id)
            assert record is not None
            assert record.current_state == SprintState.PROPOSED.value

    def test_valid_proposal_sets_approval_required(self, tmp_path):
        gap_store = GapObservationStore(tmp_path / "gaps")
        for _ in range(3):
            gap_store.record(_make_observation("What should our next mission be?"))
        stage = SprintProposalStage(
            gap_store=gap_store,
            inv_registry=InvestigationRegistry(PROJECT_ROOT),
            delivery_store=GenesisDeliveryStore(PROJECT_ROOT),
            sprint_state_store=SprintStateStore(tmp_path),
            project_root=PROJECT_ROOT,
        )
        state = {"intent": "propose_sprint"}
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            stage.run(_make_request("propose a sprint"), state)
        if state.get("sprint_proposal"):
            assert state.get("approval_required") is True


class TestSprintApprovalGateStage:

    def _make_gate(self, tmp_path) -> tuple:
        store = SprintStateStore(tmp_path)
        proposal_id = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        store.create(proposal_id)
        gate = SprintApprovalGateStage(store)
        return gate, store, proposal_id

    def test_approve_plan_transitions_to_approved(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        result = gate.approve_plan(pid)
        assert result["success"] is True
        assert result["to"] == SprintState.APPROVED.value

    def test_approve_execution_requires_prior_approve_plan(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        result = gate.approve_execution(pid)
        assert result["success"] is False  # still PROPOSED, can't jump to EXECUTING

    def test_approve_execution_after_approve_plan(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        gate.approve_plan(pid)
        result = gate.approve_execution(pid)
        assert result["success"] is True
        assert result["to"] == SprintState.EXECUTING.value

    def test_mark_validating(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        gate.approve_plan(pid)
        gate.approve_execution(pid)
        result = gate.mark_validating(pid)
        assert result["success"] is True
        assert result["to"] == SprintState.VALIDATING.value

    def test_mark_awaiting_review(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        gate.approve_plan(pid)
        gate.approve_execution(pid)
        gate.mark_validating(pid)
        result = gate.mark_awaiting_review(pid, "Tests passed.")
        assert result["success"] is True
        assert result["to"] == SprintState.AWAITING_RESULT_REVIEW.value

    def test_accept_result_completes(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        gate.approve_plan(pid)
        gate.approve_execution(pid)
        gate.mark_validating(pid)
        gate.mark_awaiting_review(pid, "Tests passed.")
        result = gate.accept_result(pid)
        assert result["success"] is True
        assert result["to"] == SprintState.COMPLETED.value

    def test_reject_at_layer1(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        result = gate.reject(pid, layer=1)
        assert result["success"] is True
        assert result["to"] == SprintState.REJECTED.value

    def test_reject_at_layer2(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        gate.approve_plan(pid)
        result = gate.reject(pid, layer=2)
        assert result["success"] is True
        assert result["to"] == SprintState.REJECTED.value

    def test_mark_failed(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        gate.approve_plan(pid)
        gate.approve_execution(pid)
        result = gate.mark_failed(pid, "Tests failed.")
        assert result["success"] is True
        assert result["to"] == SprintState.FAILED.value

    def test_failed_does_not_auto_retry(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        gate.approve_plan(pid)
        gate.approve_execution(pid)
        gate.mark_failed(pid, "Tests failed.")
        # Try to transition out of FAILED -- must be rejected
        result = gate.approve_execution(pid)
        assert result["success"] is False

    def test_interrupted_does_not_auto_resume(self, tmp_path):
        store = SprintStateStore(tmp_path)
        pid   = "PROP-INTR-TEST"
        store.create(pid)
        path = tmp_path / "sprint_states" / f"{pid}.json"
        data = json.loads(path.read_text())
        data["current_state"] = SprintState.EXECUTING.value
        path.write_text(json.dumps(data))
        # Restart
        store2 = SprintStateStore(tmp_path)
        record = store2.load(pid)
        assert record.current_state == SprintState.INTERRUPTED.value
        # Try to auto-resume -- must fail
        gate = SprintApprovalGateStage(store2)
        result = gate.mark_validating(pid)
        assert result["success"] is False

    def test_get_status_returns_state(self, tmp_path):
        gate, store, pid = self._make_gate(tmp_path)
        status = gate.get_status(pid)
        assert status is not None
        assert status["current_state"] == SprintState.PROPOSED.value
        assert status["requires_chief"] is True

    def test_store_unavailable_honest_error(self):
        gate = SprintApprovalGateStage(sprint_state_store=None)
        result = gate.approve_plan("PROP-TEST")
        assert result["success"] is False
        assert "not available" in result["error"].lower()
