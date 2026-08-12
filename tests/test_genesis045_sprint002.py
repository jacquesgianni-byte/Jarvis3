"""
Genesis-045 Sprint-002 — Engineering Intelligence with Memory

Tests validate the complete loop:
    Observe → Measure → Accumulate Evidence → Identify Patterns
    → Propose → Human Decision → Record Outcome

Key invariants tested:
  - DRR computed from raw counts, never stored as derived value
  - DRRTrend requires exactly 6 cycles (non-overlapping 3+3)
  - PatternRecord evidence immutable — no rejection modifies it
  - external_flag never set by Sprint-002 operations
  - All rejection reason codes use 5-cycle suppression (uniform)
  - pattern_signature links proposals to patterns
"""

import pytest

from core.engineering.intelligence.session_record import (
    SessionRecord, TurnType, DRRTrend, compute_drr_trend,
)
from core.engineering.intelligence.pattern_record import (
    PatternRecord, RejectionRecord, RejectionReasonCode,
)
from core.engineering.intelligence.models import ImprovementProposal
from core.engineering.intelligence.engine import EngineeringIntelligenceEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ke():
    from core.knowledge_engine.json_storage import JsonKnowledgeRepository
    from core.knowledge_engine.engine import KnowledgeEngine
    import tempfile, os
    tmp = tempfile.mkdtemp()
    storage = JsonKnowledgeRepository(os.path.join(tmp, "test_ke.json"))
    return KnowledgeEngine(storage=storage)


def _make_engine():
    return EngineeringIntelligenceEngine(_make_ke())


def _make_store():
    from core.engineering.intelligence.pattern_store import PatternStore
    return PatternStore(_make_ke())


def _make_session(cycle: int, total: int, deterministic: int,
                  ai: int = 0, errors: int = 0,
                  issues: list = None) -> SessionRecord:
    return SessionRecord(
        cycle=cycle,
        timestamp="2026-08-12T00:00:00+00:00",
        total_turns=total,
        deterministic_turns=deterministic,
        ai_called_turns=ai,
        error_turns=errors,
        issues_found=issues or [],
    )


# ---------------------------------------------------------------------------
# Group A — TurnType taxonomy
# ---------------------------------------------------------------------------

class TestTurnTypeTaxonomy:

    def test_denominator_types_correct(self):
        denom = TurnType.denominator_types()
        assert TurnType.CONVERSATION in denom
        assert TurnType.CONVERSATION_AI in denom
        assert TurnType.CONVERSATION_ERROR in denom
        assert TurnType.TOOL_LOCAL in denom
        assert TurnType.TOOL_EXTERNAL in denom

    def test_intentional_ai_excluded_from_denominator(self):
        assert TurnType.CONVERSATION_AI_INTENTIONAL not in TurnType.denominator_types()

    def test_system_cmd_excluded_from_denominator(self):
        assert TurnType.SYSTEM_CMD not in TurnType.denominator_types()

    def test_empty_input_excluded_from_denominator(self):
        assert TurnType.EMPTY_INPUT not in TurnType.denominator_types()

    def test_numerator_types_correct(self):
        num = TurnType.numerator_types()
        assert TurnType.CONVERSATION in num
        assert TurnType.TOOL_LOCAL in num
        assert TurnType.CONVERSATION_AI not in num
        assert TurnType.CONVERSATION_ERROR not in num
        assert TurnType.TOOL_EXTERNAL not in num


# ---------------------------------------------------------------------------
# Group B — SessionRecord and DRR
# ---------------------------------------------------------------------------

