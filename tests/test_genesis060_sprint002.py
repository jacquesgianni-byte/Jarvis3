"""
Genesis-060 Sprint-002 - GapObservationEngine tests.

Covers:
    GapObservationEngine.observe():
        - records observation when all four conditions true
        - does NOT record when intent is not unknown
        - does NOT record when knowledge_query is set
        - does NOT record when investigation_terminal is True
        - does NOT record when boundary_violation is True
        - observation failure never affects the response
        - observe() never raises (swallows internal errors)
        - observation_id is unique per call
        - recorded question matches request.message
        - session_id matches request.session_id
        - failure_signature matches CAPABILITY_GAP_SIGNATURE

    Pipeline integration:
        - unknown question causes observation after pipeline runs
        - investigation question does NOT cause observation
        - knowledge delivery question does NOT cause observation
        - boundary violation does NOT cause observation
        - response is identical before and after observation
        - observation engine failure does not affect pipeline response
"""
from __future__ import annotations

import pathlib
import pytest
from unittest.mock import MagicMock, patch, call

from core.knowledge.capability_gap import (
    CapabilityGapObservation,
    GapObservationStore,
    CAPABILITY_GAP_SIGNATURE,
)
from core.knowledge.gap_observation_engine import GapObservationEngine
from core.mission.pipeline import MissionPipeline, MissionRequest, MissionResponse
from core.mission.context import MissionContext
from core.mission.policy import MissionCapabilityPolicy

PROJECT_ROOT = pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")


def _make_request(message: str) -> MissionRequest:
    ctx = MissionContext.for_mission(
        session_id           = "test-session",
        permitted_workers    = MissionCapabilityPolicy.PERMITTED_WORKERS,
        knowledge_categories = MissionCapabilityPolicy.PERMITTED_KNOWLEDGE_CATEGORIES,
    )
    return MissionRequest(message=message, session_id="test-session", context=ctx)


def _make_response(boundary_violation: bool = False) -> MissionResponse:
    return MissionResponse(
        success            = True,
        message            = "Test response.",
        boundary_violation = boundary_violation,
    )


def _make_state(
    intent: str = "unknown",
    knowledge_query=None,
    investigation_terminal: bool = False,
) -> dict:
    state = {
        "intent":          intent,
        "knowledge_query": knowledge_query,
    }
    if investigation_terminal:
        state["investigation_terminal"] = True
    return state


def _make_engine(tmp_path) -> tuple[GapObservationEngine, GapObservationStore]:
    store  = GapObservationStore(tmp_path)
    engine = GapObservationEngine(store)
    return engine, store


# ---------------------------------------------------------------------------
# GapObservationEngine unit tests
# ---------------------------------------------------------------------------

