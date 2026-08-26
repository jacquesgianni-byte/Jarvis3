"""
Genesis-061 Sprint-002 - GapReportStage proximity wiring tests.

Covers:
    GapReportStage with registry:
        - why_failed report includes proximity section when observation exists
        - what_needed report includes proximity section when observation exists
        - proximity section absent when no observations (not manufactured)
        - proximity section absent when registry is None
        - proximity failure does not prevent report (graceful degradation)
        - report still contains gap evidence alongside proximity
        - no semantic label in proximity section of report
        - isolated gap reported as ISOLATED in proximity section
        - proximity analysis uses most recent observation question

    MissionPipeline wiring:
        - GapReportStage has registry after pipeline construction
        - two InvestigationRegistry instances share same catalogue

    End-to-end:
        - why_failed response contains proximity audit trail
        - what_needed response contains proximity audit trail
        - mission question produces ISOLATED proximity result in report
"""
from __future__ import annotations

import json
import pathlib
import pytest
from unittest.mock import patch, MagicMock
import uuid
from datetime import datetime, timezone

from core.knowledge.capability_gap import (
    CapabilityGapObservation,
    GapObservationStore,
    CAPABILITY_GAP_SIGNATURE,
)
from core.knowledge.proximity import CapabilityProximityAnalyser, ProximityResult
from core.mission.pipeline import (
    GapReportStage,
    MissionPipeline,
    MissionRequest,
)
from core.mission.investigation_registry import InvestigationRegistry
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


def _make_stage_with_obs(tmp_path, question="What should our next mission be?"):
    store    = GapObservationStore(tmp_path)
    store.record(_make_observation(question))
    registry = InvestigationRegistry(PROJECT_ROOT)
    stage    = GapReportStage(store, registry)
    return stage, store


