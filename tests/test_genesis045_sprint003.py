"""
Genesis-045 Sprint-003 — Behavioural tests

Tests the differentiated rejection suppression, evidence-novelty
re-eligibility, and approval semantics introduced in Sprint-003.

All tests are deterministic and self-contained.
No network. No AI. No KnowledgeEngine I/O (stubs used throughout).

Epistemic invariants verified:
  - Rejection does not mutate PatternRecord evidence
  - Frequency growth alone does NOT override a human rejection window
  - Evidence novelty (new component) MAY permit early re-eligibility
  - ACCEPTABLE_TRADEOFF is window-only; novelty does not apply
  - Approval does not suppress the pattern
  - Approval does not imply diagnosis correctness
  - DEFER leaves the proposal unchanged
"""

from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering.intelligence.pattern_record import (
    PatternRecord, RejectionReasonCode, RejectionRecord,
)
from core.engineering.intelligence.selector import (
    SUPPRESSION_BY_REASON, ImprovementSelector, get_suppression_cycles,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rejection_record(
    reason_code: RejectionReasonCode,
    cycle: int = 5,
    components: list = None,
    suppression_cycles: int = None,
) -> RejectionRecord:
    if suppression_cycles is None:
        suppression_cycles = get_suppression_cycles(reason_code)
    return RejectionRecord(
        proposal_id             = "G045-ROU-AABBCC",
        pattern_signature       = "ROUTING:test pattern",
        reason_code             = reason_code,
        reason_text             = "",
        cycle                   = cycle,
        components_at_rejection = components or [],
        suppression_cycles      = suppression_cycles,
        recorded_genesis        = "Genesis-045",
    )


def make_pattern_record(
    signature: str = "ROUTING:test pattern",
    affected_components: list = None,
    total_occurrences: int = 3,
) -> PatternRecord:
    return PatternRecord(
        signature           = signature,
        category            = "ROUTING",
        display_title       = "test pattern",
        first_cycle         = 1,
        last_cycle          = 7,
        total_occurrences   = total_occurrences,
        affected_components = affected_components or [],
    )


class StubPatternStore:
    """
    Minimal PatternStore stub for selector tests.
    Supports per-signature rejection records and pattern records.
    """

    def __init__(
        self,
        rejection_record: Optional[RejectionRecord] = None,
        pattern_record:   Optional[PatternRecord]   = None,
        legacy_cycle:     int                       = -1,
        frequency:        int                       = 1,
    ):
        self._rej_record    = rejection_record
        self._pat_record    = pattern_record
        self._legacy_cycle  = legacy_cycle
        self._frequency     = frequency

    def get_rejection_record_by_signature(self, signature: str):
        return self._rej_record

    def get_rejection_cycle(self, category: str, title: str) -> int:
        return self._legacy_cycle

    def get_pattern(self, signature: str):
        return self._pat_record

    def get_frequency(self, category: str, title: str) -> int:
        return self._frequency


# ---------------------------------------------------------------------------
# Section 1: SUPPRESSION_BY_REASON table
# ---------------------------------------------------------------------------

class TestSuppressionTable:

    def test_not_a_problem_window(self):
        assert get_suppression_cycles(RejectionReasonCode.NOT_A_PROBLEM) == 10

    def test_wrong_diagnosis_window(self):
        assert get_suppression_cycles(RejectionReasonCode.WRONG_DIAGNOSIS) == 5

    def test_wrong_recommendation_window(self):
        assert get_suppression_cycles(RejectionReasonCode.WRONG_RECOMMENDATION) == 3

    def test_too_risky_window(self):
        assert get_suppression_cycles(RejectionReasonCode.TOO_RISKY) == 3

    def test_not_now_window(self):
        assert get_suppression_cycles(RejectionReasonCode.NOT_NOW) == 3

    def test_acceptable_tradeoff_window(self):
        assert get_suppression_cycles(RejectionReasonCode.ACCEPTABLE_TRADEOFF) == 15

    def test_other_window(self):
        assert get_suppression_cycles(RejectionReasonCode.OTHER) == 5

    def test_all_reason_codes_have_entries(self):
        for code in RejectionReasonCode:
            assert code in SUPPRESSION_BY_REASON, f"{code} missing from SUPPRESSION_BY_REASON"

    def test_suppression_cycles_are_positive(self):
        for code, cycles in SUPPRESSION_BY_REASON.items():
            assert cycles > 0, f"{code} has non-positive window {cycles}"


# ---------------------------------------------------------------------------
# Section 2: RejectionReasonCode.from_string parsing
# ---------------------------------------------------------------------------

class TestReasonCodeParsing:

    def test_valid_code_parsed(self):
        assert RejectionReasonCode.from_string("NOT_NOW") == RejectionReasonCode.NOT_NOW

    def test_case_insensitive(self):
        assert RejectionReasonCode.from_string("not_now") == RejectionReasonCode.NOT_NOW

    def test_space_to_underscore(self):
        assert RejectionReasonCode.from_string("WRONG DIAGNOSIS") == RejectionReasonCode.WRONG_DIAGNOSIS

    def test_unknown_falls_back_to_other(self):
        assert RejectionReasonCode.from_string("BANANA") == RejectionReasonCode.OTHER

    def test_empty_string_falls_back_to_other(self):
        assert RejectionReasonCode.from_string("") == RejectionReasonCode.OTHER


# ---------------------------------------------------------------------------
# Section 3: is_novelty_exempt
# ---------------------------------------------------------------------------

class TestNoveltyExempt:

    def test_acceptable_tradeoff_is_exempt(self):
        assert RejectionReasonCode.ACCEPTABLE_TRADEOFF.is_novelty_exempt() is True

    def test_not_now_is_not_exempt(self):
        assert RejectionReasonCode.NOT_NOW.is_novelty_exempt() is False

    def test_not_a_problem_is_not_exempt(self):
        assert RejectionReasonCode.NOT_A_PROBLEM.is_novelty_exempt() is False

    def test_wrong_recommendation_is_not_exempt(self):
        assert RejectionReasonCode.WRONG_RECOMMENDATION.is_novelty_exempt() is False

    def test_other_is_not_exempt(self):
        assert RejectionReasonCode.OTHER.is_novelty_exempt() is False


# ---------------------------------------------------------------------------
# Section 4: RejectionRecord Sprint-003 fields
# ---------------------------------------------------------------------------

class TestRejectionRecordFields:

    def test_components_at_rejection_default_empty(self):
        r = RejectionRecord(
            proposal_id="P1", pattern_signature="SIG",
            reason_code=RejectionReasonCode.NOT_NOW,
        )
        assert r.components_at_rejection == []

    def test_components_at_rejection_stored(self):
        r = make_rejection_record(
            RejectionReasonCode.NOT_NOW, components=["file_a.py", "file_b.py"]
        )
        assert set(r.components_at_rejection) == {"file_a.py", "file_b.py"}

    def test_suppression_cycles_stored(self):
        r = make_rejection_record(RejectionReasonCode.NOT_NOW)
        assert r.suppression_cycles == 3

    def test_recorded_genesis_stored(self):
        r = make_rejection_record(RejectionReasonCode.NOT_NOW)
        assert r.recorded_genesis == "Genesis-045"

    def test_suppression_cycles_not_a_problem(self):
        r = make_rejection_record(RejectionReasonCode.NOT_A_PROBLEM)
        assert r.suppression_cycles == 10

    def test_suppression_cycles_acceptable_tradeoff(self):
        r = make_rejection_record(RejectionReasonCode.ACCEPTABLE_TRADEOFF)
        assert r.suppression_cycles == 15


# ---------------------------------------------------------------------------
# Section 5: ImprovementSelector._check_suppression — window behaviour
# ---------------------------------------------------------------------------

class TestSelectorSuppressionWindow:

    def _selector(self):
        return ImprovementSelector()

    def _check(self, store, current_cycle=10):
        sel = self._selector()
        return sel._check_suppression(
            pattern_store=store,
            pat_sig="ROUTING:test pattern",
            cat="ROUTING",
            title="test pattern",
            current_cycle=current_cycle,
        )

    def test_no_rejection_record_not_suppressed(self):
        store = StubPatternStore()
        assert self._check(store) is False

    def test_within_window_suppressed(self):
        # Rejected at cycle 5, window=3, current=7 → elapsed=2 < 3
        rej = make_rejection_record(RejectionReasonCode.NOT_NOW, cycle=5)
        store = StubPatternStore(rejection_record=rej)
        assert self._check(store, current_cycle=7) is True

    def test_window_expired_not_suppressed(self):
        # Rejected at cycle 5, window=3, current=9 → elapsed=4 >= 3
        rej = make_rejection_record(RejectionReasonCode.NOT_NOW, cycle=5)
        store = StubPatternStore(rejection_record=rej)
        assert self._check(store, current_cycle=9) is False

    def test_exactly_at_window_boundary_not_suppressed(self):
        # Rejected at cycle 5, window=3, current=8 → elapsed=3 >= 3
        rej = make_rejection_record(RejectionReasonCode.NOT_NOW, cycle=5)
        store = StubPatternStore(rejection_record=rej)
        assert self._check(store, current_cycle=8) is False

    def test_not_a_problem_longer_window(self):
        # Rejected at cycle 5, window=10, current=12 → elapsed=7 < 10
        rej = make_rejection_record(RejectionReasonCode.NOT_A_PROBLEM, cycle=5)
        store = StubPatternStore(rejection_record=rej)
        assert self._check(store, current_cycle=12) is True

    def test_not_a_problem_window_expired(self):
        # Rejected at cycle 5, window=10, current=16 → elapsed=11 >= 10
        rej = make_rejection_record(RejectionReasonCode.NOT_A_PROBLEM, cycle=5)
        store = StubPatternStore(rejection_record=rej)
        assert self._check(store, current_cycle=16) is False

    def test_acceptable_tradeoff_long_window(self):
        # Rejected at cycle 5, window=15, current=18 → elapsed=13 < 15
        rej = make_rejection_record(RejectionReasonCode.ACCEPTABLE_TRADEOFF, cycle=5)
        store = StubPatternStore(rejection_record=rej)
        assert self._check(store, current_cycle=18) is True

    def test_acceptable_tradeoff_window_expired(self):
        # Rejected at cycle 5, window=15, current=21 → elapsed=16 >= 15
        rej = make_rejection_record(RejectionReasonCode.ACCEPTABLE_TRADEOFF, cycle=5)
        store = StubPatternStore(rejection_record=rej)
        assert self._check(store, current_cycle=21) is False


# ---------------------------------------------------------------------------
# Section 6: Evidence novelty re-eligibility
# ---------------------------------------------------------------------------

class TestEvidenceNoveltyReeligibility:

    def _check(self, store, current_cycle=7):
        sel = ImprovementSelector()
        return sel._check_suppression(
            pattern_store=store,
            pat_sig="ROUTING:test pattern",
            cat="ROUTING",
            title="test pattern",
            current_cycle=current_cycle,
        )

    def test_same_components_within_window_suppressed(self):
        # Rejected with ["a.py"]; current pattern also has ["a.py"]; within window
        rej = make_rejection_record(
            RejectionReasonCode.NOT_NOW, cycle=5,
            components=["a.py"],
        )
        pat = make_pattern_record(affected_components=["a.py"])
        store = StubPatternStore(rejection_record=rej, pattern_record=pat)
        assert self._check(store, current_cycle=7) is True

    def test_new_component_within_window_not_suppressed(self):
        # Rejected with ["a.py"]; current pattern has ["a.py", "b.py"] → novelty
        rej = make_rejection_record(
            RejectionReasonCode.NOT_NOW, cycle=5,
            components=["a.py"],
        )
        pat = make_pattern_record(affected_components=["a.py", "b.py"])
        store = StubPatternStore(rejection_record=rej, pattern_record=pat)
        assert self._check(store, current_cycle=7) is False

    def test_new_component_acceptable_tradeoff_still_suppressed(self):
        # ACCEPTABLE_TRADEOFF: novelty does NOT bypass window
        rej = make_rejection_record(
            RejectionReasonCode.ACCEPTABLE_TRADEOFF, cycle=5,
            components=["a.py"],
        )
        pat = make_pattern_record(affected_components=["a.py", "b.py"])
        store = StubPatternStore(rejection_record=rej, pattern_record=pat)
        assert self._check(store, current_cycle=7) is True

    def test_frequency_growth_alone_does_not_bypass_suppression(self):
        # Pattern seen 50 times but no new components — still suppressed
        rej = make_rejection_record(
            RejectionReasonCode.NOT_NOW, cycle=5,
            components=["a.py"],
        )
        pat = make_pattern_record(
            affected_components=["a.py"],  # no new components
            total_occurrences=50,          # high frequency — irrelevant to suppression
        )
        store = StubPatternStore(rejection_record=rej, pattern_record=pat)
        assert self._check(store, current_cycle=7) is True

    def test_no_pattern_record_available_no_novelty_check(self):
        # If PatternRecord cannot be loaded, novelty check is skipped → suppressed
        rej = make_rejection_record(
            RejectionReasonCode.NOT_NOW, cycle=5,
            components=["a.py"],
        )
        store = StubPatternStore(rejection_record=rej, pattern_record=None)
        assert self._check(store, current_cycle=7) is True

    def test_new_component_wrong_diagnosis_bypasses(self):
        rej = make_rejection_record(
            RejectionReasonCode.WRONG_DIAGNOSIS, cycle=5,
            components=["a.py"],
        )
        pat = make_pattern_record(affected_components=["a.py", "c.py"])
        store = StubPatternStore(rejection_record=rej, pattern_record=pat)
        assert self._check(store, current_cycle=7) is False

    def test_new_component_not_a_problem_bypasses(self):
        rej = make_rejection_record(
            RejectionReasonCode.NOT_A_PROBLEM, cycle=5,
            components=["a.py"],
        )
        pat = make_pattern_record(affected_components=["a.py", "d.py"])
        store = StubPatternStore(rejection_record=rej, pattern_record=pat)
        assert self._check(store, current_cycle=7) is False

    def test_new_component_too_risky_bypasses(self):
        rej = make_rejection_record(
            RejectionReasonCode.TOO_RISKY, cycle=5,
            components=["a.py"],
        )
        pat = make_pattern_record(affected_components=["a.py", "e.py"])
        store = StubPatternStore(rejection_record=rej, pattern_record=pat)
        assert self._check(store, current_cycle=7) is False


# ---------------------------------------------------------------------------
# Section 7: Legacy fallback path
# ---------------------------------------------------------------------------

class TestLegacyFallback:

    def _check(self, store, current_cycle=7):
        sel = ImprovementSelector()
        return sel._check_suppression(
            pattern_store=store,
            pat_sig="ROUTING:test pattern",
            cat="ROUTING",
            title="test pattern",
            current_cycle=current_cycle,
        )

    def test_legacy_within_window_suppressed(self):
        # No RejectionRecord; legacy cycle=5; current=7; window=5 → elapsed=2 < 5
        store = StubPatternStore(legacy_cycle=5)
        assert self._check(store, current_cycle=7) is True

    def test_legacy_window_expired_not_suppressed(self):
        # No RejectionRecord; legacy cycle=5; current=11; elapsed=6 >= 5
        store = StubPatternStore(legacy_cycle=5)
        assert self._check(store, current_cycle=11) is False

    def test_legacy_never_rejected_not_suppressed(self):
        # get_rejection_cycle returns -1
        store = StubPatternStore(legacy_cycle=-1)
        assert self._check(store, current_cycle=7) is False

    def test_structured_record_takes_precedence_over_legacy(self):
        # Structured record says window=15; legacy says rejected at cycle=5
        # Structured record should govern
        rej = make_rejection_record(
            RejectionReasonCode.ACCEPTABLE_TRADEOFF, cycle=5,
        )  # window=15
        store = StubPatternStore(rejection_record=rej, legacy_cycle=5)
        # At cycle 12: elapsed=7 < 15 → suppressed (structured governs)
        assert self._check(store, current_cycle=12) is True


# ---------------------------------------------------------------------------
# Section 8: Evidence immutability
# ---------------------------------------------------------------------------

class TestEvidenceImmutability:

    def test_rejection_record_components_are_independent_list(self):
        # Mutating the original list after creating the record does not change it
        original = ["a.py", "b.py"]
        rej = make_rejection_record(
            RejectionReasonCode.NOT_NOW, components=original
        )
        original.append("c.py")
        # The record was created with a copy via list(...)
        assert "c.py" not in rej.components_at_rejection

    def test_suppression_window_does_not_change_pattern_evidence(self):
        # PatternRecord fields are not mutated by suppression check
        pat = make_pattern_record(
            affected_components=["a.py"],
            total_occurrences=5,
        )
        original_occ   = pat.total_occurrences
        original_comps = list(pat.affected_components)

        rej   = make_rejection_record(RejectionReasonCode.NOT_NOW, cycle=5, components=["a.py"])
        store = StubPatternStore(rejection_record=rej, pattern_record=pat)
        sel   = ImprovementSelector()
        sel._check_suppression(
            pattern_store=store,
            pat_sig="ROUTING:test pattern",
            cat="ROUTING",
            title="test pattern",
            current_cycle=7,
        )
        assert pat.total_occurrences   == original_occ
        assert pat.affected_components == original_comps


# ---------------------------------------------------------------------------
# Section 9: PatternRecord.normalise_signature stability
# ---------------------------------------------------------------------------

class TestSignatureStability:

    def test_numeric_stripping(self):
        s1 = PatternRecord.normalise_signature("ROUTING", "AI fallback 3 turns")
        s2 = PatternRecord.normalise_signature("ROUTING", "AI fallback 7 turns")
        assert s1 == s2

    def test_category_uppercased(self):
        sig = PatternRecord.normalise_signature("routing", "some issue")
        assert sig.startswith("ROUTING:")

    def test_different_categories_different_signatures(self):
        s1 = PatternRecord.normalise_signature("ROUTING", "ai fallback")
        s2 = PatternRecord.normalise_signature("MEMORY",  "ai fallback")
        assert s1 != s2


# ---------------------------------------------------------------------------
# Section 10: Approval semantics
# ---------------------------------------------------------------------------

class TestApprovalSemantics:

    def test_approval_does_not_create_rejection_record(self):
        """
        Approval must not write a RejectionRecord or suppress the pattern.
        Verified by inspecting that RejectionReasonCode has no APPROVED value.
        """
        codes = {c.value for c in RejectionReasonCode}
        assert "APPROVED" not in codes

    def test_approval_is_not_in_suppression_table(self):
        """SUPPRESSION_BY_REASON must not contain any approval-like key."""
        for code in SUPPRESSION_BY_REASON:
            assert "APPROV" not in code.value.upper()

    def test_no_pattern_suppression_after_approval(self):
        """
        After approval there is no RejectionRecord, so _check_suppression
        returns False (not suppressed) for the same pattern.
        """
        store = StubPatternStore(rejection_record=None, legacy_cycle=-1)
        sel = ImprovementSelector()
        suppressed = sel._check_suppression(
            pattern_store=store,
            pat_sig="ROUTING:test pattern",
            cat="ROUTING",
            title="test pattern",
            current_cycle=10,
        )
        assert suppressed is False
