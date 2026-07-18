"""
Genesis-020 Sprint-004 — Decision Engine Tests
Completely self-contained. No dependency on other test files.

Coverage (target 130-170 tests):
  - DecisionStatus: all statuses, labels, is_active
  - ArchitecturalDecision: immutable, fields, explain(), with_status(), summary()
  - ArchitecturalDecision: with_payload(), version, date_str
  - DecisionEngine: record, supersede, reject, get, all_decisions
  - DecisionEngine: active, superseded, rejected, proposed, by_status
  - DecisionEngine: search, explain, latest, on_date, count, summary
  - DecisionEngine: Projection replay from Timeline events
  - DecisionEngine: apply() for all DECISION_* event types
  - DecisionEngine: legacy DECISION event handling
  - DecisionQueryEngine: can_answer for all query types
  - DecisionQueryEngine: answers for all query types
  - DecisionQueryEngine: miss when empty, graceful empty responses
  - DecisionInspector: returns string, shows counts, is_empty
  - EventType: new DECISION_* types exist
  - Timeline integration: DECISION_* events round-trip
  - Backwards compatibility: no regressions
  - Regression safety: existing tests unaffected
"""

import sys
from datetime import UTC, datetime
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.architectural_decision import (
    ArchitecturalDecision, DecisionStatus
)
from core.conversation.decision_engine import DecisionEngine
from core.conversation.decision_query import DecisionQueryEngine, DecisionQueryResult
from core.conversation.decision_inspector import DecisionInspector
from core.conversation.timeline_event import EventType, TimelineEvent
from core.conversation.conversation_timeline import ConversationTimeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_decision(
    title="Use Event Sourcing",
    decision="Adopt an append-only immutable Timeline as the source of truth.",
    reason="Eliminates direct state mutation, supports replay, simplifies Worker coordination.",
    status=DecisionStatus.ACCEPTED,
    source_turn=5,
    alternatives=("Direct state mutation", "External database"),
    tags=("architecture", "timeline"),
    confidence=0.95,
    **kwargs,
) -> ArchitecturalDecision:
    return ArchitecturalDecision(
        title=title,
        decision=decision,
        reason=reason,
        status=status,
        source_turn=source_turn,
        alternatives=tuple(alternatives),
        tags=tuple(tags),
        confidence=confidence,
        **kwargs,
    )


def make_engine() -> DecisionEngine:
    return DecisionEngine()


def make_query_engine(engine=None):
    e = engine or make_engine()
    return DecisionQueryEngine(e), e


def make_timeline_event(
    event_type=EventType.DECISION_ACCEPTED,
    value="Use Event Sourcing",
    turn=5,
    payload=None,
    notes="",
) -> TimelineEvent:
    return TimelineEvent(
        event_type=event_type,
        value=value,
        turn=turn,
        payload=payload or {},
        notes=notes,
    )


# ===========================================================================
# 1. DECISION STATUS
# ===========================================================================

class TestDecisionStatus:

    def test_all_statuses_exist(self):
        for name in ["PROPOSED", "ACCEPTED", "SUPERSEDED", "REJECTED", "EXPERIMENTAL"]:
            assert hasattr(DecisionStatus, name)

    def test_values_unique(self):
        values = [s.value for s in DecisionStatus]
        assert len(values) == len(set(values))

    def test_label_human_readable(self):
        assert DecisionStatus.ACCEPTED.label() == "Accepted"
        assert DecisionStatus.SUPERSEDED.label() == "Superseded"
        assert DecisionStatus.EXPERIMENTAL.label() == "Experimental"

    def test_is_active_accepted(self):
        assert DecisionStatus.ACCEPTED.is_active

    def test_is_active_experimental(self):
        assert DecisionStatus.EXPERIMENTAL.is_active

    def test_is_not_active_superseded(self):
        assert not DecisionStatus.SUPERSEDED.is_active

    def test_is_not_active_rejected(self):
        assert not DecisionStatus.REJECTED.is_active

    def test_is_not_active_proposed(self):
        assert not DecisionStatus.PROPOSED.is_active


# ===========================================================================
# 2. ARCHITECTURAL DECISION — data model
# ===========================================================================

