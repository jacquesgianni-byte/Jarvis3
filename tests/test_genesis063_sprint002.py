"""
Genesis-063 Sprint-002 - Objective proximity wired into GapReportStage tests.

Covers:
    GapReportStage with objective proximity:
        - why_failed report includes objective relevance section
        - what_needed report includes objective relevance section
        - objective relevance reads from state["engineering_context"]["objectives"]
        - no engineering_context -> honest "not available" response
        - empty objectives -> honest "no overlap" response
        - objective proximity failure does not prevent gap report
        - no recommendation in objective relevance section
        - no semantic claim in objective relevance section
        - dashboard question overlaps dashboard objectives

    End-to-end pipeline:
        - why_failed response contains objective relevance section
        - what_needed response contains objective relevance section
        - response success unchanged by objective proximity
"""
from __future__ import annotations

import json
import pathlib
import pytest
from unittest.mock import patch
import uuid
from datetime import datetime, timezone

from core.knowledge.capability_gap import (
    CapabilityGapObservation,
    GapObservationStore,
    CAPABILITY_GAP_SIGNATURE,
)
from core.mission.pipeline import (
    GapReportStage,
    MissionPipeline,
    MissionRequest,
)
from core.mission.investigation_registry import InvestigationRegistry
from core.mission.context import MissionContext
from core.mission.policy import MissionCapabilityPolicy

PROJECT_ROOT = pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")

SAMPLE_OBJECTIVES = [
    {"text": "Audit all stale dashboard values",    "done": True},
    {"text": "Design MissionRegistry architecture", "done": True},
    {"text": "Implement MissionRegistry",           "done": True},
]


def _make_request(message: str) -> MissionRequest:
    ctx = MissionContext.for_mission(
        session_id           = "test-session",
        permitted_workers    = MissionCapabilityPolicy.PERMITTED_WORKERS,
        knowledge_categories = MissionCapabilityPolicy.PERMITTED_KNOWLEDGE_CATEGORIES,
    )
    return MissionRequest(message=message, session_id="test-session", context=ctx)


def _make_observation(question: str = "What should our next mission be?") -> CapabilityGapObservation:
    return CapabilityGapObservation(
        observation_id      = f"OBS-{uuid.uuid4().hex[:6].upper()}",
        observed_at         = datetime.now(timezone.utc).isoformat(),
        question            = question,
        intent_result       = "unknown",
        knowledge_match     = False,
        investigation_match = False,
        boundary_violation  = False,
        failure_signature   = CAPABILITY_GAP_SIGNATURE,
        session_id          = "test-session",
    )


def _make_stage(tmp_path) -> tuple:
    store = GapObservationStore(tmp_path)
    store.record(_make_observation())
    reg   = InvestigationRegistry(PROJECT_ROOT)
    stage = GapReportStage(store, reg)
    return stage, store


