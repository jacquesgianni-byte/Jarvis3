"""
Genesis-049: Content-aware local response tests.

Principle: ANSWER_DIRECTLY response is grounded in what was understood.
Not a type label. Not a phrase dictionary. Actual content.

Rules verified:
- Response references the understood event content
- Response is short (under 80 chars)
- Response does not call AI
- Existing temporal recall unaffected
- "I finally finished that bloody report." stays AI fallback
"""
from __future__ import annotations
import pytest


def _compose(text: str) -> str:
    """Run _compose_acknowledgement via the actual pipeline."""
    import sys
    sys.path.insert(0, r"C:\Users\ljmas\Desktop\jarvis3")
    from core.conversation.fact_extractor import FactExtractor, FactType
    from core.conversation.temporal_parser import TemporalParser
    from core.agent import Agent

    fe = FactExtractor(temporal_parser=TemporalParser())
    facts = fe.extract(text)
    # Create a minimal agent just to call the method
    a = Agent.__new__(Agent)
    return a._compose_acknowledgement(facts, text)


class TestComposeAcknowledgement:

    def test_event_tap_references_content(self):
        """Response must reference the understood event, not just 'Got it.'"""
        msg = _compose("I replaced the broken tap yesterday.")
        assert msg != "Got it.", "Must not return hardcoded fallback"
        assert len(msg) < 80, "Must be short"
        # Should mention something from the event
        assert any(word in msg.lower() for word in ["replaced", "broken", "tap", "yesterday"]),             f"Response should reference event content. Got: {msg!r}"

    def test_event_shed_references_content(self):
        """Shed demolition response must reference the event."""
        msg = _compose("I demolished the old shed last Saturday.")
        assert msg != "Got it."
        assert len(msg) < 80
        assert any(word in msg.lower() for word in ["demolished", "shed", "saturday"]),             f"Response should reference event content. Got: {msg!r}"

    def test_response_is_short(self):
        """All responses must be concise."""
        msg = _compose("I replaced the broken tap yesterday.")
        assert len(msg) < 80, f"Response too long: {len(msg)} chars: {msg!r}"

    def test_no_leading_i_in_response(self):
        """'I demolished...' should not echo as 'Got it — I demolished...'"""
        msg = _compose("I demolished the old shed last Saturday.")
        # The stripped value should not start with "I "
        grounded_part = msg.replace("Got it — ", "").rstrip(".")
        assert not grounded_part.lower().startswith("i "),             f"Should strip leading 'I': {msg!r}"

    def test_no_facts_returns_fallback(self):
        """When no facts are extracted, fall back to 'Got it.'"""
        from core.agent import Agent
        a = Agent.__new__(Agent)
        msg = a._compose_acknowledgement([], "That's a great idea.")
        assert msg == "Got it."

    def test_no_temporal_stays_ai_fallback(self):
        """'I finally finished that bloody report.' has no temporal anchor.
        Genesis-049 must NOT expand understanding coverage.
        FactExtractor returns no EVENT — stays as AI fallback.
        """
        from core.conversation.fact_extractor import FactExtractor, FactType
        from core.conversation.temporal_parser import TemporalParser
        fe = FactExtractor(temporal_parser=TemporalParser())
        facts = fe.extract("I finally finished that bloody report.")
        event_facts = [f for f in facts if f.fact_type == FactType.EVENT]
        assert not event_facts,             "No temporal anchor → no EVENT → must stay AI fallback. "             "Genesis-049 must not expand FactExtractor coverage."


class TestAcknowledgementIntegration:
    """Integration: full pipeline produces content-aware response."""

    def test_temporal_recall_unaffected(self, tmp_path):
        """'What did I do last Saturday?' must still use TemporalRecall."""
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        from core.conversation.temporal_parser import TemporalParser
        e = TemporalRecallEngine(temporal_parser=TemporalParser())
        q = e.detect_query("What did I do last Saturday?")
        assert q is not None, "TemporalRecall must still detect this query"
