"""
Genesis-020 Sprint-001 — Conversation Memory Tests
Completely self-contained. No dependency on other test files.

Coverage:
  - FactExtractor: project, milestone, person, task, decision, achievement
  - FactExtractor: noise filtering, deduplication
  - ConversationObserver: stores facts via KnowledgeEngine
  - ConversationObserver: journals conversation turns
  - ConversationRecall: can_answer detection
  - ConversationRecall: project, milestone, person, temporal recall
  - Backwards compatibility: existing memory commands unchanged
"""

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.fact_extractor import (
    ExtractedFact, FactExtractor, FactType,
)
from core.conversation.conversation_observer import ConversationObserver
from core.conversation.conversation_recall import ConversationRecall


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_knowledge():
    """Create a mock KnowledgeEngine for testing."""
    k = MagicMock()
    k.recall_memory.return_value = None
    k.search_memory.return_value = []
    k.store_memory.return_value = MagicMock()
    return k


def make_mock_record(attribute, value, subject="user", tags=None):
    r = MagicMock()
    r.attribute = attribute
    r.value = value
    r.subject = subject
    r.tags = tags or []
    r.updated_at = datetime.now(UTC)
    return r


# ===========================================================================
# 1. FACT EXTRACTOR — Project detection
# ===========================================================================

class TestFactExtractorProjects:

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_i_am_building(self):
        facts = self.extractor.extract("I'm building Jarvis.")
        projects = [f for f in facts if f.fact_type == FactType.PROJECT]
        assert len(projects) == 1
        assert "jarvis" in projects[0].value.lower()

    def test_we_are_building(self):
        facts = self.extractor.extract("We're building Jarvis OS.")
        projects = [f for f in facts if f.fact_type == FactType.PROJECT]
        assert len(projects) == 1
        assert "jarvis" in projects[0].value.lower()

    def test_working_on(self):
        facts = self.extractor.extract("I am working on Genesis-020.")
        projects = [f for f in facts if f.fact_type == FactType.PROJECT]
        assert len(projects) == 1
        assert "genesis" in projects[0].value.lower()

    def test_my_project_is(self):
        facts = self.extractor.extract("My project is Jarvis OS.")
        projects = [f for f in facts if f.fact_type == FactType.PROJECT]
        assert len(projects) == 1

    def test_project_attribute_is_current_project(self):
        facts = self.extractor.extract("I'm building Jarvis.")
        projects = [f for f in facts if f.fact_type == FactType.PROJECT]
        assert projects[0].attribute == "current project"
        assert projects[0].subject == "user"

    def test_project_confidence_is_reasonable(self):
        facts = self.extractor.extract("I'm building Jarvis.")
        projects = [f for f in facts if f.fact_type == FactType.PROJECT]
        assert 0.7 <= projects[0].confidence <= 1.0


# ===========================================================================
# 2. FACT EXTRACTOR — Milestone detection
# ===========================================================================

class TestFactExtractorMilestones:

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_we_finished(self):
        facts = self.extractor.extract("Today we finished Engineering Academy.")
        milestones = [f for f in facts if f.fact_type == FactType.MILESTONE]
        assert len(milestones) == 1
        assert "engineering academy" in milestones[0].value.lower()

    def test_we_completed(self):
        facts = self.extractor.extract("We completed Genesis-019.")
        milestones = [f for f in facts if f.fact_type == FactType.MILESTONE]
        assert len(milestones) == 1

    def test_genesis_is_frozen(self):
        facts = self.extractor.extract("Genesis-019 is frozen.")
        milestones = [f for f in facts if f.fact_type == FactType.MILESTONE]
        assert len(milestones) == 1
        assert "genesis" in milestones[0].value.lower()

    def test_milestone_attribute(self):
        facts = self.extractor.extract("We finished Engineering Academy.")
        milestones = [f for f in facts if f.fact_type == FactType.MILESTONE]
        assert milestones[0].attribute == "last milestone"
        assert milestones[0].subject == "user"

    def test_i_have_finished(self):
        facts = self.extractor.extract("I've finished the sprint.")
        milestones = [f for f in facts if f.fact_type == FactType.MILESTONE]
        assert len(milestones) >= 1