class TestArchitecturalDecision:

    def test_decision_is_frozen(self):
        d = make_decision()
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            d.title = "changed"

    def test_has_auto_id(self):
        d = make_decision()
        assert d.id
        assert len(d.id) > 0

    def test_has_timestamp(self):
        d = make_decision()
        assert isinstance(d.timestamp, datetime)

    def test_default_version_is_one(self):
        d = make_decision()
        assert d.version == 1

    def test_default_payload_is_empty(self):
        d = make_decision()
        assert d.payload == {}

    def test_alternatives_stored_as_tuple(self):
        d = make_decision()
        assert isinstance(d.alternatives, tuple)

    def test_tags_stored_as_tuple(self):
        d = make_decision()
        assert isinstance(d.tags, tuple)

    def test_str_includes_title(self):
        d = make_decision(title="Use Event Sourcing")
        assert "Use Event Sourcing" in str(d)

    def test_str_includes_status(self):
        d = make_decision(status=DecisionStatus.ACCEPTED)
        assert "Accepted" in str(d)

    def test_date_str_format(self):
        d = make_decision()
        assert len(d.date_str()) == 10
        assert d.date_str()[4] == "-"

    def test_summary_includes_title(self):
        d = make_decision(title="Use Event Sourcing")
        assert "Use Event Sourcing" in d.summary()

    def test_summary_includes_status(self):
        d = make_decision(status=DecisionStatus.ACCEPTED)
        assert "Accepted" in d.summary()

    def test_summary_includes_turn(self):
        d = make_decision(source_turn=42)
        assert "42" in d.summary()

    def test_with_status_returns_new_instance(self):
        d = make_decision(status=DecisionStatus.ACCEPTED)
        d2 = d.with_status(DecisionStatus.SUPERSEDED)
        assert d2 is not d
        assert d2.status == DecisionStatus.SUPERSEDED
        assert d.status == DecisionStatus.ACCEPTED  # original unchanged

    def test_with_status_preserves_id(self):
        d = make_decision()
        d2 = d.with_status(DecisionStatus.SUPERSEDED)
        assert d2.id == d.id

    def test_with_status_preserves_all_fields(self):
        d = make_decision(title="X", reason="Y", confidence=0.8)
        d2 = d.with_status(DecisionStatus.REJECTED)
        assert d2.title == "X"
        assert d2.reason == "Y"
        assert d2.confidence == 0.8


# ===========================================================================
# 3. ARCHITECTURAL DECISION — explain()
# ===========================================================================

class TestArchitecturalDecisionExplain:

    def test_explain_includes_title(self):
        d = make_decision(title="Use Event Sourcing")
        assert "Use Event Sourcing" in d.explain()

    def test_explain_includes_decision(self):
        d = make_decision(decision="Adopt immutable Timeline.")
        assert "Adopt immutable Timeline" in d.explain()

    def test_explain_includes_reason(self):
        d = make_decision(reason="Supports replay and simplifies Workers.")
        assert "Supports replay" in d.explain()

    def test_explain_includes_alternatives(self):
        d = make_decision(alternatives=("Direct mutation", "External DB"))
        explanation = d.explain()
        assert "Direct mutation" in explanation
        assert "External DB" in explanation

    def test_explain_includes_status(self):
        d = make_decision(status=DecisionStatus.EXPERIMENTAL)
        assert "Experimental" in d.explain()

    def test_explain_includes_confidence(self):
        d = make_decision(confidence=0.95)
        assert "95%" in d.explain()

    def test_explain_includes_turn(self):
        d = make_decision(source_turn=15)
        assert "15" in d.explain()

    def test_explain_no_alternatives_section_when_empty(self):
        d = make_decision(alternatives=())
        assert "Alternatives considered" not in d.explain()

    def test_explain_supersedes_note(self):
        d = make_decision(supersedes_id="old-id-123")
        assert "supersedes" in d.explain().lower()


# ===========================================================================
# 4. DECISION ENGINE — basic operations
# ===========================================================================