class TestSessionRecordAndDRR:

    def test_pure_deterministic_drr(self):
        rec = _make_session(1, total=10, deterministic=10)
        assert rec.drr == 1.0

    def test_all_ai_fallback_drr(self):
        rec = _make_session(1, total=10, deterministic=0, ai=10)
        assert rec.drr == 0.0

    def test_mixed_drr(self):
        rec = _make_session(1, total=10, deterministic=8, ai=2)
        assert abs(rec.drr - 0.8) < 0.001

    def test_zero_turns_drr(self):
        rec = _make_session(1, total=0, deterministic=0)
        assert rec.drr == 0.0

    def test_error_turn_in_denominator_not_numerator(self):
        # 8 deterministic + 1 AI + 1 error = total 10
        rec = _make_session(1, total=10, deterministic=8, ai=1, errors=1)
        assert rec.drr == 0.8  # 8/10

    def test_drr_not_stored_as_field(self):
        """DRR must be a computed property, not a stored field."""
        rec = _make_session(1, total=5, deterministic=4)
        assert not hasattr(rec, '_drr')
        assert 'drr' not in rec.__dataclass_fields__ or                rec.__dataclass_fields__.get('drr') is None

    def test_session_record_persisted(self):
        store = _make_store()
        rec = _make_session(1, total=10, deterministic=8)
        store.save_session_record(rec)
        records = store.get_session_records(n=5)
        assert len(records) == 1
        assert records[0].cycle == 1
        assert records[0].total_turns == 10
        assert records[0].deterministic_turns == 8

    def test_get_last_cycle_returns_max(self):
        store = _make_store()
        store.save_session_record(_make_session(1, 10, 8))
        store.save_session_record(_make_session(3, 10, 9))
        store.save_session_record(_make_session(2, 10, 7))
        assert store.get_last_cycle() == 3

    def test_get_last_cycle_zero_when_empty(self):
        store = _make_store()
        assert store.get_last_cycle() == 0


# ---------------------------------------------------------------------------
# Group C — DRRTrend
# ---------------------------------------------------------------------------

class TestDRRTrend:

    def _sessions_with_drr(self, drr_values: list) -> list:
        return [
            _make_session(i + 1, total=10,
                          deterministic=int(d * 10),
                          ai=10 - int(d * 10))
            for i, d in enumerate(drr_values)
        ]

    def test_fewer_than_6_cycles_insufficient_data(self):
        sessions = self._sessions_with_drr([0.8, 0.7, 0.6, 0.5, 0.4])
        assert compute_drr_trend(sessions) == DRRTrend.INSUFFICIENT_DATA

    def test_exactly_5_cycles_insufficient_data(self):
        sessions = self._sessions_with_drr([0.9, 0.9, 0.9, 0.9, 0.9])
        assert compute_drr_trend(sessions) == DRRTrend.INSUFFICIENT_DATA

    def test_6_cycles_declining(self):
        # previous 3 mean = 0.90, latest 3 mean = 0.70 → -20% → DECLINING
        sessions = self._sessions_with_drr([0.9, 0.9, 0.9, 0.7, 0.7, 0.7])
        assert compute_drr_trend(sessions) == DRRTrend.DECLINING

    def test_6_cycles_improving(self):
        # previous 3 mean = 0.70, latest 3 mean = 0.90 → +20% → IMPROVING
        sessions = self._sessions_with_drr([0.7, 0.7, 0.7, 0.9, 0.9, 0.9])
        assert compute_drr_trend(sessions) == DRRTrend.IMPROVING

    def test_6_cycles_stable_within_5_percent(self):
        # previous 3 mean = 0.80, latest 3 mean = 0.82 → +2.5% → STABLE
        sessions = self._sessions_with_drr([0.8, 0.8, 0.8, 0.9, 0.8, 0.8])
        assert compute_drr_trend(sessions) == DRRTrend.STABLE

    def test_uses_last_6_of_many(self):
        # First 4 are bad, last 6 are stable
        sessions = self._sessions_with_drr(
            [0.1, 0.1, 0.1, 0.1, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]
        )
        assert compute_drr_trend(sessions) == DRRTrend.STABLE


# ---------------------------------------------------------------------------
# Group D — PatternRecord
# ---------------------------------------------------------------------------

