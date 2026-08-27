"""Genesis-064 Sprint-003a - SprintStateStore + SprintStateMachine tests.

Covers:
    SprintState enum:
        - all expected states exist
        - terminal states are correct

    SprintStateMachine:
        - valid transitions succeed
        - invalid transitions rejected
        - chief_action=False rejected for protected states
        - chief_action=True accepted for protected states
        - terminal states have no outgoing transitions
        - transition record appended on success
        - state unchanged on failure

    SprintStateRecord:
        - is_terminal correct for all states
        - requires_chief_action correct for protected states
        - to_dict / from_dict round-trip

    SprintStateStore:
        - create() produces PROPOSED record
        - load() returns None for unknown proposal
        - transition() persists state to disk
        - load() after restart returns correct state
        - EXECUTING on restart -> INTERRUPTED (restart safety)
        - VALIDATING on restart -> INTERRUPTED (restart safety)
        - PROPOSED on restart -> PROPOSED (no interruption)
        - APPROVED on restart -> APPROVED (no interruption)
        - COMPLETED on restart -> COMPLETED (terminal, no change)
        - simulated crash at every boundary
        - all_active() excludes terminal records
        - all_records() includes all
        - tolerates corrupt files
"""
from __future__ import annotations

import json
import pathlib
import pytest

from core.knowledge.sprint_state import (
    SprintState,
    SprintStateMachine,
    SprintStateRecord,
    SprintStateStore,
    TransitionResult,
    _CHIEF_REQUIRED,
    _TRANSITIONS,
)


def _store(tmp_path) -> SprintStateStore:
    return SprintStateStore(tmp_path)


class TestSprintStateEnum:

    def test_all_states_exist(self):
        states = {s.value for s in SprintState}
        for expected in ("proposed", "approved", "executing", "validating",
                         "awaiting_result_review", "completed", "rejected",
                         "failed", "interrupted"):
            assert expected in states

    def test_terminal_states(self):
        terminal = {SprintState.COMPLETED, SprintState.REJECTED,
                    SprintState.FAILED, SprintState.INTERRUPTED}
        for s in terminal:
            assert _TRANSITIONS[s] == (), f"{s.value} should have no transitions"

    def test_non_terminal_states_have_transitions(self):
        non_terminal = {SprintState.PROPOSED, SprintState.APPROVED,
                        SprintState.EXECUTING, SprintState.VALIDATING,
                        SprintState.AWAITING_RESULT_REVIEW}
        for s in non_terminal:
            assert len(_TRANSITIONS[s]) > 0, f"{s.value} should have transitions"


