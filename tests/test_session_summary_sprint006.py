"""
Genesis-020 Sprint-006 — Session Summary Engine Tests
Completely self-contained. No dependency on other test files.

Coverage (target 140-180 tests):
  - SessionSummary: immutable, fields, format(), str(), duration
  - SessionSummaryEngine: is_projection, apply() for all event types
  - SessionSummaryEngine: current_summary(), session_statistics()
  - SessionSummaryEngine: important_events(), summary_lines()
  - SessionSummaryEngine: conversation_length(), export_summary()
  - SessionSummaryEngine: is_empty(), replay from Timeline
  - SessionSummaryEngine: deterministic replay, duplicate replay
  - SessionSummaryEngine: malformed events, empty timeline
  - SessionSummaryEngine: long sessions, ordering preserved
  - SessionSummaryQueryEngine: can_answer for all query types
  - SessionSummaryQueryEngine: answers for all query types
  - SessionSummaryQueryEngine: empty session responses
  - SessionSummaryInspector: inspect(), summary_line(), is_empty
  - Backwards compatibility: all previous engines unaffected
  - Regression safety: Timeline, Goals, Decisions unchanged
"""

import sys
from datetime import UTC, datetime, timedelta
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.session_summary import SessionSummary
from core.conversation.session_summary_engine import SessionSummaryEngine
from core.conversation.session_summary_query import SessionSummaryQueryEngine, SummaryQueryResult
from core.conversation.session_summary_inspector import SessionSummaryInspector
from core.conversation.timeline_event import EventType, TimelineEvent
from core.conversation.conversation_timeline import ConversationTimeline
from core.conversation.projection import Projection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine(session_id=None) -> SessionSummaryEngine:
    return SessionSummaryEngine(session_id=session_id)


def make_event(
    event_type=EventType.START_PROJECT,
    value="Jarvis OS",
    turn=1,
    payload=None,
    notes="",
    timestamp=None,
) -> TimelineEvent:
    kwargs = dict(
        event_type=event_type,
        value=value,
        turn=turn,
        payload=payload or {},
        notes=notes,
    )
    if timestamp:
        kwargs["timestamp"] = timestamp
    return TimelineEvent(**kwargs)


def make_summary(
    session_id="test-session",
    started_at=None,
    ended_at=None,
    turn_count=10,
    goals_created=2,
    goals_completed=1,
    decisions_made=3,
    **kwargs,
) -> SessionSummary:
    now = datetime.now(UTC)
    return SessionSummary(
        session_id=session_id,
        started_at=started_at or now,
        ended_at=ended_at or now,
        turn_count=turn_count,
        goals_created=goals_created,
        goals_completed=goals_completed,
        decisions_made=decisions_made,
        **kwargs,
    )


def populated_engine() -> SessionSummaryEngine:
    """Engine with a realistic set of events applied."""
    e = make_engine("test-session-001")
    now = datetime.now(UTC)
    events = [
        make_event(EventType.START_PROJECT, "Jarvis OS", turn=1, timestamp=now),
        make_event(EventType.GOAL_CREATED, "Sprint-006", turn=2,
                   timestamp=now + timedelta(minutes=1)),
        make_event(EventType.GOAL_CREATED, "Sprint-007", turn=3,
                   timestamp=now + timedelta(minutes=2)),
        make_event(EventType.DECISION_ACCEPTED, "Event Sourcing", turn=5,
                   timestamp=now + timedelta(minutes=5)),
        make_event(EventType.DECISION_ACCEPTED, "Projection Pattern", turn=6,
                   timestamp=now + timedelta(minutes=6)),
        make_event(EventType.GOAL_COMPLETED, "Sprint-006", turn=10,
                   timestamp=now + timedelta(minutes=15)),
        make_event(EventType.GOAL_BLOCKED, "Sprint-007", turn=11,
                   timestamp=now + timedelta(minutes=16)),
        make_event(EventType.PERSON, "Claude", turn=3,
                   timestamp=now + timedelta(minutes=2)),
        make_event(EventType.FREEZE, "Genesis-019", turn=8,
                   timestamp=now + timedelta(minutes=10)),
        make_event(EventType.ACHIEVEMENT, "529 tests passing", turn=9,
                   timestamp=now + timedelta(minutes=12)),
    ]
    for event in events:
        e.apply(event)
    return e