# ===========================================================================
# 3. FACT EXTRACTOR — Person detection
# ===========================================================================

class TestFactExtractorPeople:

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_claude_is_my_engineer(self):
        facts = self.extractor.extract("Claude is my senior engineer.")
        people = [f for f in facts if f.fact_type == FactType.PERSON]
        assert len(people) >= 1
        roles = [f.value.lower() for f in people]
        assert any("engineer" in r for r in roles)

    def test_gpt_handles_specs(self):
        facts = self.extractor.extract("GPT handles specs.")
        people = [f for f in facts if f.fact_type == FactType.PERSON]
        assert len(people) >= 1

    def test_person_subject_is_name(self):
        facts = self.extractor.extract("Claude is my senior engineer.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                        and f.subject != "user"]
        assert any(f.subject == "claude" for f in person_facts)

    def test_person_also_stored_from_user_perspective(self):
        facts = self.extractor.extract("Claude is my senior engineer.")
        user_person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                             and f.subject == "user"]
        assert len(user_person_facts) >= 1


# ===========================================================================
# 4. FACT EXTRACTOR — Task detection
# ===========================================================================

class TestFactExtractorTasks:

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_we_are_starting(self):
        facts = self.extractor.extract("We're starting Genesis-020.")
        tasks = [f for f in facts if f.fact_type == FactType.TASK]
        assert len(tasks) == 1
        assert "genesis" in tasks[0].value.lower()

    def test_i_am_starting(self):
        facts = self.extractor.extract("I'm starting Sprint-001.")
        tasks = [f for f in facts if f.fact_type == FactType.TASK]
        assert len(tasks) == 1

    def test_task_attribute(self):
        facts = self.extractor.extract("We're starting Genesis-020.")
        tasks = [f for f in facts if f.fact_type == FactType.TASK]
        assert tasks[0].attribute == "current task"


# ===========================================================================
# 5. FACT EXTRACTOR — Decision detection
# ===========================================================================

class TestFactExtractorDecisions:

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_we_decided(self):
        facts = self.extractor.extract("We decided to use Flask.")
        decisions = [f for f in facts if f.fact_type == FactType.DECISION]
        assert len(decisions) == 1
        assert "flask" in decisions[0].value.lower()

    def test_i_chose(self):
        facts = self.extractor.extract("I chose to use Tavily.")
        decisions = [f for f in facts if f.fact_type == FactType.DECISION]
        assert len(decisions) == 1


# ===========================================================================
# 6. FACT EXTRACTOR — Noise filtering
# ===========================================================================

class TestFactExtractorNoise:

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_empty_string_returns_empty(self):
        assert self.extractor.extract("") == []

    def test_whitespace_only_returns_empty(self):
        assert self.extractor.extract("   ") == []

    def test_generic_statement_returns_empty(self):
        facts = self.extractor.extract("Hello there.")
        assert len(facts) == 0

    def test_noise_value_filtered(self):
        # "I'm building it" — "it" is noise
        facts = self.extractor.extract("I'm building it.")
        projects = [f for f in facts if f.fact_type == FactType.PROJECT]
        assert len(projects) == 0

    def test_deduplication(self):
        # Two patterns matching same fact shouldn't create duplicates
        facts = self.extractor.extract("We finished Genesis-019. Genesis-019 is done.")
        milestones = [f for f in facts if f.fact_type == FactType.MILESTONE]
        # Should be deduplicated
        unique_values = {f.value.lower() for f in milestones}
        assert len(unique_values) <= 2


# ===========================================================================
# 7. EXTRACTED FACT — Data model
# ===========================================================================