class TestSprintStateMachine:

    def _record(self, state=SprintState.PROPOSED) -> SprintStateRecord:
        import uuid
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        return SprintStateRecord(proposal_id=str(uuid.uuid4())[:8],
            current_state=state.value, created_at=now, updated_at=now)

    def test_valid_transition_proposed_to_approved(self):
        m   = SprintStateMachine()
        rec = self._record(SprintState.PROPOSED)
        r   = m.transition(rec, SprintState.APPROVED, "Chief approved", chief_action=True)
        assert r.success is True
        assert rec.current_state == SprintState.APPROVED.value

    def test_valid_transition_approved_to_executing(self):
        m   = SprintStateMachine()
        rec = self._record(SprintState.APPROVED)
        r   = m.transition(rec, SprintState.EXECUTING, "Chief triggered", chief_action=True)
        assert r.success is True
        assert rec.current_state == SprintState.EXECUTING.value

    def test_invalid_transition_proposed_to_executing(self):
        m   = SprintStateMachine()
        rec = self._record(SprintState.PROPOSED)
        r   = m.transition(rec, SprintState.EXECUTING, "skip", chief_action=True)
        assert r.success is False
        assert rec.current_state == SprintState.PROPOSED.value

    def test_invalid_transition_proposed_to_completed(self):
        m   = SprintStateMachine()
        rec = self._record(SprintState.PROPOSED)
        r   = m.transition(rec, SprintState.COMPLETED, "skip", chief_action=True)
        assert r.success is False

    def test_chief_required_rejected_without_chief_action(self):
        m   = SprintStateMachine()
        rec = self._record(SprintState.PROPOSED)
        r   = m.transition(rec, SprintState.APPROVED, "auto", chief_action=False)
        assert r.success is False
        assert "Chief action" in r.error or "chief" in r.error.lower()
        assert rec.current_state == SprintState.PROPOSED.value

    def test_chief_required_for_all_protected_states(self):
        m = SprintStateMachine()
        for s in _CHIEF_REQUIRED:
            rec = self._record(s)
            # Try any valid next state without chief_action
            allowed = _TRANSITIONS.get(s, ())
            if allowed:
                r = m.transition(rec, allowed[0], "auto", chief_action=False)
                assert r.success is False, f"{s.value} should require chief action"

    def test_terminal_states_reject_all_transitions(self):
        m = SprintStateMachine()
        for terminal in (SprintState.COMPLETED, SprintState.REJECTED,
                         SprintState.FAILED, SprintState.INTERRUPTED):
            rec = self._record(terminal)
            for target in SprintState:
                if target != terminal:
                    r = m.transition(rec, target, "test", chief_action=True)
                    assert r.success is False, f"{terminal.value} -> {target.value} should be rejected"

    def test_transition_appends_to_audit_trail(self):
        m   = SprintStateMachine()
        rec = self._record(SprintState.PROPOSED)
        assert len(rec.transitions) == 0
        m.transition(rec, SprintState.APPROVED, "Chief approved", chief_action=True)
        assert len(rec.transitions) == 1
        assert rec.transitions[0]["from_state"] == "proposed"
        assert rec.transitions[0]["to_state"]   == "approved"
        assert rec.transitions[0]["chief_action"] is True

    def test_failed_transition_does_not_append_to_trail(self):
        m   = SprintStateMachine()
        rec = self._record(SprintState.PROPOSED)
        m.transition(rec, SprintState.EXECUTING, "invalid", chief_action=True)
        assert len(rec.transitions) == 0

    def test_full_happy_path_transitions(self):
        m   = SprintStateMachine()
        rec = self._record(SprintState.PROPOSED)
        m.transition(rec, SprintState.APPROVED,             "L1", chief_action=True)
        m.transition(rec, SprintState.EXECUTING,            "L2", chief_action=True)
        m.transition(rec, SprintState.VALIDATING,           "auto", chief_action=False)
        m.transition(rec, SprintState.AWAITING_RESULT_REVIEW, "auto", chief_action=False)
        m.transition(rec, SprintState.COMPLETED,            "L3", chief_action=True)
        assert rec.current_state == SprintState.COMPLETED.value
        assert len(rec.transitions) == 5


class TestSprintStateRecord:

    def _rec(self, state: SprintState) -> SprintStateRecord:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        return SprintStateRecord(proposal_id="TEST",
            current_state=state.value, created_at=now, updated_at=now)

    def test_is_terminal_true_for_terminal_states(self):
        for s in (SprintState.COMPLETED, SprintState.REJECTED,
                  SprintState.FAILED, SprintState.INTERRUPTED):
            assert self._rec(s).is_terminal is True

    def test_is_terminal_false_for_active_states(self):
        for s in (SprintState.PROPOSED, SprintState.APPROVED,
                  SprintState.EXECUTING, SprintState.VALIDATING,
                  SprintState.AWAITING_RESULT_REVIEW):
            assert self._rec(s).is_terminal is False

    def test_requires_chief_action_for_protected_states(self):
        for s in _CHIEF_REQUIRED:
            assert self._rec(s).requires_chief_action is True

    def test_does_not_require_chief_for_executing(self):
        assert self._rec(SprintState.EXECUTING).requires_chief_action is False

    def test_to_dict_from_dict_round_trip(self):
        rec = self._rec(SprintState.PROPOSED)
        d   = rec.to_dict()
        rec2 = SprintStateRecord.from_dict(d)
        assert rec2.proposal_id   == rec.proposal_id
        assert rec2.current_state == rec.current_state