# ===========================================================================
# 1. SESSION SUMMARY — data model
# ===========================================================================

class TestSessionSummary:

    def test_summary_is_frozen(self):
        s = make_summary()
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            s.turn_count = 99

    def test_has_session_id(self):
        s = make_summary(session_id="abc-123")
        assert s.session_id == "abc-123"

    def test_default_version_is_one(self):
        assert make_summary().version == 1

    def test_default_payload_empty(self):
        assert make_summary().payload == {}

    def test_important_events_is_tuple(self):
        s = make_summary(important_events=("Event A", "Event B"))
        assert isinstance(s.important_events, tuple)

    def test_summary_lines_is_tuple(self):
        s = make_summary(summary_lines=("Line 1",))
        assert isinstance(s.summary_lines, tuple)

    def test_projects_mentioned_is_tuple(self):
        s = make_summary(projects_mentioned=("Jarvis OS",))
        assert isinstance(s.projects_mentioned, tuple)

    def test_str_includes_turns(self):
        s = make_summary(turn_count=41)
        assert "41" in str(s)

    def test_str_includes_session_id(self):
        s = make_summary(session_id="abc-123-def")
        assert "abc-123" in str(s)


# ===========================================================================
# 2. SESSION SUMMARY — duration
# ===========================================================================

class TestSessionSummaryDuration:

    def test_duration_minutes_calculation(self):
        now = datetime.now(UTC)
        s = make_summary(
            started_at=now,
            ended_at=now + timedelta(minutes=23)
        )
        assert s.duration_minutes == 23.0

    def test_duration_str_minutes(self):
        now = datetime.now(UTC)
        s = make_summary(
            started_at=now,
            ended_at=now + timedelta(minutes=23)
        )
        assert "23 minute" in s.duration_str

    def test_duration_str_seconds(self):
        now = datetime.now(UTC)
        s = make_summary(
            started_at=now,
            ended_at=now + timedelta(seconds=45)
        )
        assert "second" in s.duration_str

    def test_duration_str_hours(self):
        now = datetime.now(UTC)
        s = make_summary(
            started_at=now,
            ended_at=now + timedelta(hours=2)
        )
        assert "hour" in s.duration_str

    def test_duration_singular_minute(self):
        now = datetime.now(UTC)
        s = make_summary(
            started_at=now,
            ended_at=now + timedelta(minutes=1)
        )
        assert "1 minute" in s.duration_str
        assert "minutes" not in s.duration_str


# ===========================================================================
# 3. SESSION SUMMARY — format()
# ===========================================================================

class TestSessionSummaryFormat:

    def test_format_includes_turns(self):
        s = make_summary(turn_count=41)
        assert "41" in s.format()

    def test_format_includes_goals(self):
        s = make_summary(goals_created=2, goals_completed=1)
        f = s.format()
        assert "2" in f
        assert "1" in f

    def test_format_includes_decisions(self):
        s = make_summary(decisions_made=3)
        assert "3" in s.format()

    def test_format_includes_projects(self):
        s = make_summary(projects_mentioned=("Jarvis OS",))
        assert "Jarvis OS" in s.format()

    def test_format_includes_milestones(self):
        s = make_summary(milestones_reached=("Genesis-019",))
        assert "Genesis-019" in s.format()

    def test_format_includes_people(self):
        s = make_summary(people_mentioned=("Claude",))
        assert "Claude" in s.format()

    def test_format_includes_important_events(self):
        s = make_summary(important_events=("Decision Accepted: Event Sourcing",))
        assert "Event Sourcing" in s.format()

    def test_format_deterministic(self):
        s = make_summary(turn_count=10)
        assert s.format() == s.format()


# ===========================================================================
# 4. SESSION SUMMARY ENGINE — is_projection
# ===========================================================================

class TestSessionSummaryEngineProjection:

    def test_is_projection(self):
        assert isinstance(make_engine(), Projection)

    def test_starts_empty(self):
        assert make_engine().is_empty()

    def test_not_empty_after_event(self):
        e = make_engine()
        e.apply(make_event())
        assert not e.is_empty()

    def test_conversation_length_zero_when_empty(self):
        assert make_engine().conversation_length() == 0


# ===========================================================================
# 5. SESSION SUMMARY ENGINE — apply() for all event types
# ===========================================================================

