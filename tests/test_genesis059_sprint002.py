"""
Genesis-059 Sprint-002 ? KnowledgePreclassificationStage + KnowledgeQueryStage tests.

Covers:
    KnowledgePreclassificationStage:
        - delivery questions set knowledge_query with resolved_id
        - investigation-shaped questions do NOT set knowledge_query
        - questions with concept but wrong shape do NOT set knowledge_query
        - no current_genesis in context -> knowledge_query = None
        - unresolvable concept -> knowledge_query = None

    IntentStage:
        - knowledge_query signal -> intent = read_knowledge, skips matching
        - no knowledge_query signal -> normal intent matching

    KnowledgeQueryStage:
        - no knowledge_query -> skipped
        - delivery query + known record -> answer returned, terminal
        - delivery query + unknown record -> honest no-record response
        - no project_root -> honest unavailable response

    Adversarial acceptance tests (the four-question suite + guard cases):
        - "What changed in the latest Genesis?"          -> KNOWLEDGE
        - "What did the latest Genesis deliver?"         -> KNOWLEDGE
        - "Tell me what the last Genesis delivered."     -> KNOWLEDGE
        - "What was added in the current Genesis?"       -> KNOWLEDGE
        - "Should we investigate the latest Genesis?"    -> INVESTIGATION
        - "Is the latest Genesis consistent with Git?"   -> INVESTIGATION
        - "What is the latest Genesis?"                  -> NOT KNOWLEDGE (unsupported)

    End-to-end pipeline integration:
        - delivery question routes to KnowledgeQueryStage and returns answer
        - investigation question routes to InvestigationStage
"""
from __future__ import annotations

import pathlib
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from core.mission.pipeline import (
    KnowledgePreclassificationStage,
    KnowledgeQueryStage,
    IntentStage,
    MissionRequest,
    MissionPipeline,
)
from core.mission.context import MissionContext, InterfaceMode
from core.knowledge.genesis_record import GenesisDeliveryRecord, GenesisDeliveryStore
from core.knowledge.concept_resolver import ConceptResolver

PROJECT_ROOT    = pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")
FAKE_ROOT       = pathlib.Path(r"C:\nonexistent\path")
CURRENT_GENESIS = "Genesis-058"


def _make_request(message: str) -> MissionRequest:
    from core.mission.policy import MissionCapabilityPolicy
    ctx = MissionContext.for_mission(
        session_id           = "test-session",
        permitted_workers    = MissionCapabilityPolicy.PERMITTED_WORKERS,
        knowledge_categories = MissionCapabilityPolicy.PERMITTED_KNOWLEDGE_CATEGORIES,
    )
    return MissionRequest(message=message, session_id="test-session", context=ctx)


def _state_with_genesis(genesis_id: str = CURRENT_GENESIS) -> dict:
    return {"engineering_context": {"current_genesis": genesis_id}}


# ---------------------------------------------------------------------------
# KnowledgePreclassificationStage
# ---------------------------------------------------------------------------

class TestKnowledgePreclassificationStage:

    def _run(self, message: str, genesis_id: str = CURRENT_GENESIS) -> dict:
        stage  = KnowledgePreclassificationStage()
        state  = _state_with_genesis(genesis_id)
        stage.run(_make_request(message), state)
        return state

    # Delivery questions -> knowledge_query set
    def test_what_changed_sets_knowledge_query(self):
        state = self._run("What changed in the latest Genesis?")
        assert state["knowledge_query"] is not None

    def test_what_changed_resolved_id(self):
        state = self._run("What changed in the latest Genesis?")
        assert state["knowledge_query"]["resolved_id"] == CURRENT_GENESIS

    def test_what_changed_query_type_delivery(self):
        state = self._run("What changed in the latest Genesis?")
        assert state["knowledge_query"]["query_type"] == "delivery"

    def test_what_did_deliver_sets_knowledge_query(self):
        state = self._run("What did the latest Genesis deliver?")
        assert state["knowledge_query"] is not None

    def test_tell_me_what_delivered_sets_knowledge_query(self):
        state = self._run("Tell me what the last Genesis delivered.")
        assert state["knowledge_query"] is not None

    def test_what_was_added_sets_knowledge_query(self):
        state = self._run("What was added in the current Genesis?")
        assert state["knowledge_query"] is not None

    # Investigation-shaped -> knowledge_query NOT set
    def test_investigate_latest_genesis_not_knowledge(self):
        state = self._run("Should we investigate the latest Genesis?")
        assert state["knowledge_query"] is None

    def test_consistent_latest_genesis_not_knowledge(self):
        state = self._run("Is the latest Genesis consistent with Git?")
        assert state["knowledge_query"] is None

    def test_why_latest_genesis_not_knowledge(self):
        state = self._run("Why is the latest Genesis failing?")
        assert state["knowledge_query"] is None

    # Concept resolves but not delivery-shaped -> knowledge_query NOT set
    def test_what_is_latest_genesis_not_knowledge(self):
        state = self._run("What is the latest Genesis?")
        assert state["knowledge_query"] is None

    # No concept resolved -> knowledge_query None
    def test_unrelated_question_no_knowledge_query(self):
        state = self._run("What is the capital of France?")
        assert state["knowledge_query"] is None

    # No current_genesis -> knowledge_query None
    def test_no_current_genesis_in_context(self):
        stage = KnowledgePreclassificationStage()
        state = {"engineering_context": {}}
        stage.run(_make_request("What changed in the latest Genesis?"), state)
        assert state["knowledge_query"] is None

    def test_empty_context_no_knowledge_query(self):
        stage = KnowledgePreclassificationStage()
        state = {}
        stage.run(_make_request("What changed in the latest Genesis?"), state)
        assert state["knowledge_query"] is None


