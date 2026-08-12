"""
Genesis-045 Sprint-004 — Behavioural tests

Tests outcome tracking: IMPLEMENTED, VALIDATED, FAILED_VALIDATION.
All tests are deterministic and self-contained.
No network. No AI. No KnowledgeEngine I/O (stubs used).

Epistemic invariants verified:
  - IMPLEMENTED ≠ diagnosis correct ≠ problem solved
  - VALIDATED = expected improvement observed; causation NOT established
  - FAILED_VALIDATION = improvement not observed; cause uncertain
  - Evidence never erased by any outcome
  - No outcome triggers autonomous engineering action
  - FAILED_VALIDATION restores normal selector priority
  - VALIDATED reduces selector priority (grace period only)
"""

from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering.intelligence.pattern_record import (
    OutcomeStatus, ProposalOutcomeRecord, PatternRecord,
    RejectionReasonCode, RejectionRecord,
)
from core.engineering.intelligence.models import ProposalStatus
from core.engineering.intelligence.selector import (
    ImprovementSelector,
    VALIDATED_SCORE_FACTOR,
    VALIDATED_GRACE_CYCLES,
    get_suppression_cycles,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_outcome_record(
    status: OutcomeStatus,
    proposal_id: str = "G045-ROU-AABBCC",
    pattern_signature: str = "ROUTING:test pattern",
    approved_at_cycle: int = 5,
    implemented_at_cycle: int = 6,
    validated_at_cycle: Optional[int] = None,
    tests_run: int = 100,
    files_changed: int = 2,
    snapshot_sha: str = "abc12345",
) -> ProposalOutcomeRecord:
    return ProposalOutcomeRecord(
        proposal_id          = proposal_id,
        pattern_signature    = pattern_signature,
        status               = status,
        approved_at_cycle    = approved_at_cycle,
        implemented_at_cycle = implemented_at_cycle,
        validated_at_cycle   = validated_at_cycle,
        tests_run            = tests_run,
        files_changed        = files_changed,
        snapshot_sha         = snapshot_sha,
        recorded_genesis     = "Genesis-045",
    )


class StubPatternStoreWithOutcome:
    """PatternStore stub that supports outcome record lookup."""

    def __init__(
        self,
        outcome: Optional[ProposalOutcomeRecord] = None,
        rejection_record=None,
        pattern_record=None,
        legacy_cycle: int = -1,
        frequency: int = 1,
    ):
        self._outcome         = outcome
        self._rej_record      = rejection_record
        self._pat_record      = pattern_record
        self._legacy_cycle    = legacy_cycle
        self._frequency       = frequency

    def get_rejection_record_by_signature(self, sig):
        return self._rej_record

    def get_rejection_cycle(self, cat, title):
        return self._legacy_cycle

    def get_pattern(self, sig):
        return self._pat_record

    def get_frequency(self, cat, title):
        return self._frequency

    def get_latest_outcome_for_pattern(self, pat_sig):
        return self._outcome


# ---------------------------------------------------------------------------
# Section 1: OutcomeStatus enum
# ---------------------------------------------------------------------------

class TestOutcomeStatus:

    def test_implemented_value(self):
        assert OutcomeStatus.IMPLEMENTED.value == "IMPLEMENTED"

    def test_validated_value(self):
        assert OutcomeStatus.VALIDATED.value == "VALIDATED"

    def test_failed_validation_value(self):
        assert OutcomeStatus.FAILED_VALIDATION.value == "FAILED_VALIDATION"

    def test_label_implemented(self):
        assert "Implemented" in OutcomeStatus.IMPLEMENTED.label()

    def test_label_validated(self):
        assert "Validated" in OutcomeStatus.VALIDATED.label()

    def test_label_failed_validation(self):
        assert OutcomeStatus.FAILED_VALIDATION.label() != ""


# ---------------------------------------------------------------------------
# Section 2: ProposalOutcomeRecord fields and chronology
# ---------------------------------------------------------------------------

class TestProposalOutcomeRecord:

    def test_implemented_record_has_no_validated_cycle(self):
        r = make_outcome_record(OutcomeStatus.IMPLEMENTED)
        assert r.validated_at_cycle is None

    def test_validated_record_has_validated_cycle(self):
        r = make_outcome_record(OutcomeStatus.VALIDATED, validated_at_cycle=10)
        assert r.validated_at_cycle == 10

    def test_failed_validation_has_validated_cycle(self):
        r = make_outcome_record(OutcomeStatus.FAILED_VALIDATION, validated_at_cycle=9)
        assert r.validated_at_cycle == 9

    def test_chronology_approved_before_implemented(self):
        r = make_outcome_record(
            OutcomeStatus.IMPLEMENTED,
            approved_at_cycle=5,
            implemented_at_cycle=6,
        )
        assert r.approved_at_cycle <= r.implemented_at_cycle

    def test_chronology_implemented_before_validated(self):
        r = make_outcome_record(
            OutcomeStatus.VALIDATED,
            implemented_at_cycle=6,
            validated_at_cycle=8,
        )
        assert r.implemented_at_cycle <= r.validated_at_cycle

    def test_recorded_genesis_default(self):
        r = make_outcome_record(OutcomeStatus.IMPLEMENTED)
        assert r.recorded_genesis == "Genesis-045"

    def test_snapshot_sha_stored(self):
        r = make_outcome_record(OutcomeStatus.IMPLEMENTED, snapshot_sha="deadbeef")
        assert r.snapshot_sha == "deadbeef"

    def test_tests_run_zero_is_valid(self):
        # A change may produce no test output — does not prevent IMPLEMENTED
        r = make_outcome_record(OutcomeStatus.IMPLEMENTED, tests_run=0)
        assert r.tests_run == 0

    def test_files_changed_zero_is_valid(self):
        # Edge case: execution ran but produced no file changes
        r = make_outcome_record(OutcomeStatus.IMPLEMENTED, files_changed=0)
        assert r.files_changed == 0


# ---------------------------------------------------------------------------
# Section 3: ProposalStatus extended values
# ---------------------------------------------------------------------------

class TestProposalStatusExtended:

    def test_implemented_in_enum(self):
        assert ProposalStatus.IMPLEMENTED is not None

    def test_validated_in_enum(self):
        assert ProposalStatus.VALIDATED is not None

    def test_failed_validation_in_enum(self):
        assert ProposalStatus.FAILED_VALIDATION is not None

    def test_existing_statuses_unchanged(self):
        assert ProposalStatus.PENDING  is not None
        assert ProposalStatus.APPROVED is not None
        assert ProposalStatus.REJECTED is not None
        assert ProposalStatus.DEFERRED is not None
        assert ProposalStatus.EXPIRED  is not None
        assert ProposalStatus.STALE    is not None

    def test_implemented_label(self):
        assert ProposalStatus.IMPLEMENTED.label() != ""

    def test_validated_label(self):
        assert ProposalStatus.VALIDATED.label() != ""

    def test_failed_validation_label(self):
        assert ProposalStatus.FAILED_VALIDATION.label() != ""

    def test_serialisation_round_trip(self):
        # ProposalStatus is serialised as .name in PatternStore
        for status in ProposalStatus:
            assert ProposalStatus[status.name] == status


# ---------------------------------------------------------------------------
# Section 4: Selector outcome-aware scoring
# ---------------------------------------------------------------------------

class TestSelectorOutcomeScoring:

    def _score(self, store, current_cycle=10, base_score=1.0):
        sel = ImprovementSelector()
        return sel._apply_outcome_scoring(
            score=base_score,
            pat_sig="ROUTING:test pattern",
            pattern_store=store,
            current_cycle=current_cycle,
        )

    def test_no_outcome_record_score_unchanged(self):
        store = StubPatternStoreWithOutcome(outcome=None)
        assert self._score(store) == 1.0

    def test_implemented_score_unchanged(self):
        outcome = make_outcome_record(OutcomeStatus.IMPLEMENTED)
        store   = StubPatternStoreWithOutcome(outcome=outcome)
        assert self._score(store) == 1.0

    def test_failed_validation_score_unchanged(self):
        # FAILED_VALIDATION = issue not resolved; full priority
        outcome = make_outcome_record(
            OutcomeStatus.FAILED_VALIDATION, validated_at_cycle=7
        )
        store = StubPatternStoreWithOutcome(outcome=outcome)
        assert self._score(store, current_cycle=8) == 1.0

    def test_validated_within_grace_period_score_reduced(self):
        # Validated at cycle 8; current=9; grace=5; 1 < 5 → reduced
        outcome = make_outcome_record(
            OutcomeStatus.VALIDATED, validated_at_cycle=8
        )
        store = StubPatternStoreWithOutcome(outcome=outcome)
        result = self._score(store, current_cycle=9, base_score=1.0)
        assert result == pytest.approx(VALIDATED_SCORE_FACTOR)

    def test_validated_outside_grace_period_score_restored(self):
        # Validated at cycle 8; current=20; grace=5; 12 >= 5 → full score
        outcome = make_outcome_record(
            OutcomeStatus.VALIDATED, validated_at_cycle=8
        )
        store = StubPatternStoreWithOutcome(outcome=outcome)
        assert self._score(store, current_cycle=20) == 1.0

    def test_validated_at_grace_boundary_score_restored(self):
        # Validated at cycle 8; current=13; elapsed=5 = VALIDATED_GRACE_CYCLES → full
        outcome = make_outcome_record(
            OutcomeStatus.VALIDATED, validated_at_cycle=8
        )
        store = StubPatternStoreWithOutcome(outcome=outcome)
        assert self._score(store, current_cycle=8 + VALIDATED_GRACE_CYCLES) == 1.0

    def test_validated_no_validated_cycle_score_unchanged(self):
        # validated_at_cycle=None should not reduce score
        outcome = make_outcome_record(OutcomeStatus.VALIDATED, validated_at_cycle=None)
        store   = StubPatternStoreWithOutcome(outcome=outcome)
        assert self._score(store) == 1.0

    def test_score_factor_is_less_than_one(self):
        assert 0.0 < VALIDATED_SCORE_FACTOR < 1.0


# ---------------------------------------------------------------------------
# Section 5: Epistemic invariants
# ---------------------------------------------------------------------------

class TestEpistemicInvariants:

    def test_implemented_does_not_imply_diagnosis_correct(self):
        """
        IMPLEMENTED records tests_run and files_changed from ChangeSummary.
        These are facts about execution, not about diagnosis correctness.
        The Diagnosis.uncertainty field on the original proposal is unchanged.
        Verified structurally: ProposalOutcomeRecord has no diagnosis field.
        """
        r = make_outcome_record(OutcomeStatus.IMPLEMENTED)
        assert not hasattr(r, "diagnosis")
        assert not hasattr(r, "inference")

    def test_validated_does_not_claim_causation(self):
        """
        VALIDATED = expected improvement observed.
        The record has no causal claim field.
        """
        r = make_outcome_record(OutcomeStatus.VALIDATED, validated_at_cycle=10)
        assert not hasattr(r, "caused_by")
        assert not hasattr(r, "root_cause_confirmed")

    def test_failed_validation_does_not_erase_status_record(self):
        """
        FAILED_VALIDATION is recorded, not suppressed.
        The record has a status field that persists.
        """
        r = make_outcome_record(OutcomeStatus.FAILED_VALIDATION, validated_at_cycle=9)
        assert r.status == OutcomeStatus.FAILED_VALIDATION
        assert r.validated_at_cycle == 9

    def test_failed_validation_does_not_suppress_pattern(self):
        """
        FAILED_VALIDATION does not trigger suppression.
        Verified by selector: FAILED_VALIDATION → normal score (not suppressed).
        """
        outcome = make_outcome_record(
            OutcomeStatus.FAILED_VALIDATION, validated_at_cycle=7
        )
        store = StubPatternStoreWithOutcome(outcome=outcome)
        sel   = ImprovementSelector()
        score = sel._apply_outcome_scoring(
            score=1.0,
            pat_sig="ROUTING:test pattern",
            pattern_store=store,
            current_cycle=10,
        )
        assert score == 1.0  # normal priority; not suppressed

    def test_no_autonomous_action_field_on_outcome(self):
        """
        ProposalOutcomeRecord has no field that triggers or represents
        autonomous engineering action.
        """
        r = make_outcome_record(OutcomeStatus.FAILED_VALIDATION)
        assert not hasattr(r, "auto_retry")
        assert not hasattr(r, "next_action")
        assert not hasattr(r, "trigger")

    def test_outcome_status_is_independent_of_rejection_reason(self):
        """
        OutcomeStatus and RejectionReasonCode are separate enums.
        No OutcomeStatus value overlaps with RejectionReasonCode.
        """
        outcome_values   = {s.value for s in OutcomeStatus}
        rejection_values = {r.value for r in RejectionReasonCode}
        assert outcome_values.isdisjoint(rejection_values)


# ---------------------------------------------------------------------------
# Section 6: Chronology integrity
# ---------------------------------------------------------------------------

class TestChronologyIntegrity:

    def test_implemented_has_no_validated_cycle(self):
        r = make_outcome_record(OutcomeStatus.IMPLEMENTED)
        assert r.validated_at_cycle is None

    def test_transition_implemented_to_validated(self):
        # Simulate the engine updating from IMPLEMENTED to VALIDATED
        impl = make_outcome_record(
            OutcomeStatus.IMPLEMENTED,
            approved_at_cycle=5,
            implemented_at_cycle=6,
            validated_at_cycle=None,
        )
        # Engine creates a new record with updated status
        from dataclasses import replace
        validated = replace(
            impl,
            status           = OutcomeStatus.VALIDATED,
            validated_at_cycle = 8,
        )
        assert validated.approved_at_cycle    == 5
        assert validated.implemented_at_cycle == 6
        assert validated.validated_at_cycle   == 8
        assert validated.status               == OutcomeStatus.VALIDATED

    def test_transition_implemented_to_failed_validation(self):
        impl = make_outcome_record(
            OutcomeStatus.IMPLEMENTED,
            approved_at_cycle=5,
            implemented_at_cycle=6,
        )
        from dataclasses import replace
        failed = replace(
            impl,
            status             = OutcomeStatus.FAILED_VALIDATION,
            validated_at_cycle = 7,
        )
        assert failed.approved_at_cycle    == 5
        assert failed.implemented_at_cycle == 6
        assert failed.validated_at_cycle   == 7
        assert failed.status               == OutcomeStatus.FAILED_VALIDATION

    def test_chronology_order_preserved(self):
        r = make_outcome_record(
            OutcomeStatus.VALIDATED,
            approved_at_cycle=3,
            implemented_at_cycle=5,
            validated_at_cycle=8,
        )
        assert r.approved_at_cycle <= r.implemented_at_cycle <= r.validated_at_cycle
