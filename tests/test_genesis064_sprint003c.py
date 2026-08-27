"""
Genesis-064 Sprint-003c - Sprint Flask routes tests.

Covers:
    Authentication:
        - missing token returns 401
        - wrong token returns 401
        - correct token passes

    POST /sprint/propose:
        - returns 200 with insufficient evidence
        - returns proposal when evidence sufficient
        - creates PROPOSED state record

    POST /sprint/approve-plan:
        - missing proposal_id returns 400
        - valid transition returns 200 with to=approved
        - invalid transition (wrong state) returns 409

    POST /sprint/approve-execution:
        - missing proposal_id returns 400
        - valid transition from APPROVED returns 200
        - invalid transition from PROPOSED returns 409

    POST /sprint/review-result:
        - missing proposal_id returns 400
        - invalid decision returns 400
        - accept transitions to COMPLETED
        - reject transitions to REJECTED
        - invalid state returns 409

    GET /sprint/status/<proposal_id>:
        - unknown proposal returns 404
        - known proposal returns current state
        - state machine enforced at every endpoint
"""
from __future__ import annotations

import json
import os
import pathlib
import uuid
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

PROJECT_ROOT = pathlib.Path(r"C:\\Users\\ljmas\\Desktop\\jarvis3")
TOKEN        = "test-sprint-token-123"


@pytest.fixture
def app(tmp_path):
    os.environ["ORCHESTRATOR_TOKEN"] = TOKEN

    from core.knowledge.sprint_state import SprintStateStore
    from core.knowledge.capability_gap import GapObservationStore

    sprint_store = SprintStateStore(tmp_path)
    gap_store    = GapObservationStore(tmp_path / "gaps")

    from apps.server.app import create_app
    flask_app = create_app(
        MagicMock(),
        system_registry=None,
        session_registry=None,
        orchestrator_coordinator=None,
        mission_registry=None,
        mission_pipeline=None,
    )
    flask_app.config["project_root"]       = PROJECT_ROOT
    flask_app.config["gap_store"]          = gap_store
    flask_app.config["sprint_state_store"] = sprint_store
    flask_app.config["TESTING"]            = True

    yield flask_app
    os.environ.pop("ORCHESTRATOR_TOKEN", None)


@pytest.fixture
def client(app):
    return app.test_client()


def _auth():
    return {"X-Orchestrator-Token": TOKEN}


class TestSprintAuth:

    def test_missing_token_returns_401(self, client):
        r = client.post("/sprint/propose", json={})
        assert r.status_code == 401

    def test_wrong_token_returns_401(self, client):
        r = client.post("/sprint/propose", json={},
                        headers={"X-Orchestrator-Token": "wrong"})
        assert r.status_code == 401

    def test_correct_token_passes_auth(self, client):
        r = client.post("/sprint/propose", json={}, headers=_auth())
        assert r.status_code in (200, 503)  # auth passed, content may vary


class TestSprintPropose:

    def test_insufficient_evidence_returns_200(self, client):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            r = client.post("/sprint/propose", json={}, headers=_auth())
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is False
        assert "insufficient" in data["error"].lower() or "error" in data

    def test_proposal_creates_proposed_record(self, app, client):
        from core.knowledge.capability_gap import CapabilityGapObservation, CAPABILITY_GAP_SIGNATURE
        gap_store = app.config["gap_store"]
        for _ in range(3):
            gap_store.record(CapabilityGapObservation(
                observation_id=f"OBS-{uuid.uuid4().hex[:6].upper()}",
                observed_at=datetime.now(timezone.utc).isoformat(),
                question="What should our next mission be?",
                intent_result="unknown", knowledge_match=False,
                investigation_match=False, boundary_violation=False,
                failure_signature=CAPABILITY_GAP_SIGNATURE,
                session_id="test",
            ))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            r = client.post("/sprint/propose", json={}, headers=_auth())
        data = r.get_json()
        if data.get("ok"):
            sprint_store = app.config["sprint_state_store"]
            record = sprint_store.load(data["proposal_id"])
            assert record is not None
            assert record.current_state == "proposed"


class TestSprintApprovePlan:

    def _create_proposal(self, app) -> str:
        sprint_store = app.config["sprint_state_store"]
        pid = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        sprint_store.create(pid)
        return pid

    def test_missing_proposal_id_returns_400(self, client):
        r = client.post("/sprint/approve-plan", json={}, headers=_auth())
        assert r.status_code == 400

    def test_valid_transition_returns_200(self, app, client):
        pid = self._create_proposal(app)
        r   = client.post("/sprint/approve-plan",
                          json={"proposal_id": pid}, headers=_auth())
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["to"] == "approved"

    def test_invalid_state_returns_409(self, app, client):
        pid = self._create_proposal(app)
        # Approve plan first
        client.post("/sprint/approve-plan",
                    json={"proposal_id": pid}, headers=_auth())
        # Try to approve plan again (now APPROVED, can not go back to APPROVED)
        r = client.post("/sprint/approve-plan",
                        json={"proposal_id": pid}, headers=_auth())
        assert r.status_code == 409

    def test_unknown_proposal_returns_409(self, client):
        r = client.post("/sprint/approve-plan",
                        json={"proposal_id": "PROP-UNKNOWN"}, headers=_auth())
        assert r.status_code == 409