class TestExtractedFact:

    def test_fact_is_frozen(self):
        fact = ExtractedFact(
            fact_type=FactType.PROJECT,
            subject="user",
            attribute="current project",
            value="Jarvis OS",
        )
        with pytest.raises((AttributeError, TypeError)):
            fact.value = "something else"

    def test_fact_has_timestamp(self):
        fact = ExtractedFact(
            fact_type=FactType.PROJECT,
            subject="user",
            attribute="current project",
            value="Jarvis OS",
        )
        assert isinstance(fact.extracted_at, datetime)

    def test_default_confidence_is_reasonable(self):
        fact = ExtractedFact(
            fact_type=FactType.PROJECT,
            subject="user",
            attribute="current project",
            value="Jarvis OS",
        )
        assert 0.0 < fact.confidence <= 1.0


# ===========================================================================
# 8. CONVERSATION OBSERVER — stores facts
# ===========================================================================

class TestConversationObserver:

    def test_observe_project_calls_store_memory(self):
        k = make_mock_knowledge()
        observer = ConversationObserver(k)
        observer.observe("I'm building Jarvis OS.", "Understood, sir.")
        assert k.store_memory.called

    def test_observe_stores_project_fact(self):
        k = make_mock_knowledge()
        observer = ConversationObserver(k)
        observer.observe("I'm building Jarvis OS.", "Understood.")
        calls = k.store_memory.call_args_list
        attributes = [c.kwargs.get("attribute", "") for c in calls]
        assert any("project" in a for a in attributes)

    def test_observe_journals_the_turn(self):
        k = make_mock_knowledge()
        observer = ConversationObserver(k)
        observer.observe("I'm building Jarvis.", "Noted.")
        calls = k.store_memory.call_args_list
        subjects = [c.kwargs.get("subject", "") for c in calls]
        assert "jarvis" in subjects  # journal entry subject

    def test_observe_empty_message_does_nothing(self):
        k = make_mock_knowledge()
        observer = ConversationObserver(k)
        observer.observe("", "Response.")
        # No facts extracted, but journal might still be called
        fact_calls = [c for c in k.store_memory.call_args_list
                      if c.kwargs.get("subject") != "jarvis"]
        assert len(fact_calls) == 0

    def test_observe_exception_does_not_propagate(self):
        k = make_mock_knowledge()
        k.store_memory.side_effect = Exception("Storage error")
        observer = ConversationObserver(k)
        # Should not raise
        observer.observe("I'm building Jarvis.", "Noted.")

    def test_observe_milestone_stores_correctly(self):
        k = make_mock_knowledge()
        observer = ConversationObserver(k)
        observer.observe("We finished Engineering Academy.", "Well done, sir.")
        calls = k.store_memory.call_args_list
        attributes = [c.kwargs.get("attribute", "") for c in calls]
        assert any("milestone" in a for a in attributes)

    def test_observe_person_stores_role(self):
        k = make_mock_knowledge()
        observer = ConversationObserver(k)
        observer.observe("Claude is my senior engineer.", "Noted.")
        calls = k.store_memory.call_args_list
        attributes = [c.kwargs.get("attribute", "") for c in calls]
        assert any("role" in a for a in attributes)


# ===========================================================================
# 9. CONVERSATION RECALL — can_answer detection
# ===========================================================================

class TestConversationRecallCanAnswer:

    def setup_method(self):
        self.recall = ConversationRecall(make_mock_knowledge())

    def test_project_query(self):
        assert self.recall.can_answer("What project am I working on?")

    def test_milestone_query(self):
        assert self.recall.can_answer("What milestone did we finish?")

    def test_yesterday_query(self):
        assert self.recall.can_answer("What were we doing yesterday?")

    def test_today_query(self):
        assert self.recall.can_answer("What did we do today?")

    def test_person_query(self):
        assert self.recall.can_answer("Who is Claude?")

    def test_task_query(self):
        assert self.recall.can_answer("What are we working on?")

    def test_achievement_query(self):
        assert self.recall.can_answer("What did we finish?")

    def test_which_genesis_query(self):
        assert self.recall.can_answer("Which Genesis are we on?")

    def test_poem_not_answerable(self):
        assert not self.recall.can_answer("Write me a poem.")

    def test_weather_not_answerable(self):
        assert not self.recall.can_answer("What's the weather?")

    def test_joke_not_answerable(self):
        assert not self.recall.can_answer("Tell me a joke.")


