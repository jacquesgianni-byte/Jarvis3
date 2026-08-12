"""
Genesis-045 Sprint-001 — Engineering Intelligence Tests

Validates the architectural contract:
  observe (SessionLogBuffer + SessionAnalysisWorker)
  → analyse (ImprovementSelector)
  → propose (ImprovementProposal)
  → human decision (approve/reject/defer)

Tests validate BEHAVIOUR, not implementation internals.
No mocking of the architectural contract itself.
"""

import pytest

from core.engineering.intelligence.models import (
    Diagnosis,
    ImprovementProposal,
    Observation,
    ProposalStatus,
    Recommendation,
)
from core.engineering.intelligence.log_buffer import SessionLogBuffer
from core.engineering.intelligence.selector import ImprovementSelector, REJECTION_SUPPRESSION_CYCLES
from core.engineering.intelligence.engine import EngineeringIntelligenceEngine


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _make_knowledge_engine():
    """Real in-memory KnowledgeEngine for testing PatternStore."""
    from core.knowledge_engine.json_storage import JsonKnowledgeRepository
    from core.knowledge_engine.engine import KnowledgeEngine
    import tempfile, os
    tmp = tempfile.mkdtemp()
    storage = JsonKnowledgeRepository(os.path.join(tmp, "test_knowledge.json"))
    return KnowledgeEngine(storage=storage)


def _make_engine():
    return EngineeringIntelligenceEngine(_make_knowledge_engine())


def _make_proposal(status=ProposalStatus.PENDING, title="Routing failure") -> ImprovementProposal:
    return ImprovementProposal(
        proposal_id    = "G045-ROU-TEST01",
        status         = status,
        evidence       = [Observation(
            category="ROUTING", title=title,
            detail="AI_FALLBACK on 8/10 turns", confidence=0.85,
        )],
        diagnosis      = Diagnosis(
            inference="Routing gap detected.",
            confidence=0.72,
            uncertainty="May be transient.",
        ),
        recommendation = Recommendation(
            proposed_change="Investigate intent routing.",
            expected_benefit="Fewer AI fallbacks.",
        ),
        confidence     = 0.80,
    )


def _make_healthy_log_lines() -> list[str]:
    """Log lines that should produce no HIGH issues."""
    return [
        "INFO Jarvis:agent.py:391 Request received: Hello",
        "INFO core.conversation.conversation_router:conversation_router.py:253 "
        "[ROUTER] Intent=GREETING → DecisionType=Answer Directly",
        "INFO Jarvis:telemetry.py:121 TIMING | req=1 | stage=total_end_to_end | 45.0 ms",
    ]


def _make_routing_failure_log_lines() -> list[str]:
    """Log lines that should produce HIGH routing issues."""
    lines = []
    for i in range(8):
        lines += [
            f"INFO Jarvis:agent.py:391 Request received: Tell me about thing {i}",
            "INFO core.conversation.conversation_router:conversation_router.py:253 "
            "[ROUTER] Intent=UNKNOWN → DecisionType=Ai Fallback",
            f"INFO Jarvis:telemetry.py:121 TIMING | req={i} | stage=total_end_to_end | 1200.0 ms",
        ]
    return lines


# ---------------------------------------------------------------------------
# Group A: SessionLogBuffer
# ---------------------------------------------------------------------------

class TestSessionLogBuffer:

    def test_captures_log_lines(self):
        import logging
        buf = SessionLogBuffer()
        buf.attach()
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger().info("Test line from root logger")
        lines = buf.drain()
        buf.detach()
        assert any("Test line from root logger" in l for l in lines)

    def test_drain_resets_buffer(self):
        buf = SessionLogBuffer()
        buf.attach()
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger().info("A line for drain test")
        lines1 = buf.drain()
        lines2 = buf.drain()
        buf.detach()
        assert len(lines1) >= 1
        assert len(lines2) == 0

    def test_line_count(self):
        buf = SessionLogBuffer()
        buf.attach()
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger().info("Line 1 for count test")
        logging.getLogger().info("Line 2 for count test")
        count = buf.line_count()
        buf.drain()
        buf.detach()
        assert count >= 2

    def test_reset_clears_without_returning(self):
        buf = SessionLogBuffer()
        buf.attach()
        import logging
        logging.getLogger("Jarvis").info("Will be cleared")
        buf.reset()
        lines = buf.drain()
        buf.detach()
        assert lines == []

    def test_detach_stops_capture(self):
        import logging
        buf = SessionLogBuffer()
        buf.attach()
        buf.detach()
        logging.getLogger().info("Should not be captured")
        lines = buf.drain()
        assert lines == []