# ---------------------------------------------------------------------------
# IntentStage ? knowledge_query signal
# ---------------------------------------------------------------------------

class TestIntentStageKnowledgeSignal:

    def test_knowledge_query_signal_sets_read_knowledge_intent(self):
        stage = IntentStage()
        state = {
            "knowledge_query": {"resolved_id": CURRENT_GENESIS, "query_type": "delivery"},
        }
        stage.run(_make_request("What changed in the latest Genesis?"), state)
        assert state["intent"] == "read_knowledge"

    def test_no_knowledge_query_uses_normal_matching(self):
        stage = IntentStage()
        state = {"knowledge_query": None}
        stage.run(_make_request("Is everything consistent?"), state)
        assert state["intent"] == "investigate"

    def test_knowledge_intent_skips_investigate_keywords(self):
        """Even if message contains investigate keywords, knowledge signal wins."""
        stage = IntentStage()
        state = {
            "knowledge_query": {"resolved_id": CURRENT_GENESIS, "query_type": "delivery"},
        }
        stage.run(_make_request("What changed and should we investigate?"), state)
        assert state["intent"] == "read_knowledge"


# ---------------------------------------------------------------------------
# KnowledgeQueryStage
# ---------------------------------------------------------------------------

class TestKnowledgeQueryStage:

    def test_no_knowledge_query_skipped(self):
        stage = KnowledgeQueryStage(PROJECT_ROOT)
        state = {"knowledge_query": None}
        result = stage.run(_make_request("test"), state)
        assert result.executed is False

    def test_known_record_returns_answer(self):
        stage = KnowledgeQueryStage(PROJECT_ROOT)
        state = {"knowledge_query": {"resolved_id": "Genesis-058", "query_type": "delivery"}}
        result = stage.run(_make_request("What changed?"), state)
        assert result.terminal is True
        assert "Genesis-058" in state["response_message"]

    def test_unknown_record_honest_response(self):
        stage = KnowledgeQueryStage(PROJECT_ROOT)
        state = {"knowledge_query": {"resolved_id": "Genesis-001", "query_type": "delivery"}}
        result = stage.run(_make_request("What changed?"), state)
        assert result.terminal is True
        assert "Genesis-001" in state["response_message"]
        assert "don't have" in state["response_message"].lower() or "no delivery" in state["response_message"].lower() or "record" in state["response_message"].lower()

    def test_no_project_root_honest_response(self):
        stage = KnowledgeQueryStage(None)
        state = {"knowledge_query": {"resolved_id": "Genesis-058", "query_type": "delivery"}}
        result = stage.run(_make_request("What changed?"), state)
        assert result.terminal is True
        assert "not available" in state["response_message"].lower()

    def test_unsupported_query_type_honest_response(self):
        stage = KnowledgeQueryStage(PROJECT_ROOT)
        state = {"knowledge_query": {"resolved_id": "Genesis-058", "query_type": "unknown_type"}}
        result = stage.run(_make_request("What changed?"), state)
        assert result.terminal is True


# ---------------------------------------------------------------------------
# Adversarial acceptance tests
# ---------------------------------------------------------------------------