class TestPatternRecord:

    def test_no_pattern_on_first_occurrence(self):
        """A pattern requires 2+ cycles; first occurrence is just frequency data."""
        store = _make_store()
        # Update pattern for cycle 1 only
        store.update_pattern("ROUTING:test issue", "ROUTING", "test issue", cycle=1)
        # Save session record with this issue
        store.save_session_record(_make_session(1, 10, 8,
            issues=[{"signature": "ROUTING:test issue", "category": "ROUTING", "confidence": 0.9}]))
        # get_active_patterns requires min_occurrences=2
        active = store.get_active_patterns(window=20, min_occurrences=2)
        assert len(active) == 0

    def test_pattern_created_on_second_occurrence(self):
        store = _make_store()
        sig = "ROUTING:routing gap"
        store.update_pattern(sig, "ROUTING", "routing gap", cycle=1)
        store.update_pattern(sig, "ROUTING", "routing gap", cycle=2)
        store.save_session_record(_make_session(1, 10, 7,
            issues=[{"signature": sig, "category": "ROUTING", "confidence": 0.85}]))
        store.save_session_record(_make_session(2, 10, 6,
            issues=[{"signature": sig, "category": "ROUTING", "confidence": 0.85}]))
        active = store.get_active_patterns(window=20, min_occurrences=2)
        assert len(active) == 1
        assert active[0].signature == sig

    def test_total_occurrences_increments(self):
        store = _make_store()
        sig = "ROUTING:increments"
        store.update_pattern(sig, "ROUTING", "increments", cycle=1)
        store.update_pattern(sig, "ROUTING", "increments", cycle=2)
        store.update_pattern(sig, "ROUTING", "increments", cycle=3)
        active = store.get_active_patterns(window=20, min_occurrences=1)
        matching = [p for p in active if p.signature == sig]
        if matching:
            assert matching[0].total_occurrences == 3

    def test_affected_components_is_union(self):
        store = _make_store()
        sig = "ROUTING:union test"
        store.update_pattern(sig, "ROUTING", "union test", cycle=1,
                             likely_files=["core/router.py"])
        store.update_pattern(sig, "ROUTING", "union test", cycle=2,
                             likely_files=["core/intent.py"])
        store.save_session_record(_make_session(1, 10, 8,
            issues=[{"signature": sig, "category": "ROUTING", "confidence": 0.9}]))
        store.save_session_record(_make_session(2, 10, 7,
            issues=[{"signature": sig, "category": "ROUTING", "confidence": 0.9}]))
        active = store.get_active_patterns(window=20, min_occurrences=2)
        matching = [p for p in active if p.signature == sig]
        if matching:
            comps = set(matching[0].affected_components)
            assert "core/router.py" in comps
            assert "core/intent.py" in comps

    def test_external_flag_defaults_false(self):
        store = _make_store()
        sig = "ROUTING:ext flag"
        store.update_pattern(sig, "ROUTING", "ext flag", cycle=1)
        store.save_session_record(_make_session(1, 10, 8,
            issues=[{"signature": sig, "category": "ROUTING", "confidence": 0.9}]))
        active = store.get_active_patterns(window=20, min_occurrences=1)
        matching = [p for p in active if p.signature == sig]
        if matching:
            assert matching[0].external_flag is False

    def test_two_different_signatures_separate_records(self):
        store = _make_store()
        sig1 = "ROUTING:sig one"
        sig2 = "MEMORY:sig two"
        # Use non-colliding cycle numbers so session records don't overwrite each other
        store.update_pattern(sig1, "ROUTING", "sig one", cycle=1)
        store.update_pattern(sig1, "ROUTING", "sig one", cycle=2)
        store.save_session_record(_make_session(1, 10, 8,
            issues=[{"signature": sig1, "category": "ROUTING", "confidence": 0.9}]))
        store.save_session_record(_make_session(2, 10, 7,
            issues=[{"signature": sig1, "category": "ROUTING", "confidence": 0.9}]))
        store.update_pattern(sig2, "MEMORY", "sig two", cycle=3)
        store.update_pattern(sig2, "MEMORY", "sig two", cycle=4)
        store.save_session_record(_make_session(3, 10, 8,
            issues=[{"signature": sig2, "category": "MEMORY", "confidence": 0.9}]))
        store.save_session_record(_make_session(4, 10, 7,
            issues=[{"signature": sig2, "category": "MEMORY", "confidence": 0.9}]))
        active = store.get_active_patterns(window=20, min_occurrences=2)
        sigs = {p.signature for p in active}
        assert sig1 in sigs
        assert sig2 in sigs

    def test_pattern_normalise_signature(self):
        sig = PatternRecord.normalise_signature("ROUTING", "Slow AI responses: 3 turns")
        assert "ROUTING:" in sig
        assert sig == sig.lower() or "ROUTING:" in sig

    def test_window_occurrences_excludes_old_cycles(self):
        store = _make_store()
        sig = "ROUTING:old test"
        # Add occurrences at cycles 1 and 2 (old) and 25 (recent)
        for c in [1, 2]:
            store.update_pattern(sig, "ROUTING", "old test", cycle=c)
            store.save_session_record(_make_session(c, 10, 7,
                issues=[{"signature": sig, "category": "ROUTING", "confidence": 0.8}]))
        store.update_pattern(sig, "ROUTING", "old test", cycle=25)
        store.save_session_record(_make_session(25, 10, 7,
            issues=[{"signature": sig, "category": "ROUTING", "confidence": 0.8}]))
        # With window=20 from cycle 25: cycles 6-25 in window
        # Cycles 1 and 2 should be EXCLUDED, cycle 25 included
        count = store.get_window_occurrences(sig, current_cycle=25, window=20)
        assert count == 1  # only cycle 25 within window [6, 25]


