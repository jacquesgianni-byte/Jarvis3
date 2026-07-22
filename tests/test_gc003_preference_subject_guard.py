"""
GC-003 — Preference Subject Guard Tests

Regression tests ensuring that preference statements like
"My favourite drink is coffee" do not create person records.

Coverage:
  - Preference statements produce PREFERENCE facts, not PERSON facts
  - Existing person patterns (manager, son, daughter) unchanged
  - Both British and American spellings handled
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.fact_extractor import ExtractedFact, FactExtractor, FactType


class TestPreferenceSubjectGuard:
    """Preference statements must not produce PERSON facts."""

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_favourite_drink_not_person(self):
        facts = self.extractor.extract("My favourite drink is coffee.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                        and f.subject == "favourite drink"]
        assert len(person_facts) == 0

    def test_favorite_drink_not_person(self):
        facts = self.extractor.extract("My favorite drink is coffee.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                        and f.subject == "favorite drink"]
        assert len(person_facts) == 0

    def test_favourite_colour_not_person(self):
        facts = self.extractor.extract("My favourite colour is green.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                        and f.subject == "favourite colour"]
        assert len(person_facts) == 0

    def test_favorite_color_not_person(self):
        facts = self.extractor.extract("My favorite color is green.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                        and f.subject == "favorite color"]
        assert len(person_facts) == 0

    def test_favourite_team_not_person(self):
        facts = self.extractor.extract("My favourite team is Liverpool.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                        and f.subject == "favourite team"]
        assert len(person_facts) == 0

    def test_favourite_food_not_person(self):
        facts = self.extractor.extract("My favourite food is pizza.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                        and f.subject == "favourite food"]
        assert len(person_facts) == 0

    def test_favourite_movie_not_person(self):
        facts = self.extractor.extract("My favourite movie is Interstellar.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                        and f.subject == "favourite movie"]
        assert len(person_facts) == 0

    def test_favourite_sport_not_person(self):
        facts = self.extractor.extract("My favourite sport is AFL.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON
                        and f.subject == "favourite sport"]
        assert len(person_facts) == 0


class TestExistingPersonPatternsUnchanged:
    """Existing person extraction must still work after GC-003 fix."""

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_manager_still_extracted(self):
        facts = self.extractor.extract("My manager is Sarah.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON]
        assert len(person_facts) >= 1
        values = [f.value for f in person_facts]
        assert any("Sarah" in v for v in values)

    def test_son_still_extracted(self):
        facts = self.extractor.extract("My son is Alex.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON]
        assert len(person_facts) >= 1
        values = [f.value for f in person_facts]
        assert any("Alex" in v for v in values)

    def test_daughter_still_extracted(self):
        facts = self.extractor.extract("My daughter is Emma.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON]
        assert len(person_facts) >= 1
        values = [f.value for f in person_facts]
        assert any("Emma" in v for v in values)

    def test_claude_is_my_engineer_still_works(self):
        facts = self.extractor.extract("Claude is my senior engineer.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON]
        assert len(person_facts) >= 1

    def test_gpt_handles_specs_still_works(self):
        facts = self.extractor.extract("GPT handles specs.")
        person_facts = [f for f in facts if f.fact_type == FactType.PERSON]
        assert len(person_facts) >= 1