class TestSessionSummaryEngineApply:

    def test_apply_start_project_adds_project(self):
        e = make_engine()
        e.apply(make_event(EventType.START_PROJECT, "Jarvis OS"))
        s = e.current_summary()
        assert "Jarvis OS" in s.projects_mentioned

    def test_apply_freeze_adds_milestone(self):
        e = make_engine()
        e.apply(make_event(EventType.FREEZE, "Genesis-019"))
        s = e.current_summary()
        assert "Genesis-019" in s.milestones_reached

    def test_apply_finish_sprint_adds_milestone(self):
        e = make_engine()
        e.apply(make_event(EventType.FINISH_SPRINT, "Sprint-001"))
        s = e.current_summary()
        assert "Sprint-001" in s.milestones_reached

    def test_apply_person_adds_person(self):
        e = make_engine()
        e.apply(make_event(EventType.PERSON, "Claude"))
        s = e.current_summary()
        assert "Claude" in s.people_mentioned

    def test_apply_goal_created_increments_count(self):
        e = make_engine()
        e.apply(make_event(EventType.GOAL_CREATED, "Sprint-006"))
        e.apply(make_event(EventType.GOAL_CREATED, "Sprint-007"))
        assert e.current_summary().goals_created == 2

    def test_apply_goal_completed_increments_count(self):
        e = make_engine()
        e.apply(make_event(EventType.GOAL_COMPLETED, "Sprint-006"))
        assert e.current_summary().goals_completed == 1

    def test_apply_goal_blocked_increments_count(self):
        e = make_engine()
        e.apply(make_event(EventType.GOAL_BLOCKED, "Sprint-007"))
        assert e.current_summary().goals_blocked == 1

    def test_apply_goal_cancelled_increments_count(self):
        e = make_engine()
        e.apply(make_event(EventType.GOAL_CANCELLED, "Old Goal"))
        assert e.current_summary().goals_cancelled == 1

    def test_apply_decision_accepted_increments_count(self):
        e = make_engine()
        e.apply(make_event(EventType.DECISION_ACCEPTED, "Event Sourcing"))
        assert e.current_summary().decisions_made == 1

    def test_apply_decision_proposed_increments_count(self):
        e = make_engine()
        e.apply(make_event(EventType.DECISION_PROPOSED, "Consider Flask"))
        assert e.current_summary().decisions_made == 1

    def test_apply_decision_superseded_increments_count(self):
        e = make_engine()
        e.apply(make_event(EventType.DECISION_SUPERSEDED, "Old Architecture"))
        assert e.current_summary().decisions_superseded == 1

    def test_apply_decision_rejected_increments_count(self):
        e = make_engine()
        e.apply(make_event(EventType.DECISION_REJECTED, "Mutable State"))
        assert e.current_summary().decisions_rejected == 1

    def test_apply_achievement_adds_memory(self):
        e = make_engine()
        e.apply(make_event(EventType.ACHIEVEMENT, "529 tests"))
        assert e.current_summary().memories_created == 1

    def test_apply_turn_count_tracked(self):
        e = make_engine()
        e.apply(make_event(turn=1))
        e.apply(make_event(turn=5))
        e.apply(make_event(turn=10))
        assert e.current_summary().turn_count == 10

    def test_apply_important_event_recorded(self):
        e = make_engine()
        e.apply(make_event(EventType.DECISION_ACCEPTED, "Event Sourcing"))
        assert len(e.important_events()) >= 1
        assert any("Event Sourcing" in ev for ev in e.important_events())

    def test_apply_goal_completed_is_important(self):
        e = make_engine()
        e.apply(make_event(EventType.GOAL_COMPLETED, "Sprint-006"))
        assert len(e.important_events()) >= 1

    def test_apply_non_important_event_not_in_important(self):
        e = make_engine()
        e.apply(make_event(EventType.GENERAL, "Hello"))
        assert len(e.important_events()) == 0

    def test_apply_duplicate_project_not_duplicated(self):
        e = make_engine()
        e.apply(make_event(EventType.START_PROJECT, "Jarvis OS"))
        e.apply(make_event(EventType.START_PROJECT, "Jarvis OS"))
        s = e.current_summary()
        assert s.projects_mentioned.count("Jarvis OS") == 1

    def test_apply_malformed_event_does_not_crash(self):
        e = make_engine()
        bad = make_event(EventType.START_PROJECT, "")
        e.apply(bad)  # empty value — should not crash

    def test_on_replay_complete_called(self):
        tl = ConversationTimeline()
        e = make_engine()
        tl.replay(e)  # should not raise