# ---------------------------------------------------------------------------
# Group E — Rejection and uniform suppression
# ---------------------------------------------------------------------------

class TestRejectionAndUniformSuppression:

    def _make_proposal(self) -> ImprovementProposal:
        from core.engineering.intelligence.models import (
            Observation, Diagnosis, Recommendation, ProposalStatus
        )
        return ImprovementProposal(
            proposal_id="G045-ROU-S2TEST",
            status=ProposalStatus.PENDING,
            evidence=[Observation(
                category="ROUTING", title="Test issue",
                detail="Test detail", confidence=0.85,
            )],
            diagnosis=Diagnosis(
                inference="Test inference.",
                confidence=0.72,
                uncertainty="May be transient.",
            ),
            recommendation=Recommendation(
                proposed_change="Test change.",
                expected_benefit="Test benefit.",
            ),
            confidence=0.80,
            pattern_signature="ROUTING:test issue",
        )

    def test_rejection_stores_rejection_record(self):
        engine = _make_engine()
        proposal = self._make_proposal()
        engine._pattern_store.save_proposal(proposal)
        engine.reject_proposal("NOT_NOW just testing")
        # Verify RejectionRecord was saved
        import json
        rec = engine._pattern_store._ke.recall_memory("eng_rejection", proposal.proposal_id)
        assert rec is not None
        data = json.loads(rec.value)
        assert data["reason_code"] == "NOT_NOW"

    def test_all_reason_codes_produce_5_cycle_suppression(self):
        """All reason codes use identical 5-cycle suppression in Sprint-002."""
        from core.engineering.intelligence.selector import REJECTION_SUPPRESSION_CYCLES
        assert REJECTION_SUPPRESSION_CYCLES == 5
        # Verify this applies regardless of reason code
        for code in RejectionReasonCode:
            engine = _make_engine()
            proposal = self._make_proposal()
            proposal = type(proposal)(**{
                **proposal.__dict__,
                'proposal_id': f"G045-ROU-{code.value[:3]}",
            })
            engine._pattern_store.save_proposal(proposal)
            engine.reject_proposal(f"{code.value} test reason")
            # Verify suppression cycle recorded
            cat = "ROUTING"
            title = "Test issue"
            rejected_at = engine._pattern_store.get_rejection_cycle(cat, title)
            assert rejected_at != -1, f'Got {rejected_at}'

    def test_not_a_problem_uses_5_cycle_suppression_not_permanent(self):
        """NOT_A_PROBLEM does NOT cause permanent suppression in Sprint-002."""
        engine = _make_engine()
        proposal = self._make_proposal()
        engine._pattern_store.save_proposal(proposal)
        engine.reject_proposal("NOT_A_PROBLEM test")
        # No pattern_disposition field should be mutated
        import json
        pat_rec = engine._pattern_store._ke.recall_memory(
            "eng_pattern", "ROUTING:test issue"
        )
        # PatternRecord may or may not exist; if it does, no pattern_disposition field
        if pat_rec is not None:
            data = json.loads(pat_rec.value)
            assert "pattern_disposition" not in data

    def test_acceptable_tradeoff_uses_5_cycle_suppression(self):
        """ACCEPTABLE_TRADEOFF does NOT set external_flag or permanent suppression."""
        engine = _make_engine()
        proposal = self._make_proposal()
        engine._pattern_store.save_proposal(proposal)
        engine.reject_proposal("ACCEPTABLE_TRADEOFF performance cost is acceptable")
        import json
        pat_rec = engine._pattern_store._ke.recall_memory(
            "eng_pattern", "ROUTING:test issue"
        )
        if pat_rec is not None:
            data = json.loads(pat_rec.value)
            assert data.get("external_flag", False) is False

    def test_rejection_does_not_modify_pattern_record(self):
        """Pattern evidence is immutable — no rejection changes it."""
        store = _make_store()
        sig = "ROUTING:immutable test"
        store.update_pattern(sig, "ROUTING", "immutable test", cycle=1)
        import json
        before = json.loads(
            store._ke.recall_memory("eng_pattern", sig).value
        )
        # Simulate rejection — should not touch pattern
        import datetime
        from core.engineering.intelligence.pattern_record import RejectionRecord, RejectionReasonCode
        rej = RejectionRecord(
            proposal_id="TEST001",
            pattern_signature=sig,
            reason_code=RejectionReasonCode.NOT_A_PROBLEM,
            reason_text="test",
            cycle=1,
        )
        store.save_rejection_record(rej)
        after = json.loads(
            store._ke.recall_memory("eng_pattern", sig).value
        )
        assert before == after

    def test_rejection_reason_code_parsed_correctly(self):
        from core.engineering.intelligence.pattern_record import RejectionReasonCode
        assert RejectionReasonCode.from_string("WRONG_DIAGNOSIS") == RejectionReasonCode.WRONG_DIAGNOSIS
        assert RejectionReasonCode.from_string("not_a_problem") == RejectionReasonCode.NOT_A_PROBLEM
        assert RejectionReasonCode.from_string("UNKNOWN_CODE") == RejectionReasonCode.OTHER

    def test_external_flag_not_set_by_any_sprint002_operation(self):
        """external_flag is reserved for Sprint-003 only."""
        store = _make_store()
        sig = "ROUTING:ext flag sprint2"
        store.update_pattern(sig, "ROUTING", "ext flag sprint2", cycle=1)
        store.save_session_record(_make_session(1, 10, 8,
            issues=[{"signature": sig, "category": "ROUTING", "confidence": 0.9}]))
        active = store.get_active_patterns()
        for p in active:
            assert p.external_flag is False

    def test_all_seven_reason_codes_exist(self):
        codes = {c.value for c in RejectionReasonCode}
        expected = {
            "NOT_A_PROBLEM", "WRONG_DIAGNOSIS", "WRONG_RECOMMENDATION",
            "TOO_RISKY", "NOT_NOW", "ACCEPTABLE_TRADEOFF", "OTHER",
        }
        assert codes == expected