class TestSprintStateStore:

    def test_create_produces_proposed(self, tmp_path):
        store  = _store(tmp_path)
        record = store.create("PROP-001")
        assert record.current_state == SprintState.PROPOSED.value

    def test_create_persists_to_disk(self, tmp_path):
        store = _store(tmp_path)
        store.create("PROP-002")
        assert (tmp_path / "sprint_states" / "PROP-002.json").exists()

    def test_load_unknown_returns_none(self, tmp_path):
        store = _store(tmp_path)
        assert store.load("NONEXISTENT") is None

    def test_transition_persists_state(self, tmp_path):
        store = _store(tmp_path)
        store.create("PROP-003")
        result = store.transition("PROP-003", SprintState.APPROVED,
            "Chief approved", chief_action=True)
        assert result.success is True
        record = store.load("PROP-003")
        assert record.current_state == SprintState.APPROVED.value

    def test_load_after_restart_returns_correct_state(self, tmp_path):
        store1 = _store(tmp_path)
        store1.create("PROP-004")
        store1.transition("PROP-004", SprintState.APPROVED,
            "Chief approved", chief_action=True)
        # Simulate restart -- new store instance
        store2 = _store(tmp_path)
        record = store2.load("PROP-004")
        assert record.current_state == SprintState.APPROVED.value

    # -------------------------------------------------------------------
    # Restart safety tests -- the critical invariant
    # -------------------------------------------------------------------

    def test_executing_on_restart_becomes_interrupted(self, tmp_path):
        """CRITICAL: Server restart during EXECUTING must produce INTERRUPTED."""
        store1 = _store(tmp_path)
        store1.create("PROP-005")
        store1.transition("PROP-005", SprintState.APPROVED, "L1", chief_action=True)
        # Manually write EXECUTING state to simulate crash mid-execution
        path = tmp_path / "sprint_states" / "PROP-005.json"
        data = json.loads(path.read_text())
        data["current_state"] = SprintState.EXECUTING.value
        path.write_text(json.dumps(data))
        # New store instance simulates restart
        store2 = _store(tmp_path)
        record = store2.load("PROP-005")
        assert record.current_state == SprintState.INTERRUPTED.value

    def test_validating_on_restart_becomes_interrupted(self, tmp_path):
        store1 = _store(tmp_path)
        store1.create("PROP-006")
        path = tmp_path / "sprint_states" / "PROP-006.json"
        data = json.loads(path.read_text())
        data["current_state"] = SprintState.VALIDATING.value
        path.write_text(json.dumps(data))
        store2 = _store(tmp_path)
        record = store2.load("PROP-006")
        assert record.current_state == SprintState.INTERRUPTED.value

    def test_proposed_on_restart_stays_proposed(self, tmp_path):
        store1 = _store(tmp_path)
        store1.create("PROP-007")
        store2 = _store(tmp_path)
        record = store2.load("PROP-007")
        assert record.current_state == SprintState.PROPOSED.value

    def test_approved_on_restart_stays_approved(self, tmp_path):
        store1 = _store(tmp_path)
        store1.create("PROP-008")
        store1.transition("PROP-008", SprintState.APPROVED, "L1", chief_action=True)
        store2 = _store(tmp_path)
        record = store2.load("PROP-008")
        assert record.current_state == SprintState.APPROVED.value

    def test_completed_on_restart_stays_completed(self, tmp_path):
        store1 = _store(tmp_path)
        store1.create("PROP-009")
        path = tmp_path / "sprint_states" / "PROP-009.json"
        data = json.loads(path.read_text())
        data["current_state"] = SprintState.COMPLETED.value
        path.write_text(json.dumps(data))
        store2 = _store(tmp_path)
        record = store2.load("PROP-009")
        assert record.current_state == SprintState.COMPLETED.value

    def test_interrupted_state_requires_no_chief_action_to_enter(self, tmp_path):
        """INTERRUPTED is entered automatically on restart -- not Chief action."""
        store1 = _store(tmp_path)
        store1.create("PROP-010")
        path = tmp_path / "sprint_states" / "PROP-010.json"
        data = json.loads(path.read_text())
        data["current_state"] = SprintState.EXECUTING.value
        path.write_text(json.dumps(data))
        store2 = _store(tmp_path)
        record = store2.load("PROP-010")
        # Transition to INTERRUPTED was automatic -- no Chief action required
        interrupted_tr = [t for t in record.transitions if t["to_state"] == "interrupted"]
        assert len(interrupted_tr) == 1
        assert interrupted_tr[0]["chief_action"] is False

    # Simulated crash at every important boundary

    def test_crash_after_proposal_creation(self, tmp_path):
        """Crash immediately after PROPOSED -- restart returns PROPOSED."""
        store1 = _store(tmp_path)
        store1.create("PROP-CRASH-1")
        # No transition -- crash here
        store2 = _store(tmp_path)
        record = store2.load("PROP-CRASH-1")
        assert record.current_state == SprintState.PROPOSED.value
        assert record.requires_chief_action is True

    def test_crash_after_layer1_approval(self, tmp_path):
        """Crash after APPROVED -- restart returns APPROVED, not EXECUTING."""
        store1 = _store(tmp_path)
        store1.create("PROP-CRASH-2")
        store1.transition("PROP-CRASH-2", SprintState.APPROVED, "L1", chief_action=True)
        # Crash here -- no execution triggered
        store2 = _store(tmp_path)
        record = store2.load("PROP-CRASH-2")
        assert record.current_state == SprintState.APPROVED.value
        assert record.requires_chief_action is True  # Still needs L2

    def test_crash_before_execution(self, tmp_path):
        """Crash immediately before execution triggered -- stays APPROVED."""
        store = _store(tmp_path)
        store.create("PROP-CRASH-3")
        store.transition("PROP-CRASH-3", SprintState.APPROVED, "L1", chief_action=True)
        # Restart before L2 is tapped
        store2 = _store(tmp_path)
        record = store2.load("PROP-CRASH-3")
        assert record.current_state == SprintState.APPROVED.value

    def test_crash_during_execution(self, tmp_path):
        """Crash during EXECUTING -- restart returns INTERRUPTED."""
        store = _store(tmp_path)
        store.create("PROP-CRASH-4")
        path = tmp_path / "sprint_states" / "PROP-CRASH-4.json"
        data = json.loads(path.read_text())
        data["current_state"] = SprintState.EXECUTING.value
        path.write_text(json.dumps(data))
        store2 = _store(tmp_path)
        record = store2.load("PROP-CRASH-4")
        assert record.current_state == SprintState.INTERRUPTED.value

    def test_crash_after_execution_before_validation(self, tmp_path):
        """Crash after execution but before VALIDATING -- returns INTERRUPTED."""
        store = _store(tmp_path)
        store.create("PROP-CRASH-5")
        path = tmp_path / "sprint_states" / "PROP-CRASH-5.json"
        data = json.loads(path.read_text())
        data["current_state"] = SprintState.VALIDATING.value
        path.write_text(json.dumps(data))
        store2 = _store(tmp_path)
        record = store2.load("PROP-CRASH-5")
        assert record.current_state == SprintState.INTERRUPTED.value

    def test_crash_after_validation_before_layer3(self, tmp_path):
        """Crash in AWAITING_RESULT_REVIEW -- restart stays there."""
        store = _store(tmp_path)
        store.create("PROP-CRASH-6")
        path = tmp_path / "sprint_states" / "PROP-CRASH-6.json"
        data = json.loads(path.read_text())
        data["current_state"] = SprintState.AWAITING_RESULT_REVIEW.value
        path.write_text(json.dumps(data))
        store2 = _store(tmp_path)
        record = store2.load("PROP-CRASH-6")
        # AWAITING_RESULT_REVIEW is not in _INTERRUPT_ON_RESTART
        assert record.current_state == SprintState.AWAITING_RESULT_REVIEW.value
        assert record.requires_chief_action is True

    def test_all_active_excludes_terminal(self, tmp_path):
        store = _store(tmp_path)
        store.create("ACTIVE-1")
        store.create("TERM-1")
        path = tmp_path / "sprint_states" / "TERM-1.json"
        data = json.loads(path.read_text())
        data["current_state"] = SprintState.COMPLETED.value
        path.write_text(json.dumps(data))
        active = store.all_active()
        ids = [r.proposal_id for r in active]
        assert "ACTIVE-1" in ids
        assert "TERM-1" not in ids

    def test_all_records_includes_all(self, tmp_path):
        store = _store(tmp_path)
        store.create("ALL-1")
        store.create("ALL-2")
        records = store.all_records()
        ids = [r.proposal_id for r in records]
        assert "ALL-1" in ids
        assert "ALL-2" in ids

    def test_tolerates_corrupt_file(self, tmp_path):
        store = _store(tmp_path)
        bad   = tmp_path / "sprint_states" / "BAD.json"
        bad.write_text("not json", encoding="utf-8")
        assert store.load("BAD") is None
        assert store.all_records() == []  # corrupt file skipped