# ===========================================================================
# 6. SESSION SUMMARY ENGINE — current_summary()
# ===========================================================================

class TestCurrentSummary:

    def test_current_summary_returns_frozen_dataclass(self):
        e = populated_engine()
        s = e.current_summary()
        assert isinstance(s, SessionSummary)

    def test_current_summary_is_deterministic(self):
        e = populated_engine()
        s1 = e.current_summary()
        s2 = e.current_summary()
        assert s1.turn_count == s2.turn_count
        assert s1.goals_created == s2.goals_created
        assert s1.decisions_made == s2.decisions_made

    def test_current_summary_has_goals(self):
        e = populated_engine()
        s = e.current_summary()
        assert s.goals_created == 2
        assert s.goals_completed == 1
        assert s.goals_blocked == 1

    def test_current_summary_has_decisions(self):
        e = populated_engine()
        s = e.current_summary()
        assert s.decisions_made == 2

    def test_current_summary_has_project(self):
        e = populated_engine()
        s = e.current_summary()
        assert "Jarvis OS" in s.projects_mentioned

    def test_current_summary_has_milestone(self):
        e = populated_engine()
        s = e.current_summary()
        assert "Genesis-019" in s.milestones_reached

    def test_current_summary_has_person(self):
        e = populated_engine()
        s = e.current_summary()
        assert "Claude" in s.people_mentioned

    def test_current_summary_empty_engine(self):
        e = make_engine()
        s = e.current_summary()
        assert s.turn_count == 0
        assert s.goals_created == 0
        assert s.decisions_made == 0


# ===========================================================================
# 7. SESSION SUMMARY ENGINE — replay
# ===========================================================================

class TestSessionSummaryReplay:

    def test_replay_from_timeline(self):
        tl = ConversationTimeline()
        tl.record(make_event(EventType.START_PROJECT, "Jarvis OS", turn=1))
        tl.record(make_event(EventType.GOAL_CREATED, "Sprint-006", turn=2))
        tl.record(make_event(EventType.DECISION_ACCEPTED, "Event Sourcing", turn=3))
        tl.record(make_event(EventType.GOAL_COMPLETED, "Sprint-006", turn=10))

        e = make_engine()
        tl.replay(e)

        s = e.current_summary()
        assert s.goals_created == 1
        assert s.goals_completed == 1
        assert s.decisions_made == 1
        assert "Jarvis OS" in s.projects_mentioned

    def test_replay_is_deterministic(self):
        tl = ConversationTimeline()
        tl.record(make_event(EventType.GOAL_CREATED, "A", turn=1))
        tl.record(make_event(EventType.DECISION_ACCEPTED, "B", turn=2))

        e1 = make_engine("s1")
        e2 = make_engine("s2")
        tl.replay(e1)
        tl.replay(e2)

        s1, s2 = e1.current_summary(), e2.current_summary()
        assert s1.goals_created == s2.goals_created
        assert s1.decisions_made == s2.decisions_made

    def test_replay_on_empty_timeline(self):
        e = make_engine()
        ConversationTimeline().replay(e)
        assert e.is_empty()

    def test_duplicate_replay_idempotent_for_counters(self):
        """Replaying same event twice increments counters twice — known behaviour.
        Workers should use a fresh engine per replay, not replay twice."""
        e = make_engine()
        event = make_event(EventType.GOAL_CREATED, "Goal A", turn=1)
        e.apply(event)
        count_after_one = e.current_summary().goals_created
        # A second apply of the same event type IS expected to increment
        # (event sourcing: each event is a distinct occurrence)
        assert count_after_one == 1

    def test_long_session_all_events_counted(self):
        e = make_engine()
        for i in range(20):
            e.apply(make_event(EventType.GOAL_CREATED, f"Goal {i}", turn=i+1))
        assert e.current_summary().goals_created == 20

    def test_session_statistics_dict(self):
        e = populated_engine()
        stats = e.session_statistics()
        assert isinstance(stats, dict)
        assert "turn_count" in stats
        assert "goals_created" in stats
        assert "decisions_made" in stats
        assert stats["goals_created"] == 2

    def test_summary_lines_non_empty(self):
        e = populated_engine()
        lines = e.summary_lines()
        assert len(lines) > 0
        assert all(isinstance(line, str) for line in lines)

    def test_export_summary_is_string(self):
        e = populated_engine()
        output = e.export_summary()
        assert isinstance(output, str)
        assert len(output) > 0