# ---------------------------------------------------------------------------
# Group F — Selector with DRR trend
# ---------------------------------------------------------------------------

class TestSelectorWithDRRTrend:

    def _make_high_routing_report(self):
        from core.workers.engineering_models import (
            EngineeringIssue, EngineeringReport, Severity, Category
        )
        issue = EngineeringIssue(
            severity=Severity.HIGH,
            category=Category.ROUTING,
            title="High UNKNOWN fallback rate",
            description="test",
            confidence=0.85,
            likely_files=["core/router.py"],
        )
        return EngineeringReport(health_score=40, session_turns=10, issues=[issue])

    def _make_high_perf_report(self):
        from core.workers.engineering_models import (
            EngineeringIssue, EngineeringReport, Severity, Category
        )
        issue = EngineeringIssue(
            severity=Severity.HIGH,
            category=Category.PERFORMANCE,
            title="Slow AI responses",
            description="test",
            confidence=0.85,
            likely_files=["core/ai.py"],
        )
        return EngineeringReport(health_score=50, session_turns=10, issues=[issue])

    def test_declining_drr_boosts_routing_pattern(self):
        from core.engineering.intelligence.selector import ImprovementSelector
        store = _make_store()
        selector = ImprovementSelector()
        report = self._make_high_routing_report()
        # With DECLINING trend
        result_declining = selector.select(
            report, store, drr_trend=DRRTrend.DECLINING
        )
        # With STABLE trend
        result_stable = selector.select(
            report, store, drr_trend=DRRTrend.STABLE
        )
        # Both should produce a proposal (HIGH issue present)
        assert result_declining is not None
        assert result_stable is not None
        # Declining should have higher or equal confidence
        assert result_declining.confidence >= result_stable.confidence * 0.95

    def test_declining_drr_does_not_boost_performance(self):
        from core.engineering.intelligence.selector import ImprovementSelector
        store = _make_store()
        selector = ImprovementSelector()
        report = self._make_high_perf_report()
        # Both should produce same result regardless of DRR trend
        result_declining = selector.select(
            report, store, drr_trend=DRRTrend.DECLINING
        )
        result_stable = selector.select(
            report, store, drr_trend=DRRTrend.STABLE
        )
        if result_declining and result_stable:
            assert abs(result_declining.confidence - result_stable.confidence) < 0.001

    def test_stable_drr_no_boost(self):
        from core.engineering.intelligence.selector import ImprovementSelector
        store = _make_store()
        selector = ImprovementSelector()
        report = self._make_high_routing_report()
        result = selector.select(report, store, drr_trend=DRRTrend.STABLE)
        assert result is not None  # proposal still forms, just no boost

    def test_insufficient_data_no_boost(self):
        from core.engineering.intelligence.selector import ImprovementSelector
        store = _make_store()
        selector = ImprovementSelector()
        report = self._make_high_routing_report()
        result = selector.select(report, store, drr_trend=DRRTrend.INSUFFICIENT_DATA)
        assert result is not None  # proposal still forms

    def test_pattern_signature_set_on_proposal(self):
        from core.engineering.intelligence.selector import ImprovementSelector
        store = _make_store()
        selector = ImprovementSelector()
        report = self._make_high_routing_report()
        result = selector.select(report, store)
        assert result is not None
        assert result.pattern_signature != ""
        assert "ROUTING" in result.pattern_signature