class TestGapReportStageProximity:

    def test_why_failed_includes_proximity_when_observation_exists(self, tmp_path):
        stage, _ = _make_stage_with_obs(tmp_path)
        state    = {"intent": "why_failed"}
        stage.run(_make_request("Why couldn't you answer?"), state)
        assert "Proximity analysis" in state["response_message"] or "audit trail" in state["response_message"].lower()

    def test_what_needed_includes_proximity_when_observation_exists(self, tmp_path):
        stage, _ = _make_stage_with_obs(tmp_path)
        state    = {"intent": "what_needed"}
        stage.run(_make_request("What would you need?"), state)
        assert "Proximity analysis" in state["response_message"] or "audit trail" in state["response_message"].lower()

    def test_why_failed_no_proximity_when_no_observations(self, tmp_path):
        store = GapObservationStore(tmp_path)
        stage = GapReportStage(store, InvestigationRegistry(PROJECT_ROOT))
        state = {"intent": "why_failed"}
        stage.run(_make_request("Why couldn't you answer?"), state)
        assert "no recorded" in state["response_message"].lower()

    def test_proximity_absent_when_registry_none(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        stage = GapReportStage(store, registry=None)
        state = {"intent": "why_failed"}
        stage.run(_make_request("Why?"), state)
        assert "not available" in state["response_message"].lower()

    def test_proximity_failure_does_not_prevent_report(self, tmp_path):
        store    = GapObservationStore(tmp_path)
        store.record(_make_observation())
        bad_reg  = MagicMock()
        bad_reg.all_descriptors.side_effect = Exception("registry broken")
        stage = GapReportStage(store, bad_reg)
        state = {"intent": "why_failed"}
        result = stage.run(_make_request("Why?"), state)
        assert result.terminal is True
        assert "CAPABILITY GAP EVIDENCE" in state["response_message"]

    def test_report_contains_gap_evidence_alongside_proximity(self, tmp_path):
        stage, _ = _make_stage_with_obs(tmp_path)
        state    = {"intent": "why_failed"}
        stage.run(_make_request("Why?"), state)
        msg = state["response_message"]
        assert "intent=unknown" in msg
        assert "Proximity" in msg or "audit trail" in msg.lower()

    def test_no_semantic_label_in_proximity_section(self, tmp_path):
        stage, _ = _make_stage_with_obs(tmp_path, "What should our next mission be?")
        state    = {"intent": "why_failed"}
        stage.run(_make_request("Why?"), state)
        msg = state["response_message"].lower()
        assert "mission planning" not in msg
        assert "recommendation system" not in msg

    def test_mission_question_produces_isolated_in_report(self, tmp_path):
        stage, _ = _make_stage_with_obs(tmp_path, "What should our next mission be?")
        state    = {"intent": "why_failed"}
        stage.run(_make_request("Why?"), state)
        assert "ISOLATED" in state["response_message"]

    def test_proximity_uses_most_recent_observation_question(self, tmp_path):
        store    = GapObservationStore(tmp_path)
        store.record(_make_observation("First question"))
        store.record(_make_observation("What should our next mission be?"))
        registry = InvestigationRegistry(PROJECT_ROOT)
        stage    = GapReportStage(store, registry)
        state    = {"intent": "why_failed"}
        stage.run(_make_request("Why?"), state)
        # Most recent question should be visible in report
        assert "What should our next mission be?" in state["response_message"]


class TestPipelineRegistryWiring:

    def test_gap_report_has_registry_after_construction(self):
        from core.mission.registry import MissionRegistry
        mr = MissionRegistry(PROJECT_ROOT)
        mr.load()
        pipeline = MissionPipeline(mission_registry=mr, project_root=PROJECT_ROOT)
        assert pipeline._gap_report._registry is not None

    def test_two_registry_instances_share_same_catalogue(self):
        reg1 = InvestigationRegistry(PROJECT_ROOT)
        reg2 = InvestigationRegistry(PROJECT_ROOT)
        names1 = {d.name for d in reg1.all_descriptors()}
        names2 = {d.name for d in reg2.all_descriptors()}
        assert names1 == names2


class TestEndToEndProximity:

    def _make_pipeline(self, tmp_path):
        from core.mission.registry import MissionRegistry
        from core.knowledge.gap_observation_engine import GapObservationEngine
        ps_path  = PROJECT_ROOT / "project_state.json"
        original = ps_path.read_text(encoding="utf-8-sig")
        try:
            data = json.loads(original)
            data["current_genesis"] = "Genesis-061"
            ps_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            mr = MissionRegistry(PROJECT_ROOT)
            mr.load()
        finally:
            ps_path.write_text(original, encoding="utf-8")
        pipeline  = MissionPipeline(mission_registry=mr, project_root=PROJECT_ROOT)
        gap_store = GapObservationStore(tmp_path)
        pipeline._gap_engine = GapObservationEngine(gap_store)
        pipeline._gap_store  = gap_store
        pipeline._gap_report = GapReportStage(gap_store, InvestigationRegistry(PROJECT_ROOT))
        return pipeline, gap_store

    def _git_patch(self):
        return patch("core.mission.pipeline.ReadOnlyGitReader",
                     **{"return_value.head_message.return_value": "Genesis-061 Sprint-002 - fix",
                        "return_value.head_sha.return_value": "ca3f0ea",
                        "return_value.branch.return_value": "main"})

    def test_why_failed_contains_proximity_audit_trail(self, tmp_path):
        pipeline, _ = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            response = pipeline.process(_make_request("Why couldn't you answer that?"))
        assert response.success is True
        assert "CAPABILITY GAP EVIDENCE" in response.message
        assert "project_state_vs_git" in response.message

    def test_what_needed_contains_proximity_audit_trail(self, tmp_path):
        pipeline, _ = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            response = pipeline.process(_make_request("What would you need to answer it?"))
        assert response.success is True
        assert "project_state_vs_git" in response.message

    def test_mission_question_isolated_in_end_to_end_report(self, tmp_path):
        pipeline, _ = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            response = pipeline.process(_make_request("Why couldn't you answer that?"))
        assert "ISOLATED" in response.message

    def test_response_success_unchanged_by_proximity(self, tmp_path):
        pipeline, _ = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            response = pipeline.process(_make_request("Why couldn't you answer that?"))
        assert response.success is True
        assert response.boundary_violation is False
