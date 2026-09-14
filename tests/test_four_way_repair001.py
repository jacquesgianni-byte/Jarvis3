"""
Four-Way Workflow Reliability — Repair 001 regression tests.

Test 1 — Success path:
    A successful Jarvis sprint execution must write a governed contribution
    through GenesisContributionStore.contribute(), persist it, and make it
    retrievable via get_contributions(). Summary must contain structured
    test-count evidence.

Test 2 — Failed execution cannot write:
    A failed execution must NOT write to GenesisContributionStore.
    Chief governance rule: only successes enter the record.
"""

import json
import pathlib
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.knowledge.genesis_contributions import GenesisContributionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: pathlib.Path) -> GenesisContributionStore:
    return GenesisContributionStore(tmp_path)


def _make_step_result(action_type="run_tests", success=True,
                      detail="6131 passed, 33 skipped, 0 failed",
                      commit_sha="056a784"):
    r = MagicMock()
    r.step_number = 1
    r.action_type = action_type
    r.success     = success
    r.detail      = detail
    r.commit_sha  = commit_sha
    return r


def _write_sprint_state(tmp_path: pathlib.Path, genesis_id: str,
                        proposal_id: str) -> pathlib.Path:
    """
    Write a minimal sprint state JSON that _run_sprint_execution can read.
    Includes a valid stored_proposal so BoundSprintProposal reconstruction succeeds.
    """
    state_dir = tmp_path / "data"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / f"{proposal_id}.json"
    state_file.write_text(json.dumps({
        "genesis_id": genesis_id,
        "stored_proposal": {
            "proposal_id":           proposal_id,
            "genesis_id":            genesis_id,
            "created_at":            datetime.now(timezone.utc).isoformat(),
            "template_id":           "test_template",
            "proposed_sprint_name":  "Test Sprint",
            "rationale":             "Test rationale",
            "evidence_summary":      "Test evidence",
            "gap_observation_count": 1,
            "recurring_question":    "Test question",
            "steps":                 [],
            "acceptance_criteria":   [],
            "not_doing":             [],
            "evidence_sources":      [],
            "objective_text":        "",
            "objective_score":       0,
            "objective_confidence":  "NONE",
        },
    }), encoding="utf-8")
    return state_dir


def _run(proposal_id, tmp_path, store, sprint_store, gap_store, step_results, success):
    """
    Run _run_sprint_execution with SprintExecutor patched at its source module
    so the local import inside the function picks up the mock.
    """
    mock_executor = MagicMock()
    mock_executor.execute.return_value = (success, step_results)

    # SprintExecutor is imported inside _run_sprint_execution as:
    #   from core.knowledge.sprint_executor import SprintExecutor
    # Patch it at the source so the local import gets the mock.
    with patch("core.knowledge.sprint_executor.SprintExecutor",
               return_value=mock_executor) as _mock_cls:
        # Make SprintExecutor(proposal, project_root) return mock_executor
        _mock_cls.return_value = mock_executor

        from apps.server.sprint_routes import _run_sprint_execution
        _run_sprint_execution(
            proposal_id        = proposal_id,
            project_root       = tmp_path,
            sprint_store       = sprint_store,
            gap_store          = gap_store,
            contribution_store = store,
        )


# ---------------------------------------------------------------------------
# Test 1 — Successful execution writes a Jarvis contribution
# ---------------------------------------------------------------------------

def test_repair001_successful_execution_writes_contribution(tmp_path):
    """
    Repair 001: a successful Jarvis sprint execution must write a governed
    contribution through GenesisContributionStore.contribute(), and that
    contribution must be retrievable with correct fields and test-count evidence.
    """
    genesis_id  = "Genesis-081"
    proposal_id = str(uuid.uuid4())

    store     = _make_store(tmp_path)
    state_dir = _write_sprint_state(tmp_path, genesis_id, proposal_id)

    step_results = [_make_step_result(
        action_type="run_tests",
        success=True,
        detail="6131 passed, 33 skipped, 0 failed",
        commit_sha="056a784",
    )]

    mock_record = MagicMock()
    mock_record.execution_trace = []
    mock_record.contributions   = []

    mock_sprint_store = MagicMock()
    mock_sprint_store._path_for.return_value = state_dir / f"{proposal_id}.json"
    mock_sprint_store.load.return_value      = mock_record

    _run(proposal_id, tmp_path, store, mock_sprint_store, MagicMock(),
         step_results, success=True)

    # --- Verify persistence through real store API ---
    contributions = store.get_contributions(genesis_id)
    assert len(contributions) == 1, (
        f"Expected 1 contribution, got {len(contributions)}"
    )

    c = contributions[0]
    assert c.agent      == "jarvis",    f"agent: {c.agent!r}"
    assert c.role       == "execution", f"role: {c.role!r}"
    assert c.genesis_id == genesis_id,  f"genesis_id: {c.genesis_id!r}"

    # Summary must contain structured execution evidence
    assert "tests_passed=6131" in c.summary, (
        f"summary missing test counts: {c.summary!r}"
    )
    assert "tests_skipped=33"  in c.summary, (
        f"summary missing skipped count: {c.summary!r}"
    )
    assert "056a784" in c.artifact or "056a784" in c.summary, (
        f"commit ref missing — artifact={c.artifact!r} summary={c.summary!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Failed execution must NOT write a contribution
# ---------------------------------------------------------------------------

def test_repair001_failed_execution_does_not_write_contribution(tmp_path):
    """
    Repair 001: a failed sprint execution must NOT write to GenesisContributionStore.
    Chief governance rule: only successes enter the governed record.
    """
    genesis_id  = "Genesis-081"
    proposal_id = str(uuid.uuid4())

    store     = _make_store(tmp_path)
    state_dir = _write_sprint_state(tmp_path, genesis_id, proposal_id)

    step_results = [_make_step_result(
        action_type="run_tests",
        success=False,
        detail="1 failed",
        commit_sha="",
    )]

    mock_record = MagicMock()
    mock_record.execution_trace = []
    mock_record.contributions   = []

    mock_sprint_store = MagicMock()
    mock_sprint_store._path_for.return_value = state_dir / f"{proposal_id}.json"
    mock_sprint_store.load.return_value      = mock_record

    _run(proposal_id, tmp_path, store, mock_sprint_store, MagicMock(),
         step_results, success=False)

    contributions = store.get_contributions(genesis_id)
    assert len(contributions) == 0, (
        f"Expected 0 contributions after failed execution, "
        f"got {len(contributions)}: {[c.to_dict() for c in contributions]}"
    )
