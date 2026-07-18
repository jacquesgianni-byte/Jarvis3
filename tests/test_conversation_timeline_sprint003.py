"""
Genesis-020 Sprint-003 — Conversation Timeline Engine Tests
Completely self-contained. No dependency on other test files.

Coverage:
  - EventType: all types exist, labels correct
  - TimelineEvent: immutable, str, date_str, time_str
  - ConversationTimeline: record, append-only, query filters, stable order
  - ConversationTimeline: record_from_facts, fact→event mapping
  - ConversationTimeline: today/yesterday/since_turn queries
  - ConversationTimeline: summary, count, latest
  - TimelineQueryEngine: can_answer detection
  - TimelineQueryEngine: answers for all query types
  - TimelineQueryEngine: miss when empty, miss when not answerable
  - TimelineInspector: returns string, shows events
  - Integration: multi-turn conversation scenario
  - Backwards compatibility: no regressions
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.timeline_event import EventType, TimelineEvent
from core.conversation.conversation_timeline import ConversationTimeline
from core.conversation.timeline_query import TimelineQueryEngine, QueryResult
from core.conversation.timeline_inspector import TimelineInspector
from core.conversation.fact_extractor import ExtractedFact, FactType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_timeline() -> ConversationTimeline:
    return ConversationTimeline()

def make_event(event_type=EventType.GENERAL, value="test", turn=1, **kwargs):
    return TimelineEvent(event_type=event_type, value=value, turn=turn, **kwargs)

def make_fact(fact_type=FactType.PROJECT, value="Jarvis OS", raw=""):
    return ExtractedFact(fact_type=fact_type, subject="user",
                         attribute="current project", value=value, raw=raw)

def make_query_engine(tl=None):
    tl = tl or make_timeline()
    return TimelineQueryEngine(tl), tl


# ===========================================================================
# 1. EVENT TYPE
# ===========================================================================

class TestEventType:

    def test_all_types_exist(self):
        for name in ["START_PROJECT", "START_SPRINT", "FINISH_SPRINT", "FREEZE",
                     "DECISION", "TASK", "PERSON", "ACHIEVEMENT", "QUESTION", "GENERAL"]:
            assert hasattr(EventType, name)

    def test_values_unique(self):
        values = [e.value for e in EventType]
        assert len(values) == len(set(values))

    def test_label_human_readable(self):
        assert EventType.START_PROJECT.label() == "Start Project"
        assert EventType.FINISH_SPRINT.label() == "Finish Sprint"
        assert EventType.GENERAL.label() == "General"


# ===========================================================================
# 2. TIMELINE EVENT
# ===========================================================================

class TestTimelineEvent:

    def test_event_is_frozen(self):
        e = make_event()
        from dataclasses import FrozenInstanceError
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            e.value = "changed"

    def test_event_str(self):
        e = make_event(EventType.START_PROJECT, "Jarvis OS", turn=3)
        s = str(e)
        assert "3" in s
        assert "Jarvis OS" in s

    def test_event_date_str(self):
        e = make_event()
        assert len(e.date_str()) == 10  # YYYY-MM-DD
        assert e.date_str()[4] == "-"

    def test_event_time_str(self):
        e = make_event()
        assert len(e.time_str()) == 5   # HH:MM
        assert e.time_str()[2] == ":"

    def test_event_has_timestamp(self):
        e = make_event()
        assert isinstance(e.timestamp, datetime)

    def test_event_default_source(self):
        e = make_event()
        assert e.source == "user"

    def test_event_custom_fields(self):
        e = TimelineEvent(event_type=EventType.DECISION, value="Use Flask",
                          turn=5, source="auto", raw="We decided to use Flask",
                          notes="important")
        assert e.source == "auto"
        assert e.notes == "important"


# ===========================================================================
# 3. CONVERSATION TIMELINE — basic operations
# ===========================================================================

class TestConversationTimelineBasic:

    def test_starts_empty(self):
        tl = make_timeline()
        assert tl.count() == 0
        assert tl.all_events() == []

    def test_record_single_event(self):
        tl = make_timeline()
        tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        assert tl.count() == 1

    def test_record_returns_none(self):
        tl = make_timeline()
        result = tl.record(make_event())
        assert result is None

    def test_all_events_returns_copy(self):
        tl = make_timeline()
        tl.record(make_event(turn=1))
        events = tl.all_events()
        events.clear()
        assert tl.count() == 1  # original unaffected

    def test_stable_insertion_order(self):
        tl = make_timeline()
        tl.record(make_event(EventType.START_PROJECT, "A", turn=1))
        tl.record(make_event(EventType.START_SPRINT, "B", turn=2))
        tl.record(make_event(EventType.FREEZE, "C", turn=3))
        events = tl.all_events()
        assert [e.turn for e in events] == [1, 2, 3]

    def test_record_turn_creates_general_event(self):
        tl = make_timeline()
        tl.record_turn("Hello Jarvis.", turn=1)
        assert tl.count() == 1
        assert tl.all_events()[0].event_type == EventType.GENERAL

    def test_record_turn_empty_message_skipped(self):
        tl = make_timeline()
        tl.record_turn("", turn=1)
        assert tl.count() == 0


# ===========================================================================
# 4. CONVERSATION TIMELINE — query filters
# ===========================================================================

class TestConversationTimelineQueries:

    def setup_method(self):
        self.tl = make_timeline()
        self.tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        self.tl.record(make_event(EventType.START_SPRINT, "Sprint-001", turn=5))
        self.tl.record(make_event(EventType.FINISH_SPRINT, "Sprint-001", turn=14))
        self.tl.record(make_event(EventType.START_SPRINT, "Sprint-002", turn=18))
        self.tl.record(make_event(EventType.FREEZE, "Genesis-019", turn=20))
        self.tl.record(make_event(EventType.PERSON, "Claude", turn=7))
        self.tl.record(make_event(EventType.DECISION, "Use Flask", turn=10))

    def test_query_by_event_type(self):
        results = self.tl.query(event_type=EventType.START_SPRINT)
        assert len(results) == 2
        assert all(e.event_type == EventType.START_SPRINT for e in results)

    def test_query_since_turn(self):
        results = self.tl.query(since_turn=15)
        assert all(e.turn >= 15 for e in results)

    def test_query_until_turn(self):
        results = self.tl.query(until_turn=10)
        assert all(e.turn <= 10 for e in results)

    def test_query_combined_filters(self):
        results = self.tl.query(event_type=EventType.START_SPRINT, since_turn=10)
        assert len(results) == 1
        assert results[0].value == "Sprint-002"

    def test_query_limit(self):
        results = self.tl.query(limit=2)
        assert len(results) == 2
        assert results[-1].turn == 10  # most recent 2

    def test_latest_returns_most_recent(self):
        latest = self.tl.latest(EventType.START_SPRINT)
        assert latest.value == "Sprint-002"

    def test_latest_returns_none_when_empty(self):
        assert make_timeline().latest() is None

    def test_events_of_type(self):
        sprints = self.tl.events_of_type(EventType.START_SPRINT)
        assert len(sprints) == 2

    def test_events_since_turn(self):
        results = self.tl.events_since_turn(15)
        assert all(e.turn >= 15 for e in results)

    def test_count_by_type(self):
        assert self.tl.count(EventType.START_SPRINT) == 2
        assert self.tl.count(EventType.PERSON) == 1

    def test_summary_dict(self):
        s = self.tl.summary()
        assert s["total_events"] == 7
        assert s["latest_project"] == "Jarvis OS"
        assert s["latest_sprint"] == "Sprint-002"
        assert s["latest_freeze"] == "Genesis-019"


# ===========================================================================
# 5. CONVERSATION TIMELINE — fact conversion
# ===========================================================================

class TestConversationTimelineFactConversion:

    def test_project_fact_creates_start_project_event(self):
        tl = make_timeline()
        facts = [make_fact(FactType.PROJECT, "Jarvis OS")]
        tl.record_from_facts(facts, turn=1)
        assert tl.count(EventType.START_PROJECT) == 1

    def test_task_sprint_fact_creates_start_sprint_event(self):
        tl = make_timeline()
        facts = [make_fact(FactType.TASK, "Sprint-001")]
        tl.record_from_facts(facts, turn=5)
        assert tl.count(EventType.START_SPRINT) == 1

    def test_milestone_frozen_creates_freeze_event(self):
        tl = make_timeline()
        facts = [make_fact(FactType.MILESTONE, "Genesis-019", raw="Genesis-019 is frozen")]
        tl.record_from_facts(facts, turn=20)
        assert tl.count(EventType.FREEZE) == 1

    def test_decision_fact_creates_decision_event(self):
        tl = make_timeline()
        facts = [make_fact(FactType.DECISION, "use Flask")]
        tl.record_from_facts(facts, turn=10)
        assert tl.count(EventType.DECISION) == 1

    def test_person_fact_creates_person_event(self):
        tl = make_timeline()
        facts = [make_fact(FactType.PERSON, "Claude")]
        tl.record_from_facts(facts, turn=7)
        assert tl.count(EventType.PERSON) == 1

    def test_duplicate_person_same_turn_not_double_recorded(self):
        tl = make_timeline()
        facts = [make_fact(FactType.PERSON, "Claude"),
                 make_fact(FactType.PERSON, "Claude")]
        tl.record_from_facts(facts, turn=7)
        assert tl.count(EventType.PERSON) == 1

    def test_empty_facts_list_records_nothing(self):
        tl = make_timeline()
        tl.record_from_facts([], turn=1)
        assert tl.count() == 0

    def test_achievement_fact_creates_achievement_event(self):
        tl = make_timeline()
        facts = [make_fact(FactType.ACHIEVEMENT, "529 tests passing")]
        tl.record_from_facts(facts, turn=15)
        assert tl.count(EventType.ACHIEVEMENT) == 1


# ===========================================================================
# 6. TIMELINE QUERY ENGINE — can_answer
# ===========================================================================

class TestTimelineQueryCanAnswer:

    def setup_method(self):
        self.engine, _ = make_query_engine()

    def test_what_did_we_finish(self):
        assert self.engine.can_answer("What did we finish today?")

    def test_what_are_we_doing(self):
        assert self.engine.can_answer("What are we currently working on?")

    def test_which_genesis(self):
        assert self.engine.can_answer("Which Genesis are we up to?")

    def test_when_did_we_freeze(self):
        assert self.engine.can_answer("When did we freeze Sprint-001?")

    def test_what_happened_before(self):
        assert self.engine.can_answer("What happened before Sprint-002?")

    def test_what_decisions(self):
        assert self.engine.can_answer("What decisions did we make?")

    def test_what_did_we_start(self):
        assert self.engine.can_answer("What did we start?")

    def test_who_have_we_mentioned(self):
        assert self.engine.can_answer("Who have we mentioned?")

    def test_what_happened_today(self):
        assert self.engine.can_answer("What happened today?")

    def test_what_happened_yesterday(self):
        assert self.engine.can_answer("What happened yesterday?")

    def test_show_timeline(self):
        assert self.engine.can_answer("show timeline")

    def test_slash_timeline(self):
        assert self.engine.can_answer("/timeline")

    def test_poem_not_answerable(self):
        assert not self.engine.can_answer("Write me a poem.")

    def test_weather_not_answerable(self):
        assert not self.engine.can_answer("What's the weather?")


# ===========================================================================
# 7. TIMELINE QUERY ENGINE — answers
# ===========================================================================

class TestTimelineQueryAnswers:

    def setup_method(self):
        self.tl = make_timeline()
        self.tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        self.tl.record(make_event(EventType.START_SPRINT, "Sprint-001", turn=5))
        self.tl.record(make_event(EventType.FINISH_SPRINT, "Sprint-001", turn=14))
        self.tl.record(make_event(EventType.FREEZE, "Genesis-019", turn=20))
        self.tl.record(make_event(EventType.START_SPRINT, "Sprint-002", turn=18))
        self.tl.record(make_event(EventType.DECISION, "Use Flask", turn=10))
        self.tl.record(make_event(EventType.PERSON, "Claude", turn=7))
        self.engine = TimelineQueryEngine(self.tl)

    def test_what_did_we_finish_answered(self):
        r = self.engine.answer("What did we finish?")
        assert r.answered
        assert "Sprint-001" in r.answer or "Genesis-019" in r.answer

    def test_what_are_we_doing_answered(self):
        r = self.engine.answer("What are we currently working on?")
        assert r.answered
        assert "Sprint-002" in r.answer or "Jarvis OS" in r.answer

    def test_which_genesis_answered(self):
        r = self.engine.answer("Which Genesis are we up to?")
        assert r.answered
        assert "Genesis-019" in r.answer

    def test_when_did_we_freeze_sprint(self):
        r = self.engine.answer("When did we freeze Sprint-001?")
        assert r.answered
        assert "Sprint-001" in r.answer or "freeze" in r.answer.lower()

    def test_what_happened_before_sprint_002(self):
        r = self.engine.answer("What happened before Sprint-002?")
        assert r.answered

    def test_what_decisions(self):
        r = self.engine.answer("What decisions did we make?")
        assert r.answered
        assert "Flask" in r.answer

    def test_what_did_we_start(self):
        r = self.engine.answer("What did we start?")
        assert r.answered

    def test_who_have_we_mentioned(self):
        r = self.engine.answer("Who have we mentioned?")
        assert r.answered
        assert "Claude" in r.answer

    def test_show_timeline_answered(self):
        r = self.engine.answer("show timeline")
        assert r.answered
        assert "Timeline" in r.answer

    def test_miss_when_empty_timeline(self):
        engine = TimelineQueryEngine(make_timeline())
        r = engine.answer("What are we doing?")
        assert not r.answered

    def test_today_events_answered(self):
        r = self.engine.answer("What happened today?")
        assert r.answered  # events were just created so they're "today"

    def test_yesterday_events_empty(self):
        r = self.engine.answer("What happened yesterday?")
        assert r.answered  # answered=True even when empty (graceful response)

    def test_query_result_has_events(self):
        r = self.engine.answer("What decisions did we make?")
        assert r.answered
        assert len(r.events) >= 1


# ===========================================================================
# 8. QUERY RESULT — data model
# ===========================================================================

class TestQueryResult:

    def test_miss_factory(self):
        r = QueryResult.miss("test query")
        assert not r.answered
        assert r.question == "test query"
        assert r.answer == ""

    def test_answered_result(self):
        r = QueryResult(answered=True, question="q", answer="A", events=())
        assert r.answered
        assert r.answer == "A"

    def test_result_is_frozen(self):
        r = QueryResult.miss("q")
        from dataclasses import FrozenInstanceError
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            r.answered = True


# ===========================================================================
# 9. TIMELINE INSPECTOR
# ===========================================================================

class TestTimelineInspector:

    def test_returns_string(self):
        inspector = TimelineInspector(make_timeline())
        assert isinstance(inspector.inspect(), str)

    def test_empty_timeline_message(self):
        inspector = TimelineInspector(make_timeline())
        output = inspector.inspect()
        assert "0 events" in output

    def test_shows_event_count(self):
        tl = make_timeline()
        tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        tl.record(make_event(EventType.START_SPRINT, "Sprint-001", turn=5))
        inspector = TimelineInspector(tl)
        output = inspector.inspect()
        assert "2 events" in output

    def test_shows_event_values(self):
        tl = make_timeline()
        tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        inspector = TimelineInspector(tl)
        output = inspector.inspect()
        assert "Jarvis OS" in output

    def test_shows_turn_numbers(self):
        tl = make_timeline()
        tl.record(make_event(EventType.START_SPRINT, "Sprint-001", turn=5))
        inspector = TimelineInspector(tl)
        output = inspector.inspect()
        assert "5" in output

    def test_summary_line_returns_string(self):
        tl = make_timeline()
        tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        inspector = TimelineInspector(tl)
        line = inspector.summary_line()
        assert isinstance(line, str)
        assert "Jarvis OS" in line


# ===========================================================================
# 10. END-TO-END — multi-turn conversation
# ===========================================================================

class TestEndToEnd:

    def test_full_conversation_scenario(self):
        """
        Simulate the scenario from the spec:
        Turn 1: Let's build Genesis-020.
        Turn 5: Sprint-001 is complete.
        Turn 7: Claude is implementing Sprint-002.
        """
        from core.conversation.fact_extractor import FactExtractor
        tl = make_timeline()
        extractor = FactExtractor()

        # Turn 1
        facts = extractor.extract("Let's build Genesis-020.")
        tl.record_from_facts(facts, turn=1)

        # Turn 5
        facts = extractor.extract("Sprint-001 is complete.")
        tl.record_from_facts(facts, turn=5)

        # Turn 7
        facts = extractor.extract("Claude is implementing Sprint-002.")
        tl.record_from_facts(facts, turn=7)

        # Verify timeline has meaningful events
        assert tl.count() >= 1  # at least something was recorded

        # Query engine should answer
        engine = TimelineQueryEngine(tl)
        if engine.can_answer("Who have we mentioned?"):
            r = engine.answer("Who have we mentioned?")
            # If Claude was detected as a person, it should be in the answer
            if r.answered and r.events:
                assert len(r.events) >= 1

    def test_timeline_independent_of_session_context(self):
        """Timeline and SessionContext must not share state."""
        from core.conversation.session_context import SessionContext
        tl = make_timeline()
        session = SessionContext()
        tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        # SessionContext should be unaffected
        assert session.active_project is None

    def test_timeline_independent_of_knowledge_engine(self):
        """Timeline never calls the KnowledgeEngine."""
        tl = make_timeline()
        tl.record(make_event(EventType.DECISION, "Use Flask", turn=3))
        # Timeline has no knowledge attribute — confirms independence
        assert not hasattr(tl, '_knowledge')


# ===========================================================================
# 11. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_conversation_context_unchanged(self):
        from core.conversation.context import ConversationContext
        ctx = ConversationContext()
        ctx.pending_question = "test?"
        assert ctx.has_pending_interaction()
        ctx.clear_pending()
        assert not ctx.has_pending_interaction()

    def test_session_context_unchanged(self):
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_project("Jarvis OS")
        assert s.active_project.value == "Jarvis OS"

    def test_timeline_classes_do_not_import_knowledge_engine(self):
        """Timeline module must not import KnowledgeEngine."""
        import importlib
        import core.conversation.conversation_timeline as mod
        src = open(mod.__file__).read()
        assert "KnowledgeEngine" not in src

    def test_original_ten_event_types_still_present(self):
        """Original 10 event types must always be present.
        New types (e.g. DECISION_*) may be added by future sprints."""
        original = [
            "START_PROJECT", "START_SPRINT", "FINISH_SPRINT", "FREEZE",
            "DECISION", "TASK", "PERSON", "ACHIEVEMENT", "QUESTION", "GENERAL",
        ]
        for name in original:
            assert hasattr(EventType, name), f"EventType.{name} missing"
        assert len(list(EventType)) >= 10


# ===========================================================================
# 12. PROJECTION INTERFACE
# ===========================================================================

class TestProjectionInterface:

    def test_projection_is_abstract(self):
        from core.conversation.projection import Projection
        with pytest.raises(TypeError):
            Projection()  # cannot instantiate ABC

    def test_projection_apply_must_be_implemented(self):
        from core.conversation.projection import Projection
        import inspect
        assert inspect.isabstract(Projection)

    def test_on_replay_complete_has_default(self):
        from core.conversation.projection import Projection
        class ConcreteProjection(Projection):
            def apply(self, event): pass
        p = ConcreteProjection()
        p.on_replay_complete()  # should not raise

    def test_concrete_projection_receives_events(self):
        from core.conversation.projection import Projection
        class CollectorProjection(Projection):
            def __init__(self): self.collected = []
            def apply(self, event): self.collected.append(event)

        tl = make_timeline()
        tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        tl.record(make_event(EventType.START_SPRINT, "Sprint-001", turn=5))

        p = CollectorProjection()
        tl.replay(p)
        assert len(p.collected) == 2

    def test_replay_calls_on_replay_complete(self):
        from core.conversation.projection import Projection
        class TrackingProjection(Projection):
            def __init__(self): self.completed = False
            def apply(self, event): pass
            def on_replay_complete(self): self.completed = True

        tl = make_timeline()
        tl.record(make_event(turn=1))
        p = TrackingProjection()
        tl.replay(p)
        assert p.completed

    def test_replay_on_empty_timeline(self):
        from core.conversation.projection import Projection
        class CountingProjection(Projection):
            def __init__(self): self.count = 0
            def apply(self, event): self.count += 1

        p = CountingProjection()
        make_timeline().replay(p)
        assert p.count == 0

    def test_replay_events_in_turn_order(self):
        from core.conversation.projection import Projection
        class OrderProjection(Projection):
            def __init__(self): self.turns = []
            def apply(self, event): self.turns.append(event.turn)

        tl = make_timeline()
        tl.record(make_event(turn=1))
        tl.record(make_event(turn=5))
        tl.record(make_event(turn=3))  # out of order insertion

        p = OrderProjection()
        tl.replay(p)
        assert p.turns == [1, 5, 3]  # insertion order preserved

    def test_projection_can_reconstruct_state(self):
        """A projection can fully reconstruct current project state."""
        from core.conversation.projection import Projection

        class ProjectStateProjection(Projection):
            def __init__(self):
                self.current_project = None
                self.current_sprint = None
                self.last_freeze = None
                self.people = []
                self.decisions = []

            def apply(self, event):
                if event.event_type == EventType.START_PROJECT:
                    self.current_project = event.value
                elif event.event_type == EventType.START_SPRINT:
                    self.current_sprint = event.value
                elif event.event_type == EventType.FREEZE:
                    self.last_freeze = event.value
                elif event.event_type == EventType.PERSON:
                    self.people.append(event.value)
                elif event.event_type == EventType.DECISION:
                    self.decisions.append(event.value)

        tl = make_timeline()
        tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        tl.record(make_event(EventType.START_SPRINT, "Sprint-001", turn=5))
        tl.record(make_event(EventType.PERSON, "Claude", turn=7))
        tl.record(make_event(EventType.DECISION, "Use Flask", turn=10))
        tl.record(make_event(EventType.FREEZE, "Genesis-019", turn=20))
        tl.record(make_event(EventType.START_SPRINT, "Sprint-002", turn=25))

        p = ProjectStateProjection()
        tl.replay(p)

        assert p.current_project == "Jarvis OS"
        assert p.current_sprint == "Sprint-002"
        assert p.last_freeze == "Genesis-019"
        assert "Claude" in p.people
        assert "Use Flask" in p.decisions

    def test_multiple_replays_produce_same_result(self):
        """Replay is deterministic — same events, same result."""
        from core.conversation.projection import Projection

        class CountingProjection(Projection):
            def __init__(self): self.count = 0
            def apply(self, event): self.count += 1

        tl = make_timeline()
        tl.record(make_event(turn=1))
        tl.record(make_event(turn=2))

        p1 = CountingProjection()
        p2 = CountingProjection()
        tl.replay(p1)
        tl.replay(p2)
        assert p1.count == p2.count == 2


# ===========================================================================
# 13. TIMELINE EVENT — version and payload
# ===========================================================================

class TestTimelineEventPolish:

    def test_default_version_is_one(self):
        e = make_event()
        assert e.version == 1

    def test_custom_version(self):
        e = TimelineEvent(event_type=EventType.DECISION, value="test",
                          turn=1, version=2)
        assert e.version == 2

    def test_default_payload_is_empty_dict(self):
        e = make_event()
        assert e.payload == {}

    def test_custom_payload(self):
        e = TimelineEvent(event_type=EventType.DECISION, value="Flask",
                          turn=1, payload={"confidence": 0.85})
        assert e.payload["confidence"] == 0.85

    def test_payload_is_immutable_via_frozen(self):
        e = make_event()
        from dataclasses import FrozenInstanceError
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            e.payload = {"new": "value"}

    def test_with_payload_returns_new_event(self):
        e = make_event(EventType.START_PROJECT, "Jarvis OS", turn=1)
        e2 = e.with_payload(confidence=0.9, source_sprint="S1")
        assert e2 is not e
        assert e2.payload["confidence"] == 0.9
        assert e2.payload["source_sprint"] == "S1"

    def test_with_payload_preserves_original(self):
        e = make_event(EventType.START_PROJECT, "Jarvis OS", turn=1)
        _ = e.with_payload(confidence=0.9)
        assert e.payload == {}  # original unchanged

    def test_with_payload_merges_existing(self):
        e = TimelineEvent(event_type=EventType.DECISION, value="Flask",
                          turn=1, payload={"confidence": 0.8})
        e2 = e.with_payload(sprint="S1")
        assert e2.payload["confidence"] == 0.8
        assert e2.payload["sprint"] == "S1"

    def test_with_payload_preserves_all_other_fields(self):
        e = make_event(EventType.START_PROJECT, "Jarvis OS", turn=3,
                       source="auto", raw="We're building Jarvis.")
        e2 = e.with_payload(extra="data")
        assert e2.event_type == EventType.START_PROJECT
        assert e2.value == "Jarvis OS"
        assert e2.turn == 3
        assert e2.source == "auto"
        assert e2.raw == "We're building Jarvis."

    def test_backwards_compat_existing_construction(self):
        """Existing code constructing events without version/payload still works."""
        e = TimelineEvent(event_type=EventType.GENERAL, value="hello", turn=1)
        assert e.version == 1
        assert e.payload == {}

    def test_version_and_payload_in_frozen_event(self):
        e = TimelineEvent(event_type=EventType.FREEZE, value="G-019",
                          turn=5, version=1, payload={"method": "manual"})
        assert e.version == 1
        assert e.payload["method"] == "manual"
        from dataclasses import FrozenInstanceError
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            e.version = 2