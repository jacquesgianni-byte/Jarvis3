"""
Genesis-026 Sprint-001 — Conversational Coverage Expansion Tests

Verifies that multiple natural phrasings resolve to the same RecallRequest.
All tests are entity-agnostic — they work for any EntityGroup kind.

Coverage:
  - Names slot: canonical + 7 paraphrase variants
  - Colours slot: 5 variants
  - Ages slot: 4 variants
  - Breeds slot: 2 variants
  - Roles slot: 2 variants
  - No entity-specific logic introduced
  - Golden conversations unchanged
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.contextual_recall_engine import ContextualRecallEngine, RecallRequest
from core.conversation.session_context import SessionContext


def make_session(active_topic: str) -> SessionContext:
    s = SessionContext()
    s.set_topic(active_topic, raw=active_topic)
    return s


def resolve(query: str, active_topic: str) -> str | None:
    """Helper — resolve query and return attribute or None."""
    engine = ContextualRecallEngine()
    session = make_session(active_topic)
    req = engine.resolve(query, session)
    return req.attribute if req else None


# ===========================================================================
# 1. NAMES slot — all phrasings resolve to "pet names" for animals
# ===========================================================================

class TestNamesSlot:

    def test_canonical_what_are_their_names(self):
        assert resolve("What are their names?", "2 dogs") == "pet names"

    def test_who_are_they(self):
        assert resolve("Who are they?", "2 dogs") == "pet names"

    def test_what_are_they_called(self):
        assert resolve("What are they called?", "2 dogs") == "pet names"

    def test_what_did_i_call_them(self):
        assert resolve("What did I call them?", "2 dogs") == "pet names"

    def test_remind_me_of_their_names(self):
        assert resolve("Remind me of their names.", "2 dogs") == "pet names"

    def test_tell_me_their_names(self):
        assert resolve("Tell me their names.", "2 dogs") == "pet names"

    def test_tell_me_their_names_again(self):
        assert resolve("Tell me their names again.", "2 dogs") == "pet names"

    def test_can_you_tell_me_their_names(self):
        assert resolve("Can you tell me their names?", "2 dogs") == "pet names"

    def test_which_names_did_i_give_them(self):
        assert resolve("Which names did I give them?", "2 dogs") == "pet names"

    def test_what_names_did_i_give_them(self):
        assert resolve("What names did I give them?", "2 dogs") == "pet names"

    def test_what_were_their_names_again(self):
        assert resolve("What were their names again?", "2 dogs") == "pet names"

    def test_what_are_my_dogs_called(self):
        assert resolve("What are my dogs called?", "2 dogs") == "pet names"

    def test_what_did_i_name_them(self):
        assert resolve("What did I name them?", "2 dogs") == "pet names"

    def test_remind_me_what_theyre_called(self):
        assert resolve("Remind me what they're called.", "2 dogs") == "pet names"


# ===========================================================================
# 2. NAMES slot — generic across entity types
# ===========================================================================

class TestNamesSlotGeneric:

    def test_children_names(self):
        assert resolve("What are their names?", "2 children") == "people names"

    def test_guitars_names(self):
        assert resolve("What are they called?", "3 guitars") == "instrument names"

    def test_servers_names(self):
        assert resolve("What are their names?", "5 servers") == "server names"

    def test_who_are_they_cats(self):
        assert resolve("Who are they?", "3 cats") == "pet names"

    def test_who_are_they_employees(self):
        assert resolve("Who are they?", "3 employees") == "people names"


# ===========================================================================
# 3. COLOURS slot
# ===========================================================================

class TestColoursSlot:

    def test_what_colour_are_they(self):
        assert resolve("What colour are they?", "2 dogs") == "pet colours"

    def test_what_colors_are_they(self):
        assert resolve("What colors are they?", "2 dogs") == "pet colours"

    def test_what_are_their_colours(self):
        assert resolve("What are their colours?", "2 dogs") == "pet colours"

    def test_what_are_their_colors(self):
        assert resolve("What are their colors?", "2 dogs") == "pet colours"

    def test_what_do_they_look_like(self):
        assert resolve("What do they look like?", "2 dogs") == "pet colours"

    def test_describe_them(self):
        assert resolve("Describe them.", "2 dogs") == "pet colours"


# ===========================================================================
# 4. AGES slot
# ===========================================================================

class TestAgesSlot:

    def test_how_old_are_they(self):
        assert resolve("How old are they?", "2 dogs") == "pet ages"

    def test_what_are_their_ages(self):
        assert resolve("What are their ages?", "2 dogs") == "pet ages"

    def test_how_old_were_they(self):
        assert resolve("How old were they again?", "2 dogs") == "pet ages"

    def test_tell_me_their_ages(self):
        assert resolve("Tell me their ages.", "2 dogs") == "pet ages"

    def test_what_ages_are_they(self):
        assert resolve("What ages are they?", "2 dogs") == "pet ages"


# ===========================================================================
# 5. BREEDS slot
# ===========================================================================

class TestBreedsSlot:

    def test_what_breed_are_they(self):
        assert resolve("What breed are they?", "2 dogs") == "pet breeds"

    def test_what_are_their_breeds(self):
        assert resolve("What are their breeds?", "2 dogs") == "pet breeds"


# ===========================================================================
# 6. ROLES slot
# ===========================================================================

class TestRolesSlot:

    def test_what_are_their_roles(self):
        assert resolve("What are their roles?", "5 servers") == "group:server:roles"

    def test_what_do_they_do(self):
        assert resolve("What do they do?", "5 servers") == "group:server:roles"


# ===========================================================================
# 7. can_answer() coverage
# ===========================================================================

class TestCanAnswer:

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_who_are_they_with_topic(self):
        s = make_session("2 dogs")
        assert self.engine.can_answer("Who are they?", s)

    def test_what_did_i_call_them_with_topic(self):
        s = make_session("2 dogs")
        assert self.engine.can_answer("What did I call them?", s)

    def test_how_old_are_they_with_topic(self):
        s = make_session("2 dogs")
        assert self.engine.can_answer("How old are they?", s)

    def test_describe_them_with_topic(self):
        s = make_session("2 dogs")
        assert self.engine.can_answer("Describe them.", s)

    def test_no_topic_returns_false(self):
        s = SessionContext()
        assert not self.engine.can_answer("Who are they?", s)

    def test_unrelated_query_returns_false(self):
        s = make_session("2 dogs")
        assert not self.engine.can_answer("What is the weather?", s)


# ===========================================================================
# 8. Golden conversation parity (must not regress)
# ===========================================================================

class TestGoldenConversationParity:

    def test_gt1_who_are_rex_and_tom_not_intercepted(self):
        """GT1: 'Who are Rex and Tom?' should NOT go through ContextualRecallEngine."""
        engine = ContextualRecallEngine()
        s = make_session("2 dogs")
        assert not engine.can_answer("Who are Rex and Tom?", s)

    def test_gt2_what_are_their_names_intercepted(self):
        """GT2: 'What are their names?' SHOULD go through ContextualRecallEngine."""
        engine = ContextualRecallEngine()
        s = make_session("3 cats")
        assert engine.can_answer("What are their names?", s)

    def test_gt2_resolves_to_pet_names(self):
        assert resolve("What are their names?", "3 cats") == "pet names"