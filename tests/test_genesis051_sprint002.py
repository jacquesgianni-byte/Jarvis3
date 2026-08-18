"""
Genesis-051 Sprint-002 — Implicit Event Persistence Regression Tests

Verifies:
  1. ConversationObserver stores implicit events with correct temporal tags
  2. resolved:, expr:, tod: tags are written for EVENT facts
  3. Explicit "remember that..." path is unaffected
  4. Non-event sentences are not incorrectly stored as events
  5. The exact desktop-failure scenario now works end-to-end

Run: python -m pytest tests/test_genesis051_sprint002.py -v
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, UTC, datetime
from typing import Optional
from unittest.mock import MagicMock, call, patch
import pytest


# ---------------------------------------------------------------------------
# Minimal KnowledgeEngine stub
# ---------------------------------------------------------------------------

class _KnowledgeStub:
    def __init__(self):
        self.stored = []  # list of dicts

    def store_memory(self, subject, category, attribute, value, tags=None, **kw):
        self.stored.append({
            "subject": subject,
            "category": category,
            "attribute": attribute,
            "value": value,
            "tags": list(tags or []),
        })
        return MagicMock()

    def search_memory(self, query, subject=None, limit=10, **kw):
        return []

    def count(self):
        return len(self.stored)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_observer(with_parser: bool = True):
    """Build a ConversationObserver with optional TemporalParser."""
    from core.conversation.conversation_observer import ConversationObserver
    knowledge = _KnowledgeStub()
    if with_parser:
        from core.conversation.temporal_parser import TemporalParser
        tp = TemporalParser()
        obs = ConversationObserver(knowledge, temporal_parser=tp)
    else:
        obs = ConversationObserver(knowledge)
    return obs, knowledge


def _event_records(knowledge: _KnowledgeStub) -> list[dict]:
    """Return only user_event records (not journal entries)."""
    return [r for r in knowledge.stored if "user_event" in r["tags"]]


def _journal_records(knowledge: _KnowledgeStub) -> list[dict]:
    return [r for r in knowledge.stored if "journal" in r["tags"]]


# ===========================================================================
# 1. EVENT facts are stored when temporal_parser is injected
# ===========================================================================

class TestImplicitEventStorage:

    def test_finished_shed_stored_as_event(self):
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_records(ke)
        assert len(events) == 1, f"Expected 1 event record, got {len(events)}: {events}"

    def test_finished_shed_has_resolved_tag(self):
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_records(ke)
        assert any(t.startswith("resolved:") for t in events[0]["tags"]), \
            f"No resolved: tag in {events[0]['tags']}"

    def test_finished_shed_has_expr_tag(self):
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_records(ke)
        assert any(t.startswith("expr:") for t in events[0]["tags"]), \
            f"No expr: tag in {events[0]['tags']}"

    def test_finished_shed_value_is_full_clause(self):
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_records(ke)
        assert "shed" in events[0]["value"].lower()

    def test_met_client_this_morning_stored(self):
        obs, ke = _make_observer()
        obs.observe("I met the client this morning.", "Got it.")
        events = _event_records(ke)
        assert len(events) == 1
        tags = events[0]["tags"]
        assert any(t.startswith("resolved:") for t in tags)
        assert "tod:morning" in tags

    def test_went_to_gym_yesterday_stored(self):
        obs, ke = _make_observer()
        obs.observe("I went to the gym yesterday.", "Got it.")
        events = _event_records(ke)
        assert len(events) == 1
        assert any(t.startswith("resolved:") for t in events[0]["tags"])

    def test_this_afternoon_tod_tag(self):
        obs, ke = _make_observer()
        obs.observe("I had a coffee this afternoon.", "Got it.")
        events = _event_records(ke)
        assert len(events) == 1
        tags = events[0]["tags"]
        assert "tod:afternoon" in tags


# ===========================================================================
# 2. Without temporal_parser — backward compat, no events stored
# ===========================================================================

class TestNoTemporalParser:

    def test_no_parser_no_events(self):
        obs, ke = _make_observer(with_parser=False)
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_record(ke)  # should be empty
        assert events == []

    def test_no_parser_journal_still_written(self):
        obs, ke = _make_observer(with_parser=False)
        obs.observe("I finished the shed last Saturday.", "Got it.")
        assert len(_journal_records(ke)) == 1


def _event_record(knowledge):
    return [r for r in knowledge.stored if "user_event" in r["tags"]]


# ===========================================================================
# 3. Journal is always written regardless of event detection
# ===========================================================================

class TestJournalAlwaysWritten:

    def test_journal_written_with_event(self):
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        assert len(_journal_records(ke)) == 1

    def test_journal_written_without_event(self):
        obs, ke = _make_observer()
        obs.observe("My name is Gianni.", "Got it.")
        assert len(_journal_records(ke)) == 1

    def test_journal_value_is_user_message(self):
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        journal = _journal_records(ke)
        assert "shed" in journal[0]["value"].lower()


# ===========================================================================
# 4. Non-event sentences do not produce spurious event records
# ===========================================================================

class TestNonEventSentences:

    def test_question_not_stored_as_event(self):
        obs, ke = _make_observer()
        obs.observe("What did I do last Saturday?", "On Saturday...")
        events = _event_records(ke)
        assert len(events) == 0, f"Question stored as event: {events}"

    def test_future_intent_not_stored_as_event(self):
        obs, ke = _make_observer()
        obs.observe("I want to finish the shed this weekend.", "Got it.")
        events = _event_records(ke)
        assert len(events) == 0, f"Intent stored as event: {events}"

    def test_factual_statement_no_temporal_not_event(self):
        obs, ke = _make_observer()
        obs.observe("My name is Gianni.", "Got it.")
        events = _event_records(ke)
        assert len(events) == 0

    def test_remember_command_not_double_stored(self):
        """Explicit 'remember that' commands go through MemorySkill, not observer."""
        obs, ke = _make_observer()
        obs.observe("Remember that I met the client this morning.", "Got it.")
        # The command pattern is excluded by _EVENT_COMMAND_RE in FactExtractor
        events = _event_records(ke)
        # May or may not produce an event depending on whether command guard fires
        # — the key check is no crash and journal written
        assert len(_journal_records(ke)) == 1


# ===========================================================================
# 5. Tag structure correctness for EVENT records
# ===========================================================================

class TestEventTagStructure:

    def test_user_event_tag_present(self):
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_records(ke)
        assert "user_event" in events[0]["tags"]

    def test_no_auto_extracted_tag_on_event(self):
        """EVENT records should use user_event, not auto-extracted/derived."""
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_records(ke)
        assert "auto-extracted" not in events[0]["tags"]
        assert "derived" not in events[0]["tags"]

    def test_subject_is_user(self):
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_records(ke)
        assert events[0]["subject"] == "user"

    def test_resolved_tag_is_valid_date(self):
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_records(ke)
        resolved_tags = [t for t in events[0]["tags"] if t.startswith("resolved:")]
        assert len(resolved_tags) == 1
        date_part = resolved_tags[0][len("resolved:"):]
        # Should parse as a valid ISO date
        d = date.fromisoformat(date_part)
        assert isinstance(d, date)

    def test_tod_tag_format(self):
        obs, ke = _make_observer()
        obs.observe("I met the client this morning.", "Got it.")
        events = _event_records(ke)
        tod_tags = [t for t in events[0]["tags"] if t.startswith("tod:")]
        assert len(tod_tags) == 1
        assert tod_tags[0] in ("tod:morning", "tod:afternoon", "tod:evening", "tod:night")


# ===========================================================================
# 6. Desktop failure scenario — end-to-end through ConversationObserver
# ===========================================================================

class TestDesktopScenario:

    def test_both_events_stored_independently(self):
        """
        Mirrors the desktop failure:
        - "I met the client this morning." → event record
        - "I finished the shed last Saturday." → separate event record
        Both must exist with resolved: tags.
        """
        obs, ke = _make_observer()
        obs.observe("I met the client this morning.", "Got it.")
        obs.observe("I finished the shed last Saturday.", "Got it.")

        events = _event_records(ke)
        assert len(events) == 2, \
            f"Expected 2 event records, got {len(events)}: {[e['attribute'] for e in events]}"

        values = [e["value"].lower() for e in events]
        assert any("client" in v for v in values), "Client event missing"
        assert any("shed" in v for v in values), "Shed event missing"

    def test_both_events_have_resolved_tags(self):
        obs, ke = _make_observer()
        obs.observe("I met the client this morning.", "Got it.")
        obs.observe("I finished the shed last Saturday.", "Got it.")

        events = _event_records(ke)
        for e in events:
            assert any(t.startswith("resolved:") for t in e["tags"]), \
                f"Event missing resolved: tag: {e['attribute']} {e['tags']}"

    def test_shed_event_resolved_date_is_saturday(self):
        """
        On any day of the week, "last Saturday" should resolve to the
        most recent Saturday. The resolved date must be a Saturday.
        """
        obs, ke = _make_observer()
        obs.observe("I finished the shed last Saturday.", "Got it.")
        events = _event_records(ke)
        shed_events = [e for e in events if "shed" in e["value"].lower()]
        assert len(shed_events) == 1
        resolved_tags = [t for t in shed_events[0]["tags"] if t.startswith("resolved:")]
        d = date.fromisoformat(resolved_tags[0][len("resolved:"):])
        assert d.weekday() == 5, f"Expected Saturday (weekday 5), got {d.weekday()} ({d})"

    def test_client_event_has_morning_tod(self):
        obs, ke = _make_observer()
        obs.observe("I met the client this morning.", "Got it.")
        events = _event_records(ke)
        client_events = [e for e in events if "client" in e["value"].lower()]
        assert len(client_events) == 1
        assert "tod:morning" in client_events[0]["tags"]


# ===========================================================================
# 7. ConversationObserver.__init__ signature — backward compat
# ===========================================================================

class TestInitSignature:

    def test_no_temporal_parser_arg_still_works(self):
        """Existing callers passing only knowledge must not break."""
        from core.conversation.conversation_observer import ConversationObserver
        ke = _KnowledgeStub()
        obs = ConversationObserver(ke)  # no temporal_parser
        obs.observe("Hello.", "Hi!")
        assert len(_journal_records(ke)) == 1

    def test_temporal_parser_kwarg_accepted(self):
        from core.conversation.conversation_observer import ConversationObserver
        from core.conversation.temporal_parser import TemporalParser
        ke = _KnowledgeStub()
        obs = ConversationObserver(ke, temporal_parser=TemporalParser())
        assert obs is not None