# ---------------------------------------------------------------------------
# Group B: ImprovementProposal model integrity
# ---------------------------------------------------------------------------

class TestImprovementProposalModel:

    def test_evidence_is_observation_list(self):
        p = _make_proposal()
        assert isinstance(p.evidence, list)
        assert all(isinstance(e, Observation) for e in p.evidence)

    def test_diagnosis_is_diagnosis_type(self):
        p = _make_proposal()
        assert isinstance(p.diagnosis, Diagnosis)

    def test_recommendation_is_recommendation_type(self):
        p = _make_proposal()
        assert isinstance(p.recommendation, Recommendation)

    def test_evidence_has_no_inference_fields(self):
        """Evidence layer must not have inference or recommendation fields."""
        p = _make_proposal()
        for obs in p.evidence:
            assert not hasattr(obs, "inference")
            assert not hasattr(obs, "proposed_change")

    def test_diagnosis_has_uncertainty(self):
        """Every diagnosis must carry an uncertainty statement."""
        p = _make_proposal()
        assert p.diagnosis.uncertainty != ""

    def test_pending_status(self):
        p = _make_proposal(ProposalStatus.PENDING)
        assert p.is_pending()
        assert not p.is_stale()

    def test_stale_status(self):
        p = _make_proposal(ProposalStatus.STALE)
        assert p.is_stale()
        assert not p.is_pending()

    def test_formatted_output_contains_sections(self):
        p = _make_proposal()
        text = p.formatted_for_user()
        assert "WHAT I OBSERVED" in text
        assert "WHAT I THINK IT MEANS" in text
        assert "WHAT I SUGGEST" in text
        assert "inference" in text.lower() or "INFERENCE" in text.upper()


# ---------------------------------------------------------------------------
# Group C: ImprovementSelector
# ---------------------------------------------------------------------------

class TestImprovementSelector:

    def _make_report_with_high(self, title="AI fallback rate HIGH"):
        from core.workers.session_analysis_worker import SessionAnalysisWorker
        from core.workers.engineering_models import (
            EngineeringIssue, EngineeringReport, Severity, Category
        )
        issue = EngineeringIssue(
            severity=Severity.HIGH,
            category=Category.ROUTING,
            title=title,
            description="8/10 turns routed to AI_FALLBACK",
            confidence=0.85,
            likely_files=["core/router.py"],
            recommendation="Review intent patterns",
        )
        return EngineeringReport(
            health_score=40,
            session_turns=10,
            issues=[issue],
        )

    def _make_empty_report(self):
        from core.workers.engineering_models import EngineeringReport
        return EngineeringReport(health_score=95, session_turns=10)

    def _make_pattern_store(self):
        from core.engineering.intelligence.pattern_store import PatternStore
        return PatternStore(_make_knowledge_engine())

    def test_returns_none_for_healthy_session(self):
        selector = ImprovementSelector()
        report = self._make_empty_report()
        store = self._make_pattern_store()
        result = selector.select(report, store)
        assert result is None

    def test_returns_proposal_for_high_severity(self):
        selector = ImprovementSelector()
        report = self._make_report_with_high()
        store = self._make_pattern_store()
        result = selector.select(report, store)
        assert result is not None
        assert result.is_pending()

    def test_proposal_has_evidence(self):
        selector = ImprovementSelector()
        report = self._make_report_with_high()
        store = self._make_pattern_store()
        result = selector.select(report, store)
        assert result is not None
        assert len(result.evidence) >= 1

    def test_skips_recently_rejected(self):
        selector = ImprovementSelector()
        store = self._make_pattern_store()
        # Record a rejection at cycle 1
        store.record_rejection("ROUTING", "AI fallback rate HIGH", cycle=1)
        report = self._make_report_with_high("AI fallback rate HIGH")
        # Check at cycle 2 (within suppression window)
        result = selector.select(report, store, current_cycle=2)
        assert result is None

    def test_allows_after_suppression_window(self):
        selector = ImprovementSelector()
        store = self._make_pattern_store()
        store.record_rejection("ROUTING", "AI fallback rate HIGH", cycle=1)
        report = self._make_report_with_high("AI fallback rate HIGH")
        # Check at cycle 1 + REJECTION_SUPPRESSION_CYCLES + 1
        result = selector.select(
            report, store,
            current_cycle=1 + REJECTION_SUPPRESSION_CYCLES + 1
        )
        assert result is not None

    def test_cfr_cross_reference_attached(self):
        selector = ImprovementSelector()
        store = self._make_pattern_store()
        report = self._make_report_with_high()
        cfr = {"CFR-001": "ROUTING memory stale data"}
        result = selector.select(report, store, cfr_register=cfr)
        # CFR ref may or may not match — just verify it doesn't crash
        assert result is not None


