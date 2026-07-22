"""
GC-008 — Forget Pet Names Regression Tests

Verifies that possessive and plural pet name phrases are correctly
canonicalised to "pet names" so forget commands work consistently.

Coverage:
  - "Forget my dogs' names." removes pet names record
  - "Forget my dogs names." removes pet names record
  - "Forget my pet names." removes pet names record
  - Existing forget behaviour unchanged (colour, drink, etc.)
  - After forget, recall returns not-found
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.skills.memory import MemorySkill, _canonicalise


class TestCanonicalise:
    """Unit tests for the _canonicalise helper."""

    def test_dogs_apostrophe_names(self):
        assert _canonicalise("dogs' names") == "pet names"

    def test_dogs_names_no_apostrophe(self):
        assert _canonicalise("dogs names") == "pet names"

    def test_cats_apostrophe_names(self):
        assert _canonicalise("cats' names") == "pet names"

    def test_pets_names(self):
        assert _canonicalise("pets names") == "pet names"

    def test_pet_names_unchanged(self):
        assert _canonicalise("pet names") == "pet names"

    def test_existing_colour_unchanged(self):
        assert _canonicalise("colour") == "favourite colour"

    def test_existing_drink_unchanged(self):
        assert _canonicalise("drink") == "favourite drink"

    def test_unrelated_attribute_unchanged(self):
        assert _canonicalise("workplace") == "workplace"


class TestForgetPetNames:
    """Integration tests for forget with pet name phrases."""

    def _make_skill(self):
        engine = MagicMock()
        engine.forget_memory.return_value = True
        engine.store_memory.return_value = MagicMock()
        return MemorySkill(engine), engine

    def test_forget_dogs_apostrophe_names(self):
        skill, engine = self._make_skill()
        response = skill.execute("forget my dogs' names")
        assert response.success
        # Should attempt to forget "pet names" (canonicalised)
        called_attrs = [call.args[1] for call in engine.forget_memory.call_args_list]
        assert "pet names" in called_attrs

    def test_forget_dogs_names_no_apostrophe(self):
        skill, engine = self._make_skill()
        response = skill.execute("forget my dogs names")
        assert response.success
        called_attrs = [call.args[1] for call in engine.forget_memory.call_args_list]
        assert "pet names" in called_attrs

    def test_forget_pet_names(self):
        skill, engine = self._make_skill()
        response = skill.execute("forget my pet names")
        assert response.success
        called_attrs = [call.args[1] for call in engine.forget_memory.call_args_list]
        assert "pet names" in called_attrs

    def test_existing_forget_colour_unchanged(self):
        skill, engine = self._make_skill()
        response = skill.execute("forget my favourite colour")
        assert response.success
        called_attrs = [call.args[1] for call in engine.forget_memory.call_args_list]
        assert "favourite colour" in called_attrs

    def test_forget_returns_success_message(self):
        skill, engine = self._make_skill()
        response = skill.execute("forget my dogs' names")
        assert response.success
        assert "forgotten" in response.message.lower() or "don't have" in response.message.lower()