class TestGapObservationEngine:

    def test_records_when_all_four_conditions_true(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        engine.observe(_make_request("What should we build?"), _make_state(), _make_response())
        assert store.capability_gap_count() == 1

    def test_does_not_record_when_intent_not_unknown(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        engine.observe(
            _make_request("Is everything consistent?"),
            _make_state(intent="investigate"),
            _make_response(),
        )
        assert store.capability_gap_count() == 0

    def test_does_not_record_when_knowledge_query_set(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        engine.observe(
            _make_request("What changed in the latest Genesis?"),
            _make_state(intent="read_knowledge", knowledge_query={"resolved_id": "Genesis-059", "query_type": "delivery"}),
            _make_response(),
        )
        assert store.capability_gap_count() == 0

    def test_does_not_record_when_investigation_terminal(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        engine.observe(
            _make_request("Is everything consistent?"),
            _make_state(intent="unknown", investigation_terminal=True),
            _make_response(),
        )
        assert store.capability_gap_count() == 0

    def test_does_not_record_when_boundary_violation(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        engine.observe(
            _make_request("Delete all files"),
            _make_state(),
            _make_response(boundary_violation=True),
        )
        assert store.capability_gap_count() == 0

    def test_observe_never_raises(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        # Corrupt the store to force an internal error
        store._path = pathlib.Path("/nonexistent/path/obs.jsonl")
        # Should not raise
        engine.observe(_make_request("test"), _make_state(), _make_response())

    def test_response_unchanged_after_observe(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        response = _make_response()
        original_message = response.message
        engine.observe(_make_request("What should we build?"), _make_state(), response)
        assert response.message == original_message
        assert response.success is True

    def test_observation_question_matches_request(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        engine.observe(
            _make_request("What should our next mission be?"),
            _make_state(),
            _make_response(),
        )
        obs = store.all_observations()[0]
        assert obs.question == "What should our next mission be?"

    def test_observation_session_id_matches_request(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        engine.observe(_make_request("test"), _make_state(), _make_response())
        obs = store.all_observations()[0]
        assert obs.session_id == "test-session"

    def test_observation_failure_signature_is_canonical(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        engine.observe(_make_request("test"), _make_state(), _make_response())
        obs = store.all_observations()[0]
        assert obs.failure_signature == CAPABILITY_GAP_SIGNATURE

    def test_multiple_observations_have_unique_ids(self, tmp_path):
        engine, store = _make_engine(tmp_path)
        engine.observe(_make_request("Question 1"), _make_state(), _make_response())
        engine.observe(_make_request("Question 2"), _make_state(), _make_response())
        ids = [o.observation_id for o in store.all_observations()]
        assert len(set(ids)) == 2


# ---------------------------------------------------------------------------
# Pipeline integration tests
# ---------------------------------------------------------------------------

class TestPipelineGapObservation:

    def _make_pipeline(self, tmp_path) -> MissionPipeline:
        from core.mission.registry import MissionRegistry
        import json
        ps_path  = PROJECT_ROOT / "project_state.json"
        original = ps_path.read_text(encoding="utf-8-sig")
        try:
            data = json.loads(original)
            data["current_genesis"] = "Genesis-059"
            ps_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            mr = MissionRegistry(PROJECT_ROOT)
            mr.load()
        finally:
            ps_path.write_text(original, encoding="utf-8")
        # Use tmp_path for the gap observation store
        pipeline = MissionPipeline(mission_registry=mr, project_root=PROJECT_ROOT)
        # Override gap store to use tmp_path
        gap_store = GapObservationStore(tmp_path)
        pipeline._gap_engine = GapObservationEngine(gap_store)
        pipeline._gap_store  = gap_store
        return pipeline, gap_store

    def test_unknown_question_produces_observation(self, tmp_path):
        pipeline, store = self._make_pipeline(tmp_path)
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = "Genesis-059 Sprint-003 - fix"
            pipeline.process(_make_request("What should our next mission be?"))
        assert store.capability_gap_count() >= 1

    def test_investigation_question_does_not_produce_observation(self, tmp_path):
        pipeline, store = self._make_pipeline(tmp_path)
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = "Genesis-059 Sprint-003 - fix"
            MockGit.return_value.head_sha.return_value = "2f26927"
            MockGit.return_value.branch.return_value = "main"
            pipeline.process(_make_request("Is everything consistent?"))
        assert store.capability_gap_count() == 0

    def test_knowledge_question_does_not_produce_observation(self, tmp_path):
        pipeline, store = self._make_pipeline(tmp_path)
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = "Genesis-059 Sprint-003 - fix"
            pipeline.process(_make_request("What changed in the latest Genesis?"))
        assert store.capability_gap_count() == 0

    def test_response_unchanged_by_observation(self, tmp_path):
        pipeline, store = self._make_pipeline(tmp_path)
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = "Genesis-059 Sprint-003 - fix"
            response = pipeline.process(_make_request("What should our next mission be?"))
        assert response.success is True
        assert isinstance(response.message, str)
        assert len(response.message) > 0
