"""
Genesis-024 Sprint-001 — Memory Consistency Audit Tests

Covers the three bugs identified and fixed:

  Fix 1 (fact_extractor.py):
    Person pattern 2 ("my X is Y") now requires Y to be a proper noun.
    Preference statements no longer create spurious PERSON facts.

  Fix 2 (conversation_observer.py):
    Observer-derived records are tagged "derived" so the recall layer
    can identify and exclude them.

  Fix 3 (memory.py):
    Fuzzy recall fallback excludes "derived" records to prevent
    zombie matches after a canonical memory is forgotten.

Test scenarios:
    remember → recall → forget → recall
    for: favourite colour, name, age, occupation, arbitrary attributes

Verifies:
    - no duplicate storage from observer
    - no orphaned / zombie recall after forget
    - no stale recall after forget
    - existing public API preserved
    - no regressions
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from dataclasses import dataclass, field
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.fact_extractor import FactExtractor, FactType, _is_proper_noun


# ===========================================================================
# 1. FACT EXTRACTOR — person pattern guard
# ===========================================================================

class TestFactExtractorPersonGuard:
    """
    Fix 1: person pattern 2 must not fire on preference statements.
    "my X is Y" should only create PERSON facts when Y is a proper noun.
    """

    def setup_method(self):
        self.fe = FactExtractor()

    def _person_facts(self, text):
        return [f for f in self.fe.extract(text) if f.fact_type == FactType.PERSON]

    # Preference statements — must produce ZERO person facts
    def test_favourite_colour_no_person_facts(self):
        assert self._person_facts("Remember my favourite colour is blue") == []

    def test_favourite_colour_capital_no_person_facts(self):
        assert self._person_facts("my favourite colour is Blue") == []

    def test_favourite_food_no_person_facts(self):
        assert self._person_facts("my favourite food is pizza") == []

    def test_favourite_drink_no_person_facts(self):
        assert self._person_facts("my favourite drink is coffee") == []

    def test_favourite_sport_no_person_facts(self):
        assert self._person_facts("my favourite sport is tennis") == []

    def test_age_no_person_facts(self):
        assert self._person_facts("my age is 30") == []

    def test_occupation_no_person_facts(self):
        # "developer" is not a proper noun
        assert self._person_facts("my occupation is developer") == []

    def test_remember_pattern_no_person_facts(self):
        assert self._person_facts("remember my favourite colour is blue") == []

    # Person statements — must produce person facts
    def test_senior_engineer_is_claude(self):
        facts = self._person_facts("my senior engineer is Claude")
        assert len(facts) == 2  # subject=claude + subject=user

    def test_boss_is_sarah(self):
        facts = self._person_facts("my boss is Sarah")
        assert len(facts) >= 1

    def test_name_is_ludovic(self):
        # "Ludovic" is a proper noun — should match
        facts = self._person_facts("my name is Ludovic")
        assert len(facts) >= 1

    def test_best_friend_alice_smith(self):
        facts = self._person_facts("my best friend is Alice Smith")
        assert len(facts) >= 1

    # Questions — always zero facts
    def test_question_no_facts(self):
        assert self.fe.extract("What is my favourite colour?") == []

    def test_who_question_no_facts(self):
        assert self.fe.extract("Who is my senior engineer?") == []


# ===========================================================================
# 2. PROPER NOUN GUARD
# ===========================================================================

class TestProperNounGuard:

    def test_blue_not_proper(self):
        assert not _is_proper_noun("blue")

    def test_Blue_not_proper(self):
        assert not _is_proper_noun("Blue")  # in non-name vocab

    def test_pizza_not_proper(self):
        assert not _is_proper_noun("pizza")

    def test_coffee_not_proper(self):
        assert not _is_proper_noun("coffee")

    def test_claude_is_proper(self):
        assert _is_proper_noun("Claude")

    def test_ludovic_is_proper(self):
        assert _is_proper_noun("Ludovic")

    def test_arsenal_is_proper(self):
        assert _is_proper_noun("Arsenal")

    def test_alice_smith_is_proper(self):
        assert _is_proper_noun("Alice Smith")

    def test_lowercase_not_proper(self):
        assert not _is_proper_noun("developer")

    def test_number_not_proper(self):
        assert not _is_proper_noun("30")

    def test_empty_not_proper(self):
        assert not _is_proper_noun("")


# ===========================================================================
# 3. OBSERVER DERIVED TAG
# ===========================================================================

class TestObserverDerivedTag:
    """
    Fix 2: observer-derived records must carry the "derived" tag.
    """

    def test_derived_tag_in_observer_stored_facts(self):
        from core.conversation.conversation_observer import ConversationObserver

        stored_calls = []

        mock_engine = MagicMock()
        mock_engine.store_memory.side_effect = lambda **kw: stored_calls.append(kw)

        observer = ConversationObserver(mock_engine)

        # Trigger a fact that would be extracted
        observer.observe(
            "My senior engineer is Claude",
            "Noted."
        )

        # All non-journal store_memory calls should include "derived" tag
        fact_calls = [
            c for c in stored_calls
            if c.get("subject") not in ("jarvis",)  # exclude journal
        ]

        for call_kwargs in fact_calls:
            tags = call_kwargs.get("tags", [])
            assert "derived" in tags, (
                f"Observer fact missing 'derived' tag: {call_kwargs}"
            )

    def test_journal_entries_not_tagged_derived(self):
        """Journal entries are system records, not derived facts."""
        from core.conversation.conversation_observer import ConversationObserver

        stored_calls = []
        mock_engine = MagicMock()
        mock_engine.store_memory.side_effect = lambda **kw: stored_calls.append(kw)

        observer = ConversationObserver(mock_engine)
        observer.observe("Hello Jarvis", "Good day, sir.")

        journal_calls = [c for c in stored_calls if c.get("subject") == "jarvis"]
        for call_kwargs in journal_calls:
            tags = call_kwargs.get("tags", [])
            assert "derived" not in tags or "journal" in tags


# ===========================================================================
# 4. MEMORY SKILL — zombie recall prevention
# ===========================================================================

class TestZombieRecallPrevention:
    """
    Fix 3: fuzzy search fallback must not return derived records.
    After forgetting a canonical memory, recall must return a miss.
    """

    def _make_mock_record(self, attribute, value, tags=None):
        """Create a mock KnowledgeRecord."""
        record = MagicMock()
        record.attribute = attribute
        record.value = value
        record.tags = tags or []
        return record

    def test_derived_record_excluded_from_fuzzy_recall(self):
        """After forget, derived zombie record must not be returned."""
        from core.skills.memory import MemorySkill

        mock_engine = MagicMock()

        # Simulate: canonical deleted, only derived remains
        mock_engine.recall_memory.return_value = None  # canonical = gone
        zombie = self._make_mock_record(
            "favourite colour role", "blue", tags=["person", "auto-extracted", "derived"]
        )
        mock_engine.search_memory.return_value = [zombie]

        skill = MemorySkill(mock_engine)
        response = skill._recall("favourite colour")

        # Must be a miss — not the zombie value
        assert "blue" not in response.message.lower() or "don't have" in response.message.lower()
        assert response.data.get("memory_miss") is True

    def test_canonical_record_returned_from_fuzzy_recall(self):
        """Non-derived records are still returned by fuzzy fallback."""
        from core.skills.memory import MemorySkill

        mock_engine = MagicMock()
        mock_engine.recall_memory.return_value = None

        canonical = self._make_mock_record(
            "favourite colour", "blue", tags=["preference"]
        )
        mock_engine.search_memory.return_value = [canonical]

        skill = MemorySkill(mock_engine)
        response = skill._recall("colour")

        assert "blue" in response.message.lower()
        assert response.success

    def test_mixed_results_canonical_wins(self):
        """When both derived and canonical exist, canonical is returned."""
        from core.skills.memory import MemorySkill

        mock_engine = MagicMock()
        mock_engine.recall_memory.return_value = None

        zombie = self._make_mock_record(
            "favourite colour role", "blue", tags=["derived"]
        )
        canonical = self._make_mock_record(
            "favourite colour", "red", tags=["preference"]
        )
        mock_engine.search_memory.return_value = [zombie, canonical]

        skill = MemorySkill(mock_engine)
        response = skill._recall("favourite colour")

        assert "red" in response.message.lower()

    def test_all_derived_returns_miss(self):
        """If only derived records exist, treat as miss."""
        from core.skills.memory import MemorySkill

        mock_engine = MagicMock()
        mock_engine.recall_memory.return_value = None

        derived1 = self._make_mock_record("attr role", "val", tags=["derived"])
        derived2 = self._make_mock_record("attr x", "val2", tags=["auto-extracted", "derived"])
        mock_engine.search_memory.return_value = [derived1, derived2]

        skill = MemorySkill(mock_engine)
        response = skill._recall("attr")

        assert response.data.get("memory_miss") is True


# ===========================================================================
# 5. REMEMBER → RECALL → FORGET → RECALL lifecycle
# ===========================================================================

class TestMemoryLifecycle:
    """
    End-to-end lifecycle tests using mock engine.
    Verifies no duplicate storage, no orphaned records, no stale recall.
    """

    def _make_skill_with_store(self):
        """Return (skill, engine_mock, store) where store simulates the KE."""
        from core.skills.memory import MemorySkill

        store = {}  # attribute → (value, tags)

        mock_engine = MagicMock()

        def store_memory(subject, category, attribute, value, **kwargs):
            store[(subject, attribute)] = {"value": value, "tags": kwargs.get("tags", [])}

        def recall_memory(subject, attribute):
            key = (subject, attribute)
            if key in store:
                r = MagicMock()
                r.attribute = attribute
                r.value = store[key]["value"]
                r.tags = store[key]["tags"]
                return r
            return None

        def forget_memory(subject, attribute):
            key = (subject, attribute)
            if key in store:
                del store[key]
                return True
            return False

        def search_memory(query, subject=None, category=None):
            results = []
            for (s, a), data in store.items():
                if subject and s != subject:
                    continue
                if query.lower() in a.lower() or query.lower() in data["value"].lower():
                    r = MagicMock()
                    r.attribute = a
                    r.value = data["value"]
                    r.tags = data["tags"]
                    results.append(r)
            return results

        mock_engine.store_memory.side_effect = store_memory
        mock_engine.recall_memory.side_effect = recall_memory
        mock_engine.forget_memory.side_effect = forget_memory
        mock_engine.search_memory.side_effect = search_memory

        skill = MemorySkill(mock_engine)
        return skill, mock_engine, store

    def _lifecycle(self, skill, key, value):
        """remember → recall → forget → recall"""
        remember_resp = skill.remember(key, value)
        assert remember_resp.success

        recall_resp = skill._recall(key)
        assert recall_resp.success
        assert value in recall_resp.message

        forget_resp = skill._forget(key)
        assert forget_resp.success

        recall_after = skill._recall(key)
        return recall_after

    def test_favourite_colour_lifecycle(self):
        skill, _, _ = self._make_skill_with_store()
        result = self._lifecycle(skill, "favourite colour", "blue")
        assert result.data.get("memory_miss") is True
        assert "blue" not in result.message.lower() or "don't" in result.message.lower()

    def test_name_lifecycle(self):
        skill, _, _ = self._make_skill_with_store()
        result = self._lifecycle(skill, "name", "Ludovic")
        assert result.data.get("memory_miss") is True

    def test_age_lifecycle(self):
        skill, _, _ = self._make_skill_with_store()
        result = self._lifecycle(skill, "age", "35")
        assert result.data.get("memory_miss") is True

    def test_occupation_lifecycle(self):
        skill, _, _ = self._make_skill_with_store()
        result = self._lifecycle(skill, "occupation", "engineer")
        assert result.data.get("memory_miss") is True

    def test_arbitrary_attribute_lifecycle(self):
        skill, _, _ = self._make_skill_with_store()
        result = self._lifecycle(skill, "lucky number", "7")
        assert result.data.get("memory_miss") is True

    def test_no_duplicate_storage_on_remember(self):
        skill, mock_engine, store = self._make_skill_with_store()
        skill.remember("favourite colour", "blue")
        skill.remember("favourite colour", "red")  # update
        # Only one canonical record for this attribute
        canonical = [
            k for k in store.keys()
            if k[0] == "user" and "colour" in k[1]
        ]
        # Should be one or two (favourite colour + colour variant), not more
        assert len(canonical) <= 2

    def test_recall_after_forget_is_miss_not_zombie(self):
        """Core zombie prevention test."""
        from core.skills.memory import MemorySkill

        # Simulate state after canonical is forgotten but derived zombie exists
        from unittest.mock import MagicMock
        mock_engine = MagicMock()
        mock_engine.recall_memory.return_value = None

        zombie = MagicMock()
        zombie.attribute = "favourite colour role"
        zombie.value = "blue"
        zombie.tags = ["person", "auto-extracted", "derived"]
        mock_engine.search_memory.return_value = [zombie]

        skill = MemorySkill(mock_engine)
        result = skill._recall("favourite colour")

        assert result.data.get("memory_miss") is True
        assert "blue" not in result.message


# ===========================================================================
# 6. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_fact_extractor_public_api_unchanged(self):
        fe = FactExtractor()
        facts = fe.extract("We are building Jarvis OS")
        assert isinstance(facts, list)

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_genesis_022_engine_unchanged(self):
        from core.conversation.conversation_engine import ConversationEngine
        d = ConversationEngine().process("Hello.")
        assert d is not None

    def test_memory_skill_public_api_unchanged(self):
        from core.skills.memory import MemorySkill
        mock_engine = MagicMock()
        mock_engine.store_memory.return_value = None
        skill = MemorySkill(mock_engine)
        assert skill.name == "memory"

    def test_fact_extractor_project_extraction_unchanged(self):
        fe = FactExtractor()
        facts = fe.extract("I'm building Jarvis OS")
        project_facts = [f for f in facts if f.fact_type == FactType.PROJECT]
        assert len(project_facts) == 1
        assert project_facts[0].value == "Jarvis OS"

    def test_fact_extractor_milestone_extraction_unchanged(self):
        fe = FactExtractor()
        facts = fe.extract("We've completed Genesis-022")
        milestone_facts = [f for f in facts if f.fact_type == FactType.MILESTONE]
        assert len(milestone_facts) >= 1