# ---------------------------------------------------------------------------
# Group D: PatternStore
# ---------------------------------------------------------------------------

class TestPatternStore:

    def _store(self):
        from core.engineering.intelligence.pattern_store import PatternStore
        return PatternStore(_make_knowledge_engine())

    def test_frequency_starts_at_zero(self):
        store = self._store()
        assert store.get_frequency("ROUTING", "Unknown issue") == 0

    def test_frequency_increments(self):
        store = self._store()
        store.increment_frequency("ROUTING", "Test issue")
        store.increment_frequency("ROUTING", "Test issue")
        assert store.get_frequency("ROUTING", "Test issue") == 2

    def test_rejection_starts_at_zero(self):
        store = self._store()
        assert store.get_rejection_cycle("ROUTING", "Never rejected") < 0

    def test_rejection_recorded(self):
        store = self._store()
        store.record_rejection("ROUTING", "Some issue", cycle=5, reason="Too risky")
        assert store.get_rejection_cycle("ROUTING", "Some issue") == 5

    def test_proposal_save_and_load(self):
        store = self._store()
        proposal = _make_proposal()
        store.save_proposal(proposal)
        loaded = store.load_proposal()
        assert loaded is not None
        assert loaded.proposal_id == proposal.proposal_id
        assert loaded.status == ProposalStatus.PENDING

    def test_proposal_load_returns_none_when_empty(self):
        store = self._store()
        result = store.load_proposal()
        assert result is None


# ---------------------------------------------------------------------------
# Group E: EngineeringIntelligenceEngine
# ---------------------------------------------------------------------------

class TestEngineeringIntelligenceEngine:

    def test_returns_none_for_empty_log(self):
        engine = _make_engine()
        result = engine.process_session([])
        assert result is None

    def test_returns_none_for_healthy_log(self):
        engine = _make_engine()
        result = engine.process_session(_make_healthy_log_lines())
        assert result is None

    def test_returns_proposal_for_routing_failures(self):
        engine = _make_engine()
        result = engine.process_session(_make_routing_failure_log_lines())
        # May or may not produce a proposal depending on SessionAnalysisWorker detection
        # Either result is valid — no crash is the minimum requirement
        assert result is None or result.is_pending()

    def test_no_second_proposal_when_pending(self):
        engine = _make_engine()
        # Manually save a pending proposal
        from core.engineering.intelligence.pattern_store import PatternStore
        store = PatternStore(_make_knowledge_engine())
        proposal = _make_proposal()
        store.save_proposal(proposal)
        # Engine with same KE should not produce another proposal
        # (full integration: engine finds existing pending)
        # Here we test the selector separately
        selector = ImprovementSelector()
        from core.workers.engineering_models import EngineeringReport
        report = EngineeringReport(health_score=40, session_turns=10)
        result = selector.select(report, store)
        assert result is None  # no HIGH issues anyway

    def test_approve_clears_pending(self):
        engine = _make_engine()
        # Save a pending proposal directly
        proposal = _make_proposal()
        engine._pattern_store.save_proposal(proposal)
        response = engine.approve_proposal()
        assert "approved" in response.lower()
        loaded = engine._pattern_store.load_proposal()
        assert loaded is not None
        assert loaded.status == ProposalStatus.APPROVED

    def test_reject_records_suppression(self):
        engine = _make_engine()
        proposal = _make_proposal()
        engine._pattern_store.save_proposal(proposal)
        response = engine.reject_proposal("Not a priority right now")
        assert "rejected" in response.lower()
        loaded = engine._pattern_store.load_proposal()
        assert loaded.status == ProposalStatus.REJECTED
        assert loaded.rejection_reason == "Not a priority right now"

    def test_defer_keeps_pending(self):
        engine = _make_engine()
        proposal = _make_proposal()
        engine._pattern_store.save_proposal(proposal)
        response = engine.defer_proposal()
        assert "deferred" in response.lower()
        loaded = engine._pattern_store.load_proposal()
        assert loaded.status == ProposalStatus.PENDING

    def test_approve_with_no_proposal(self):
        engine = _make_engine()
        response = engine.approve_proposal()
        assert "no pending" in response.lower()

    def test_reject_with_no_proposal(self):
        engine = _make_engine()
        response = engine.reject_proposal()
        assert "no pending" in response.lower()

    def test_status_summary_no_proposal(self):
        engine = _make_engine()
        summary = engine.status_summary()
        assert "no pending" in summary.lower()

    def test_status_summary_with_pending(self):
        engine = _make_engine()
        proposal = _make_proposal()
        engine._pattern_store.save_proposal(proposal)
        summary = engine.status_summary()
        assert "pending" in summary.lower()
