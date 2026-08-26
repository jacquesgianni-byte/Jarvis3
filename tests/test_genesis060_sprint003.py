"""
Genesis-060 Sprint-003 - GapReportStage tests.

Covers:
    GapReportStage:
        - skipped when intent is not why_failed or what_needed
        - store unavailable returns honest response
        - why_failed with no observations returns honest response
        - why_failed with one observation reports evidence, not recurring
        - why_failed with two+ observations reports recurring gap
        - what_needed with no observations returns honest response
        - what_needed derives missing capability from evidence signals
        - report content derived from stored evidence not developer sentences
        - terminal=True when reporting
        - GapReportStage never creates observations
        - GapReportStage never modifies the store

    IntentStage gap-report intent classification:
        - why_failed phrases classify correctly
        - what_needed phrases classify correctly
        - why_failed does not match investigate keywords
        - what_needed does not match investigate keywords

    End-to-end acceptance experiment:
        - "What should our next mission be?" -> gap observation recorded
        - "Why couldn't you answer that?" -> evidence trail returned
        - "What would you need to answer it?" -> derived requirement returned
        - No developer sentence "Jarvis cannot recommend missions" in any response
"""
from __future__ import annotations

import json
import pathlib
import pytest
from unittest.mock import patch

from core.knowledge.capability_gap import (
    CapabilityGapObservation,
    GapObservationStore,
    CAPABILITY_GAP_SIGNATURE,
)
from core.mission.pipeline import (
    GapReportStage,
    IntentStage,
    MissionPipeline,
    MissionRequest,
    MissionStageResult,
)
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
    import uuid
    from datetime import datetime, timezone
    sig = CAPABILITY_GAP_SIGNATURE
    return CapabilityGapObservation(
        observation_id      = f"OBS-{uuid.uuid4().hex[:6].upper()}",
        observed_at         = datetime.now(timezone.utc).isoformat(),
        question            = question,
        intent_result       = "unknown",
        knowledge_match     = False,
        investigation_match = False,
        boundary_violation  = False,
        failure_signature   = sig,
        session_id          = "test-session",
    )


