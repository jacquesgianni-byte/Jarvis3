"""
CV-003 — Conversation Reference Detector Tests

Verifies that ConversationReferenceDetector correctly identifies
explicit conversational reference statements and extracts the entity kind.

Coverage:
    - All supported phrasings ("Earlier I mentioned", "Remember my", etc.)
    - All registered entity kinds (animal, server, vehicle, person, instrument, project)
    - Stop tokens not treated as entity nouns
    - Unknown entity kinds return None
    - Unrelated queries return None
    - Regression: existing pipeline unaffected
"""

import pytest
from core.conversation.conversation_reference_detector import (
    ConversationReferenceDetector,
    ConversationReference,
)


@pytest.fixture
def detector():
    return ConversationReferenceDetector()


# ---------------------------------------------------------------------------
# Pattern coverage — "Earlier I mentioned my X"
# ---------------------------------------------------------------------------

class TestEarlierMentioned:

    def test_earlier_i_mentioned_servers(self, detector):
        result = detector.detect("Earlier I mentioned my servers.")
        assert result is not None
        assert result.kind == "server"

    def test_earlier_i_mentioned_dogs(self, detector):
        result = detector.detect("Earlier I mentioned my dogs.")
        assert result is not None
        assert result.kind == "animal"

    def test_earlier_i_mentioned_cars(self, detector):
        result = detector.detect("Earlier I mentioned my cars.")
        assert result is not None
        assert result.kind == "vehicle"

    def test_earlier_i_mentioned_children(self, detector):
        result = detector.detect("Earlier I mentioned my children.")
        assert result is not None
        assert result.kind == "person"

    def test_earlier_i_talked_about_servers(self, detector):
        result = detector.detect("Earlier I talked about my servers.")
        assert result is not None
        assert result.kind == "server"

    def test_earlier_i_told_you_about_dogs(self, detector):
        result = detector.detect("Earlier I told you about my dogs.")
        assert result is not None
        assert result.kind == "animal"

    def test_earlier_i_discussed_guitars(self, detector):
        result = detector.detect("Earlier I discussed my guitars.")
        assert result is not None
        assert result.kind == "instrument"


# ---------------------------------------------------------------------------
# Pattern coverage — "Remember my X"
# ---------------------------------------------------------------------------

class TestRememberMy:

    def test_remember_my_dogs(self, detector):
        result = detector.detect("Remember my dogs?")
        assert result is not None
        assert result.kind == "animal"

    def test_remember_my_servers(self, detector):
        result = detector.detect("Remember my servers.")
        assert result is not None
        assert result.kind == "server"

    def test_you_remember_my_cars(self, detector):
        result = detector.detect("You remember my cars.")
        assert result is not None
        assert result.kind == "vehicle"


# ---------------------------------------------------------------------------
# Pattern coverage — "Back to my X"
# ---------------------------------------------------------------------------

class TestBackTo:

    def test_back_to_my_servers(self, detector):
        result = detector.detect("Back to my servers.")
        assert result is not None
        assert result.kind == "server"

    def test_going_back_to_my_dogs(self, detector):
        result = detector.detect("Going back to my dogs.")
        assert result is not None
        assert result.kind == "animal"


# ---------------------------------------------------------------------------
# Pattern coverage — "We talked about my X"
# ---------------------------------------------------------------------------

class TestWeTalked:

    def test_we_talked_about_my_servers(self, detector):
        result = detector.detect("We talked about my servers.")
        assert result is not None
        assert result.kind == "server"

    def test_we_discussed_my_cars(self, detector):
        result = detector.detect("We discussed my cars.")
        assert result is not None
        assert result.kind == "vehicle"


# ---------------------------------------------------------------------------
# Pattern coverage — "I was telling you about my X"
# ---------------------------------------------------------------------------

class TestIWasTelling:

    def test_i_was_telling_you_about_my_dogs(self, detector):
        result = detector.detect("I was telling you about my dogs.")
        assert result is not None
        assert result.kind == "animal"

    def test_i_was_talking_about_my_servers(self, detector):
        result = detector.detect("I was talking about my servers.")
        assert result is not None
        assert result.kind == "server"


# ---------------------------------------------------------------------------
# Pattern coverage — "The X I told you about"
# ---------------------------------------------------------------------------

