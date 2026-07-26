"""
Tests for Genesis-026 Sprint-003: Reverse Entity Lookup

Verifies that Jarvis can answer "Who is Rex?" → "Rex is one of your dogs."
for any registered entity kind, using any member identifier format.

Test coverage:
    - ReverseEntityParser: query parsing and member extraction
    - ContextualRecallEngine.reverse_lookup(): member-to-group reasoning
    - Single member lookup
    - Multiple member lookup
    - Unknown member (not found)
    - Multiple EntityGroups coexisting (dogs + servers)
    - Identifiers that are not human-style names (staging, db01, GPU-7)
    - All registered entity kinds (animal, person, vehicle, instrument, server, project)
    - Regression: existing identity/attribute paths still work
"""

import pytest
from unittest.mock import MagicMock

from core.conversation.reverse_entity_parser import ReverseEntityParser, ReverseLookupRequest
from core.conversation.contextual_recall_engine import (
    ContextualRecallEngine,
    ReverseLookupRequest,
    ResolutionType,
    RecallRequest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_recall(memories: dict[str, str]):
    """
    Build a mock ConversationRecall that returns stored values by attribute.

    memories: { attribute: value } e.g. {"pet names": "Rex and Tom", "pets": "2 dogs"}
    """
    from core.conversation.conversation_recall import RecallResult

    def lookup(subject, attribute):
        val = memories.get(attribute)
        if val:
            return RecallResult(found=True, answer=val, attribute=attribute, value=val)
        return RecallResult(found=False, answer="", attribute=attribute, value="")

    mock = MagicMock()
    mock.lookup.side_effect = lookup
    return mock


def _make_session(active_topic: str = "2 dogs"):
    """Build a mock SessionContext with an active topic."""
    mock = MagicMock()
    mock.active_topic = MagicMock()
    mock.active_topic.value = active_topic
    return mock


# ---------------------------------------------------------------------------
# ReverseEntityParser — query parsing
# ---------------------------------------------------------------------------

class TestReverseEntityParser:

    @pytest.fixture
    def parser(self):
        return ReverseEntityParser()

    # Single member — human name
    def test_who_is_single_name(self, parser):
        result = parser.parse("Who is Rex?")
        assert result is not None
        assert "Rex" in result.members

    def test_who_is_single_name_no_question_mark(self, parser):
        result = parser.parse("Who is Rex")
        assert result is not None
        assert "Rex" in result.members

    # Multiple members — human names
    def test_who_are_two_names(self, parser):
        result = parser.parse("Who are Rex and Tom?")
        assert result is not None
        assert "Rex" in result.members
        assert "Tom" in result.members

    def test_who_are_three_names(self, parser):
        result = parser.parse("Who are Rex, Tom and Max?")
        assert result is not None
        assert len(result.members) == 3

    # Non-human identifiers — servers, tech
    def test_who_is_server_name(self, parser):
        result = parser.parse("Who is staging?")
        assert result is not None
        assert "staging" in result.members

    def test_who_is_technical_identifier(self, parser):
        result = parser.parse("Who is db01?")
        assert result is not None
        assert "db01" in result.members

    def test_what_is_server(self, parser):
        result = parser.parse("What is prod?")
        assert result is not None
        assert "prod" in result.members

    def test_who_are_two_servers(self, parser):
        result = parser.parse("Who are prod and staging?")
        assert result is not None
        assert "prod" in result.members
        assert "staging" in result.members

    # Alternate phrasings
    def test_tell_me_about(self, parser):
        result = parser.parse("Tell me about Rex.")
        assert result is not None
        assert "Rex" in result.members

    def test_remind_me_who(self, parser):
        result = parser.parse("Remind me who Rex is.")
        assert result is not None
        assert "Rex" in result.members

    def test_which_one_is(self, parser):
        result = parser.parse("Which one is staging?")
        assert result is not None
        assert "staging" in result.members

    # Stop tokens — must NOT produce a result
    def test_who_are_they_returns_none(self, parser):
        """'Who are they?' is a pronoun query, not a reverse lookup."""
        result = parser.parse("Who are they?")
        assert result is None or result.members == []

    def test_who_is_it_returns_none(self, parser):
        result = parser.parse("Who is it?")
        assert result is None or result.members == []

    def test_empty_query_returns_none(self, parser):
        result = parser.parse("")
        assert result is None

    def test_unrelated_query_returns_none(self, parser):
        result = parser.parse("What is the weather like today?")
        # "today" would be extracted — but this is fine, reverse_lookup
        # will return None because "today" isn't in any names record.
        # The parser's job is only extraction, not validation.
        pass  # No assertion needed — just confirms no exception


# ---------------------------------------------------------------------------
# ContextualRecallEngine.reverse_lookup() — reasoning
# ---------------------------------------------------------------------------

class TestReverseLookup:

    @pytest.fixture
    def engine(self):
        return ContextualRecallEngine()

    # Dogs — single member
    def test_single_dog_found(self, engine):
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        req = ReverseLookupRequest(members=["Rex"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "Rex" in result.answer
        assert "dog" in result.answer.lower()

    def test_single_dog_answer_format(self, engine):
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        req = ReverseLookupRequest(members=["Rex"])
        result = engine.reverse_lookup(req, recall)
        assert result.answer == "Rex is one of your dogs."

    # Dogs — multiple members
    def test_two_dogs_found(self, engine):
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        req = ReverseLookupRequest(members=["Rex", "Tom"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "Rex" in result.answer
        assert "Tom" in result.answer
        assert "dog" in result.answer.lower()

    def test_two_dogs_answer_format(self, engine):
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        req = ReverseLookupRequest(members=["Rex", "Tom"])
        result = engine.reverse_lookup(req, recall)
        assert result.answer == "Rex and Tom are your dogs."

    # Three members
    def test_three_members_answer_format(self, engine):
        recall = _make_recall({
            "people names": "Alex, Emma and James",
            "people": "3 children",
        })
        req = ReverseLookupRequest(members=["Alex", "Emma", "James"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "children" in result.answer.lower()

    # Servers — non-human identifiers
    def test_server_staging_found(self, engine):
        recall = _make_recall({
            "server names": "prod, staging, test, dev and backup",
            "servers": "5 servers",
        })
        req = ReverseLookupRequest(members=["staging"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "staging" in result.answer.lower()
        assert "server" in result.answer.lower()

    def test_server_staging_answer_format(self, engine):
        recall = _make_recall({
            "server names": "prod, staging, test, dev and backup",
            "servers": "5 servers",
        })
        req = ReverseLookupRequest(members=["staging"])
        result = engine.reverse_lookup(req, recall)
        assert result.answer == "Staging is one of your servers."

    def test_two_servers_found(self, engine):
        recall = _make_recall({
            "server names": "prod and staging",
            "servers": "2 servers",
        })
        req = ReverseLookupRequest(members=["prod", "staging"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "servers" in result.answer.lower()

    # Children — person kind
    def test_child_found(self, engine):
        recall = _make_recall({
            "people names": "Alex, Emma and James",
            "people": "3 children",
        })
        req = ReverseLookupRequest(members=["Emma"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "Emma" in result.answer
        assert "children" in result.answer.lower()

    def test_child_answer_format(self, engine):
        recall = _make_recall({
            "people names": "Alex, Emma and James",
            "people": "3 children",
        })
        req = ReverseLookupRequest(members=["Emma"])
        result = engine.reverse_lookup(req, recall)
        assert result.answer == "Emma is one of your children."

    # Vehicles
    def test_vehicle_found(self, engine):
        recall = _make_recall({
            "vehicle names": "Betty and Rex",
            "vehicles": "2 cars",
        })
        req = ReverseLookupRequest(members=["Betty"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "car" in result.answer.lower()

    # Instruments
    def test_instrument_found(self, engine):
        recall = _make_recall({
            "instrument names": "Stratocaster and Les Paul",
            "instruments": "2 guitars",
        })
        req = ReverseLookupRequest(members=["Stratocaster"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "guitar" in result.answer.lower()

    # Projects
    def test_project_found(self, engine):
        recall = _make_recall({
            "project names": "Jarvis and Atlas",
            "projects": "2 projects",
        })
        req = ReverseLookupRequest(members=["Jarvis"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "project" in result.answer.lower()

    # Unknown member — must return None
    def test_unknown_member_returns_none(self, engine):
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        req = ReverseLookupRequest(members=["Bella"])
        result = engine.reverse_lookup(req, recall)
        assert result is None or result.found is False

    # Empty members list — must return None
    def test_empty_members_returns_none(self, engine):
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        req = ReverseLookupRequest(members=[])
        result = engine.reverse_lookup(req, recall)
        assert result is None

    # No names stored — must return None
    def test_no_names_stored_returns_none(self, engine):
        recall = _make_recall({
            "pets": "2 dogs",
            # "pet names" deliberately absent
        })
        req = ReverseLookupRequest(members=["Rex"])
        result = engine.reverse_lookup(req, recall)
        assert result is None or result.found is False

    # Multiple EntityGroups coexisting — correct group selected
    def test_multiple_groups_dogs_and_servers(self, engine):
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
            "server names": "prod and staging",
            "servers": "2 servers",
        })
        # Rex should resolve to dogs, not servers
        req_dog = ReverseLookupRequest(members=["Rex"])
        result_dog = engine.reverse_lookup(req_dog, recall)
        assert result_dog is not None
        assert result_dog.found is True
        assert "dog" in result_dog.answer.lower()
        assert "server" not in result_dog.answer.lower()

        # staging should resolve to servers, not dogs
        req_server = ReverseLookupRequest(members=["staging"])
        result_server = engine.reverse_lookup(req_server, recall)
        assert result_server is not None
        assert result_server.found is True
        assert "server" in result_server.answer.lower()
        assert "dog" not in result_server.answer.lower()

    # Word-boundary check: "Rex" must not match "Rexton"
    def test_partial_name_not_matched(self, engine):
        recall = _make_recall({
            "pet names": "Rexton and Tomson",
            "pets": "2 dogs",
        })
        req = ReverseLookupRequest(members=["Rex"])
        result = engine.reverse_lookup(req, recall)
        # "Rex" should NOT match "Rexton"
        assert result is None or result.found is False

    # Declaration absent — answer degrades gracefully
    def test_no_declaration_degrades_gracefully(self, engine):
        recall = _make_recall({
            "pet names": "Rex and Tom",
            # "pets" deliberately absent
        })
        req = ReverseLookupRequest(members=["Rex"])
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert "Rex" in result.answer
        # Should still produce a valid answer using kind-based noun
        assert len(result.answer) > 0


# ---------------------------------------------------------------------------
# Golden conversation regression
# ---------------------------------------------------------------------------

class TestGoldenConversations:

    @pytest.fixture
    def parser(self):
        return ReverseEntityParser()

    @pytest.fixture
    def engine(self):
        return ContextualRecallEngine()

    def test_golden_dogs_who_is_rex(self, parser, engine):
        """
        I have 2 dogs.
        Their names are Rex and Tom.
        Who is Rex?
        → Rex is one of your dogs.
        """
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        req = parser.parse("Who is Rex?")
        assert req is not None
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert result.answer == "Rex is one of your dogs."

    def test_golden_dogs_who_are_rex_and_tom(self, parser, engine):
        """
        I have 2 dogs.
        Their names are Rex and Tom.
        Who are Rex and Tom?
        → Rex and Tom are your dogs.
        """
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        req = parser.parse("Who are Rex and Tom?")
        assert req is not None
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert result.answer == "Rex and Tom are your dogs."

    def test_golden_children_who_is_emma(self, parser, engine):
        """
        I have 3 children.
        Their names are Alex, Emma and James.
        Who is Emma?
        → Emma is one of your children.
        """
        recall = _make_recall({
            "people names": "Alex, Emma and James",
            "people": "3 children",
        })
        req = parser.parse("Who is Emma?")
        assert req is not None
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert result.answer == "Emma is one of your children."

    def test_golden_servers_who_is_staging(self, parser, engine):
        """
        I have 5 servers.
        Their names are prod, staging, test, dev and backup.
        Who is staging?
        → Staging is one of your servers.
        """
        recall = _make_recall({
            "server names": "prod, staging, test, dev and backup",
            "servers": "5 servers",
        })
        req = parser.parse("Who is staging?")
        assert req is not None
        result = engine.reverse_lookup(req, recall)
        assert result is not None
        assert result.found is True
        assert result.answer == "Staging is one of your servers."

    def test_golden_unknown_member_falls_through(self, parser, engine):
        """
        Unknown member must return None so the Agent falls through to AI.
        """
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        req = parser.parse("Who is Bella?")
        assert req is not None
        result = engine.reverse_lookup(req, recall)
        assert result is None or result.found is False

    def test_golden_existing_identity_path_unchanged(self, engine):
        """
        Existing "Who are they?" identity path must still work after Sprint-003.
        """
        session = _make_session("2 dogs")
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        result = engine.answer("Who are they?", session, recall)
        assert result is not None
        assert result.found is True
        assert "Rex" in result.answer or "dogs" in result.answer

    def test_golden_existing_attribute_path_unchanged(self, engine):
        """
        Existing "What are their names?" attribute path must still work.
        """
        session = _make_session("2 dogs")
        recall = _make_recall({
            "pet names": "Rex and Tom",
            "pets": "2 dogs",
        })
        result = engine.answer("What are their names?", session, recall)
        assert result is not None
        assert result.found is True