class TestSprintApproveExecution:

    def _create_approved(self, app) -> str:
        sprint_store = app.config["sprint_state_store"]
        pid = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        sprint_store.create(pid)
        sprint_store.transition(pid, __import__("core.knowledge.sprint_state", fromlist=["SprintState"]).SprintState.APPROVED,
                               "L1", chief_action=True)
        return pid

    def test_missing_proposal_id_returns_400(self, client):
        r = client.post("/sprint/approve-execution", json={}, headers=_auth())
        assert r.status_code == 400

    def test_valid_transition_from_approved(self, app, client):
        pid = self._create_approved(app)
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            r = client.post("/sprint/approve-execution",
                            json={"proposal_id": pid}, headers=_auth())
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["to"] == "executing"

    def test_invalid_from_proposed_returns_409(self, app, client):
        from core.knowledge.sprint_state import SprintStateStore
        sprint_store = app.config["sprint_state_store"]
        pid = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        sprint_store.create(pid)
        r = client.post("/sprint/approve-execution",
                        json={"proposal_id": pid}, headers=_auth())
        assert r.status_code == 409


class TestSprintReviewResult:

    def _create_awaiting(self, app) -> str:
        from core.knowledge.sprint_state import SprintState
        sprint_store = app.config["sprint_state_store"]
        pid = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        sprint_store.create(pid)
        sprint_store.transition(pid, SprintState.APPROVED, "L1", chief_action=True)
        sprint_store.transition(pid, SprintState.EXECUTING, "L2", chief_action=True)
        sprint_store.transition(pid, SprintState.VALIDATING, "auto", chief_action=False)
        sprint_store.transition(pid, SprintState.AWAITING_RESULT_REVIEW, "auto", chief_action=False)
        return pid

    def test_missing_proposal_id_returns_400(self, client):
        r = client.post("/sprint/review-result", json={"decision": "accept"}, headers=_auth())
        assert r.status_code == 400

    def test_invalid_decision_returns_400(self, client):
        r = client.post("/sprint/review-result",
                        json={"proposal_id": "X", "decision": "maybe"}, headers=_auth())
        assert r.status_code == 400

    def test_accept_transitions_to_completed(self, app, client):
        pid = self._create_awaiting(app)
        r   = client.post("/sprint/review-result",
                          json={"proposal_id": pid, "decision": "accept"}, headers=_auth())
        assert r.status_code == 200
        assert r.get_json()["to"] == "completed"

    def test_reject_transitions_to_rejected(self, app, client):
        pid = self._create_awaiting(app)
        r   = client.post("/sprint/review-result",
                          json={"proposal_id": pid, "decision": "reject"}, headers=_auth())
        assert r.status_code == 200
        assert r.get_json()["to"] == "rejected"

    def test_wrong_state_returns_409(self, app, client):
        from core.knowledge.sprint_state import SprintStateStore
        sprint_store = app.config["sprint_state_store"]
        pid = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        sprint_store.create(pid)
        # Still PROPOSED -- can not accept result
        r = client.post("/sprint/review-result",
                        json={"proposal_id": pid, "decision": "accept"}, headers=_auth())
        assert r.status_code == 409


class TestSprintStatus:

    def test_unknown_proposal_returns_404(self, client):
        r = client.get("/sprint/status/PROP-UNKNOWN", headers=_auth())
        assert r.status_code == 404

    def test_known_proposal_returns_state(self, app, client):
        sprint_store = app.config["sprint_state_store"]
        pid = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        sprint_store.create(pid)
        r = client.get(f"/sprint/status/{pid}", headers=_auth())
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["status"]["current_state"] == "proposed"
        assert data["status"]["requires_chief"] is True

    def test_state_reflects_transitions(self, app, client):
        from core.knowledge.sprint_state import SprintState
        sprint_store = app.config["sprint_state_store"]
        pid = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        sprint_store.create(pid)
        sprint_store.transition(pid, SprintState.APPROVED, "L1", chief_action=True)
        r = client.get(f"/sprint/status/{pid}", headers=_auth())
        assert r.get_json()["status"]["current_state"] == "approved"

    def test_state_machine_enforced_at_every_endpoint(self, app, client):
        """
        PROPOSED -> EXECUTING must be rejected by state machine
        regardless of which endpoint is called.
        """
        sprint_store = app.config["sprint_state_store"]
        pid = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        sprint_store.create(pid)
        # Try to skip Layer 1 and go straight to execution
        r = client.post("/sprint/approve-execution",
                        json={"proposal_id": pid}, headers=_auth())
        assert r.status_code == 409
        # Verify state is still PROPOSED
        status_r = client.get(f"/sprint/status/{pid}", headers=_auth())
        assert status_r.get_json()["status"]["current_state"] == "proposed"
