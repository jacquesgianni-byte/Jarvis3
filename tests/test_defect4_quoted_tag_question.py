"""
Regression tests for Defect #4 — S14 quoted tag-question guard.

Proves that detect_declaration() correctly rejects tag questions
even when the UI wraps the message in surrounding quote characters.
"""
import unittest
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from core.conversation.entity_group_registry import EntityGroupRegistry


class TestDefect4QuotedTagQuestion(unittest.TestCase):
    """S14: tag questions wrapped in quotes must not fire detect_declaration."""

    def setUp(self):
        self.registry = EntityGroupRegistry()

    def test_s14_quoted_dont_i(self):
        """S14 exact reproduction: quoted tag question must not store as fact."""
        result = self.registry.detect_declaration('"I have two dogs, don\'t I?"')
        self.assertIsNone(
            result,
            f"Quoted tag question must not be detected as declaration. Got: {result}"
        )

    def test_unquoted_dont_i(self):
        """Unquoted tag question must also not fire."""
        result = self.registry.detect_declaration("I have two dogs, don't I?")
        self.assertIsNone(
            result,
            f"Unquoted tag question must not be detected as declaration. Got: {result}"
        )

    def test_quoted_right(self):
        """'\"I have two dogs, right?\"' must not fire."""
        result = self.registry.detect_declaration('"I have two dogs, right?"')
        self.assertIsNone(result, f"Got: {result}")

    def test_quoted_havent_i(self):
        """'\"I have two dogs, haven\'t I?\"' must not fire."""
        result = self.registry.detect_declaration('"I have two dogs, haven\'t I?"')
        self.assertIsNone(result, f"Got: {result}")

    def test_curly_quotes_dont_i(self):
        """Curly-quoted variant must not fire."""
        result = self.registry.detect_declaration('\u201cI have two dogs, don\u2019t I?\u201d')
        self.assertIsNone(result, f"Curly-quoted tag question must not fire. Got: {result}")

    def test_plain_declaration_still_fires(self):
        """R1: plain 'I have two dogs.' must still be detected."""
        result = self.registry.detect_declaration("I have two dogs.")
        self.assertIsNotNone(
            result,
            "Plain declaration must still be detected as a group declaration"
        )
        self.assertEqual(result.kind, "animal")
        self.assertEqual(result.count, 2)

    def test_quoted_plain_declaration_still_fires(self):
        """'\"I have two dogs.\"' (quoted but not a question) must still fire."""
        result = self.registry.detect_declaration('"I have two dogs."')
        self.assertIsNotNone(
            result,
            "Quoted plain declaration must still be detected. Got None."
        )

    def test_three_cats_still_fires(self):
        """'I have three cats.' must still be detected."""
        result = self.registry.detect_declaration("I have three cats.")
        self.assertIsNotNone(result, "Three cats declaration must still fire.")
        self.assertEqual(result.kind, "animal")


if __name__ == "__main__":
    unittest.main(verbosity=2)
