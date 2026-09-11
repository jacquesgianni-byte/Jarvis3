"""
Regression tests for Defect #3 — S9 "Cindy-Lou Who" fix.

Proves that 'keep going' embedded in a sentence does not trigger
FollowUpResolver as a follow-up, preventing the AI from generating
nonsense like "Cindy-Lou Who" when last_topic is 'Who'.
"""
import unittest
from unittest.mock import MagicMock

from core.conversation.followup_resolver import FollowUpResolver, FollowUpResult


def _make_session(last_topic="Who", last_response="Your name is Gianni."):
    session = MagicMock()
    session.last_topic = last_topic
    session.last_response = last_response
    session.last_intent = "memory"
    return session


class TestDefect3KeepGoingGuard(unittest.TestCase):
    """S9: 'keep going' embedded in a sentence must not fire FollowUpResolver."""

    def test_wife_keep_going_not_followup(self):
        """S9 exact reproduction: must not fire as follow-up."""
        resolver = FollowUpResolver()
        session = _make_session(last_topic="Who")
        result = resolver.resolve(
            "My wife and I have been talking about the project. She thinks I should keep going.",
            session,
        )
        self.assertFalse(
            result.is_followup,
            f"S9: 'keep going' in sentence must not be a follow-up. "
            f"Got type={result.resolved_type!r} context={result.context_hint!r}"
        )

    def test_i_should_keep_going_not_followup(self):
        """'I should keep going' must not fire as follow-up."""
        resolver = FollowUpResolver()
        session = _make_session(last_topic="joke")
        result = resolver.resolve("I should keep going with this project.", session)
        self.assertFalse(
            result.is_followup,
            f"'I should keep going' must not be a follow-up. "
            f"Got type={result.resolved_type!r}"
        )

    def test_thinks_i_should_keep_going_not_followup(self):
        """Third-person 'keep going' must not fire."""
        resolver = FollowUpResolver()
        session = _make_session(last_topic="Who")
        result = resolver.resolve(
            "She thinks I should keep going.", session
        )
        self.assertFalse(
            result.is_followup,
            f"'She thinks I should keep going' must not be a follow-up. "
            f"Got type={result.resolved_type!r}"
        )

    def test_keep_going_standalone_not_followup(self):
        """Even standalone 'keep going' should not fire — removed from pattern."""
        resolver = FollowUpResolver()
        session = _make_session(last_topic="joke")
        result = resolver.resolve("keep going", session)
        self.assertFalse(
            result.is_followup,
            f"Standalone 'keep going' must not be a follow-up after removal. "
            f"Got type={result.resolved_type!r}"
        )

    def test_another_one_still_fires(self):
        """Regression: 'tell me another one' must still work."""
        resolver = FollowUpResolver()
        session = _make_session(last_topic="joke")
        result = resolver.resolve("tell me another one", session)
        self.assertTrue(
            result.is_followup,
            "'tell me another one' must still be detected as follow-up"
        )
        self.assertEqual(result.resolved_type, "another")

    def test_continue_still_fires_as_expand(self):
        """'continue' in _EXPAND_RE must still work for genuine expansion."""
        resolver = FollowUpResolver()
        session = _make_session(last_topic="space facts")
        result = resolver.resolve("continue", session)
        self.assertTrue(
            result.is_followup,
            "'continue' must still fire as expand follow-up"
        )
        self.assertEqual(result.resolved_type, "expand")

    def test_go_on_still_fires_as_expand(self):
        """'go on' in _EXPAND_RE must still work."""
        resolver = FollowUpResolver()
        session = _make_session(last_topic="story")
        result = resolver.resolve("go on", session)
        self.assertTrue(
            result.is_followup,
            "'go on' must still fire as expand follow-up"
        )
        self.assertEqual(result.resolved_type, "expand")


if __name__ == "__main__":
    unittest.main(verbosity=2)
