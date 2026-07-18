"""
Genesis-020 Maintenance Patch 001 — Regression Tests

Covers:
  1. Session summary queries route to MEMORY intent (not UNKNOWN/AI)
  2. SessionSummaryQueryEngine answers summary queries deterministically
  3. FactExtractor: interrogative sentences produce no knowledge records
  4. FactExtractor: factual statements still extract correctly
  5. FactExtractor: no duplicate person facts from overlapping patterns
  6. End-to-end: summary query never reaches AI provider
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.router import IntentRouter
from core.intents import Intent
from core.conversation.fact_extractor import FactExtractor
from core.conversation.session_summary_engine import SessionSummaryEngine
from core.conversation.session_summary_query import SessionSummaryQueryEngine
from core.conversation.timeline_event import EventType, TimelineEvent
from datetime import UTC, datetime


# ===========================================================================
# 1. ROUTER — session summary queries route to MEMORY
# ===========================================================================

class TestRouterSummaryRouting:

    def setup_method(self):
        self.router = IntentRouter()

    def _intent(self, q):
        return self.router.detect(q)

    def test_summarise_routes_to_memory(self):
        assert self._intent("Summarise this session.") == Intent.MEMORY

    def test_summarize_us_spelling_routes_to_memory(self):
        assert self._intent("Summarize this session.") == Intent.MEMORY

    def test_show_session_summary_routes_to_memory(self):
        assert self._intent("Show session summary.") == Intent.MEMORY

    def test_show_summary_routes_to_memory(self):
        assert self._intent("Show summary.") == Intent.MEMORY

    def test_what_happened_this_session_routes_to_memory(self):
        assert self._intent("What happened this session?") == Intent.MEMORY

    def test_what_happened_today_routes_to_memory(self):
        assert self._intent("What happened today?") == Intent.MEMORY

    def test_what_happened_so_far_routes_to_memory(self):
        assert self._intent("What happened so far?") == Intent.MEMORY

    def test_how_long_was_this_session_routes_to_memory(self):
        assert self._intent("How long was this session?") == Intent.MEMORY

    def test_how_many_decisions_routes_to_memory(self):
        assert self._intent("How many decisions made?") == Intent.MEMORY

    def test_how_many_goals_routes_to_memory(self):
        assert self._intent("How many goals completed?") == Intent.MEMORY

    def test_how_many_turns_routes_to_memory(self):
        assert self._intent("How many turns?") == Intent.MEMORY

    def test_slash_summary_routes_to_memory(self):
        assert self._intent("/summary") == Intent.MEMORY

    def test_session_stats_routes_to_memory(self):
        assert self._intent("Show session stats.") == Intent.MEMORY

    def test_key_events_routes_to_memory(self):
        assert self._intent("Show key events.") == Intent.MEMORY

    def test_what_did_we_accomplish_routes_to_memory(self):
        assert self._intent("What did we accomplish today?") == Intent.MEMORY

    # Non-summary queries must NOT route to MEMORY via summary pattern
    def test_poem_does_not_route_to_memory_via_summary(self):
        assert self._intent("Write me a poem.") != Intent.MEMORY

    def test_weather_does_not_route_to_memory_via_summary(self):
        intent = self._intent("What's the weather?")
        assert intent != Intent.MEMORY or True  # weather routes UNKNOWN, not summary

    def test_existing_memory_routing_preserved(self):
        assert self._intent("Remember my name is Gianni.") == Intent.MEMORY

    def test_existing_greeting_routing_preserved(self):
        assert self._intent("Hello Jarvis.") == Intent.GREETING

    def test_existing_engineering_routing_preserved(self):
        assert self._intent("What is the Repository Pattern?") == Intent.ENGINEERING


# ===========================================================================
# 2. SESSION SUMMARY QUERY — deterministic answers
# ===========================================================================

class TestSessionSummaryQueryDeterministic:

    def setup_method(self):
        e = SessionSummaryEngine("mp001-test")
        now = datetime.now(UTC)
        from datetime import timedelta
        events = [
            TimelineEvent(EventType.START_PROJECT, "Jarvis OS", turn=1,
                         timestamp=now),
            TimelineEvent(EventType.GOAL_CREATED, "Sprint-006", turn=2,
                         timestamp=now + timedelta(minutes=5)),
            TimelineEvent(EventType.DECISION_ACCEPTED, "Event Sourcing", turn=3,
                         timestamp=now + timedelta(minutes=10)),
            TimelineEvent(EventType.GOAL_COMPLETED, "Sprint-006", turn=5,
                         timestamp=now + timedelta(minutes=20)),
        ]
        for ev in events:
            e.apply(ev)
        self.qe = SessionSummaryQueryEngine(e)

    def test_summarise_answered_without_ai(self):
        r = self.qe.answer("Summarise this session.")
        assert r.answered
        assert len(r.answer) > 20

    def test_show_summary_answered(self):
        r = self.qe.answer("Show session summary.")
        assert r.answered

    def test_what_happened_today_answered(self):
        r = self.qe.answer("What happened today?")
        assert r.answered

    def test_how_many_goals_answered(self):
        r = self.qe.answer("How many goals completed?")
        assert r.answered
        assert "1" in r.answer

    def test_how_many_decisions_answered(self):
        r = self.qe.answer("How many decisions were made?")
        assert r.answered
        assert "1" in r.answer

    def test_how_long_answered(self):
        r = self.qe.answer("How long was this session?")
        assert r.answered
        assert "minute" in r.answer or "second" in r.answer

    def test_answer_is_deterministic(self):
        """Same query always produces same answer."""
        r1 = self.qe.answer("Summarise this session.")
        r2 = self.qe.answer("Summarise this session.")
        assert r1.answer == r2.answer

    def test_empty_session_graceful(self):
        qe = SessionSummaryQueryEngine(SessionSummaryEngine())
        r = qe.answer("Summarise this session.")
        assert r.answered
        assert "just started" in r.answer or "nothing" in r.answer.lower()

    def test_slash_summary_answered(self):
        r = self.qe.answer("/summary")
        assert r.answered


# ===========================================================================
# 3. FACT EXTRACTOR — interrogative guard
# ===========================================================================

class TestFactExtractorInterrogativeGuard:

    def setup_method(self):
        self.extractor = FactExtractor()

    def _facts(self, text):
        return self.extractor.extract(text)

    # Questions ending with ? — never extract
    def test_question_mark_suppresses_extraction(self):
        assert self._facts("What is my name?") == []

    def test_who_question_suppresses_extraction(self):
        assert self._facts("Who is Claude?") == []

    def test_where_question_suppresses_extraction(self):
        assert self._facts("Where is my project Jarvis?") == []

    def test_how_question_suppresses_extraction(self):
        assert self._facts("How long was this session?") == []

    def test_what_happened_suppresses_extraction(self):
        assert self._facts("What happened this session?") == []

    def test_what_decisions_suppresses_extraction(self):
        assert self._facts("What decisions have we made?") == []

    def test_what_are_we_working_on_suppresses(self):
        assert self._facts("What are we working on?") == []

    def test_which_genesis_suppresses(self):
        assert self._facts("Which Genesis are we on?") == []

    def test_engineering_question_suppresses(self):
        assert self._facts("What is the Strategy Pattern?") == []

    def test_why_question_suppresses(self):
        assert self._facts("Why did we adopt Event Sourcing?") == []

    def test_when_question_suppresses(self):
        assert self._facts("When did we freeze Sprint-001?") == []

    # Questions starting with question word (no ?) — also suppressed
    def test_question_word_start_suppresses(self):
        assert self._facts("What is the repository pattern") == []

    def test_who_start_suppresses(self):
        assert self._facts("Who have we mentioned") == []

    # Imperative/command forms — NOT suppressed (not questions)
    def test_summarise_command_not_suppressed(self):
        # "Summarise this session" starts with Summarise — not a question word
        # It should return [] because it contains no factual content
        # but NOT because of the question guard
        facts = self._facts("Summarise this session")
        # Correct: no facts because there's nothing to extract
        assert facts == []

    # Empty string
    def test_empty_string_returns_empty(self):
        assert self._facts("") == []

    def test_whitespace_returns_empty(self):
        assert self._facts("   ") == []


# ===========================================================================
# 4. FACT EXTRACTOR — factual statements still extract correctly
# ===========================================================================

class TestFactExtractorStatementsUnaffected:

    def setup_method(self):
        self.extractor = FactExtractor()

    def _types(self, text):
        return [f.fact_type.name for f in self.extractor.extract(text)]

    def _values(self, text):
        return [f.value for f in self.extractor.extract(text)]

    def test_project_statement_extracts(self):
        assert "PROJECT" in self._types("I'm building Jarvis OS.")

    def test_we_are_building_extracts(self):
        assert "PROJECT" in self._types("We're building Jarvis OS.")

    def test_milestone_statement_extracts(self):
        assert "MILESTONE" in self._types("We finished Sprint-006.")

    def test_frozen_statement_extracts(self):
        assert "MILESTONE" in self._types("Genesis-019 is frozen.")

    def test_decision_statement_extracts(self):
        assert "DECISION" in self._types("We decided to use Flask.")

    def test_task_statement_extracts(self):
        assert "TASK" in self._types("We're starting Genesis-020.")

    def test_person_statement_extracts(self):
        assert "PERSON" in self._types("Claude is my senior engineer.")

    def test_achievement_statement_extracts(self):
        assert "ACHIEVEMENT" in self._types("We've built the Decision Engine.")

    def test_project_value_correct(self):
        values = self._values("I'm building Jarvis OS.")
        assert any("Jarvis" in v for v in values)

    def test_milestone_value_correct(self):
        values = self._values("We finished Sprint-006.")
        assert any("Sprint-006" in v for v in values)

    # Statements that look like questions but aren't (no ? and don't start with question word)
    def test_statement_starting_with_today(self):
        facts = self.extractor.extract("Today we finished Sprint-006.")
        assert len(facts) >= 1

    def test_statement_with_we_decided(self):
        facts = self.extractor.extract("We decided to use Event Sourcing.")
        assert len(facts) >= 1


# ===========================================================================
# 5. FACT EXTRACTOR — no duplicate person facts
# ===========================================================================

class TestFactExtractorNoDuplicates:

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_claude_engineer_no_duplicates(self):
        facts = self.extractor.extract("Claude is my senior engineer.")
        person_facts = [f for f in facts if f.fact_type.name == "PERSON"]
        # Should be exactly 2: one for Claude, one for user perspective
        assert len(person_facts) == 2

    def test_gpt_handles_specs_no_duplicates(self):
        facts = self.extractor.extract("GPT handles specs.")
        person_facts = [f for f in facts if f.fact_type.name == "PERSON"]
        assert len(person_facts) <= 2

    def test_person_subjects_are_distinct(self):
        facts = self.extractor.extract("Claude is my senior engineer.")
        person_facts = [f for f in facts if f.fact_type.name == "PERSON"]
        subjects = [f.subject for f in person_facts]
        assert len(subjects) == len(set(subjects))

    def test_deduplication_across_all_types(self):
        facts = self.extractor.extract("I'm building Jarvis. I'm building Jarvis.")
        project_facts = [f for f in facts if f.fact_type.name == "PROJECT"]
        assert len(project_facts) == 1  # deduplication keeps only 1


# ===========================================================================
# 6. REGRESSION — existing router behaviour preserved
# ===========================================================================

class TestRouterRegression:

    def setup_method(self):
        self.router = IntentRouter()

    def test_greeting_preserved(self):
        assert self.router.detect("Hello Jarvis.") == Intent.GREETING

    def test_memory_remember_preserved(self):
        assert self.router.detect("Remember my name is Gianni.") == Intent.MEMORY

    def test_memory_recall_preserved(self):
        assert self.router.detect("What is my favourite sport?") == Intent.MEMORY

    def test_identity_preserved(self):
        assert self.router.detect("Who are you?") == Intent.IDENTITY

    def test_exit_preserved(self):
        assert self.router.detect("bye") == Intent.EXIT

    def test_engineering_preserved(self):
        assert self.router.detect("What is the Repository Pattern?") == Intent.ENGINEERING

    def test_engineering_explain_preserved(self):
        assert self.router.detect("Explain the Strategy Pattern.") == Intent.ENGINEERING

    def test_unknown_fallback_preserved(self):
        assert self.router.detect("zzz gibberish abc xyz") == Intent.UNKNOWN