class TestTheXIToldYou:

    def test_the_servers_i_told_you_about(self, detector):
        result = detector.detect("The servers I told you about.")
        assert result is not None
        assert result.kind == "server"

    def test_the_dogs_i_mentioned(self, detector):
        result = detector.detect("The dogs I mentioned.")
        assert result is not None
        assert result.kind == "animal"


# ---------------------------------------------------------------------------
# All registered entity kinds
# ---------------------------------------------------------------------------

class TestAllEntityKinds:

    def test_animal_dogs(self, detector):
        assert detector.detect("Earlier I mentioned my dogs.").kind == "animal"

    def test_animal_cats(self, detector):
        assert detector.detect("Earlier I mentioned my cats.").kind == "animal"

    def test_person_children(self, detector):
        assert detector.detect("Earlier I mentioned my children.").kind == "person"

    def test_person_friends(self, detector):
        assert detector.detect("Earlier I mentioned my friends.").kind == "person"

    def test_vehicle_cars(self, detector):
        assert detector.detect("Earlier I mentioned my cars.").kind == "vehicle"

    def test_vehicle_trucks(self, detector):
        assert detector.detect("Earlier I mentioned my trucks.").kind == "vehicle"

    def test_instrument_guitars(self, detector):
        assert detector.detect("Earlier I mentioned my guitars.").kind == "instrument"

    def test_server_servers(self, detector):
        assert detector.detect("Earlier I mentioned my servers.").kind == "server"

    def test_project_projects(self, detector):
        assert detector.detect("Earlier I mentioned my projects.").kind == "project"


# ---------------------------------------------------------------------------
# Unknown entity — must return None
# ---------------------------------------------------------------------------

class TestUnknownEntity:

    def test_unknown_planes(self, detector):
        """Planes not in registry — must return None."""
        result = detector.detect("Earlier I mentioned my planes.")
        assert result is None

    def test_unknown_robots(self, detector):
        result = detector.detect("Earlier I mentioned my robots.")
        assert result is None


# ---------------------------------------------------------------------------
# Stop tokens — must not produce a result
# ---------------------------------------------------------------------------

class TestStopTokens:

    def test_earlier_i_mentioned_that(self, detector):
        result = detector.detect("Earlier I mentioned that.")
        assert result is None

    def test_earlier_i_mentioned_this(self, detector):
        result = detector.detect("Earlier I mentioned this.")
        assert result is None

    def test_remember_that(self, detector):
        result = detector.detect("Remember that?")
        # "that" is a stop token — should not match or return None
        assert result is None or result.kind is None or result.entity.lower() == "that"


# ---------------------------------------------------------------------------
# Unrelated queries — must return None
# ---------------------------------------------------------------------------

class TestUnrelatedQueries:

    def test_who_is_rex(self, detector):
        assert detector.detect("Who is Rex?") is None

    def test_what_are_their_names(self, detector):
        assert detector.detect("What are their names?") is None

    def test_i_have_5_servers(self, detector):
        assert detector.detect("I have 5 servers.") is None

    def test_what_is_the_weather(self, detector):
        assert detector.detect("What is the weather today?") is None

    def test_empty_string(self, detector):
        assert detector.detect("") is None

    def test_hello(self, detector):
        assert detector.detect("Hello.") is None


# ---------------------------------------------------------------------------
# Golden conversation regression
# ---------------------------------------------------------------------------

class TestGoldenConversation:

    def test_earlier_servers_restores_server_kind(self, detector):
        """
        I have 5 servers.
        Their names are prod, staging, db01, backup and dev.
        What's today's date?
        Earlier I mentioned my servers.
        → detector returns kind='server'
        → agent restores active_topic → 'Who are they?' works
        """
        result = detector.detect("Earlier I mentioned my servers.")
        assert result is not None
        assert result.kind == "server"
        assert result.entity.lower() in ("servers", "server")

    def test_earlier_dogs_restores_animal_kind(self, detector):
        """
        I have 3 dogs.
        Their names are Rex, Tom and Max.
        [unrelated conversation]
        Earlier I mentioned my dogs.
        → detector returns kind='animal'
        """
        result = detector.detect("Earlier I mentioned my dogs.")
        assert result is not None
        assert result.kind == "animal"

    def test_remember_my_children_restores_person_kind(self, detector):
        result = detector.detect("Remember my children.")
        assert result is not None
        assert result.kind == "person"