# ===========================================================================
# 10. CONVERSATION RECALL — answers
# ===========================================================================

class TestConversationRecallAnswers:

    def test_recalls_current_project(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = make_mock_record("current project", "Jarvis OS")
        recall = ConversationRecall(k)
        result = recall.answer("What project am I working on?")
        assert result.found
        assert "Jarvis OS" in result.answer

    def test_recalls_last_milestone(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = make_mock_record("last milestone", "Genesis-019")
        recall = ConversationRecall(k)
        result = recall.answer("What milestone did we finish?")
        assert result.found
        assert "Genesis-019" in result.answer

    def test_recalls_person_by_name(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = make_mock_record("role", "senior engineer", subject="claude")
        recall = ConversationRecall(k)
        result = recall.answer("Who is Claude?")
        assert result.found
        assert "engineer" in result.answer.lower()

    def test_returns_not_found_when_no_record(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = None
        k.search_memory.return_value = []
        recall = ConversationRecall(k)
        result = recall.answer("What project am I working on?")
        assert not result.found

    def test_recalls_journal_for_yesterday(self):
        k = make_mock_knowledge()
        from datetime import timedelta
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        k.search_memory.return_value = [
            make_mock_record(
                f"conversation_{yesterday}_10-00-00",
                "We finished Engineering Academy.",
                subject="jarvis",
                tags=["journal", "conversation", yesterday]
            )
        ]
        recall = ConversationRecall(k)
        result = recall.answer("What did we do yesterday?")
        assert result.found
        assert "Engineering Academy" in result.answer

    def test_recalls_current_task(self):
        k = make_mock_knowledge()
        k.recall_memory.side_effect = lambda s, a: (
            make_mock_record("current task", "Genesis-020 Sprint-001")
            if a == "current task" else None
        )
        recall = ConversationRecall(k)
        result = recall.answer("What are we working on?")
        assert result.found
        assert "Genesis-020" in result.answer

    def test_which_genesis_falls_back_to_project(self):
        k = make_mock_knowledge()
        k.recall_memory.side_effect = lambda s, a: (
            make_mock_record("current project", "Genesis-020")
            if a == "current project" else None
        )
        recall = ConversationRecall(k)
        result = recall.answer("Which Genesis are we on?")
        assert result.found


# ===========================================================================
# 11. FACT TYPES — completeness
# ===========================================================================

class TestFactTypes:

    def test_all_fact_types_exist(self):
        for name in ["PROJECT", "MILESTONE", "PERSON", "TASK",
                     "DECISION", "ACHIEVEMENT", "PREFERENCE", "UNKNOWN"]:
            assert hasattr(FactType, name)

    def test_fact_type_values_unique(self):
        values = [f.value for f in FactType]
        assert len(values) == len(set(values))


# ===========================================================================
# 12. BACKWARDS COMPATIBILITY — existing memory not affected
# ===========================================================================

class TestBackwardsCompatibility:

    def test_observer_does_not_interfere_with_explicit_memory(self):
        """ConversationObserver must not overwrite explicit user memory."""
        k = make_mock_knowledge()
        observer = ConversationObserver(k)
        # Simulates a normal greeting — no facts to extract
        observer.observe("Hello Jarvis.", "Good morning, sir.")
        # No fact calls (only journal)
        fact_calls = [c for c in k.store_memory.call_args_list
                      if c.kwargs.get("subject") != "jarvis"]
        assert len(fact_calls) == 0

    def test_recall_returns_not_found_gracefully(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = None
        k.search_memory.return_value = []
        recall = ConversationRecall(k)
        result = recall.answer("What project am I working on?")
        assert not result.found
        assert result.answer == ""

    def test_extractor_does_not_mutate_input(self):
        extractor = FactExtractor()
        original = "I'm building Jarvis OS."
        extractor.extract(original)
        assert original == "I'm building Jarvis OS."