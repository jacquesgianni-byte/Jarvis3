"""
Genesis-073 Defect #1 — Focused regression tests
FactExtractor._TASK_PATTERNS Pattern 2 fix

Run: python -m pytest tests/test_genesis073_defect1.py -v
"""
import sys
import pathlib
import unittest

# Ensure project root is on path
sys.path.insert(0, str(pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")))

from core.conversation.fact_extractor import FactExtractor, FactType


def _task_values(text: str) -> list[str]:
    """Extract TASK fact values from text. Returns empty list if none."""
    extractor = FactExtractor()
    facts = extractor.extract(text)
    return [f.value for f in facts if f.fact_type == FactType.TASK]


class TestTaskPatternFix(unittest.TestCase):
    """Pattern 2 in _TASK_PATTERNS must require explicit 'is'."""

    # --- Fix tests: these must NO LONGER produce a TASK fact ---

    def test_s2_travel_not_a_task(self):
        """S2: 'thinking about getting away next year' is not a task declaration."""
        result = _task_values(
            "I've been thinking about getting away next year, "
            "but I haven't decided where I want to go yet."
        )
        self.assertEqual(result, [],
            f"Expected no TASK fact, got: {result}")

    def test_next_year_temporal_not_a_task(self):
        """'Next year I want to travel' contains temporal 'next year', not a task."""
        result = _task_values("Next year I want to travel.")
        self.assertEqual(result, [],
            f"Expected no TASK fact, got: {result}")

    def test_next_time_not_a_task(self):
        """'Next time we should try...' is a suggestion, not a task declaration."""
        result = _task_values("Next time we should try a different approach.")
        self.assertEqual(result, [],
            f"Expected no TASK fact, got: {result}")

    def test_hoping_next_year_not_a_task(self):
        """'I'm hoping to do this next year' is an intention, not a task."""
        result = _task_values("I'm hoping to do this next year.")
        self.assertEqual(result, [],
            f"Expected no TASK fact, got: {result}")

    def test_next_month_not_a_task(self):
        """'Next month' is a temporal marker, not a task."""
        result = _task_values("I'm going to Melbourne next month.")
        self.assertEqual(result, [],
            f"Expected no TASK fact, got: {result}")

    # --- Regression tests: these must STILL produce a TASK fact ---

    def test_next_up_is_still_a_task(self):
        """'Next up is the deployment' is a legitimate task declaration."""
        result = _task_values("Next up is the deployment.")
        self.assertIn("the deployment", result,
            f"Expected 'the deployment' in TASK facts, got: {result}")

    def test_next_is_genesis_still_a_task(self):
        """'Next is Genesis-074' is a legitimate task declaration."""
        result = _task_values("Next is Genesis-074.")
        self.assertIn("Genesis-074", result,
            f"Expected 'Genesis-074' in TASK facts, got: {result}")

    def test_next_up_is_sprint_still_a_task(self):
        """'Next up is Sprint-001' is a legitimate task declaration."""
        result = _task_values("Next up is Genesis-074 Sprint-001.")
        self.assertTrue(any("Sprint-001" in v or "Genesis-074" in v for v in result),
            f"Expected sprint reference in TASK facts, got: {result}")

    def test_im_starting_still_a_task(self):
        """'I'm starting Genesis-074' is a legitimate task declaration."""
        result = _task_values("I'm starting Genesis-074.")
        self.assertTrue(len(result) > 0,
            f"Expected TASK fact for 'I'm starting', got none")
        self.assertIn("Genesis-074", result[0])

    def test_were_starting_still_a_task(self):
        """'We're starting Sprint-001' is a legitimate task declaration."""
        result = _task_values("We're starting Sprint-001.")
        self.assertTrue(len(result) > 0,
            f"Expected TASK fact for 'We're starting', got none")

    def test_were_beginning_still_a_task(self):
        """'We're beginning the new phase' is a legitimate task declaration."""
        result = _task_values("We're beginning the new phase.")
        self.assertTrue(len(result) > 0,
            f"Expected TASK fact, got none")

    def test_im_kicking_off_still_a_task(self):
        """'I'm kicking off the release' is a legitimate task declaration."""
        result = _task_values("I'm kicking off the release.")
        self.assertTrue(len(result) > 0,
            f"Expected TASK fact, got none")

    def test_starting_genesis_still_a_task(self):
        """Bare 'Starting Genesis-073' is a legitimate task declaration."""
        result = _task_values("Starting Genesis-073.")
        self.assertTrue(len(result) > 0,
            f"Expected TASK fact for bare 'Starting Genesis-NNN', got none")


class TestFactExtractorQuestionGuard(unittest.TestCase):
    """Confirm FactExtractor's own question guard still works."""

    def test_question_mark_produces_no_facts(self):
        """Messages ending in ? should produce no facts at all."""
        extractor = FactExtractor()
        facts = extractor.extract("What is my favourite colour?")
        self.assertEqual(facts, [])

    def test_question_word_produces_no_facts(self):
        """Messages starting with question words produce no facts."""
        extractor = FactExtractor()
        facts = extractor.extract("Who are my dogs?")
        self.assertEqual(facts, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