class TestDecisionEngineBasic:

    def test_starts_empty(self):
        e = make_engine()
        assert e.count() == 0
        assert e.all_decisions() == []

    def test_record_single_decision(self):
        e = make_engine()
        e.record(make_decision())
        assert e.count() == 1

    def test_all_decisions_returns_list(self):
        e = make_engine()
        e.record(make_decision())
        assert isinstance(e.all_decisions(), list)

    def test_all_decisions_returns_copy(self):
        e = make_engine()
        e.record(make_decision())
        copy = e.all_decisions()
        copy.clear()
        assert e.count() == 1

    def test_get_by_id(self):
        e = make_engine()
        d = make_decision()
        e.record(d)
        retrieved = e.get(d.id)
        assert retrieved is not None
        assert retrieved.id == d.id

    def test_get_missing_id_returns_none(self):
        e = make_engine()
        assert e.get("nonexistent-id") is None

    def test_insertion_order_preserved(self):
        e = make_engine()
        d1 = make_decision(title="First", source_turn=1)
        d2 = make_decision(title="Second", source_turn=2)
        d3 = make_decision(title="Third", source_turn=3)
        e.record(d1); e.record(d2); e.record(d3)
        titles = [d.title for d in e.all_decisions()]
        assert titles == ["First", "Second", "Third"]


# ===========================================================================
# 5. DECISION ENGINE — status filtering
# ===========================================================================

class TestDecisionEngineFiltering:

    def setup_method(self):
        self.e = make_engine()
        self.d_accepted  = make_decision(title="Event Sourcing", status=DecisionStatus.ACCEPTED)
        self.d_proposed  = make_decision(title="Vector DB", status=DecisionStatus.PROPOSED)
        self.d_rejected  = make_decision(title="Mutable State", status=DecisionStatus.REJECTED)
        self.d_experimental = make_decision(title="Shared Memory", status=DecisionStatus.EXPERIMENTAL)
        for d in [self.d_accepted, self.d_proposed, self.d_rejected, self.d_experimental]:
            self.e.record(d)

    def test_active_returns_accepted_and_experimental(self):
        active = self.e.active()
        titles = [d.title for d in active]
        assert "Event Sourcing" in titles
        assert "Shared Memory" in titles
        assert "Mutable State" not in titles
        assert "Vector DB" not in titles

    def test_proposed(self):
        proposed = self.e.proposed()
        assert len(proposed) == 1
        assert proposed[0].title == "Vector DB"

    def test_rejected(self):
        rejected = self.e.rejected()
        assert len(rejected) == 1
        assert rejected[0].title == "Mutable State"

    def test_by_status(self):
        experimental = self.e.by_status(DecisionStatus.EXPERIMENTAL)
        assert len(experimental) == 1
        assert experimental[0].title == "Shared Memory"

    def test_count_by_status(self):
        assert self.e.count(DecisionStatus.ACCEPTED) == 1
        assert self.e.count(DecisionStatus.REJECTED) == 1
        assert self.e.count() == 4


# ===========================================================================
# 6. DECISION ENGINE — supersede and reject
# ===========================================================================

class TestDecisionEngineTransitions:

    def test_supersede_marks_old_as_superseded(self):
        e = make_engine()
        old = make_decision(title="Old Architecture")
        e.record(old)
        new = make_decision(title="New Architecture", supersedes_id=old.id)
        e.supersede(old.id, new)
        assert e.get(old.id).status == DecisionStatus.SUPERSEDED

    def test_supersede_adds_new_decision(self):
        e = make_engine()
        old = make_decision(title="Old")
        e.record(old)
        new = make_decision(title="New")
        e.supersede(old.id, new)
        assert e.count() == 2

    def test_supersede_missing_id_still_records_new(self):
        e = make_engine()
        new = make_decision(title="New")
        e.supersede("nonexistent", new)
        assert e.count() == 1

    def test_reject_marks_decision_rejected(self):
        e = make_engine()
        d = make_decision(status=DecisionStatus.PROPOSED)
        e.record(d)
        e.reject(d.id, "Too complex.")
        assert e.get(d.id).status == DecisionStatus.REJECTED

    def test_reject_updates_reason(self):
        e = make_engine()
        d = make_decision(reason="Original reason")
        e.record(d)
        e.reject(d.id, "New rejection reason.")
        assert e.get(d.id).reason == "New rejection reason."

    def test_reject_missing_id_does_nothing(self):
        e = make_engine()
        e.reject("nonexistent", "reason")  # should not raise
        assert e.count() == 0

    def test_superseded_list(self):
        e = make_engine()
        old = make_decision(title="Old")
        e.record(old)
        new = make_decision(title="New")
        e.supersede(old.id, new)
        superseded = e.superseded()
        assert len(superseded) == 1
        assert superseded[0].title == "Old"


# ===========================================================================
# 7. DECISION ENGINE — search
# ===========================================================================

