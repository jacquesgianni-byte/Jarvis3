"""
Genesis-068 Sprint-002 - GenesisContributionStore tests.

Covers:
    Authority table:
        - Known agents are claude, gpt, jarvis, chief
        - Each agent has correct permitted roles
        - Unknown agent is rejected
        - Known agent with wrong role is rejected

    GenesisContribution:
        - Fields accessible
        - Immutable
        - to_dict / from_dict round-trip

    GenesisContributionStore.contribute():
        - Valid contribution returns success + contribution_id
        - Unknown agent returns failure
        - Wrong role for agent returns failure
        - Contribution is persisted (survives store reload)
        - Two contributions to same genesis accumulate in order
        - Two contributions to different genesis ids are isolated
        - contribution_id is a non-empty string
        - timestamp is an ISO-8601 string

    GenesisContributionStore.get_contributions():
        - Returns empty list for unknown genesis_id (never raises)
        - Returns contributions in append order
        - Each element is a GenesisContribution

    GenesisContributionStore.permitted_roles():
        - Returns correct tuple for known agent
        - Returns empty tuple for unknown agent

    GenesisContributionStore.known_agents():
        - Returns list containing all four agents
"""
from __future__ import annotations

import pathlib
import tempfile
import pytest

from core.knowledge.genesis_contributions import (
    GenesisContribution,
    GenesisContributionStore,
    ContributeResult,
    _AUTHORITY_TABLE,
    _check_authority,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    """Fresh GenesisContributionStore in a temp directory."""
    return GenesisContributionStore(tmp_path)


GENESIS_ID = "Genesis-068"


# ---------------------------------------------------------------------------
# Authority table
# ---------------------------------------------------------------------------

class TestAuthorityTable:

    def test_claude_in_table(self):
        assert "claude" in _AUTHORITY_TABLE

    def test_gpt_in_table(self):
        assert "gpt" in _AUTHORITY_TABLE

    def test_jarvis_in_table(self):
        assert "jarvis" in _AUTHORITY_TABLE

    def test_chief_in_table(self):
        assert "chief" in _AUTHORITY_TABLE

    def test_claude_roles(self):
        assert "implementation" in _AUTHORITY_TABLE["claude"]
        assert "critique" in _AUTHORITY_TABLE["claude"]

    def test_gpt_roles(self):
        assert "architecture" in _AUTHORITY_TABLE["gpt"]
        assert "critique" in _AUTHORITY_TABLE["gpt"]

    def test_jarvis_roles(self):
        assert "execution" in _AUTHORITY_TABLE["jarvis"]
        assert "observation" in _AUTHORITY_TABLE["jarvis"]

    def test_chief_roles(self):
        assert "decision" in _AUTHORITY_TABLE["chief"]
        assert "observation" in _AUTHORITY_TABLE["chief"]

    def test_unknown_agent_rejected(self):
        err = _check_authority("rogue", "implementation")
        assert err is not None
        assert "rogue" in err

    def test_wrong_role_rejected(self):
        # claude cannot claim architecture (that is gpt's role)
        err = _check_authority("claude", "architecture")
        assert err is not None
        assert "claude" in err

    def test_valid_returns_none(self):
        assert _check_authority("claude", "implementation") is None
        assert _check_authority("gpt", "architecture") is None
        assert _check_authority("jarvis", "execution") is None
        assert _check_authority("chief", "decision") is None


# ---------------------------------------------------------------------------
# GenesisContribution dataclass
# ---------------------------------------------------------------------------

class TestGenesisContribution:

    def _make(self) -> GenesisContribution:
        return GenesisContribution(
            contribution_id = "test-uuid-001",
            genesis_id      = GENESIS_ID,
            agent           = "claude",
            role            = "implementation",
            summary         = "Implemented the contribution store.",
            artifact        = "core/knowledge/genesis_contributions.py",
            timestamp       = "2026-09-02T00:00:00+00:00",
        )

    def test_fields_accessible(self):
        c = self._make()
        assert c.contribution_id == "test-uuid-001"
        assert c.genesis_id      == GENESIS_ID
        assert c.agent           == "claude"
        assert c.role            == "implementation"
        assert c.summary         == "Implemented the contribution store."
        assert c.artifact        == "core/knowledge/genesis_contributions.py"
        assert c.timestamp       == "2026-09-02T00:00:00+00:00"

    def test_immutable(self):
        c = self._make()
        with pytest.raises((AttributeError, TypeError)):
            c.agent = "gpt"

    def test_to_dict_round_trip(self):
        c = self._make()
        d = c.to_dict()
        c2 = GenesisContribution.from_dict(d)
        assert c2.contribution_id == c.contribution_id
        assert c2.agent           == c.agent
        assert c2.role            == c.role
        assert c2.summary         == c.summary
        assert c2.artifact        == c.artifact

    def test_to_dict_has_all_keys(self):
        c = self._make()
        d = c.to_dict()
        for key in ("contribution_id", "genesis_id", "agent", "role",
                    "summary", "artifact", "timestamp"):
            assert key in d


# ---------------------------------------------------------------------------
# GenesisContributionStore.contribute()
# ---------------------------------------------------------------------------

class TestContribute:

    def test_valid_contribution_succeeds(self, store):
        result = store.contribute(
            genesis_id = GENESIS_ID,
            agent      = "claude",
            role       = "implementation",
            summary    = "Wrote the contribution store.",
        )
        assert result.success is True
        assert result.error   == ""

    def test_valid_contribution_returns_id(self, store):
        result = store.contribute(
            genesis_id = GENESIS_ID,
            agent      = "gpt",
            role       = "architecture",
            summary    = "Proposed the GenesisRecord architecture.",
        )
        assert isinstance(result.contribution_id, str)
        assert len(result.contribution_id) > 0

    def test_unknown_agent_fails(self, store):
        result = store.contribute(
            genesis_id = GENESIS_ID,
            agent      = "rogue",
            role       = "implementation",
            summary    = "Should not be written.",
        )
        assert result.success is False
        assert result.contribution_id == ""
        assert "rogue" in result.error

    def test_wrong_role_fails(self, store):
        result = store.contribute(
            genesis_id = GENESIS_ID,
            agent      = "jarvis",
            role       = "architecture",   # jarvis cannot claim architecture
            summary    = "Should not be written.",
        )
        assert result.success is False
        assert "jarvis" in result.error

    def test_contribution_persists(self, store):
        store.contribute(
            genesis_id = GENESIS_ID,
            agent      = "claude",
            role       = "implementation",
            summary    = "Persisted contribution.",
        )
        # Reload from same data_dir
        store2 = GenesisContributionStore(store._dir.parent)
        contribs = store2.get_contributions(GENESIS_ID)
        assert len(contribs) == 1
        assert contribs[0].agent == "claude"

    def test_two_contributions_accumulate(self, store):
        store.contribute(GENESIS_ID, "claude", "implementation", "First.")
        store.contribute(GENESIS_ID, "gpt",    "architecture",   "Second.")
        contribs = store.get_contributions(GENESIS_ID)
        assert len(contribs) == 2
        assert contribs[0].agent == "claude"
        assert contribs[1].agent == "gpt"

    def test_different_genesis_ids_isolated(self, store):
        store.contribute("Genesis-067", "claude", "implementation", "Old genesis.")
        store.contribute("Genesis-068", "gpt",    "architecture",   "New genesis.")
        assert len(store.get_contributions("Genesis-067")) == 1
        assert len(store.get_contributions("Genesis-068")) == 1
        assert store.get_contributions("Genesis-067")[0].agent == "claude"
        assert store.get_contributions("Genesis-068")[0].agent == "gpt"

    def test_contribution_id_is_uuid_shaped(self, store):
        result = store.contribute(GENESIS_ID, "jarvis", "execution", "Ran the suite.")
        # UUID4 has 36 chars with hyphens
        assert len(result.contribution_id) == 36
        assert "-" in result.contribution_id

    def test_timestamp_is_iso8601(self, store):
        store.contribute(GENESIS_ID, "chief", "decision", "Approved sprint.")
        contribs = store.get_contributions(GENESIS_ID)
        ts = contribs[0].timestamp
        assert "T" in ts
        assert "+" in ts or "Z" in ts or ts.endswith("00:00")

    def test_artifact_defaults_to_empty_string(self, store):
        store.contribute(GENESIS_ID, "claude", "critique", "Reviewed architecture.")
        contribs = store.get_contributions(GENESIS_ID)
        assert contribs[0].artifact == ""

    def test_artifact_stored_when_provided(self, store):
        store.contribute(
            GENESIS_ID, "gpt", "architecture", "Full proposal.",
            artifact="genesis_record_proposal.md",
        )
        contribs = store.get_contributions(GENESIS_ID)
        assert contribs[0].artifact == "genesis_record_proposal.md"


# ---------------------------------------------------------------------------
# GenesisContributionStore.get_contributions()
# ---------------------------------------------------------------------------

class TestGetContributions:

    def test_unknown_genesis_returns_empty_list(self, store):
        result = store.get_contributions("Genesis-999")
        assert result == []

    def test_returns_list(self, store):
        store.contribute(GENESIS_ID, "claude", "implementation", "Did work.")
        result = store.get_contributions(GENESIS_ID)
        assert isinstance(result, list)

    def test_elements_are_genesis_contributions(self, store):
        store.contribute(GENESIS_ID, "claude", "implementation", "Did work.")
        result = store.get_contributions(GENESIS_ID)
        assert all(isinstance(c, GenesisContribution) for c in result)

    def test_append_order_preserved(self, store):
        store.contribute(GENESIS_ID, "gpt",    "architecture",   "First.")
        store.contribute(GENESIS_ID, "claude", "implementation", "Second.")
        store.contribute(GENESIS_ID, "jarvis", "execution",      "Third.")
        contribs = store.get_contributions(GENESIS_ID)
        assert contribs[0].agent == "gpt"
        assert contribs[1].agent == "claude"
        assert contribs[2].agent == "jarvis"


# ---------------------------------------------------------------------------
# GenesisContributionStore.permitted_roles() + known_agents()
# ---------------------------------------------------------------------------

class TestMetadata:

    def test_permitted_roles_claude(self, store):
        roles = store.permitted_roles("claude")
        assert "implementation" in roles
        assert "critique" in roles

    def test_permitted_roles_unknown_agent(self, store):
        assert store.permitted_roles("rogue") == ()

    def test_known_agents_contains_all_four(self, store):
        agents = store.known_agents()
        for expected in ("claude", "gpt", "jarvis", "chief"):
            assert expected in agents

    def test_known_agents_returns_list(self, store):
        assert isinstance(store.known_agents(), list)