class TestAdversarialAcceptance:
    """
    The four-question suite plus guard cases.
    Proves: resolvable concept != automatic knowledge path.
    """

    def _preclassify(self, message: str) -> dict:
        stage = KnowledgePreclassificationStage()
        state = _state_with_genesis()
        stage.run(_make_request(message), state)
        return state

    def test_what_changed_latest_genesis_is_knowledge(self):
        state = self._preclassify("What changed in the latest Genesis?")
        assert state["knowledge_query"] is not None
        assert state["knowledge_query"]["query_type"] == "delivery"

    def test_what_did_latest_genesis_deliver_is_knowledge(self):
        state = self._preclassify("What did the latest Genesis deliver?")
        assert state["knowledge_query"] is not None

    def test_tell_me_what_last_genesis_delivered_is_knowledge(self):
        state = self._preclassify("Tell me what the last Genesis delivered.")
        assert state["knowledge_query"] is not None

    def test_what_was_added_current_genesis_is_knowledge(self):
        state = self._preclassify("What was added in the current Genesis?")
        assert state["knowledge_query"] is not None

    def test_should_we_investigate_latest_genesis_is_not_knowledge(self):
        state = self._preclassify("Should we investigate the latest Genesis?")
        assert state["knowledge_query"] is None

    def test_is_latest_genesis_consistent_is_not_knowledge(self):
        state = self._preclassify("Is the latest Genesis consistent with Git?")
        assert state["knowledge_query"] is None

    def test_what_is_latest_genesis_is_not_knowledge(self):
        state = self._preclassify("What is the latest Genesis?")
        assert state["knowledge_query"] is None


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------

class TestPipelineEndToEnd:
    """
    End-to-end pipeline tests with controlled project_state.json isolation.

    These tests inject a known current_genesis by writing a temporary
    project_state.json before the test and restoring the original after.
    This prevents other tests in the suite from corrupting the state
    these tests depend on.
    """

    def _make_pipeline_with_genesis(self, genesis_id: str) -> MissionPipeline:
        """
        Build a MissionPipeline with a controlled current_genesis.
        Writes a temporary project_state.json, loads registry, restores after.
        Uses a real GenesisDeliveryStore record ? Genesis-058 is always declared.
        """
        import json
        from core.mission.registry import MissionRegistry

        ps_path = PROJECT_ROOT / "project_state.json"
        original = ps_path.read_text(encoding="utf-8-sig")
        try:
            data = json.loads(original)
            data["current_genesis"] = genesis_id
            data["current_sprint"]  = "Sprint-001"
            ps_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            mr = MissionRegistry(PROJECT_ROOT)
            mr.load()
        except Exception:
            mr = None
        finally:
            ps_path.write_text(original, encoding="utf-8")
        return MissionPipeline(mission_registry=mr, project_root=PROJECT_ROOT)

    def test_delivery_question_returns_genesis_058_answer(self):
        """
        Full chain: delivery question -> KnowledgeQueryStage -> Genesis-058 record.
        Uses controlled genesis_id=Genesis-058 so record is always in the store.
        """
        pipeline = self._make_pipeline_with_genesis("Genesis-058")
        req      = _make_request("What changed in the latest Genesis?")
        response = pipeline.process(req)
        assert response.success is True
        # KnowledgeQueryStage must have been reached
        assert "KnowledgeQueryStage" in response.stage_trace
        # Response must contain Genesis-058 delivery record content
        assert "Genesis-058" in response.message
        assert "Investigation Selection" in response.message
        assert "Sprint" in response.message
        # Must not be fallback/investigation response
        assert "I am in Mission Mode" not in response.message
        assert "INVESTIGATION" not in response.message

    def test_delivery_question_answer_contains_components(self):
        """Delivery record response contains component names."""
        pipeline = self._make_pipeline_with_genesis("Genesis-058")
        req      = _make_request("What did the latest Genesis deliver?")
        response = pipeline.process(req)
        assert response.success is True
        assert "InvestigationDescriptor" in response.message or "Components" in response.message

    def test_investigation_question_not_hijacked_by_knowledge(self):
        """
        Investigation question must NOT route to KnowledgeQueryStage
        even when it contains a resolvable genesis concept.
        """
        pipeline = self._make_pipeline_with_genesis("Genesis-058")
        req      = _make_request("Is the latest Genesis consistent with Git?")
        response = pipeline.process(req)
        assert response.success is True
        # KnowledgeQueryStage must have been skipped (not terminal)
        assert "KnowledgeQueryStage" in response.stage_trace
        # Must be investigation output, not delivery record
        assert "Investigation Selection" not in response.message
        assert (
            "INVESTIGATION" in response.message
            or "consistent" in response.message.lower()
            or "Sources" in response.message
        )