class TestDecisionEngineSearch:

    def setup_method(self):
        self.e = make_engine()
        self.e.record(make_decision(
            title="Event Sourcing",
            decision="Use immutable Timeline.",
            reason="Supports replay.",
            tags=("architecture",)
        ))
        self.e.record(make_decision(
            title="Projection Pattern",
            decision="Derive state from events.",
            reason="Keeps Timeline as source of truth.",
            tags=("architecture", "pattern")
        ))
        self.e.record(make_decision(
            title="Reject Mutable State",
            decision="Never mutate records in place.",
            reason="Prevents race conditions.",
            status=DecisionStatus.REJECTED
        ))

    def test_search_by_title(self):
        results = self.e.search("Event Sourcing")
        assert len(results) == 1
        assert results[0].title == "Event Sourcing"

    def test_search_by_reason(self):
        results = self.e.search("replay")
        assert len(results) >= 1

    def test_search_by_tag(self):
        results = self.e.search("pattern")
        assert any(d.title == "Projection Pattern" for d in results)

    def test_search_case_insensitive(self):
        results = self.e.search("event sourcing")
        assert len(results) >= 1

    def test_search_no_results(self):
        results = self.e.search("quantum physics")
        assert results == []

    def test_search_across_all_statuses(self):
        results = self.e.search("Mutable")
        assert any(d.title == "Reject Mutable State" for d in results)


# ===========================================================================
# 8. DECISION ENGINE — query helpers
# ===========================================================================

class TestDecisionEngineQueryHelpers:

    def test_latest_returns_most_recent(self):
        e = make_engine()
        e.record(make_decision(title="First"))
        e.record(make_decision(title="Second"))
        e.record(make_decision(title="Third"))
        latest = e.latest(2)
        assert len(latest) == 2
        assert latest[-1].title == "Third"

    def test_latest_empty_engine(self):
        e = make_engine()
        assert e.latest() == []

    def test_on_date_today(self):
        e = make_engine()
        e.record(make_decision())
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        results = e.on_date(today)
        assert len(results) == 1

    def test_on_date_no_match(self):
        e = make_engine()
        e.record(make_decision())
        results = e.on_date("2020-01-01")
        assert results == []

    def test_today(self):
        e = make_engine()
        e.record(make_decision())
        assert len(e.today()) == 1

    def test_summary_dict(self):
        e = make_engine()
        e.record(make_decision(title="A", status=DecisionStatus.ACCEPTED))
        e.record(make_decision(title="B", status=DecisionStatus.REJECTED))
        s = e.summary()
        assert s["total"] == 2
        assert s["active"] == 1
        assert s["rejected"] == 1
        assert "A" in s["latest"] or "B" in s["latest"]

    def test_explain_by_id(self):
        e = make_engine()
        d = make_decision(title="Event Sourcing", reason="Supports replay.")
        e.record(d)
        explanation = e.explain(d.id)
        assert "Event Sourcing" in explanation
        assert "Supports replay" in explanation

    def test_explain_missing_id(self):
        e = make_engine()
        result = e.explain("nonexistent")
        assert "No decision found" in result


# ===========================================================================
# 9. DECISION ENGINE — Projection replay
# ===========================================================================