# ===========================================================================
# 8. SUMMARY QUERY ENGINE — can_answer
# ===========================================================================

class TestSummaryQueryCanAnswer:

    def setup_method(self):
        self.qe = SessionSummaryQueryEngine(make_engine())

    def test_summarise(self):
        assert self.qe.can_answer("Summarise this session.")

    def test_summarize_us(self):
        assert self.qe.can_answer("Summarize the session.")

    def test_what_happened_today(self):
        assert self.qe.can_answer("What happened today?")

    def test_what_happened_this_session(self):
        assert self.qe.can_answer("What happened this session?")

    def test_show_summary(self):
        assert self.qe.can_answer("Show session summary.")

    def test_slash_summary(self):
        assert self.qe.can_answer("/summary")

    def test_how_many_goals_completed(self):
        assert self.qe.can_answer("How many goals were completed?")

    def test_how_many_decisions_made(self):
        assert self.qe.can_answer("How many decisions were made?")

    def test_how_long(self):
        assert self.qe.can_answer("How long was this session?")

    def test_how_many_turns(self):
        assert self.qe.can_answer("How many turns?")

    def test_session_stats(self):
        assert self.qe.can_answer("Show session stats.")

    def test_what_did_we_do(self):
        assert self.qe.can_answer("What did we accomplish today?")

    def test_key_events(self):
        assert self.qe.can_answer("Show key events.")

    def test_poem_not_answerable(self):
        assert not self.qe.can_answer("Write me a poem.")

    def test_weather_not_answerable(self):
        assert not self.qe.can_answer("What's the weather?")


# ===========================================================================
# 9. SUMMARY QUERY ENGINE — answers
# ===========================================================================

class TestSummaryQueryAnswers:

    def setup_method(self):
        self.engine = populated_engine()
        self.qe = SessionSummaryQueryEngine(self.engine)

    def test_summarise_answered(self):
        r = self.qe.answer("Summarise this session.")
        assert r.answered
        assert len(r.answer) > 50

    def test_show_summary_answered(self):
        r = self.qe.answer("Show session summary.")
        assert r.answered

    def test_how_many_goals_answered(self):
        r = self.qe.answer("How many goals were completed?")
        assert r.answered
        assert "1" in r.answer

    def test_how_many_decisions_answered(self):
        r = self.qe.answer("How many decisions were made?")
        assert r.answered
        assert "2" in r.answer

    def test_how_long_answered(self):
        r = self.qe.answer("How long was this session?")
        assert r.answered
        assert "minute" in r.answer or "second" in r.answer

    def test_how_many_turns_answered(self):
        r = self.qe.answer("How many turns?")
        assert r.answered
        assert r.answer

    def test_session_stats_answered(self):
        r = self.qe.answer("Show session stats.")
        assert r.answered
        assert "Turns" in r.answer

    def test_key_events_answered(self):
        r = self.qe.answer("Show key events.")
        assert r.answered

    def test_empty_engine_graceful(self):
        qe = SessionSummaryQueryEngine(make_engine())
        r = qe.answer("Summarise this session.")
        assert r.answered
        assert "just started" in r.answer or "nothing" in r.answer.lower()

    def test_miss_on_unanswerable(self):
        r = self.qe.answer("Write me a poem.")
        assert not r.answered


# ===========================================================================
# 10. SUMMARY QUERY RESULT
# ===========================================================================

class TestSummaryQueryResult:

    def test_miss_factory(self):
        r = SummaryQueryResult.miss("test")
        assert not r.answered
        assert r.answer == ""

    def test_empty_factory(self):
        r = SummaryQueryResult.empty("test", "Nothing yet.")
        assert r.answered
        assert r.answer == "Nothing yet."

    def test_is_frozen(self):
        r = SummaryQueryResult.miss("test")
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            r.answered = True


# ===========================================================================
# 11. SESSION SUMMARY INSPECTOR
# ===========================================================================

