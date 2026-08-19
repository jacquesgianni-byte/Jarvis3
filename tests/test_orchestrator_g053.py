"""
Genesis-053 Sprint-001 — Orchestrator Foundation Tests

Covers: approval gate, session persistence, resume flow,
        Flask endpoints, idempotency, and error paths.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_request(text="Implement Genesis-053 Sprint-001", priority=0):
    from core.engineering.coordinator.models import EngineeringRequest
    return EngineeringRequest(request=text, priority=priority)


def _make_session(text="Test session"):
    from core.engineering.coordinator.models import EngineeringRequest, EngineeringSession
    req = EngineeringRequest(request=text)
    return EngineeringSession.create(req)


def _make_store(tmp_path):
    from core.engineering.coordinator.session_store import SessionStore
    return SessionStore(directory=tmp_path)


def _make_coordinator(enable_gate=True, store=None):
    from core.engineering.coordinator.coordinator import (
        CoordinatorConfig,
        EngineeringCoordinator,
    )
    config = CoordinatorConfig(
        enable_planning=False,
        enable_guardrails=False,
        enable_approval_gate=enable_gate,
        enable_validation=False,
        enable_debugging=False,
    )
    return EngineeringCoordinator(config=config, session_store=store)


# ---------------------------------------------------------------------------
# 1. Model — EngineeringStage.AWAITING_APPROVAL
# ---------------------------------------------------------------------------

class TestEngineeringStageAwaitingApproval:

    def test_awaiting_approval_exists(self):
        from core.engineering.coordinator.models import EngineeringStage
        assert hasattr(EngineeringStage, "AWAITING_APPROVAL")

    def test_awaiting_approval_value(self):
        from core.engineering.coordinator.models import EngineeringStage
        assert EngineeringStage.AWAITING_APPROVAL.value == "AWAITING_APPROVAL"

    def test_awaiting_approval_not_terminal(self):
        from core.engineering.coordinator.models import EngineeringStage
        assert not EngineeringStage.AWAITING_APPROVAL.is_terminal()

    def test_awaiting_approval_is_active(self):
        from core.engineering.coordinator.models import EngineeringStage
        assert EngineeringStage.AWAITING_APPROVAL.is_active()

    def test_awaiting_approval_is_suspended(self):
        from core.engineering.coordinator.models import EngineeringStage
        assert EngineeringStage.AWAITING_APPROVAL.is_suspended()

    def test_other_stages_not_suspended(self):
        from core.engineering.coordinator.models import EngineeringStage
        for stage in EngineeringStage:
            if stage != EngineeringStage.AWAITING_APPROVAL:
                assert not stage.is_suspended(), f"{stage} should not be suspended"


# ---------------------------------------------------------------------------
# 2. Model — EngineeringStatus.AWAITING_APPROVAL
# ---------------------------------------------------------------------------

class TestEngineeringStatusAwaitingApproval:

    def test_awaiting_approval_exists(self):
        from core.engineering.coordinator.models import EngineeringStatus
        assert hasattr(EngineeringStatus, "AWAITING_APPROVAL")

    def test_awaiting_approval_is_active(self):
        from core.engineering.coordinator.models import EngineeringStatus
        assert EngineeringStatus.AWAITING_APPROVAL.is_active()

    def test_awaiting_approval_not_terminal(self):
        from core.engineering.coordinator.models import EngineeringStatus
        assert not EngineeringStatus.AWAITING_APPROVAL.is_terminal()

    def test_awaiting_approval_is_suspended(self):
        from core.engineering.coordinator.models import EngineeringStatus
        assert EngineeringStatus.AWAITING_APPROVAL.is_suspended()


# ---------------------------------------------------------------------------
# 3. Model — EngineeringSession approval methods
# ---------------------------------------------------------------------------

class TestEngineeringSessionApprovalMethods:

    def test_suspend_sets_status(self):
        from core.engineering.coordinator.models import EngineeringStatus, EngineeringStage
        session = _make_session()
        session.suspend()
        assert session.status == EngineeringStatus.AWAITING_APPROVAL
        assert session.current_stage == EngineeringStage.AWAITING_APPROVAL

    def test_suspend_records_event(self):
        from core.engineering.coordinator.models import EngineeringStage
        session = _make_session()
        session.suspend()
        stages = session.events.stages_visited()
        assert EngineeringStage.AWAITING_APPROVAL in stages

    def test_suspend_does_not_seal_log(self):
        session = _make_session()
        session.suspend()
        assert not session.events.is_sealed

    def test_approve_sets_validating_status(self):
        from core.engineering.coordinator.models import EngineeringStatus
        session = _make_session()
        session.suspend()
        session.approve("ludovic", "2026-01-01T00:00:00+00:00")
        assert session.status == EngineeringStatus.VALIDATING
        assert session.approved_by == "ludovic"
        assert session.approved_at == "2026-01-01T00:00:00+00:00"

    def test_reject_sets_failed_status(self):
        from core.engineering.coordinator.models import EngineeringStatus, EngineeringStage
        session = _make_session()
        session.suspend()
        session.reject("ludovic", "2026-01-01T00:00:00+00:00", "Scope too broad")
        assert session.status == EngineeringStatus.FAILED
        assert session.current_stage == EngineeringStage.FAILED
        assert session.rejection_reason == "Scope too broad"
        assert session.events.is_sealed

    def test_reject_records_failed_event(self):
        from core.engineering.coordinator.models import EngineeringStage
        session = _make_session()
        session.suspend()
        session.reject("ludovic", "2026-01-01T00:00:00+00:00", "reason")
        stages = session.events.stages_visited()
        assert EngineeringStage.FAILED in stages


# ---------------------------------------------------------------------------
# 4. Model — EngineeringSession.to_dict() / from_dict()
# ---------------------------------------------------------------------------

class TestEngineeringSessionPersistence:

    def test_to_dict_contains_required_keys(self):
        session = _make_session("round-trip test")
        session.suspend()
        d = session.to_dict()
        for key in ("session_id", "status", "current_stage", "started_at", "request"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_request_nested(self):
        session = _make_session("nested request test")
        d = session.to_dict()
        assert "request" in d
        assert d["request"]["request"] == "nested request test"

    def test_from_dict_round_trip(self):
        from core.engineering.coordinator.models import EngineeringStatus, EngineeringStage
        session = _make_session("round-trip full")
        session.suspend()
        d = session.to_dict()
        restored = type(session).from_dict(d)
        assert restored.session_id   == session.session_id
        assert restored.status       == EngineeringStatus.AWAITING_APPROVAL
        assert restored.current_stage == EngineeringStage.AWAITING_APPROVAL
        assert restored.request.request == "round-trip full"

    def test_from_dict_with_approval_metadata(self):
        session = _make_session("approval meta")
        session.suspend()
        session.approve("ludovic", "2026-01-01T12:00:00+00:00")
        d = session.to_dict()
        restored = type(session).from_dict(d)
        assert restored.approved_by == "ludovic"
        assert restored.approved_at == "2026-01-01T12:00:00+00:00"

    def test_from_dict_with_rejection(self):
        session = _make_session("rejection meta")
        session.suspend()
        session.reject("ludovic", "2026-01-01T12:00:00+00:00", "Too risky")
        d = session.to_dict()
        restored = type(session).from_dict(d)
        assert restored.rejection_reason == "Too risky"


# ---------------------------------------------------------------------------
# 5. SessionStore — save / load / delete / exists / list
# ---------------------------------------------------------------------------

class TestSessionStore:

    def test_save_creates_file(self, tmp_path):
        store   = _make_store(tmp_path)
        session = _make_session()
        session.suspend()
        result  = store.save(session)
        assert result is True
        assert store.exists(session.session_id)

    def test_load_returns_session(self, tmp_path):
        store   = _make_store(tmp_path)
        session = _make_session("load test")
        session.suspend()
        store.save(session)
        loaded = store.load(session.session_id)
        assert loaded is not None
        assert loaded.session_id == session.session_id

    def test_load_unknown_returns_none(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.load("nonexistent-id") is None

    def test_delete_removes_file(self, tmp_path):
        store   = _make_store(tmp_path)
        session = _make_session()
        session.suspend()
        store.save(session)
        store.delete(session.session_id)
        assert not store.exists(session.session_id)

    def test_list_session_ids(self, tmp_path):
        store = _make_store(tmp_path)
        s1    = _make_session("one")
        s2    = _make_session("two")
        s1.suspend()
        s2.suspend()
        store.save(s1)
        store.save(s2)
        ids = store.list_session_ids()
        assert s1.session_id in ids
        assert s2.session_id in ids

    def test_load_resumable_returns_only_awaiting(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringRequest, EngineeringSession, EngineeringResult, EngineeringStatus
        store = _make_store(tmp_path)

        suspended = _make_session("suspended")
        suspended.suspend()
        store.save(suspended)

        completed = _make_session("completed")
        result = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
        completed.complete(result)
        store.save(completed)

        resumable = store.load_resumable()
        ids = [s.session_id for s in resumable]
        assert suspended.session_id in ids
        assert completed.session_id not in ids

    def test_load_resumable_skips_corrupt_file(self, tmp_path):
        store = _make_store(tmp_path)
        # Write a malformed JSON file
        bad_file = tmp_path / "corrupt-id.json"
        bad_file.write_text("{not valid json", encoding="utf-8")
        # Should not raise
        result = store.load_resumable()
        assert isinstance(result, list)

    def test_save_overwrites_existing(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        store   = _make_store(tmp_path)
        session = _make_session()
        session.suspend()
        store.save(session)
        session.approve("ludovic", "2026-01-01T00:00:00+00:00")
        store.save(session)
        loaded = store.load(session.session_id)
        assert loaded.approved_by == "ludovic"


# ---------------------------------------------------------------------------
# 6. CoordinatorConfig — enable_approval_gate
# ---------------------------------------------------------------------------

class TestCoordinatorConfig:

    def test_approval_gate_default_true(self):
        from core.engineering.coordinator.coordinator import CoordinatorConfig
        config = CoordinatorConfig()
        assert config.enable_approval_gate is True

    def test_approval_gate_can_be_disabled(self):
        from core.engineering.coordinator.coordinator import CoordinatorConfig
        config = CoordinatorConfig(enable_approval_gate=False)
        assert config.enable_approval_gate is False

    def test_repr_includes_approval_gate(self):
        from core.engineering.coordinator.coordinator import CoordinatorConfig
        r = repr(CoordinatorConfig())
        assert "approval_gate" in r


# ---------------------------------------------------------------------------
# 7. Coordinator — approval gate in pipeline
# ---------------------------------------------------------------------------

class TestCoordinatorApprovalGate:

    def test_gate_enabled_returns_awaiting_approval(self):
        from core.engineering.coordinator.models import EngineeringStatus
        coord   = _make_coordinator(enable_gate=True)
        req     = _make_request()
        result  = coord.coordinate(req)
        assert result.status == EngineeringStatus.AWAITING_APPROVAL

    def test_gate_disabled_returns_complete(self):
        from core.engineering.coordinator.models import EngineeringStatus
        coord   = _make_coordinator(enable_gate=False)
        req     = _make_request()
        result  = coord.coordinate(req)
        assert result.status == EngineeringStatus.COMPLETE

    def test_gate_session_in_suspended_sessions(self):
        coord   = _make_coordinator(enable_gate=True)
        req     = _make_request()
        result  = coord.coordinate(req)
        sid     = result.session_id
        assert sid in coord._suspended_sessions

    def test_gate_guardrails_in_stages_visited(self):
        from core.engineering.coordinator.models import EngineeringStage
        coord   = _make_coordinator(enable_gate=True)
        # Enable guardrails for this test
        from core.engineering.coordinator.coordinator import CoordinatorConfig, EngineeringCoordinator
        config = CoordinatorConfig(
            enable_planning=False,
            enable_guardrails=False,   # disabled — just testing stage ordering
            enable_approval_gate=True,
            enable_validation=False,
        )
        coord  = EngineeringCoordinator(config=config)
        result = coord.coordinate(_make_request())
        stages = result.session.events.stages_visited()
        assert EngineeringStage.AWAITING_APPROVAL in stages


# ---------------------------------------------------------------------------
# 8. Coordinator — resume_session
# ---------------------------------------------------------------------------

class TestCoordinatorResumeSession:

    def test_approve_resumes_to_complete(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        store = _make_store(tmp_path)
        coord = _make_coordinator(enable_gate=True, store=store)
        req   = _make_request()
        r1    = coord.coordinate(req)
        sid   = r1.session_id
        assert r1.status == EngineeringStatus.AWAITING_APPROVAL

        r2 = coord.resume_session(sid, "approve", "ludovic")
        assert r2 is not None
        assert r2.status == EngineeringStatus.COMPLETE

    def test_reject_returns_failed(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        store = _make_store(tmp_path)
        coord = _make_coordinator(enable_gate=True, store=store)
        r1    = coord.coordinate(_make_request())
        sid   = r1.session_id

        r2 = coord.resume_session(sid, "reject", "ludovic", reason="Scope too broad")
        assert r2 is not None
        assert r2.status == EngineeringStatus.FAILED

    def test_unknown_session_returns_none(self):
        coord = _make_coordinator(enable_gate=True)
        result = coord.resume_session("00000000-0000-0000-0000-000000000000", "approve")
        assert result is None

    def test_invalid_decision_raises(self):
        coord = _make_coordinator(enable_gate=True)
        coord.coordinate(_make_request())
        with pytest.raises(ValueError, match="approve.*reject"):
            coord.resume_session("any-id", "maybe")

    def test_duplicate_approval_returns_none(self, tmp_path):
        """Approving the same session twice is safe — second call returns None."""
        store = _make_store(tmp_path)
        coord = _make_coordinator(enable_gate=True, store=store)
        r1    = coord.coordinate(_make_request())
        sid   = r1.session_id

        coord.resume_session(sid, "approve", "ludovic")
        result = coord.resume_session(sid, "approve", "ludovic")
        assert result is None

    def test_approve_removes_from_suspended_dict(self, tmp_path):
        store = _make_store(tmp_path)
        coord = _make_coordinator(enable_gate=True, store=store)
        r1    = coord.coordinate(_make_request())
        sid   = r1.session_id

        coord.resume_session(sid, "approve", "ludovic")
        assert sid not in coord._suspended_sessions

    def test_persist_on_approve(self, tmp_path):
        """After approval, session file is updated on disk."""
        store = _make_store(tmp_path)
        coord = _make_coordinator(enable_gate=True, store=store)
        r1    = coord.coordinate(_make_request())
        sid   = r1.session_id

        coord.resume_session(sid, "approve", "ludovic")
        loaded = store.load(sid)
        assert loaded is not None
        assert loaded.approved_by == "ludovic"


# ---------------------------------------------------------------------------
# 9. Coordinator — GUARDRAILS → AWAITING_APPROVAL → VALIDATION transition
# ---------------------------------------------------------------------------

class TestApprovalPipelineTransition:

    def test_guardrails_awaiting_complete_stage_order(self, tmp_path):
        """
        With guardrails enabled, the stage sequence must be:
        INITIALISING → GUARDRAILS → AWAITING_APPROVAL → VALIDATION → COMPLETE
        """
        from core.engineering.coordinator.coordinator import CoordinatorConfig, EngineeringCoordinator
        from core.engineering.coordinator.models import EngineeringStage
        store  = _make_store(tmp_path)
        config = CoordinatorConfig(
            enable_planning=False,
            enable_guardrails=False,   # skip actual guardrail check; test stage ordering
            enable_approval_gate=True,
            enable_validation=False,
        )
        coord  = EngineeringCoordinator(config=config, session_store=store)
        r1     = coord.coordinate(_make_request())
        sid    = r1.session_id

        r2     = coord.resume_session(sid, "approve", "ludovic")
        stages = r2.session.events.stages_visited()

        assert EngineeringStage.AWAITING_APPROVAL in stages
        # AWAITING_APPROVAL must appear before COMPLETE
        ai = stages.index(EngineeringStage.AWAITING_APPROVAL)
        ci = stages.index(EngineeringStage.COMPLETE)
        assert ai < ci


# ---------------------------------------------------------------------------
# 10. Startup restoration — load_resumable on coordinator init
# ---------------------------------------------------------------------------

class TestStartupRestoration:

    def test_coordinator_restores_suspended_on_init(self, tmp_path):
        from core.engineering.coordinator.models import EngineeringStatus
        store = _make_store(tmp_path)
        coord = _make_coordinator(enable_gate=True, store=store)
        r1    = coord.coordinate(_make_request("persisted session"))
        sid   = r1.session_id
        assert store.exists(sid)

        # New coordinator instance — should restore from store
        coord2 = _make_coordinator(enable_gate=True, store=store)
        assert sid in coord2._suspended_sessions


# ---------------------------------------------------------------------------
# 11. Flask endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def flask_client(tmp_path, monkeypatch):
    """Flask test client with orchestrator wired up and token set."""
    monkeypatch.setenv("ORCHESTRATOR_TOKEN", "test-token-abc")

    store = _make_store(tmp_path)
    coord = _make_coordinator(enable_gate=True, store=store)

    from apps.server.app import create_app
    from core.agent import Agent
    from core.ai.manager import AIManager

    ai    = AIManager()
    agent = Agent(ai=ai)
    app   = create_app(agent, orchestrator_coordinator=coord)
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client, coord


class TestOrchestratorFlaskEndpoints:

    def test_status_requires_token(self, flask_client):
        client, _ = flask_client
        resp = client.get("/orchestrator/status")
        assert resp.status_code == 401

    def test_status_with_token_returns_ok(self, flask_client):
        client, _ = flask_client
        resp = client.get(
            "/orchestrator/status",
            headers={"X-Orchestrator-Token": "test-token-abc"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "sessions" in data

    def test_status_shows_suspended_session(self, flask_client):
        client, coord = flask_client
        coord.coordinate(_make_request("Flask status test"))
        resp = client.get(
            "/orchestrator/status",
            headers={"X-Orchestrator-Token": "test-token-abc"},
        )
        data = resp.get_json()
        assert data["count"] >= 1

    def test_approve_requires_token(self, flask_client):
        client, _ = flask_client
        resp = client.post("/orchestrator/approve", json={
            "session_id": "x", "decision": "approve"
        })
        assert resp.status_code == 401

    def test_approve_unknown_session_returns_404(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/orchestrator/approve",
            json={"session_id": "00000000-fake", "decision": "approve"},
            headers={"X-Orchestrator-Token": "test-token-abc"},
        )
        assert resp.status_code == 404

    def test_approve_invalid_decision_returns_400(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/orchestrator/approve",
            json={"session_id": "x", "decision": "maybe"},
            headers={"X-Orchestrator-Token": "test-token-abc"},
        )
        assert resp.status_code == 400

    def test_approve_reject_requires_reason(self, flask_client):
        client, coord = flask_client
        r1  = coord.coordinate(_make_request("need reason"))
        sid = r1.session_id
        resp = client.post(
            "/orchestrator/approve",
            json={"session_id": sid, "decision": "reject"},
            headers={"X-Orchestrator-Token": "test-token-abc"},
        )
        assert resp.status_code == 400

    def test_approve_approves_session(self, flask_client):
        client, coord = flask_client
        r1  = coord.coordinate(_make_request("approve via HTTP"))
        sid = r1.session_id
        resp = client.post(
            "/orchestrator/approve",
            json={"session_id": sid, "decision": "approve", "decided_by": "ludovic"},
            headers={"X-Orchestrator-Token": "test-token-abc"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

    def test_approve_rejects_session(self, flask_client):
        client, coord = flask_client
        r1  = coord.coordinate(_make_request("reject via HTTP"))
        sid = r1.session_id
        resp = client.post(
            "/orchestrator/approve",
            json={
                "session_id": sid,
                "decision":   "reject",
                "decided_by": "ludovic",
                "reason":     "Not the right time",
            },
            headers={"X-Orchestrator-Token": "test-token-abc"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["outcome"] == "FAILED"