class TestDecisionEngineProjection:

    def test_is_projection(self):
        from core.conversation.projection import Projection
        assert isinstance(make_engine(), Projection)

    def test_apply_decision_accepted_event(self):
        e = make_engine()
        event = make_timeline_event(EventType.DECISION_ACCEPTED, "Use Flask")
        e.apply(event)
        assert e.count() == 1
        assert e.all_decisions()[0].status == DecisionStatus.ACCEPTED

    def test_apply_decision_proposed_event(self):
        e = make_engine()
        event = make_timeline_event(EventType.DECISION_PROPOSED, "Consider GraphQL")
        e.apply(event)
        assert e.count() == 1
        assert e.all_decisions()[0].status == DecisionStatus.PROPOSED

    def test_apply_decision_rejected_event(self):
        e = make_engine()
        event = make_timeline_event(EventType.DECISION_REJECTED, "Reject Mutable State")
        e.apply(event)
        assert e.count() == 1
        assert e.all_decisions()[0].status == DecisionStatus.REJECTED

    def test_apply_decision_superseded_event(self):
        e = make_engine()
        # First record an accepted decision
        old_event = make_timeline_event(
            EventType.DECISION_ACCEPTED, "Old Architecture",
            payload={"decision_id": "old-123"}
        )
        e.apply(old_event)
        # Now supersede it
        new_event = make_timeline_event(
            EventType.DECISION_SUPERSEDED, "New Architecture",
            payload={"superseded_id": "old-123", "decision_id": "new-456"}
        )
        e.apply(new_event)
        assert e.get("old-123").status == DecisionStatus.SUPERSEDED
        assert e.count() == 2

    def test_apply_legacy_decision_event(self):
        e = make_engine()
        event = make_timeline_event(EventType.DECISION, "Use Tavily")
        e.apply(event)
        assert e.count() == 1
        assert e.all_decisions()[0].status == DecisionStatus.ACCEPTED

    def test_replay_from_timeline(self):
        tl = ConversationTimeline()
        tl.record(make_timeline_event(EventType.DECISION_ACCEPTED, "Event Sourcing", turn=5))
        tl.record(make_timeline_event(EventType.DECISION_ACCEPTED, "Projection Pattern", turn=10))
        tl.record(make_timeline_event(EventType.DECISION_REJECTED, "Mutable State", turn=15))

        e = make_engine()
        tl.replay(e)

        assert e.count() == 3
        assert len(e.active()) == 2
        assert len(e.rejected()) == 1

    def test_replay_is_deterministic(self):
        tl = ConversationTimeline()
        tl.record(make_timeline_event(EventType.DECISION_ACCEPTED, "A", turn=1))
        tl.record(make_timeline_event(EventType.DECISION_ACCEPTED, "B", turn=2))

        e1 = make_engine()
        e2 = make_engine()
        tl.replay(e1)
        tl.replay(e2)

        assert [d.decision for d in e1.all_decisions()] == \
               [d.decision for d in e2.all_decisions()]

    def test_on_replay_complete_called(self):
        tl = ConversationTimeline()
        e = make_engine()
        tl.replay(e)  # should not raise

    def test_apply_bad_event_does_not_crash(self):
        e = make_engine()
        bad_event = make_timeline_event(EventType.DECISION_ACCEPTED, "")  # empty value
        e.apply(bad_event)  # should not raise, just skip


# ===========================================================================
# 10. DECISION QUERY ENGINE — can_answer
# ===========================================================================

class TestDecisionQueryCanAnswer:

    def setup_method(self):
        self.qe, _ = make_query_engine()

    def test_why_did_we_adopt(self):
        assert self.qe.can_answer("Why did we adopt Event Sourcing?")

    def test_why_did_we_choose(self):
        assert self.qe.can_answer("Why did we choose Flask?")

    def test_what_decisions(self):
        assert self.qe.can_answer("What architectural decisions have we made?")

    def test_what_did_we_decide_today(self):
        assert self.qe.can_answer("What did we decide today?")

    def test_what_did_we_decide_yesterday(self):
        assert self.qe.can_answer("What did we decide yesterday?")

    def test_which_active(self):
        assert self.qe.can_answer("Which decisions are still active?")

    def test_which_superseded(self):
        assert self.qe.can_answer("Which decisions have been superseded?")

    def test_why_rejected(self):
        assert self.qe.can_answer("Why did we reject that idea?")

    def test_how_many(self):
        assert self.qe.can_answer("How many decisions have we made?")

    def test_show_decisions(self):
        assert self.qe.can_answer("show decisions")

    def test_slash_decisions(self):
        assert self.qe.can_answer("/decisions")

    def test_explain_decision(self):
        assert self.qe.can_answer("Explain the Event Sourcing decision.")

    def test_poem_not_answerable(self):
        assert not self.qe.can_answer("Write me a poem.")

    def test_weather_not_answerable(self):
        assert not self.qe.can_answer("What's the weather?")


# ===========================================================================
# 11. DECISION QUERY ENGINE — answers
# ===========================================================================

