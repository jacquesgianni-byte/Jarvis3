"""
Genesis-069 Sprint-003 — Agent Identity and Contribution Wiring Tests

Validates:
  Fix A: request.agent flows into engineering_context["agent"]
         ColdEntryStage receives correct agent and formats accordingly
  Fix B: contribution_store passed into ColdEntryStage returns contributions
  Regression: existing Sprint-001 role-formatting still correct
  Regression: commit-safety still holds
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _FakeMissionContext:
    session_id: str = "test-session"


@dataclass(frozen=True)
class _FakeMissionRequest:
    message:    str
    session_id: str = "test-session"
    context:    object = None
    agent:      str = ""


@dataclass
class _FakeDeliveryRecord:
    display_name:         str   = "Genesis-068 — Cold Entry"
    hypothesis:           str   = "A governed cold-entry layer can reconstruct genesis state."
    outcome:              str   = "Hypothesis partially proven."
    sprints:              tuple = ("Sprint-001", "Sprint-002")
    components_delivered: tuple = ("GenesisContributionStore", "ColdEntryStage")
    tests_added:          int   = 42
    commit:               str   = "bee32ff"


@dataclass
class _FakeContribution:
    agent:   str = "claude"
    role:    str = "implementation"
    summary: str = "Implemented ColdEntryStage."


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from core.mission.pipeline import (
    MissionRequest,
    ContextBuildStage,
    ColdEntryStage,
    MissionStageResult,
)


# ---------------------------------------------------------------------------
# Fix A — MissionRequest carries agent field
# ---------------------------------------------------------------------------

class TestMissionRequestAgentField:
    """MissionRequest must accept and preserve the agent field."""

    def test_agent_field_defaults_to_empty_string(self):
        from core.mission.context import MissionContext, InterfaceMode
        ctx = MissionContext(
            session_id="s1",
            interface_mode=InterfaceMode.MISSION,
            permitted_workers=frozenset(),
            knowledge_categories=frozenset(),
        )
        req = MissionRequest(message="test", session_id="s1", context=ctx)
        assert req.agent == ""

    def test_agent_field_accepts_claude(self):
        from core.mission.context import MissionContext, InterfaceMode
        ctx = MissionContext(
            session_id="s1",
            interface_mode=InterfaceMode.MISSION,
            permitted_workers=frozenset(),
            knowledge_categories=frozenset(),
        )
        req = MissionRequest(message="test", session_id="s1", context=ctx, agent="claude")
        assert req.agent == "claude"

    def test_agent_field_accepts_all_known_agents(self):
        from core.mission.context import MissionContext, InterfaceMode
        ctx = MissionContext(
            session_id="s1",
            interface_mode=InterfaceMode.MISSION,
            permitted_workers=frozenset(),
            knowledge_categories=frozenset(),
        )
        for agent in ("claude", "gpt", "jarvis", "chief", ""):
            req = MissionRequest(message="test", session_id="s1", context=ctx, agent=agent)
            assert req.agent == agent


# ---------------------------------------------------------------------------
# Fix A — ContextBuildStage wires request.agent into engineering_context
# ---------------------------------------------------------------------------

class TestContextBuildStageAgentWiring:
    """ContextBuildStage must set engineering_context["agent"] from request.agent."""

    def _run_context_build(self, agent: str) -> dict:
        stage = ContextBuildStage(mission_registry=None, project_root=None)
        state = {}
        request = _FakeMissionRequest(message="genesis record Genesis-068", agent=agent)
        stage.run(request, state)
        return state

    def test_claude_agent_in_engineering_context(self):
        state = self._run_context_build("claude")
        assert state["engineering_context"].get("agent") == "claude"

    def test_gpt_agent_in_engineering_context(self):
        state = self._run_context_build("gpt")
        assert state["engineering_context"].get("agent") == "gpt"

    def test_jarvis_agent_in_engineering_context(self):
        state = self._run_context_build("jarvis")
        assert state["engineering_context"].get("agent") == "jarvis"

    def test_chief_agent_in_engineering_context(self):
        state = self._run_context_build("chief")
        assert state["engineering_context"].get("agent") == "chief"

    def test_empty_agent_not_set_in_engineering_context(self):
        state = self._run_context_build("")
        # Empty agent should not be stored (condition: if getattr(request, "agent", ""))
        assert state["engineering_context"].get("agent", "") == ""


# ---------------------------------------------------------------------------
# Fix A — ColdEntryStage receives agent identity and formats correctly
# ---------------------------------------------------------------------------

class TestColdEntryStageAgentFormatting:
    """ColdEntryStage must produce role-specific output when agent is set."""

    RECORD       = _FakeDeliveryRecord()
    CONTRIBUTIONS = [_FakeContribution()]

    def _run_cold_entry(self, agent: str):
        project_root  = MagicMock()
        contrib_store = MagicMock()
        contrib_store.get_contributions.return_value = self.CONTRIBUTIONS
        stage = ColdEntryStage(project_root=project_root, contribution_store=contrib_store)

        ds = MagicMock()
        ds.get.return_value = self.RECORD

        state = {
            "intent": "cold_entry_query",
            "engineering_context": {
                "current_genesis": "Genesis-068",
                "agent": agent,
            },
        }
        request = _FakeMissionRequest(
            message="genesis record Genesis-068",
            agent=agent,
        )
        with patch("core.mission.pipeline.GenesisDeliveryStore", return_value=ds):
            result = stage.run(request, state)
        return result, state

    def test_jarvis_receives_state_descriptor(self):
        result, state = self._run_cold_entry("jarvis")
        assert result.terminal is True
        assert "GENESIS STATE" in state["response_message"]
        assert "State descriptor only" in state["response_message"]
        assert "NARRATIVE" not in state["response_message"]

    def test_jarvis_does_not_receive_full_delivery_section(self):
        _, state = self._run_cold_entry("jarvis")
        assert "DELIVERY" not in state["response_message"]

    def test_chief_receives_decision_surface(self):
        _, state = self._run_cold_entry("chief")
        assert "Chief view" in state["response_message"] or "chief" in state["response_message"].lower()
        assert "Hypothesis" in state["response_message"]
        assert "DELIVERY" not in state["response_message"]

    def test_chief_does_not_receive_full_delivery_section(self):
        _, state = self._run_cold_entry("chief")
        assert "DELIVERY" not in state["response_message"]

    def test_gpt_receives_full_format(self):
        _, state = self._run_cold_entry("gpt")
        assert "NARRATIVE" in state["response_message"]
        assert "DELIVERY" in state["response_message"]

    def test_claude_receives_full_format(self):
        _, state = self._run_cold_entry("claude")
        assert "NARRATIVE" in state["response_message"]
        assert "DELIVERY" in state["response_message"]

    def test_empty_agent_receives_full_format(self):
        _, state = self._run_cold_entry("")
        assert "NARRATIVE" in state["response_message"]
        assert "DELIVERY" in state["response_message"]


# ---------------------------------------------------------------------------
# Fix B — Contribution store wired: contributions visible
# ---------------------------------------------------------------------------

class TestColdEntryStageContributionVisibility:
    """With a wired contribution store, contributions must appear in output."""

    RECORD = _FakeDeliveryRecord()

    def _run_with_contributions(self, contributions):
        project_root  = MagicMock()
        contrib_store = MagicMock()
        contrib_store.get_contributions.return_value = contributions
        stage = ColdEntryStage(project_root=project_root, contribution_store=contrib_store)

        ds = MagicMock()
        ds.get.return_value = self.RECORD

        state = {
            "intent": "cold_entry_query",
            "engineering_context": {"current_genesis": "Genesis-068", "agent": "claude"},
        }
        request = _FakeMissionRequest(message="genesis record Genesis-068", agent="claude")
        with patch("core.mission.pipeline.GenesisDeliveryStore", return_value=ds):
            stage.run(request, state)
        return state

    def test_contributions_visible_when_store_wired(self):
        contributions = [
            _FakeContribution(agent="gpt",    role="architecture", summary="GPT proposal."),
            _FakeContribution(agent="claude",  role="implementation", summary="Claude impl."),
        ]
        state = self._run_with_contributions(contributions)
        assert "CONTRIBUTIONS (2)" in state["response_message"]
        assert "gpt" in state["response_message"]
        assert "claude" in state["response_message"].lower()

    def test_contribution_summary_truncated_at_120(self):
        long_summary = "X" * 200
        contributions = [_FakeContribution(summary=long_summary)]
        state = self._run_with_contributions(contributions)
        assert "..." in state["response_message"]

    def test_no_contributions_shows_none_recorded(self):
        state = self._run_with_contributions([])
        assert "none recorded" in state["response_message"].lower() or \
               "CONTRIBUTIONS: none" in state["response_message"]

    def test_contribution_store_called_with_correct_genesis_id(self):
        project_root  = MagicMock()
        contrib_store = MagicMock()
        contrib_store.get_contributions.return_value = []
        stage = ColdEntryStage(project_root=project_root, contribution_store=contrib_store)
        ds = MagicMock()
        ds.get.return_value = self.RECORD
        state = {
            "intent": "cold_entry_query",
            "engineering_context": {"current_genesis": "Genesis-068", "agent": "gpt"},
        }
        request = _FakeMissionRequest(message="genesis record Genesis-068", agent="gpt")
        with patch("core.mission.pipeline.GenesisDeliveryStore", return_value=ds):
            stage.run(request, state)
        contrib_store.get_contributions.assert_called_once_with("Genesis-068")


# ---------------------------------------------------------------------------
# Regression — Sprint-001 commit-safety still holds
# ---------------------------------------------------------------------------

class TestSprint003CommitSafetyRegression:
    """Genesis-068 misrouting must remain fixed after Sprint-003 changes."""

    from core.mission.pipeline import IntentStage

    def _run_intent(self, message: str) -> dict:
        from core.mission.pipeline import IntentStage
        stage = IntentStage()
        state = {}
        stage.run(_FakeMissionRequest(message=message), state)
        return state

    def test_cold_entry_with_commit_still_not_write(self):
        state = self._run_intent('cold entry: {"commit": "bee32ff"}')
        assert state["intent"] != "write"
        assert state["intent"] == "cold_entry_query"

    def test_genesis_record_with_commit_still_cold_entry(self):
        state = self._run_intent("genesis record commit bee32ff")
        assert state["intent"] == "cold_entry_query"

    def test_pure_write_still_fires_write(self):
        state = self._run_intent("modify pipeline.py")
        assert state["intent"] == "write"

    def test_engineering_write_still_requires_approval(self):
        state = self._run_intent("commit and push the changes")
        assert state["intent"] == "write"


# ---------------------------------------------------------------------------
# Regression — engineering_context agent does not leak into write path
# ---------------------------------------------------------------------------

class TestAgentIdentityDoesNotAffectWritePath:
    """Agent identity in engineering_context must not change write/approval behaviour."""

    def test_write_intent_with_agent_set_still_requires_approval(self):
        """ApprovalGateStage must still block write regardless of agent identity."""
        from core.mission.pipeline import ApprovalGateStage
        stage = ApprovalGateStage()
        state = {
            "intent": "write",
            "engineering_context": {"agent": "claude", "current_genesis": "Genesis-069"},
        }
        request = _FakeMissionRequest(message="modify pipeline.py", agent="claude")
        result = stage.run(request, state)
        assert result.terminal is True
        assert state.get("approval_required") is True
