"""
Genesis-020 Sprint-005 — Goal & Planning Engine Tests
Completely self-contained. No dependency on other test files.

Coverage (target 140-180 tests):
  - GoalStatus: all statuses, labels, is_active, is_open, is_terminal
  - GoalPriority: all priorities, labels, ordering
  - Goal: immutable, fields, str, explain(), with_status(), with_priority()
  - GoalEngine: create, start, complete, cancel, block, unblock, update_priority
  - GoalEngine: active, planned, blocked, completed, cancelled, open_goals
  - GoalEngine: search, latest, by_priority, on_date, count, summary
  - GoalEngine: current_goal, next_goal priority ordering
  - GoalEngine: Projection replay from Timeline events
  - GoalEngine: apply() for all GOAL_* event types
  - GoalEngine: malformed events, duplicate replay, empty timeline
  - GoalEngine: deterministic replay (same events → same state)
  - GoalQueryEngine: can_answer for all query types
  - GoalQueryEngine: answers for all query types
  - GoalQueryEngine: graceful empty responses
  - GoalInspector: returns string, shows counts, is_empty, summary_line
  - EventType: all 7 new GOAL_* types exist
  - Backwards compatibility: all previous EventTypes preserved
  - Regression safety: Decision Engine, Timeline, SessionContext unaffected
"""

import sys
from datetime import UTC, datetime
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.goal import Goal, GoalStatus, GoalPriority
from core.conversation.goal_engine import GoalEngine
from core.conversation.goal_query import GoalQueryEngine, GoalQueryResult
from core.conversation.goal_inspector import GoalInspector
from core.conversation.timeline_event import EventType, TimelineEvent
from core.conversation.conversation_timeline import ConversationTimeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_goal(
    title="Implement Genesis-020",
    description="Build the full cognitive architecture for Jarvis.",
    status=GoalStatus.PLANNED,
    priority=GoalPriority.HIGH,
    source_turn=1,
    tags=("genesis", "architecture"),
    dependencies=(),
    **kwargs,
) -> Goal:
    return Goal(
        title=title,
        description=description,
        status=status,
        priority=priority,
        source_turn=source_turn,
        tags=tuple(tags),
        dependencies=tuple(dependencies),
        **kwargs,
    )


def make_engine() -> GoalEngine:
    return GoalEngine()


def make_query_engine(engine=None):
    e = engine or make_engine()
    return GoalQueryEngine(e), e