class TestDecisionQueryAnswers:

    def setup_method(self):
        e = make_engine()
        e.record(make_decision(
            title="Event Sourcing",
            decision="Use immutable Timeline.",
            reason="Supports replay and simplifies Worker coordination.",
            status=DecisionStatus.ACCEPTED,
            tags=("architecture",)
        ))
        e.record(make_decision(
            title="Reject Mutable State",
            decision="Never mutate records.",
            reason="Prevents race conditions.",
            status=DecisionStatus.REJECTED,
        ))
        e.record(make_decision(
            title="Old Architecture",
            status=DecisionStatus.SUPERSEDED,
        ))
        self.qe = DecisionQueryEngine(e)
        self.e = e

    def test_what_decisions_answered(self):
        r = self.qe.answer("What architectural decisions have we made?")
        assert r.answered
        assert "Event Sourcing" in r.answer

    def test_which_active_answered(self):
        r = self.qe.answer("Which decisions are still active?")
        assert r.answered
        assert "Event Sourcing" in r.answer

    def test_which_superseded_answered(self):
        r = self.qe.answer("Which decisions have been superseded?")
        assert r.answered
        assert "Old Architecture" in r.answer

    def test_why_rejected_answered(self):
        r = self.qe.answer("Why did we reject that idea?")
        assert r.answered
        assert "Mutable State" in r.answer or "race conditions" in r.answer.lower()

    def test_how_many_answered(self):
        r = self.qe.answer("How many decisions have we made?")
        assert r.answered
        assert "3" in r.answer

    def test_why_did_we_adopt_answered(self):
        r = self.qe.answer("Why did we adopt Event Sourcing?")
        assert r.answered
        assert "Event Sourcing" in r.answer
        assert "replay" in r.answer.lower() or "Worker" in r.answer

    def test_show_decisions_answered(self):
        r = self.qe.answer("show decisions")
        assert r.answered
        assert "Event Sourcing" in r.answer

    def test_today_answered(self):
        r = self.qe.answer("What did we decide today?")
        assert r.answered  # decisions were just created

    def test_empty_engine_graceful(self):
        qe = DecisionQueryEngine(make_engine())
        r = qe.answer("What architectural decisions have we made?")
        assert r.answered  # graceful empty response
        assert "No" in r.answer or "no" in r.answer

    def test_result_has_events(self):
        r = self.qe.answer("What architectural decisions have we made?")
        assert r.answered
        assert len(r.decisions) >= 1

    def test_miss_on_unanswerable(self):
        qe, _ = make_query_engine()
        r = qe.answer("Write me a poem.")
        assert not r.answered


# ===========================================================================
# 12. DECISION QUERY RESULT
# ===========================================================================

class TestDecisionQueryResult:

    def test_miss_factory(self):
        r = DecisionQueryResult.miss("test")
        assert not r.answered
        assert r.answer == ""

    def test_empty_factory(self):
        r = DecisionQueryResult.empty("test", "Nothing found.")
        assert r.answered
        assert r.answer == "Nothing found."

    def test_is_frozen(self):
        r = DecisionQueryResult.miss("test")
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            r.answered = True


# ===========================================================================
# 13. DECISION INSPECTOR
# ===========================================================================

class TestDecisionInspector:

    def test_returns_string(self):
        inspector = DecisionInspector(make_engine())
        assert isinstance(inspector.inspect(), str)

    def test_empty_engine_shows_zero(self):
        inspector = DecisionInspector(make_engine())
        output = inspector.inspect()
        assert "0 decision" in output

    def test_shows_decision_count(self):
        e = make_engine()
        e.record(make_decision(title="A"))
        e.record(make_decision(title="B"))
        inspector = DecisionInspector(e)
        output = inspector.inspect()
        assert "2 decision" in output

    def test_shows_active_count(self):
        e = make_engine()
        e.record(make_decision(status=DecisionStatus.ACCEPTED))
        inspector = DecisionInspector(e)
        output = inspector.inspect()
        assert "Active" in output

    def test_shows_latest_titles(self):
        e = make_engine()
        e.record(make_decision(title="Event Sourcing"))
        inspector = DecisionInspector(e)
        output = inspector.inspect()
        assert "Event Sourcing" in output

    def test_is_empty_when_no_decisions(self):
        inspector = DecisionInspector(make_engine())
        assert inspector.is_empty()

    def test_is_not_empty_when_has_decisions(self):
        e = make_engine()
        e.record(make_decision())
        inspector = DecisionInspector(e)
        assert not inspector.is_empty()

    def test_explain_latest(self):
        e = make_engine()
        e.record(make_decision(title="Event Sourcing", reason="Supports replay."))
        inspector = DecisionInspector(e)
        explanation = inspector.explain_latest()
        assert "Event Sourcing" in explanation

    def test_explain_latest_empty(self):
        inspector = DecisionInspector(make_engine())
        result = inspector.explain_latest()
        assert "No decisions" in result


# ===========================================================================
# 14. EVENT TYPE — new DECISION_* types
# ===========================================================================

