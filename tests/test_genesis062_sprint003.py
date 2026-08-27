"""
Genesis-062 Sprint-003 - CapabilityInventoryStage tests.

Covers:
    IntentStage:
        - "what can you do" classifies as capability_inventory
        - "what investigations can you run" classifies as capability_inventory
        - "what are your capabilities" classifies as capability_inventory
        - existing intents unaffected

    CapabilityInventoryStage:
        - skipped when intent is not capability_inventory
        - returns terminal result when intent is capability_inventory
        - report contains all registered investigation names
        - report contains investigation descriptions
        - report contains genesis delivery record names
        - report contains no hardcoded capability claims
        - report generated from registry (not developer prose)
        - no registry available -> honest response
        - no delivery store available -> honest response

    Pipeline end-to-end:
        - "what can you do" routes to CapabilityInventoryStage
        - response contains registered investigation names
        - response success is True
"""
from __future__ import annotations

import json
import pathlib
import pytest
from unittest.mock import patch

from core.mission.pipeline import (
    CapabilityInventoryStage,
    IntentStage,
    MissionPipeline,
    MissionRequest,
)
from core.mission.investigation_registry import InvestigationRegistry
from core.knowledge.genesis_record import GenesisDeliveryStore
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


class TestIntentCapabilityInventory:

    def _classify(self, message: str) -> str:
        stage = IntentStage()
        state = {"knowledge_query": None}
        stage.run(_make_request(message), state)
        return state["intent"]

    def test_what_can_you_do(self):
        assert self._classify("What can you do?") == "capability_inventory"

    def test_what_investigations_can_you_run(self):
        assert self._classify("What investigations can you run?") == "capability_inventory"

    def test_what_are_your_capabilities(self):
        assert self._classify("What are your capabilities?") == "capability_inventory"

    def test_list_your_capabilities(self):
        assert self._classify("List your capabilities.") == "capability_inventory"

    def test_what_can_you_investigate(self):
        assert self._classify("What can you investigate?") == "capability_inventory"

    def test_investigate_still_works(self):
        assert self._classify("Is everything consistent?") == "investigate"

    def test_why_failed_still_works(self):
        assert self._classify("Why couldn't you answer that?") == "why_failed"


class TestCapabilityInventoryStage:

    def _make_stage(self):
        reg   = InvestigationRegistry(PROJECT_ROOT)
        store = GenesisDeliveryStore(PROJECT_ROOT)
        return CapabilityInventoryStage(reg, store)

    def test_skipped_when_wrong_intent(self):
        stage  = self._make_stage()
        state  = {"intent": "investigate"}
        result = stage.run(_make_request("test"), state)
        assert result.executed is False

    def test_terminal_when_capability_inventory(self):
        stage  = self._make_stage()
        state  = {"intent": "capability_inventory"}
        result = stage.run(_make_request("What can you do?"), state)
        assert result.terminal is True

    def test_report_contains_investigation_names(self):
        stage = self._make_stage()
        state = {"intent": "capability_inventory"}
        stage.run(_make_request("What can you do?"), state)
        msg = state["response_message"]
        assert "project_state_vs_git" in msg
        assert "mission_registry_consistency" in msg
        assert "test_health" in msg
        assert "roadmap_vs_state" in msg

    def test_report_contains_descriptions(self):
        stage = self._make_stage()
        state = {"intent": "capability_inventory"}
        stage.run(_make_request("What can you do?"), state)
        msg = state["response_message"]
        assert "project_state.json" in msg.lower() or "git" in msg.lower()

    def test_report_contains_delivery_records(self):
        stage = self._make_stage()
        state = {"intent": "capability_inventory"}
        stage.run(_make_request("What can you do?"), state)
        msg = state["response_message"]
        assert "Genesis-058" in msg or "Genesis-061" in msg

    def test_report_no_hardcoded_claims(self):
        stage = self._make_stage()
        state = {"intent": "capability_inventory"}
        stage.run(_make_request("What can you do?"), state)
        msg = state["response_message"].lower()
        # Must not contain developer-written capability promises
        assert "i can do anything" not in msg
        assert "jarvis is capable of" not in msg

    def test_report_notes_evidence_source(self):
        stage = self._make_stage()
        state = {"intent": "capability_inventory"}
        stage.run(_make_request("What can you do?"), state)
        assert "registered evidence" in state["response_message"].lower()

    def test_no_registry_honest_response(self):
        stage = CapabilityInventoryStage(registry=None, delivery_store=None)
        state = {"intent": "capability_inventory"}
        result = stage.run(_make_request("What can you do?"), state)
        assert result.terminal is True
        assert "not available" in state["response_message"].lower()


class TestPipelineEndToEnd:

    def _make_pipeline(self) -> MissionPipeline:
        from core.mission.registry import MissionRegistry
        ps_path  = PROJECT_ROOT / "project_state.json"
        original = ps_path.read_text(encoding="utf-8-sig")
        try:
            data = json.loads(original)
            data["current_genesis"] = "Genesis-062"
            ps_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            mr = MissionRegistry(PROJECT_ROOT)
            mr.load()
        finally:
            ps_path.write_text(original, encoding="utf-8")
        return MissionPipeline(mission_registry=mr, project_root=PROJECT_ROOT)

    def _git_patch(self):
        return patch("core.mission.pipeline.ReadOnlyGitReader",
                     **{"return_value.head_message.return_value": "Genesis-062 Sprint-003 - fix",
                        "return_value.head_sha.return_value": "9684321",
                        "return_value.branch.return_value": "main"})

    def test_what_can_you_do_routes_to_inventory(self):
        pipeline = self._make_pipeline()
        with self._git_patch():
            response = pipeline.process(_make_request("What can you do?"))
        assert response.success is True
        assert "CAPABILITY INVENTORY" in response.message

    def test_response_contains_investigation_names(self):
        pipeline = self._make_pipeline()
        with self._git_patch():
            response = pipeline.process(_make_request("What investigations can you run?"))
        assert "project_state_vs_git" in response.message
        assert "test_health" in response.message

    def test_response_success_true(self):
        pipeline = self._make_pipeline()
        with self._git_patch():
            response = pipeline.process(_make_request("What are your capabilities?"))
        assert response.success is True
        assert response.boundary_violation is False