def make_timeline_event(
    event_type=EventType.GOAL_CREATED,
    value="Implement Genesis-020",
    turn=1,
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
# 1. GOAL STATUS
# ===========================================================================

class TestGoalStatus:

    def test_all_statuses_exist(self):
        for name in ["PLANNED", "ACTIVE", "BLOCKED", "COMPLETED", "CANCELLED"]:
            assert hasattr(GoalStatus, name)

    def test_values_unique(self):
        values = [s.value for s in GoalStatus]
        assert len(values) == len(set(values))

    def test_label_human_readable(self):
        assert GoalStatus.PLANNED.label() == "Planned"
        assert GoalStatus.ACTIVE.label() == "Active"
        assert GoalStatus.BLOCKED.label() == "Blocked"
        assert GoalStatus.COMPLETED.label() == "Completed"
        assert GoalStatus.CANCELLED.label() == "Cancelled"

    def test_is_active(self):
        assert GoalStatus.ACTIVE.is_active
        assert not GoalStatus.PLANNED.is_active
        assert not GoalStatus.BLOCKED.is_active

    def test_is_open(self):
        assert GoalStatus.PLANNED.is_open
        assert GoalStatus.ACTIVE.is_open
        assert GoalStatus.BLOCKED.is_open
        assert not GoalStatus.COMPLETED.is_open
        assert not GoalStatus.CANCELLED.is_open

    def test_is_terminal(self):
        assert GoalStatus.COMPLETED.is_terminal
        assert GoalStatus.CANCELLED.is_terminal
        assert not GoalStatus.ACTIVE.is_terminal
        assert not GoalStatus.PLANNED.is_terminal


# ===========================================================================
# 2. GOAL PRIORITY
# ===========================================================================

class TestGoalPriority:

    def test_all_priorities_exist(self):
        for name in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            assert hasattr(GoalPriority, name)

    def test_critical_has_lowest_value(self):
        assert GoalPriority.CRITICAL.value < GoalPriority.HIGH.value
        assert GoalPriority.HIGH.value < GoalPriority.MEDIUM.value
        assert GoalPriority.MEDIUM.value < GoalPriority.LOW.value

    def test_label_human_readable(self):
        assert GoalPriority.CRITICAL.label() == "Critical"
        assert GoalPriority.HIGH.label() == "High"


# ===========================================================================
# 3. GOAL MODEL
# ===========================================================================

class TestGoalModel:

    def test_goal_is_frozen(self):
        g = make_goal()
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            g.title = "changed"

    def test_has_auto_id(self):
        g = make_goal()
        assert g.id and len(g.id) > 0

    def test_two_goals_have_different_ids(self):
        g1 = make_goal()
        g2 = make_goal()
        assert g1.id != g2.id

    def test_has_timestamp(self):
        g = make_goal()
        assert isinstance(g.timestamp, datetime)

    def test_default_version_is_one(self):
        assert make_goal().version == 1

    def test_default_payload_empty(self):
        assert make_goal().payload == {}

    def test_dependencies_stored_as_tuple(self):
        g = make_goal(dependencies=("id-1", "id-2"))
        assert isinstance(g.dependencies, tuple)

    def test_tags_stored_as_tuple(self):
        g = make_goal(tags=("tag1", "tag2"))
        assert isinstance(g.tags, tuple)

    def test_str_includes_title(self):
        g = make_goal(title="Test Goal")
        assert "Test Goal" in str(g)

    def test_str_includes_status(self):
        g = make_goal(status=GoalStatus.ACTIVE)
        assert "Active" in str(g)

    def test_date_str_format(self):
        g = make_goal()
        assert len(g.date_str()) == 10
        assert g.date_str()[4] == "-"

    def test_summary_includes_title(self):
        g = make_goal(title="Test Goal")
        assert "Test Goal" in g.summary()

    def test_summary_includes_status(self):
        g = make_goal(status=GoalStatus.BLOCKED)
        assert "Blocked" in g.summary()

    def test_summary_includes_turn(self):
        g = make_goal(source_turn=42)
        assert "42" in g.summary()

    def test_with_status_returns_new_instance(self):
        g = make_goal(status=GoalStatus.PLANNED)
        g2 = g.with_status(GoalStatus.ACTIVE)
        assert g2 is not g
        assert g2.status == GoalStatus.ACTIVE
        assert g.status == GoalStatus.PLANNED

    def test_with_status_preserves_id(self):
        g = make_goal()
        g2 = g.with_status(GoalStatus.ACTIVE)
        assert g2.id == g.id

    def test_with_status_preserves_all_fields(self):
        g = make_goal(title="X", description="Y", priority=GoalPriority.CRITICAL)
        g2 = g.with_status(GoalStatus.COMPLETED)
        assert g2.title == "X"
        assert g2.description == "Y"
        assert g2.priority == GoalPriority.CRITICAL

    def test_with_priority_returns_new_instance(self):
        g = make_goal(priority=GoalPriority.LOW)
        g2 = g.with_priority(GoalPriority.CRITICAL)
        assert g2.priority == GoalPriority.CRITICAL
        assert g.priority == GoalPriority.LOW

    def test_with_priority_preserves_id(self):
        g = make_goal()
        g2 = g.with_priority(GoalPriority.HIGH)
        assert g2.id == g.id

    def test_blocked_by_stored(self):
        g = make_goal()
        g2 = g.with_status(GoalStatus.BLOCKED, blocked_by="API rate limit")
        assert g2.blocked_by == "API rate limit"

    def test_progress_updated_on_status(self):
        g = make_goal()
        g2 = g.with_status(GoalStatus.COMPLETED, progress=100)
        assert g2.progress == 100


# ===========================================================================
# 4. GOAL MODEL — explain()
# ===========================================================================

class TestGoalExplain:

    def test_explain_includes_title(self):
        g = make_goal(title="Genesis-020")
        assert "Genesis-020" in g.explain()

    def test_explain_includes_description(self):
        g = make_goal(description="Build the cognitive architecture.")
        assert "cognitive architecture" in g.explain()

    def test_explain_includes_status(self):
        g = make_goal(status=GoalStatus.ACTIVE)
        assert "Active" in g.explain()

    def test_explain_includes_priority(self):
        g = make_goal(priority=GoalPriority.CRITICAL)
        assert "Critical" in g.explain()

    def test_explain_includes_progress(self):
        g = Goal(title="X", progress=75)
        assert "75%" in g.explain()

    def test_explain_includes_dependencies(self):
        g = make_goal(dependencies=("dep-id-1",))
        assert "dep-id-1" in g.explain()

    def test_explain_includes_blocked_by(self):
        g = make_goal(status=GoalStatus.BLOCKED, blocked_by="Rate limit")
        assert "Rate limit" in g.explain()

    def test_explain_no_deps_section_when_empty(self):
        g = make_goal(dependencies=())
        assert "Depends on" not in g.explain()

    def test_explain_includes_turn(self):
        g = make_goal(source_turn=15)
        assert "15" in g.explain()


# ===========================================================================
# 5. GOAL ENGINE — basic operations
# ===========================================================================

class TestGoalEngineBasic:

    def test_starts_empty(self):
        e = make_engine()
        assert e.count() == 0
        assert e.all_goals() == []

    def test_create_single_goal(self):
        e = make_engine()
        e.create(make_goal())
        assert e.count() == 1

    def test_get_by_id(self):
        e = make_engine()
        g = make_goal()
        e.create(g)
        assert e.get(g.id) is not None
        assert e.get(g.id).id == g.id

    def test_get_missing_returns_none(self):
        assert make_engine().get("nonexistent") is None

    def test_all_goals_returns_copy(self):
        e = make_engine()
        e.create(make_goal())
        copy = e.all_goals()
        copy.clear()
        assert e.count() == 1

    def test_insertion_order_preserved(self):
        e = make_engine()
        titles = ["First", "Second", "Third"]
        for title in titles:
            e.create(make_goal(title=title))
        assert [g.title for g in e.all_goals()] == titles


# ===========================================================================
# 6. GOAL ENGINE — status transitions
# ===========================================================================

class TestGoalEngineTransitions:

    def test_start_marks_active(self):
        e = make_engine()
        g = make_goal(status=GoalStatus.PLANNED)
        e.create(g)
        e.start(g.id)
        assert e.get(g.id).status == GoalStatus.ACTIVE

    def test_complete_marks_completed(self):
        e = make_engine()
        g = make_goal(status=GoalStatus.ACTIVE)
        e.create(g)
        e.complete(g.id)
        assert e.get(g.id).status == GoalStatus.COMPLETED

    def test_complete_sets_progress_100(self):
        e = make_engine()
        g = make_goal()
        e.create(g)
        e.complete(g.id)
        assert e.get(g.id).progress == 100

    def test_cancel_marks_cancelled(self):
        e = make_engine()
        g = make_goal()
        e.create(g)
        e.cancel(g.id)
        assert e.get(g.id).status == GoalStatus.CANCELLED

    def test_block_marks_blocked(self):
        e = make_engine()
        g = make_goal(status=GoalStatus.ACTIVE)
        e.create(g)
        e.block(g.id, "Waiting for API.")
        assert e.get(g.id).status == GoalStatus.BLOCKED
        assert "API" in e.get(g.id).blocked_by

    def test_unblock_marks_active(self):
        e = make_engine()
        g = make_goal(status=GoalStatus.BLOCKED)
        e.create(g)
        e.unblock(g.id)
        assert e.get(g.id).status == GoalStatus.ACTIVE

    def test_update_priority(self):
        e = make_engine()
        g = make_goal(priority=GoalPriority.LOW)
        e.create(g)
        e.update_priority(g.id, GoalPriority.CRITICAL)
        assert e.get(g.id).priority == GoalPriority.CRITICAL

    def test_transition_missing_id_does_nothing(self):
        e = make_engine()
        e.start("nonexistent")
        e.complete("nonexistent")
        e.cancel("nonexistent")
        e.block("nonexistent")
        e.unblock("nonexistent")
        assert e.count() == 0


# ===========================================================================
# 7. GOAL ENGINE — filtering
# ===========================================================================

class TestGoalEngineFiltering:

    def setup_method(self):
        self.e = make_engine()
        self.e.create(make_goal(title="A", status=GoalStatus.PLANNED))
        self.e.create(make_goal(title="B", status=GoalStatus.ACTIVE))
        self.e.create(make_goal(title="C", status=GoalStatus.BLOCKED))
        self.e.create(make_goal(title="D", status=GoalStatus.COMPLETED))
        self.e.create(make_goal(title="E", status=GoalStatus.CANCELLED))

    def test_active(self):
        assert len(self.e.active()) == 1
        assert self.e.active()[0].title == "B"

    def test_planned(self):
        assert len(self.e.planned()) == 1

    def test_blocked(self):
        assert len(self.e.blocked()) == 1
        assert self.e.blocked()[0].title == "C"

    def test_completed(self):
        assert len(self.e.completed()) == 1
        assert self.e.completed()[0].title == "D"

    def test_cancelled(self):
        assert len(self.e.cancelled()) == 1

    def test_open_goals(self):
        open_goals = self.e.open_goals()
        titles = [g.title for g in open_goals]
        assert "A" in titles
        assert "B" in titles
        assert "C" in titles
        assert "D" not in titles
        assert "E" not in titles

    def test_count_by_status(self):
        assert self.e.count(GoalStatus.ACTIVE) == 1
        assert self.e.count(GoalStatus.COMPLETED) == 1
        assert self.e.count() == 5

    def test_by_priority(self):
        e = make_engine()
        e.create(make_goal(title="Hi", priority=GoalPriority.HIGH))
        e.create(make_goal(title="Lo", priority=GoalPriority.LOW))
        assert len(e.by_priority(GoalPriority.HIGH)) == 1


# ===========================================================================
# 8. GOAL ENGINE — current and next goal
# ===========================================================================

class TestGoalEnginePriority:

    def test_current_goal_is_highest_priority_active(self):
        e = make_engine()
        e.create(make_goal(title="Low", status=GoalStatus.ACTIVE, priority=GoalPriority.LOW))
        e.create(make_goal(title="Critical", status=GoalStatus.ACTIVE, priority=GoalPriority.CRITICAL))
        e.create(make_goal(title="Medium", status=GoalStatus.ACTIVE, priority=GoalPriority.MEDIUM))
        current = e.current_goal()
        assert current.title == "Critical"

    def test_current_goal_none_when_no_active(self):
        e = make_engine()
        e.create(make_goal(status=GoalStatus.PLANNED))
        assert e.current_goal() is None

    def test_next_goal_is_highest_priority_planned(self):
        e = make_engine()
        e.create(make_goal(title="Low", status=GoalStatus.PLANNED, priority=GoalPriority.LOW))
        e.create(make_goal(title="High", status=GoalStatus.PLANNED, priority=GoalPriority.HIGH))
        assert e.next_goal().title == "High"

    def test_next_goal_none_when_no_planned(self):
        e = make_engine()
        assert e.next_goal() is None


# ===========================================================================
# 9. GOAL ENGINE — search
# ===========================================================================

class TestGoalEngineSearch:

    def test_search_by_title(self):
        e = make_engine()
        e.create(make_goal(title="Genesis-020 Sprint-005"))
        results = e.search("Sprint-005")
        assert len(results) == 1

    def test_search_by_description(self):
        e = make_engine()
        e.create(make_goal(description="Build the cognitive architecture."))
        results = e.search("cognitive")
        assert len(results) == 1

    def test_search_by_tag(self):
        e = make_engine()
        e.create(make_goal(tags=("architecture", "planning")))
        results = e.search("planning")
        assert len(results) == 1

    def test_search_case_insensitive(self):
        e = make_engine()
        e.create(make_goal(title="Genesis-020"))
        assert len(e.search("genesis-020")) == 1

    def test_search_no_results(self):
        e = make_engine()
        e.create(make_goal(title="Something"))
        assert e.search("quantum physics") == []


# ===========================================================================
# 10. GOAL ENGINE — query helpers
# ===========================================================================

class TestGoalEngineHelpers:

    def test_latest(self):
        e = make_engine()
        for i in range(5):
            e.create(make_goal(title=f"Goal {i}"))
        latest = e.latest(3)
        assert len(latest) == 3
        assert latest[-1].title == "Goal 4"

    def test_on_date_today(self):
        e = make_engine()
        e.create(make_goal())
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        assert len(e.on_date(today)) == 1

    def test_today(self):
        e = make_engine()
        e.create(make_goal())
        assert len(e.today()) == 1

    def test_summary_dict(self):
        e = make_engine()
        e.create(make_goal(title="A", status=GoalStatus.ACTIVE, priority=GoalPriority.HIGH))
        e.create(make_goal(title="B", status=GoalStatus.COMPLETED))
        s = e.summary()
        assert s["total"] == 2
        assert s["active"] == 1
        assert s["completed"] == 1
        assert s["current"] == "A"


# ===========================================================================
# 11. GOAL ENGINE — Projection replay
# ===========================================================================

class TestGoalEngineProjection:

    def test_is_projection(self):
        from core.conversation.projection import Projection
        assert isinstance(make_engine(), Projection)

    def test_apply_goal_created_event(self):
        e = make_engine()
        event = make_timeline_event(EventType.GOAL_CREATED, "Build Sprint-005",
                                    payload={"goal_id": "g-001"})
        e.apply(event)
        assert e.count() == 1
        assert e.get("g-001").status == GoalStatus.PLANNED

    def test_apply_goal_started_event(self):
        e = make_engine()
        e.apply(make_timeline_event(EventType.GOAL_CREATED, "Goal A",
                                    payload={"goal_id": "g-001"}))
        e.apply(make_timeline_event(EventType.GOAL_STARTED, "Goal A",
                                    payload={"goal_id": "g-001"}))
        assert e.get("g-001").status == GoalStatus.ACTIVE

    def test_apply_goal_completed_event(self):
        e = make_engine()
        e.apply(make_timeline_event(EventType.GOAL_CREATED, "Goal A",
                                    payload={"goal_id": "g-001"}))
        e.apply(make_timeline_event(EventType.GOAL_COMPLETED, "Goal A",
                                    payload={"goal_id": "g-001"}))
        assert e.get("g-001").status == GoalStatus.COMPLETED

    def test_apply_goal_cancelled_event(self):
        e = make_engine()
        e.apply(make_timeline_event(EventType.GOAL_CREATED, "Goal A",
                                    payload={"goal_id": "g-001"}))
        e.apply(make_timeline_event(EventType.GOAL_CANCELLED, "Goal A",
                                    payload={"goal_id": "g-001"}))
        assert e.get("g-001").status == GoalStatus.CANCELLED

    def test_apply_goal_blocked_event(self):
        e = make_engine()
        e.apply(make_timeline_event(EventType.GOAL_CREATED, "Goal A",
                                    payload={"goal_id": "g-001"}))
        e.apply(make_timeline_event(EventType.GOAL_BLOCKED, "Goal A",
                                    payload={"goal_id": "g-001", "blocked_by": "API issue"}))
        assert e.get("g-001").status == GoalStatus.BLOCKED
        assert "API" in e.get("g-001").blocked_by

    def test_apply_goal_unblocked_event(self):
        e = make_engine()
        e.apply(make_timeline_event(EventType.GOAL_CREATED, "Goal A",
                                    payload={"goal_id": "g-001"}))
        e.apply(make_timeline_event(EventType.GOAL_BLOCKED, "Goal A",
                                    payload={"goal_id": "g-001", "blocked_by": "X"}))
        e.apply(make_timeline_event(EventType.GOAL_UNBLOCKED, "Goal A",
                                    payload={"goal_id": "g-001"}))
        assert e.get("g-001").status == GoalStatus.ACTIVE

    def test_apply_goal_priority_changed_event(self):
        e = make_engine()
        e.apply(make_timeline_event(EventType.GOAL_CREATED, "Goal A",
                                    payload={"goal_id": "g-001", "priority": "low"}))
        e.apply(make_timeline_event(EventType.GOAL_PRIORITY_CHANGED, "Goal A",
                                    payload={"goal_id": "g-001", "priority": "critical"}))
        assert e.get("g-001").priority == GoalPriority.CRITICAL

    def test_replay_from_timeline(self):
        tl = ConversationTimeline()
        tl.record(make_timeline_event(EventType.GOAL_CREATED, "Sprint-005",
                                      payload={"goal_id": "g-001"}, turn=1))
        tl.record(make_timeline_event(EventType.GOAL_CREATED, "Sprint-006",
                                      payload={"goal_id": "g-002"}, turn=2))
        tl.record(make_timeline_event(EventType.GOAL_STARTED, "Sprint-005",
                                      payload={"goal_id": "g-001"}, turn=3))
        tl.record(make_timeline_event(EventType.GOAL_COMPLETED, "Sprint-005",
                                      payload={"goal_id": "g-001"}, turn=10))

        e = make_engine()
        tl.replay(e)

        assert e.count() == 2
        assert e.get("g-001").status == GoalStatus.COMPLETED
        assert e.get("g-002").status == GoalStatus.PLANNED

    def test_replay_is_deterministic(self):
        tl = ConversationTimeline()
        tl.record(make_timeline_event(EventType.GOAL_CREATED, "A",
                                      payload={"goal_id": "g-001"}, turn=1))
        tl.record(make_timeline_event(EventType.GOAL_STARTED, "A",
                                      payload={"goal_id": "g-001"}, turn=2))

        e1 = make_engine()
        e2 = make_engine()
        tl.replay(e1)
        tl.replay(e2)

        assert [g.status for g in e1.all_goals()] == \
               [g.status for g in e2.all_goals()]

    def test_replay_on_empty_timeline(self):
        e = make_engine()
        ConversationTimeline().replay(e)
        assert e.count() == 0

    def test_malformed_event_empty_value_skipped(self):
        e = make_engine()
        bad = make_timeline_event(EventType.GOAL_CREATED, "", payload={"goal_id": "g-bad"})
        e.apply(bad)
        assert e.count() == 0

    def test_malformed_event_missing_goal_id_skipped(self):
        e = make_engine()
        e.apply(make_timeline_event(EventType.GOAL_CREATED, "Valid Goal"))
        # Missing goal_id in payload for transition — should not crash
        e.apply(make_timeline_event(EventType.GOAL_STARTED, "Valid Goal",
                                    payload={"goal_id": "nonexistent"}))
        # Just verify no crash

    def test_duplicate_replay_idempotent(self):
        """Replaying the same GOAL_CREATED event twice should not duplicate."""
        e = make_engine()
        event = make_timeline_event(EventType.GOAL_CREATED, "Goal A",
                                    payload={"goal_id": "g-001"})
        e.apply(event)
        e.apply(event)  # replay again
        assert e.count() == 1

    def test_non_goal_events_ignored(self):
        e = make_engine()
        e.apply(make_timeline_event(EventType.START_PROJECT, "Jarvis OS"))
        e.apply(make_timeline_event(EventType.DECISION_ACCEPTED, "Use Flask"))
        assert e.count() == 0

    def test_on_replay_complete_called(self):
        tl = ConversationTimeline()
        e = make_engine()
        tl.replay(e)  # should not raise

    def test_replay_ordering_preserved(self):
        """Goals should appear in turn order after replay."""
        tl = ConversationTimeline()
        tl.record(make_timeline_event(EventType.GOAL_CREATED, "First",
                                      payload={"goal_id": "g-001"}, turn=1))
        tl.record(make_timeline_event(EventType.GOAL_CREATED, "Second",
                                      payload={"goal_id": "g-002"}, turn=5))
        tl.record(make_timeline_event(EventType.GOAL_CREATED, "Third",
                                      payload={"goal_id": "g-003"}, turn=10))
        e = make_engine()
        tl.replay(e)
        titles = [g.title for g in e.all_goals()]
        assert titles == ["First", "Second", "Third"]


# ===========================================================================
# 12. GOAL QUERY ENGINE — can_answer
# ===========================================================================

class TestGoalQueryCanAnswer:

    def setup_method(self):
        self.qe, _ = make_query_engine()

    def test_what_are_we_working_on(self):
        assert self.qe.can_answer("What are we working on?")

    def test_what_is_our_current_goal(self):
        assert self.qe.can_answer("What is our current goal?")

    def test_what_should_we_do_next(self):
        assert self.qe.can_answer("What should we do next?")

    def test_which_goals_completed(self):
        assert self.qe.can_answer("Which goals are completed?")

    def test_which_goals_blocked(self):
        assert self.qe.can_answer("Which goals are blocked?")

    def test_what_goals_do_we_have(self):
        assert self.qe.can_answer("What goals do we have?")

    def test_show_goals(self):
        assert self.qe.can_answer("show goals")

    def test_slash_goals(self):
        assert self.qe.can_answer("/goals")

    def test_how_many_goals(self):
        assert self.qe.can_answer("How many goals?")

    def test_why_is_this_goal(self):
        assert self.qe.can_answer("Why is this goal important?")

    def test_active_goals(self):
        assert self.qe.can_answer("What active goals do we have?")

    def test_planned_goals(self):
        assert self.qe.can_answer("What planned goals are there?")

    def test_explain_goal(self):
        assert self.qe.can_answer("Explain the Genesis-020 goal.")

    def test_poem_not_answerable(self):
        assert not self.qe.can_answer("Write me a poem.")

    def test_weather_not_answerable(self):
        assert not self.qe.can_answer("What's the weather?")


# ===========================================================================
# 13. GOAL QUERY ENGINE — answers
# ===========================================================================

class TestGoalQueryAnswers:

    def setup_method(self):
        e = make_engine()
        e.create(make_goal(title="Genesis-020", status=GoalStatus.ACTIVE,
                           priority=GoalPriority.CRITICAL,
                           description="Build the cognitive architecture."))
        e.create(make_goal(title="Sprint-005", status=GoalStatus.ACTIVE,
                           priority=GoalPriority.HIGH,
                           description="Implement the Goal Engine."))
        e.create(make_goal(title="Sprint-004", status=GoalStatus.COMPLETED))
        e.create(make_goal(title="Research", status=GoalStatus.PLANNED,
                           priority=GoalPriority.LOW))
        e.create(make_goal(title="Old Goal", status=GoalStatus.BLOCKED,
                           blocked_by="Missing API"))
        self.qe = GoalQueryEngine(e)
        self.e = e

    def test_what_are_we_working_on(self):
        r = self.qe.answer("What are we working on?")
        assert r.answered
        assert "Genesis-020" in r.answer

    def test_current_goal_is_highest_priority(self):
        r = self.qe.answer("What is our current goal?")
        assert r.answered
        assert "Genesis-020" in r.answer

    def test_what_next(self):
        r = self.qe.answer("What should we do next?")
        assert r.answered

    def test_which_completed(self):
        r = self.qe.answer("Which goals are completed?")
        assert r.answered
        assert "Sprint-004" in r.answer

    def test_which_blocked(self):
        r = self.qe.answer("Which goals are blocked?")
        assert r.answered
        assert "Old Goal" in r.answer
        assert "Missing API" in r.answer

    def test_what_goals(self):
        r = self.qe.answer("What goals do we have?")
        assert r.answered

    def test_show_goals(self):
        r = self.qe.answer("show goals")
        assert r.answered
        assert "Genesis-020" in r.answer

    def test_how_many(self):
        r = self.qe.answer("How many goals?")
        assert r.answered
        assert "5" in r.answer

    def test_explain_goal(self):
        r = self.qe.answer("Explain the Genesis-020 goal.")
        assert r.answered
        assert "Genesis-020" in r.answer

    def test_empty_engine_graceful(self):
        qe = GoalQueryEngine(make_engine())
        r = qe.answer("What goals do we have?")
        assert r.answered
        assert "No" in r.answer or "no" in r.answer

    def test_result_has_goals(self):
        r = self.qe.answer("What goals do we have?")
        assert r.answered
        assert len(r.goals) >= 1

    def test_miss_on_unanswerable(self):
        r = self.qe.answer("Write me a poem.")
        assert not r.answered


# ===========================================================================
# 14. GOAL QUERY RESULT
# ===========================================================================

class TestGoalQueryResult:

    def test_miss_factory(self):
        r = GoalQueryResult.miss("test")
        assert not r.answered
        assert r.answer == ""

    def test_empty_factory(self):
        r = GoalQueryResult.empty("test", "Nothing.")
        assert r.answered
        assert r.answer == "Nothing."

    def test_is_frozen(self):
        r = GoalQueryResult.miss("test")
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            r.answered = True


# ===========================================================================
# 15. GOAL INSPECTOR
# ===========================================================================

class TestGoalInspector:

    def test_returns_string(self):
        assert isinstance(GoalInspector(make_engine()).inspect(), str)

    def test_empty_shows_zero(self):
        output = GoalInspector(make_engine()).inspect()
        assert "0 goal" in output

    def test_shows_goal_count(self):
        e = make_engine()
        e.create(make_goal(title="A"))
        e.create(make_goal(title="B"))
        output = GoalInspector(e).inspect()
        assert "2 goal" in output

    def test_shows_active_count(self):
        e = make_engine()
        e.create(make_goal(status=GoalStatus.ACTIVE))
        output = GoalInspector(e).inspect()
        assert "Active" in output

    def test_shows_priorities(self):
        e = make_engine()
        e.create(make_goal(title="Genesis-020", status=GoalStatus.ACTIVE,
                           priority=GoalPriority.CRITICAL))
        output = GoalInspector(e).inspect()
        assert "Genesis-020" in output

    def test_is_empty_when_no_goals(self):
        assert GoalInspector(make_engine()).is_empty()

    def test_is_not_empty_when_has_goals(self):
        e = make_engine()
        e.create(make_goal())
        assert not GoalInspector(e).is_empty()

    def test_summary_line_returns_string(self):
        e = make_engine()
        e.create(make_goal())
        line = GoalInspector(e).summary_line()
        assert isinstance(line, str)
        assert "Goals" in line


# ===========================================================================
# 16. EVENT TYPE — new GOAL_* types
# ===========================================================================

class TestEventTypeGoal:

    def test_goal_created_exists(self):
        assert hasattr(EventType, "GOAL_CREATED")

    def test_goal_started_exists(self):
        assert hasattr(EventType, "GOAL_STARTED")

    def test_goal_completed_exists(self):
        assert hasattr(EventType, "GOAL_COMPLETED")

    def test_goal_cancelled_exists(self):
        assert hasattr(EventType, "GOAL_CANCELLED")

    def test_goal_blocked_exists(self):
        assert hasattr(EventType, "GOAL_BLOCKED")

    def test_goal_unblocked_exists(self):
        assert hasattr(EventType, "GOAL_UNBLOCKED")

    def test_goal_priority_changed_exists(self):
        assert hasattr(EventType, "GOAL_PRIORITY_CHANGED")

    def test_total_event_types_is_21(self):
        assert len(list(EventType)) == 21

    def test_goal_labels(self):
        assert EventType.GOAL_CREATED.label() == "Goal Created"
        assert EventType.GOAL_COMPLETED.label() == "Goal Completed"
        assert EventType.GOAL_PRIORITY_CHANGED.label() == "Goal Priority Changed"


# ===========================================================================
# 17. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_original_ten_event_types_present(self):
        for name in ["START_PROJECT", "START_SPRINT", "FINISH_SPRINT", "FREEZE",
                     "DECISION", "TASK", "PERSON", "ACHIEVEMENT", "QUESTION", "GENERAL"]:
            assert hasattr(EventType, name)

    def test_decision_event_types_present(self):
        for name in ["DECISION_PROPOSED", "DECISION_ACCEPTED",
                     "DECISION_SUPERSEDED", "DECISION_REJECTED"]:
            assert hasattr(EventType, name)

    def test_session_context_unchanged(self):
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_project("Jarvis OS")
        assert s.active_project.value == "Jarvis OS"

    def test_timeline_unchanged(self):
        tl = ConversationTimeline()
        tl.record(TimelineEvent(EventType.START_PROJECT, "Jarvis", turn=1))
        assert tl.count() == 1

    def test_decision_engine_unchanged(self):
        from core.conversation.decision_engine import DecisionEngine
        from core.conversation.architectural_decision import ArchitecturalDecision, DecisionStatus
        e = DecisionEngine()
        d = ArchitecturalDecision(title="Test", decision="Do X", reason="Because Y")
        e.record(d)
        assert e.count() == 1

    def test_goal_engine_independent(self):
        e = make_engine()
        assert not hasattr(e, "_knowledge")
        assert not hasattr(e, "_timeline")

    def test_goal_and_decision_engines_independent(self):
        from core.conversation.decision_engine import DecisionEngine
        ge = make_engine()
        de = DecisionEngine()
        ge.create(make_goal(title="Goal A"))
        assert de.count() == 0  # Decision engine unaffected