class TestEventTypeDecision:

    def test_decision_proposed_exists(self):
        assert hasattr(EventType, "DECISION_PROPOSED")

    def test_decision_accepted_exists(self):
        assert hasattr(EventType, "DECISION_ACCEPTED")

    def test_decision_superseded_exists(self):
        assert hasattr(EventType, "DECISION_SUPERSEDED")

    def test_decision_rejected_exists(self):
        assert hasattr(EventType, "DECISION_REJECTED")

    def test_total_event_types(self):
        """Count grows as sprints add new event types — check minimum not exact."""
        assert len(list(EventType)) >= 14

    def test_decision_labels(self):
        assert EventType.DECISION_PROPOSED.label() == "Decision Proposed"
        assert EventType.DECISION_ACCEPTED.label() == "Decision Accepted"
        assert EventType.DECISION_SUPERSEDED.label() == "Decision Superseded"
        assert EventType.DECISION_REJECTED.label() == "Decision Rejected"


# ===========================================================================
# 15. SUCCESS CRITERIA — the spec's key capability
# ===========================================================================

class TestSuccessCriteria:

    def test_why_did_we_adopt_event_sourcing(self):
        """
        Core Sprint-004 capability:
        'Why did we adopt Event Sourcing?' →
        Full rationale including decision, reason, and alternatives.
        """
        e = make_engine()
        e.record(ArchitecturalDecision(
            title="Event Sourcing",
            decision=(
                "Use an immutable Timeline with projections to eliminate "
                "direct state mutation, support replay, and simplify "
                "future Worker coordination."
            ),
            reason=(
                "During Genesis-020 Sprint-003 we needed a way for Workers "
                "to reconstruct conversation history without parameter passing. "
                "Event sourcing provides a single source of truth."
            ),
            status=DecisionStatus.ACCEPTED,
            source_turn=31,
            alternatives=("Direct state mutation", "External database", "Shared mutable dict"),
            confidence=0.98,
            tags=("architecture", "genesis-020", "sprint-003"),
        ))

        qe = DecisionQueryEngine(e)
        result = qe.answer("Why did we adopt Event Sourcing?")

        assert result.answered
        assert "Event Sourcing" in result.answer
        assert len(result.answer) > 100  # substantive explanation
        assert len(result.decisions) == 1

    def test_replay_reconstructs_full_history(self):
        """Timeline replay fully reconstructs decision state."""
        tl = ConversationTimeline()
        tl.record(TimelineEvent(
            event_type=EventType.DECISION_ACCEPTED,
            value="Event Sourcing",
            turn=31,
            payload={
                "decision_id": "es-001",
                "reason": "Supports Worker coordination.",
                "decision": "Use immutable Timeline.",
            }
        ))
        tl.record(TimelineEvent(
            event_type=EventType.DECISION_REJECTED,
            value="Mutable State",
            turn=32,
            payload={"decision_id": "ms-001", "reason": "Race conditions."}
        ))

        e = make_engine()
        tl.replay(e)

        assert e.count() == 2
        assert len(e.active()) == 1
        assert len(e.rejected()) == 1


# ===========================================================================
# 16. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_existing_timeline_event_types_unchanged(self):
        for name in ["START_PROJECT", "START_SPRINT", "FINISH_SPRINT",
                     "FREEZE", "DECISION", "TASK", "PERSON",
                     "ACHIEVEMENT", "QUESTION", "GENERAL"]:
            assert hasattr(EventType, name)

    def test_existing_conversation_context_unchanged(self):
        from core.conversation.context import ConversationContext
        ctx = ConversationContext()
        ctx.pending_question = "test?"
        assert ctx.has_pending_interaction()

    def test_session_context_unchanged(self):
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_project("Jarvis OS")
        assert s.active_project.value == "Jarvis OS"

    def test_timeline_unchanged(self):
        tl = ConversationTimeline()
        from core.conversation.timeline_event import TimelineEvent, EventType
        tl.record(TimelineEvent(EventType.START_PROJECT, "Jarvis", turn=1))
        assert tl.count() == 1

    def test_decision_engine_independent_of_knowledge_engine(self):
        e = make_engine()
        assert not hasattr(e, "_knowledge")

    def test_decision_engine_independent_of_session_context(self):
        from core.conversation.session_context import SessionContext
        e = make_engine()
        s = SessionContext()
        e.record(make_decision())
        assert s.active_project is None  # unaffected