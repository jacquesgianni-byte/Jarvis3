"""
Genesis-059 Sprint-003 - ContextBuildStage authority resolution tests.

Covers:
    - Git genesis label overwrites stale project_state value
    - Git sprint label overwrites stale project_state value
    - No git label retains project_state value (chore commit)
    - Git unavailable retains project_state value gracefully
    - No project_root skips authority resolution
    - Authority only touches current_genesis and current_sprint
    - Proof test: project_state=Genesis-055, git=Genesis-059 -> Genesis-059
    - KnowledgePreclassificationStage receives authoritative value
    - Stale Genesis-055 never reaches ConceptResolver when git says 059
    - End-to-end pipeline: stale ps + mocked git -> correct delivery record
"""
from __future__ import annotations

import json
import pathlib
import pytest
from unittest.mock import MagicMock, patch

from core.mission.pipeline import (
    ContextBuildStage,
    KnowledgePreclassificationStage,
    MissionPipeline,
    MissionRequest,
)
from core.mission.context import MissionContext, InterfaceMode
from core.mission.policy import MissionCapabilityPolicy

PROJECT_ROOT = pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")


def _make_request(message: str) -> MissionRequest:
    ctx = MissionContext.for_mission(
        session_id           = "test-session",
        permitted_workers    = MissionCapabilityPolicy.PERMITTED_WORKERS,
        knowledge_categories = MissionCapabilityPolicy.PERMITTED_KNOWLEDGE_CATEGORIES,
    )
    return MissionRequest(message=message, session_id="test-session", context=ctx)


def _stale_registry(genesis="Genesis-055", sprint="Sprint-003"):
    registry = MagicMock()
    registry.mission_dict.return_value = {
        "current_genesis": genesis,
        "current_sprint":  sprint,
        "current_mission": "Test Mission",
        "tests_passed":    100,
    }
    return registry


class TestContextBuildStageAuthority:

    def test_git_genesis_overwrites_project_state(self):
        stage = ContextBuildStage(_stale_registry(), PROJECT_ROOT)
        state = {}
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = "Genesis-059 Sprint-002 - Authority flow"
            stage.run(_make_request("test"), state)
        assert state["engineering_context"]["current_genesis"] == "Genesis-059"

    def test_git_sprint_overwrites_project_state(self):
        stage = ContextBuildStage(_stale_registry(), PROJECT_ROOT)
        state = {}
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = "Genesis-059 Sprint-002 - Authority flow"
            stage.run(_make_request("test"), state)
        assert state["engineering_context"]["current_sprint"] == "Sprint-002"

    def test_no_git_label_retains_project_state_value(self):
        stage = ContextBuildStage(_stale_registry("Genesis-057", "Sprint-001"), PROJECT_ROOT)
        state = {}
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = "chore: update gitignore"
            stage.run(_make_request("test"), state)
        assert state["engineering_context"]["current_genesis"] == "Genesis-057"

    def test_git_unavailable_retains_project_state_value(self):
        stage = ContextBuildStage(_stale_registry("Genesis-057", "Sprint-001"), PROJECT_ROOT)
        state = {}
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.side_effect = Exception("git not available")
            stage.run(_make_request("test"), state)
        assert state["engineering_context"]["current_genesis"] == "Genesis-057"

    def test_no_project_root_retains_project_state_value(self):
        stage = ContextBuildStage(_stale_registry("Genesis-057", "Sprint-001"), project_root=None)
        state = {}
        stage.run(_make_request("test"), state)
        assert state["engineering_context"]["current_genesis"] == "Genesis-057"

    def test_authority_does_not_affect_other_fields(self):
        stage = ContextBuildStage(_stale_registry(), PROJECT_ROOT)
        state = {}
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = "Genesis-059 Sprint-002 - fix"
            stage.run(_make_request("test"), state)
        assert state["engineering_context"]["current_mission"] == "Test Mission"
        assert state["engineering_context"]["tests_passed"] == 100


class TestAuthorityProof:

    def test_stale_project_state_git_wins(self):
        """THE PROOF TEST: project_state=Genesis-055, git=Genesis-059 -> Genesis-059."""
        stage = ContextBuildStage(_stale_registry("Genesis-055", "Sprint-003"), PROJECT_ROOT)
        state = {}
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = (
                "Genesis-059 Sprint-002 - KnowledgePreclassificationStage wired"
            )
            stage.run(_make_request("test"), state)
        assert state["engineering_context"]["current_genesis"] == "Genesis-059"
        assert state["engineering_context"]["current_sprint"]  == "Sprint-002"

    def test_knowledge_preclassification_receives_authoritative_genesis(self):
        """After authority applied, KnowledgePreclassificationStage resolves correctly."""
        state = {
            "engineering_context": {
                "current_genesis": "Genesis-059",
                "current_sprint":  "Sprint-002",
            }
        }
        preclassify = KnowledgePreclassificationStage()
        preclassify.run(_make_request("What changed in the latest Genesis?"), state)
        assert state["knowledge_query"] is not None
        assert state["knowledge_query"]["resolved_id"] == "Genesis-059"

    def test_stale_genesis_055_does_not_reach_concept_resolver(self):
        """When authority applied, Genesis-055 never reaches ConceptResolver."""
        stage = ContextBuildStage(_stale_registry("Genesis-055", "Sprint-003"), PROJECT_ROOT)
        state = {}
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = "Genesis-059 Sprint-002 - fix"
            stage.run(_make_request("test"), state)
        preclassify = KnowledgePreclassificationStage()
        preclassify.run(_make_request("What changed in the latest Genesis?"), state)
        resolved = state["knowledge_query"]["resolved_id"] if state["knowledge_query"] else None
        assert resolved != "Genesis-055"
        assert resolved == "Genesis-059"


class TestPipelineAuthorityEndToEnd:

    def _make_pipeline_with_stale_ps(self, ps_genesis: str) -> MissionPipeline:
        import json
        from core.mission.registry import MissionRegistry
        ps_path = PROJECT_ROOT / "project_state.json"
        original = ps_path.read_text(encoding="utf-8-sig")
        try:
            data = json.loads(original)
            data["current_genesis"] = ps_genesis
            ps_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            mr = MissionRegistry(PROJECT_ROOT)
            mr.load()
        finally:
            ps_path.write_text(original, encoding="utf-8")
        return MissionPipeline(mission_registry=mr, project_root=PROJECT_ROOT)

    def test_delivery_question_uses_git_authoritative_genesis(self):
        """
        project_state says Genesis-055, git says Genesis-058.
        Delivery question must resolve to Genesis-058 (has a store record).
        """
        pipeline = self._make_pipeline_with_stale_ps("Genesis-055")
        req = _make_request("What changed in the latest Genesis?")
        with patch("core.mission.pipeline.ReadOnlyGitReader") as MockGit:
            MockGit.return_value.head_message.return_value = (
                "Genesis-058 Sprint-003 - Selector wired"
            )
            response = pipeline.process(req)
        assert response.success is True
        assert "Genesis-058" in response.message
        assert "Investigation Selection" in response.message