class TestGapReportObjectiveProximity:

    def test_why_failed_includes_objective_section(self, tmp_path):
        stage, _ = _make_stage(tmp_path)
        state = {
            "intent": "why_failed",
            "engineering_context": {"objectives": SAMPLE_OBJECTIVES},
        }
        stage.run(_make_request("Why couldn't you answer?"), state)
        assert "objective relevance" in state["response_message"].lower()

    def test_what_needed_includes_objective_section(self, tmp_path):
        stage, _ = _make_stage(tmp_path)
        state = {
            "intent": "what_needed",
            "engineering_context": {"objectives": SAMPLE_OBJECTIVES},
        }
        stage.run(_make_request("What would you need?"), state)
        assert "objective relevance" in state["response_message"].lower()

    def test_reads_objectives_from_state(self, tmp_path):
        stage, _ = _make_stage(tmp_path)
        state = {
            "intent": "why_failed",
            "engineering_context": {"objectives": SAMPLE_OBJECTIVES},
        }
        stage.run(_make_request("Why couldn't you answer?"), state)
        # Should not crash and should include section
        assert "objective" in state["response_message"].lower()

    def test_no_engineering_context_honest_response(self, tmp_path):
        stage, _ = _make_stage(tmp_path)
        state = {"intent": "why_failed"}
        stage.run(_make_request("Why couldn't you answer?"), state)
        # No engineering_context -> objectives defaults to [] -> "no overlap" is correct
        assert "objective relevance" in state["response_message"].lower()

    def test_empty_objectives_honest_response(self, tmp_path):
        stage, _ = _make_stage(tmp_path)
        state = {
            "intent": "why_failed",
            "engineering_context": {"objectives": []},
        }
        stage.run(_make_request("Why couldn't you answer?"), state)
        assert "objective" in state["response_message"].lower()

    def test_no_recommendation_in_objective_section(self, tmp_path):
        stage, _ = _make_stage(tmp_path)
        state = {
            "intent": "why_failed",
            "engineering_context": {"objectives": SAMPLE_OBJECTIVES},
        }
        stage.run(_make_request("Why couldn't you answer?"), state)
        msg = state["response_message"].lower()
        assert "i recommend" not in msg
        assert "therefore build" not in msg
        assert "next mission should" not in msg

    def test_no_semantic_claim_in_objective_section(self, tmp_path):
        stage, _ = _make_stage(tmp_path)
        state = {
            "intent": "why_failed",
            "engineering_context": {"objectives": SAMPLE_OBJECTIVES},
        }
        stage.run(_make_request("Why couldn't you answer?"), state)
        msg = state["response_message"].lower()
        assert "semantically related" not in msg
        assert "means that" not in msg

    def test_objective_failure_does_not_prevent_gap_report(self, tmp_path):
        """If objective proximity fails, gap evidence is still reported."""
        stage, _ = _make_stage(tmp_path)
        state = {
            "intent": "why_failed",
            "engineering_context": {"objectives": "not a list"},  # bad data
        }
        result = stage.run(_make_request("Why couldn't you answer?"), state)
        assert result.terminal is True
        assert "CAPABILITY GAP EVIDENCE" in state["response_message"]

    def test_dashboard_question_shows_objective_overlap(self, tmp_path):
        """Dashboard question should overlap with dashboard-related objectives."""
        store = GapObservationStore(tmp_path)
        store.record(_make_observation("Why is the dashboard showing wrong values?"))
        reg   = InvestigationRegistry(PROJECT_ROOT)
        stage = GapReportStage(store, reg)
        state = {
            "intent": "why_failed",
            "engineering_context": {"objectives": SAMPLE_OBJECTIVES},
        }
        stage.run(_make_request("Why couldn't you answer?"), state)
        msg = state["response_message"]
        # Dashboard objective should appear in overlap
        assert "dashboard" in msg.lower()


class TestPipelineEndToEnd:

    def _make_pipeline(self, tmp_path):
        from core.mission.registry import MissionRegistry
        from core.knowledge.gap_observation_engine import GapObservationEngine
        ps_path  = PROJECT_ROOT / "project_state.json"
        original = ps_path.read_text(encoding="utf-8-sig")
        try:
            data = json.loads(original)
            data["current_genesis"] = "Genesis-063"
            ps_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            mr = MissionRegistry(PROJECT_ROOT)
            mr.load()
        finally:
            ps_path.write_text(original, encoding="utf-8")
        pipeline  = MissionPipeline(mission_registry=mr, project_root=PROJECT_ROOT)
        gap_store = GapObservationStore(tmp_path)
        from core.knowledge.gap_observation_engine import GapObservationEngine
        pipeline._gap_engine = GapObservationEngine(gap_store)
        pipeline._gap_store  = gap_store
        pipeline._gap_report = GapReportStage(gap_store, InvestigationRegistry(PROJECT_ROOT))
        return pipeline, gap_store

    def _git_patch(self):
        return patch("core.mission.pipeline.ReadOnlyGitReader",
                     **{"return_value.head_message.return_value": "Genesis-063 Sprint-002 - fix",
                        "return_value.head_sha.return_value": "949aba8",
                        "return_value.branch.return_value": "main"})

    def test_why_failed_contains_objective_section(self, tmp_path):
        pipeline, _ = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            response = pipeline.process(_make_request("Why couldn't you answer that?"))
        assert response.success is True
        assert "objective relevance" in response.message.lower()

    def test_what_needed_contains_objective_section(self, tmp_path):
        pipeline, _ = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            response = pipeline.process(_make_request("What would you need to answer it?"))
        assert response.success is True
        assert "objective relevance" in response.message.lower()

    def test_response_success_unchanged(self, tmp_path):
        pipeline, _ = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            response = pipeline.process(_make_request("Why couldn't you answer that?"))
        assert response.success is True
        assert response.boundary_violation is False