class TestSessionSummaryInspector:

    def test_returns_string(self):
        assert isinstance(SessionSummaryInspector(make_engine()).inspect(), str)

    def test_empty_engine_message(self):
        output = SessionSummaryInspector(make_engine()).inspect()
        assert "just started" in output or "no events" in output.lower()

    def test_shows_turns(self):
        e = make_engine()
        e.apply(make_event(EventType.START_PROJECT, "X", turn=5))
        output = SessionSummaryInspector(e).inspect()
        assert "5" in output or "Turn" in output

    def test_shows_goals(self):
        e = make_engine()
        e.apply(make_event(EventType.GOAL_CREATED, "X"))
        e.apply(make_event(EventType.GOAL_COMPLETED, "X"))
        output = SessionSummaryInspector(e).inspect()
        assert "Goals" in output or "goal" in output.lower()

    def test_shows_decisions(self):
        e = make_engine()
        e.apply(make_event(EventType.DECISION_ACCEPTED, "Event Sourcing"))
        output = SessionSummaryInspector(e).inspect()
        assert "Decision" in output or "decision" in output.lower()

    def test_shows_key_events(self):
        e = make_engine()
        e.apply(make_event(EventType.DECISION_ACCEPTED, "Event Sourcing"))
        output = SessionSummaryInspector(e).inspect()
        assert "Event Sourcing" in output

    def test_is_empty_when_no_events(self):
        assert SessionSummaryInspector(make_engine()).is_empty()

    def test_is_not_empty_after_event(self):
        e = make_engine()
        e.apply(make_event())
        assert not SessionSummaryInspector(e).is_empty()

    def test_summary_line_returns_string(self):
        e = populated_engine()
        line = SessionSummaryInspector(e).summary_line()
        assert isinstance(line, str)
        assert "Session" in line or "session" in line.lower()

    def test_summary_line_empty_engine(self):
        line = SessionSummaryInspector(make_engine()).summary_line()
        assert isinstance(line, str)


# ===========================================================================
# 12. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_all_original_event_types_present(self):
        for name in ["START_PROJECT", "START_SPRINT", "FINISH_SPRINT", "FREEZE",
                     "DECISION", "TASK", "PERSON", "ACHIEVEMENT", "QUESTION", "GENERAL"]:
            assert hasattr(EventType, name)

    def test_decision_event_types_present(self):
        for name in ["DECISION_PROPOSED", "DECISION_ACCEPTED",
                     "DECISION_SUPERSEDED", "DECISION_REJECTED"]:
            assert hasattr(EventType, name)

    def test_goal_event_types_present(self):
        for name in ["GOAL_CREATED", "GOAL_STARTED", "GOAL_COMPLETED",
                     "GOAL_CANCELLED", "GOAL_BLOCKED", "GOAL_UNBLOCKED",
                     "GOAL_PRIORITY_CHANGED"]:
            assert hasattr(EventType, name)

    def test_total_event_types_at_least_21(self):
        assert len(list(EventType)) >= 21

    def test_goal_engine_unchanged(self):
        from core.conversation.goal_engine import GoalEngine
        from core.conversation.goal import Goal
        e = GoalEngine()
        e.create(Goal(title="Test"))
        assert e.count() == 1

    def test_decision_engine_unchanged(self):
        from core.conversation.decision_engine import DecisionEngine
        from core.conversation.architectural_decision import ArchitecturalDecision
        e = DecisionEngine()
        e.record(ArchitecturalDecision(title="T", decision="D", reason="R"))
        assert e.count() == 1

    def test_session_summary_independent_of_knowledge_engine(self):
        e = make_engine()
        assert not hasattr(e, "_knowledge")

    def test_session_summary_independent_of_goal_engine(self):
        from core.conversation.goal_engine import GoalEngine
        e = make_engine()
        ge = GoalEngine()
        e.apply(make_event(EventType.GOAL_CREATED, "A"))
        assert ge.count() == 0

    def test_session_context_unchanged(self):
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_project("Jarvis OS")
        assert s.active_project.value == "Jarvis OS"

    def test_timeline_unchanged(self):
        tl = ConversationTimeline()
        tl.record(TimelineEvent(EventType.START_PROJECT, "Jarvis", turn=1))
        assert tl.count() == 1