class TestGapReportStage:

    def test_skipped_when_intent_not_gap_report(self, tmp_path):
        store = GapObservationStore(tmp_path)
        stage = GapReportStage(store)
        state = {"intent": "investigate"}
        result = stage.run(_make_request("Is everything consistent?"), state)
        assert result.executed is False

    def test_skipped_when_intent_unknown(self, tmp_path):
        store = GapObservationStore(tmp_path)
        stage = GapReportStage(store)
        state = {"intent": "unknown"}
        result = stage.run(_make_request("Something unknown"), state)
        assert result.executed is False

    def test_store_unavailable_honest_response(self):
        stage = GapReportStage(gap_store=None)
        state = {"intent": "why_failed"}
        result = stage.run(_make_request("Why couldn't you answer that?"), state)
        assert result.terminal is True
        assert "not available" in state["response_message"].lower()

    def test_why_failed_no_observations(self, tmp_path):
        store = GapObservationStore(tmp_path)
        stage = GapReportStage(store)
        state = {"intent": "why_failed"}
        result = stage.run(_make_request("Why couldn't you answer that?"), state)
        assert result.terminal is True
        assert "no recorded" in state["response_message"].lower()

    def test_why_failed_one_observation_not_recurring(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        stage = GapReportStage(store)
        state = {"intent": "why_failed"}
        stage.run(_make_request("Why couldn't you answer that?"), state)
        assert "single observation" in state["response_message"].lower() or "not yet" in state["response_message"].lower()
        assert "recurring" not in state["response_message"].lower() or "not yet" in state["response_message"].lower()

    def test_why_failed_two_observations_reports_recurring(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation("Question 1"))
        store.record(_make_observation("Question 2"))
        stage = GapReportStage(store)
        state = {"intent": "why_failed"}
        stage.run(_make_request("Why couldn't you answer that?"), state)
        assert "recurring" in state["response_message"].lower()
        assert "2" in state["response_message"]

    def test_why_failed_contains_failure_signature(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        stage = GapReportStage(store)
        state = {"intent": "why_failed"}
        stage.run(_make_request("Why couldn't you answer?"), state)
        assert "intent=unknown" in state["response_message"]

    def test_why_failed_contains_original_question(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation("What should our next mission be?"))
        stage = GapReportStage(store)
        state = {"intent": "why_failed"}
        stage.run(_make_request("Why couldn't you answer?"), state)
        assert "What should our next mission be?" in state["response_message"]

    def test_what_needed_no_observations(self, tmp_path):
        store = GapObservationStore(tmp_path)
        stage = GapReportStage(store)
        state = {"intent": "what_needed"}
        stage.run(_make_request("What would you need?"), state)
        assert "no recorded" in state["response_message"].lower()

    def test_what_needed_derives_from_evidence(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        stage = GapReportStage(store)
        state = {"intent": "what_needed"}
        stage.run(_make_request("What would you need to answer it?"), state)
        msg = state["response_message"]
        # Must contain evidence-derived content
        assert "investigation" in msg.lower() or "knowledge" in msg.lower()
        # Must contain approval boundary statement
        assert "approval" in msg.lower()

    def test_what_needed_no_developer_hardcoded_sentence(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        stage = GapReportStage(store)
        state = {"intent": "what_needed"}
        stage.run(_make_request("What would you need?"), state)
        # Must NOT contain hardcoded developer capability descriptions
        assert "cannot recommend missions" not in state["response_message"].lower()
        assert "jarvis can't" not in state["response_message"].lower()

    def test_gap_report_stage_never_adds_to_store(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        initial_count = store.capability_gap_count()
        stage = GapReportStage(store)
        state = {"intent": "why_failed"}
        stage.run(_make_request("Why couldn't you?"), state)
        assert store.capability_gap_count() == initial_count

    def test_terminal_true_when_reporting(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        stage = GapReportStage(store)
        state = {"intent": "why_failed"}
        result = stage.run(_make_request("Why?"), state)
        assert result.terminal is True


class TestIntentStageGapKeywords:

    def _classify(self, message: str) -> str:
        stage = IntentStage()
        state = {"knowledge_query": None}
        stage.run(_make_request(message), state)
        return state["intent"]

    def test_why_couldnt_you_classifies_why_failed(self):
        assert self._classify("Why couldn't you answer that?") == "why_failed"

    def test_why_cant_you_answer_classifies_why_failed(self):
        assert self._classify("Why can't you answer my question?") == "why_failed"

    def test_what_went_wrong_classifies_why_failed(self):
        assert self._classify("What went wrong?") == "why_failed"

    def test_what_would_you_need_classifies_what_needed(self):
        assert self._classify("What would you need to answer it?") == "what_needed"

    def test_whats_missing_classifies_what_needed(self):
        assert self._classify("What's missing from your knowledge?") == "what_needed"

    def test_what_capability_classifies_what_needed(self):
        assert self._classify("What capability would be needed?") == "what_needed"

    def test_investigate_still_classifies_correctly(self):
        assert self._classify("Is everything consistent?") == "investigate"


class TestAcceptanceExperiment:
    """
    The full CAA acceptance experiment:
    1. Ask a question Jarvis cannot answer
    2. Ask why it couldn't answer
    3. Ask what it would need
    Verify all responses are evidence-derived, not developer-written.
    """

    def _make_pipeline(self, tmp_path) -> tuple:
        from core.mission.registry import MissionRegistry
        from core.knowledge.gap_observation_engine import GapObservationEngine

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

        pipeline  = MissionPipeline(mission_registry=mr, project_root=PROJECT_ROOT)
        gap_store = GapObservationStore(tmp_path)
        pipeline._gap_engine = GapObservationEngine(gap_store)
        pipeline._gap_store  = gap_store
        pipeline._gap_report = GapReportStage(gap_store)
        return pipeline, gap_store

    def _git_patch(self):
        return patch("core.mission.pipeline.ReadOnlyGitReader",
                     **{"return_value.head_message.return_value":
                        "Genesis-059 Sprint-003 - fix",
                        "return_value.head_sha.return_value": "2f26927",
                        "return_value.branch.return_value": "main"})

    def test_step1_unknown_question_records_observation(self, tmp_path):
        pipeline, store = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
        assert store.capability_gap_count() >= 1

    def test_step2_why_failed_returns_evidence(self, tmp_path):
        pipeline, store = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            response = pipeline.process(_make_request("Why couldn't you answer that?"))
        assert response.success is True
        assert "intent=unknown" in response.message
        assert "CAPABILITY GAP EVIDENCE" in response.message

    def test_step3_what_needed_returns_derived_requirement(self, tmp_path):
        pipeline, store = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            pipeline.process(_make_request("Why couldn't you answer that?"))
            response = pipeline.process(_make_request("What would you need to answer it?"))
        assert response.success is True
        assert "DERIVED CAPABILITY REQUIREMENT" in response.message
        assert "approval" in response.message.lower()

    def test_no_developer_hardcoded_mission_sentence(self, tmp_path):
        pipeline, store = self._make_pipeline(tmp_path)
        with self._git_patch():
            pipeline.process(_make_request("What should our next mission be?"))
            r2 = pipeline.process(_make_request("Why couldn't you answer that?"))
            r3 = pipeline.process(_make_request("What would you need to answer it?"))
        for response in [r2, r3]:
            assert "cannot recommend missions" not in response.message.lower()
            assert "jarvis can\'t" not in response.message.lower()