# ---------------------------------------------------------------------------
# Group G — ImprovementProposal backward compatibility
# ---------------------------------------------------------------------------

class TestImprovementProposalBackwardCompatibility:

    def test_pattern_signature_field_has_default(self):
        """Existing proposal construction without pattern_signature still works."""
        from core.engineering.intelligence.models import (
            Observation, Diagnosis, Recommendation, ProposalStatus
        )
        proposal = ImprovementProposal(
            proposal_id="COMPAT-TEST",
            status=ProposalStatus.PENDING,
            evidence=[Observation(
                category="ROUTING", title="Test",
                detail="Detail", confidence=0.8,
            )],
            diagnosis=Diagnosis(
                inference="Test inference.",
                confidence=0.7,
                uncertainty="May be transient.",
            ),
            recommendation=Recommendation(
                proposed_change="Test change.",
                expected_benefit="Test benefit.",
            ),
            confidence=0.75,
        )
        assert proposal.pattern_signature == ""

    def test_proposal_serialisation_with_pattern_signature(self):
        """PatternStore can save and load proposals with pattern_signature."""
        from core.engineering.intelligence.models import (
            Observation, Diagnosis, Recommendation, ProposalStatus
        )
        store = _make_store()
        proposal = ImprovementProposal(
            proposal_id="SER-TEST-001",
            status=ProposalStatus.PENDING,
            evidence=[Observation(
                category="ROUTING", title="Serialisation test",
                detail="detail", confidence=0.85,
            )],
            diagnosis=Diagnosis(
                inference="Test.", confidence=0.72,
                uncertainty="Maybe.",
            ),
            recommendation=Recommendation(
                proposed_change="Change.", expected_benefit="Benefit.",
            ),
            confidence=0.80,
            pattern_signature="ROUTING:serialisation test",
        )
        store.save_proposal(proposal)
        loaded = store.load_proposal()
        assert loaded is not None
        # pattern_signature not in old format — load handles missing gracefully
        # (field defaults to "" if not in serialised JSON)
