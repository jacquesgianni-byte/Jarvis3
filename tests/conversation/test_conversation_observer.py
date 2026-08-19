"""
Tests for ConversationObserver — Genesis-052 Sprint-001

Verifies that EVENT facts use attribute:{resolved_date} as their
uniqueness key so the same activity on different days produces separate
records rather than overwriting earlier occurrences.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from core.conversation.conversation_observer import ConversationObserver
from core.conversation.fact_extractor import ExtractedFact, FactType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event_fact(attribute: str, value: str, resolved_date: str | None) -> ExtractedFact:
    """Build a minimal EVENT ExtractedFact with the given temporal context."""
    temporal_ctx: dict = {}
    if resolved_date:
        temporal_ctx["resolved_date"] = resolved_date
    return ExtractedFact(
        fact_type=FactType.EVENT,
        subject="user",
        attribute=attribute,
        value=value,
        metadata={"temporal_ctx": temporal_ctx},
    )


def _make_plain_fact(fact_type: FactType, attribute: str, value: str) -> ExtractedFact:
    """Build a minimal non-EVENT ExtractedFact."""
    return ExtractedFact(
        fact_type=fact_type,
        subject="user",
        attribute=attribute,
        value=value,
    )


def _observer_with_facts(facts: list[ExtractedFact]) -> tuple[ConversationObserver, MagicMock]:
    """
    Return a ConversationObserver whose FactExtractor always yields `facts`,
    and a MagicMock KnowledgeEngine to inspect store_memory calls.
    """
    knowledge = MagicMock()
    observer = ConversationObserver(knowledge=knowledge)

    with patch.object(observer._extractor, "extract", return_value=facts):
        observer.observe("stub message", "stub response")

    return observer, knowledge


# ---------------------------------------------------------------------------
# Genesis-052 Sprint-001 — EVENT date-scoping tests
# ---------------------------------------------------------------------------

class TestEventAttributeDateScoping:
    """Same activity on different dates must produce separate records."""

    def test_same_activity_different_dates_produces_two_calls(self):
        """
        'met client morning' on 2026-08-15 and 2026-08-18 must be stored
        with different attribute keys so neither overwrites the other.
        """
        fact_aug15 = _make_event_fact("met client morning", "I met the client this morning", "2026-08-15")
        fact_aug18 = _make_event_fact("met client morning", "I met the client this morning", "2026-08-18")

        knowledge = MagicMock()
        observer = ConversationObserver(knowledge=knowledge)

        # First day
        with patch.object(observer._extractor, "extract", return_value=[fact_aug15]):
            observer.observe("I met the client this morning", "Got it.")

        # Second day
        with patch.object(observer._extractor, "extract", return_value=[fact_aug18]):
            observer.observe("I met the client this morning", "Got it.")

        # Collect all attribute values passed to store_memory
        attributes = [
            c.kwargs.get("attribute") or c.args[2]
            for c in knowledge.store_memory.call_args_list
            if (c.kwargs.get("subject") or c.args[0]) == "user"
        ]

        assert "met client morning:2026-08-15" in attributes, (
            "Expected Aug-15 event to be stored with date-scoped key"
        )
        assert "met client morning:2026-08-18" in attributes, (
            "Expected Aug-18 event to be stored with date-scoped key"
        )

    def test_same_activity_same_date_produces_one_key(self):
        """
        The same statement twice on the same day should produce the same
        attribute key — deduplication is handled by KnowledgeEngine.update_memory().
        """
        fact = _make_event_fact("met client morning", "I met the client this morning", "2026-08-18")

        knowledge = MagicMock()
        observer = ConversationObserver(knowledge=knowledge)

        for _ in range(2):
            with patch.object(observer._extractor, "extract", return_value=[fact]):
                observer.observe("I met the client this morning", "Got it.")

        user_attributes = [
            c.kwargs.get("attribute") or c.args[2]
            for c in knowledge.store_memory.call_args_list
            if (c.kwargs.get("subject") or c.args[0]) == "user"
        ]

        # Both calls must use the identical key — KnowledgeEngine deduplicates
        assert all(a == "met client morning:2026-08-18" for a in user_attributes), (
            f"Expected identical keys for same-day event, got: {user_attributes}"
        )

    def test_desktop_failure_aug15_survives_aug18(self):
        """
        Regression: Aug-15 'met client' record must not be overwritten when
        Aug-18 'met client' is stored. Each call must use its own dated key.
        """
        fact_aug15 = _make_event_fact("met client morning", "I met the client this morning", "2026-08-15")
        fact_aug18 = _make_event_fact("met client morning", "I met the client this morning", "2026-08-18")

        knowledge = MagicMock()
        observer = ConversationObserver(knowledge=knowledge)

        with patch.object(observer._extractor, "extract", return_value=[fact_aug15]):
            observer.observe("I met the client this morning", "Got it.")

        with patch.object(observer._extractor, "extract", return_value=[fact_aug18]):
            observer.observe("I met the client this morning", "Got it.")

        user_calls = [
            c for c in knowledge.store_memory.call_args_list
            if (c.kwargs.get("subject") or c.args[0]) == "user"
        ]
        assert len(user_calls) == 2, (
            f"Expected 2 store_memory calls for user (one per date), got {len(user_calls)}"
        )

        attributes = {c.kwargs.get("attribute") or c.args[2] for c in user_calls}
        assert "met client morning:2026-08-15" in attributes
        assert "met client morning:2026-08-18" in attributes

    def test_shed_saturday_and_sunday_produce_two_records(self):
        """
        'finished shed last Saturday' and 'finished shed last Sunday'
        must produce two separate dated attribute keys.
        """
        fact_sat = _make_event_fact("finished shed saturday", "I finished the shed last Saturday", "2026-08-15")
        fact_sun = _make_event_fact("finished shed sunday", "I finished the shed last Sunday", "2026-08-16")

        knowledge = MagicMock()
        observer = ConversationObserver(knowledge=knowledge)

        with patch.object(observer._extractor, "extract", return_value=[fact_sat]):
            observer.observe("I finished the shed last Saturday", "Got it.")

        with patch.object(observer._extractor, "extract", return_value=[fact_sun]):
            observer.observe("I finished the shed last Sunday", "Got it.")

        user_attributes = {
            c.kwargs.get("attribute") or c.args[2]
            for c in knowledge.store_memory.call_args_list
            if (c.kwargs.get("subject") or c.args[0]) == "user"
        }

        assert "finished shed saturday:2026-08-15" in user_attributes
        assert "finished shed sunday:2026-08-16" in user_attributes
        assert len(user_attributes) == 2, (
            f"Expected 2 distinct attribute keys, got: {user_attributes}"
        )

    def test_event_without_resolved_date_uses_bare_attribute(self):
        """
        If temporal context has no resolved_date, the bare attribute is used.
        No colon or None should be appended.
        """
        fact = _make_event_fact("met client morning", "I met the client this morning", resolved_date=None)

        _, knowledge = _observer_with_facts([fact])

        user_calls = [
            c for c in knowledge.store_memory.call_args_list
            if (c.kwargs.get("subject") or c.args[0]) == "user"
        ]
        assert len(user_calls) == 1
        stored_attr = user_calls[0].kwargs.get("attribute") or user_calls[0].args[2]
        assert stored_attr == "met client morning", (
            f"Expected bare attribute without date suffix, got: {stored_attr!r}"
        )
        assert ":" not in stored_attr, "No colon should appear when resolved_date is absent"


# ---------------------------------------------------------------------------
# Ordinary facts must be completely unaffected
# ---------------------------------------------------------------------------

class TestOrdinaryFactsUnchanged:
    """Non-EVENT facts must continue to use their bare attribute key."""

    @pytest.mark.parametrize("fact_type,attribute,value", [
        (FactType.PROJECT,     "current project",  "Jarvis OS"),
        (FactType.MILESTONE,   "milestone",        "Genesis-051"),
        (FactType.PERSON,      "role",             "senior engineer"),
        (FactType.TASK,        "current task",     "Sprint-001"),
        (FactType.DECISION,    "decision",         "use Flask"),
        (FactType.ACHIEVEMENT, "achievement",      "529 tests passed"),
        (FactType.PREFERENCE,  "preference",       "dark mode"),
        (FactType.WORKPLACE,   "workplace",        "Academy of Healthcare"),
    ])
    def test_non_event_fact_uses_bare_attribute(self, fact_type, attribute, value):
        """Every non-EVENT fact type must be stored with its original attribute key."""
        fact = _make_plain_fact(fact_type, attribute, value)
        _, knowledge = _observer_with_facts([fact])

        user_calls = [
            c for c in knowledge.store_memory.call_args_list
            if (c.kwargs.get("subject") or c.args[0]) == "user"
        ]
        assert len(user_calls) == 1
        stored_attr = user_calls[0].kwargs.get("attribute") or user_calls[0].args[2]
        assert stored_attr == attribute, (
            f"Expected bare attribute {attribute!r} for {fact_type}, got {stored_attr!r}"
        )
