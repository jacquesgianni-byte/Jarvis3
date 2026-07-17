"""
Genesis-019.5 — Engineering Academy Integration Tests
Completely self-contained. No dependency on other test files.

Coverage:
  - Router detects ENGINEERING intent for all success criteria queries
  - Router does NOT detect ENGINEERING for non-engineering queries
  - EngineeringSkill returns Academy response for engineering questions
  - EngineeringSkill falls back to AI for non-engineering questions
  - EngineeringSkill returns graceful miss when AI unavailable
  - Debug logging emits [ENGINEERING] prefix
  - All existing intent routing preserved (regression)
"""

import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.intents import Intent
from core.router import IntentRouter
from core.skills.engineering import EngineeringSkill
from core.models.response import Response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_skill(ai=None) -> EngineeringSkill:
    return EngineeringSkill(ai=ai)


def make_mock_ai(message="AI response") -> MagicMock:
    ai = MagicMock()
    ai.ask.return_value = Response(success=True, message=message)
    return ai


REAL_DATA = REPO_ROOT / "data" / "engineering"


# ===========================================================================
# 1. ROUTER — Engineering intent detection
# ===========================================================================

class TestRouterEngineeringDetection:
    """The router must detect ENGINEERING for all success-criteria queries."""

    def setup_method(self):
        self.router = IntentRouter()

    def _detect(self, q):
        return self.router.detect(q)

    # --- Success criteria from the spec ---

    def test_repository_pattern_detected(self):
        assert self._detect("What is the Repository Pattern?") == Intent.ENGINEERING

    def test_strategy_pattern_detected(self):
        assert self._detect("Explain the Strategy Pattern.") == Intent.ENGINEERING

    def test_engineering_principles_list_detected(self):
        assert self._detect("What engineering principles do you know?") == Intent.ENGINEERING

    def test_architecture_patterns_list_detected(self):
        assert self._detect("List the architecture patterns you know.") == Intent.ENGINEERING

    def test_god_object_anti_pattern_detected(self):
        assert self._detect("Explain the God Object anti-pattern.") == Intent.ENGINEERING

    def test_composition_vs_inheritance_detected(self):
        assert self._detect("When should I use composition instead of inheritance?") == Intent.ENGINEERING

    # --- Additional engineering queries ---

    def test_design_patterns_list_detected(self):
        assert self._detect("What design patterns do you know?") == Intent.ENGINEERING

    def test_anti_patterns_list_detected(self):
        assert self._detect("List the anti-patterns you know.") == Intent.ENGINEERING

    def test_best_practices_list_detected(self):
        assert self._detect("What best practices do you know?") == Intent.ENGINEERING

    def test_clean_architecture_detected(self):
        assert self._detect("Explain clean architecture.") == Intent.ENGINEERING

    def test_solid_principle_detected(self):
        assert self._detect("What is the single responsibility principle?") == Intent.ENGINEERING

    def test_dry_principle_detected(self):
        assert self._detect("Explain the DRY principle.") == Intent.ENGINEERING

    def test_tight_coupling_detected(self):
        assert self._detect("What is tight coupling?") == Intent.ENGINEERING

    def test_adapter_pattern_detected(self):
        assert self._detect("Tell me about the adapter pattern.") == Intent.ENGINEERING

    def test_facade_pattern_detected(self):
        assert self._detect("Describe the facade pattern.") == Intent.ENGINEERING

    def test_technical_debt_detected(self):
        assert self._detect("Explain technical debt.") == Intent.ENGINEERING

    def test_refactor_vs_rewrite_detected(self):
        assert self._detect("When should I refactor vs rewrite?") == Intent.ENGINEERING

    def test_factory_pattern_detected(self):
        assert self._detect("What is the factory pattern?") == Intent.ENGINEERING

    def test_dependency_injection_detected(self):
        assert self._detect("Explain dependency injection.") == Intent.ENGINEERING

    def test_fail_fast_detected(self):
        assert self._detect("What is fail fast?") == Intent.ENGINEERING


# ===========================================================================
# 2. ROUTER — Non-engineering queries NOT routed to ENGINEERING
# ===========================================================================

class TestRouterNonEngineeringNotDetected:
    """Non-engineering queries must NOT route to ENGINEERING."""

    def setup_method(self):
        self.router = IntentRouter()

    def _detect(self, q):
        return self.router.detect(q)

    def test_poem_not_engineering(self):
        assert self._detect("Write me a poem.") != Intent.ENGINEERING

    def test_weather_not_engineering(self):
        assert self._detect("What's the weather?") != Intent.ENGINEERING

    def test_quantum_physics_not_engineering(self):
        assert self._detect("Explain quantum physics.") != Intent.ENGINEERING

    def test_joke_not_engineering(self):
        assert self._detect("Tell me a joke.") != Intent.ENGINEERING

    def test_greeting_not_engineering(self):
        assert self._detect("Hello Jarvis.") == Intent.GREETING

    def test_personal_memory_not_engineering(self):
        assert self._detect("What is my name?") == Intent.MEMORY

    def test_exit_not_engineering(self):
        assert self._detect("bye") == Intent.EXIT


# ===========================================================================
# 3. ROUTER — Existing intent routing preserved (regression)
# ===========================================================================

class TestRouterRegression:
    """All pre-019.5 intent routing must be preserved."""

    def setup_method(self):
        self.router = IntentRouter()

    def test_greeting_hello(self):
        assert self.router.detect("hello") == Intent.GREETING

    def test_greeting_hey(self):
        assert self.router.detect("hey there") == Intent.GREETING

    def test_memory_remember(self):
        assert self.router.detect("remember that I like coffee") == Intent.MEMORY

    def test_memory_forget(self):
        assert self.router.detect("forget that") == Intent.MEMORY

    def test_memory_recall(self):
        assert self.router.detect("what is my favourite sport?") == Intent.MEMORY

    def test_identity_who_are_you(self):
        assert self.router.detect("who are you") == Intent.IDENTITY

    def test_exit_bye(self):
        assert self.router.detect("bye") == Intent.EXIT

    def test_unknown_fallback(self):
        assert self.router.detect("zzz gibberish xyz abc") == Intent.UNKNOWN

    def test_engineering_intent_exists(self):
        assert hasattr(Intent, "ENGINEERING")


# ===========================================================================
# 4. ENGINEERING SKILL — Academy responses
# ===========================================================================

class TestEngineeringSkillAcademyResponse:
    """Skill returns Academy content for known engineering questions."""

    def test_repository_pattern_answered_from_academy(self):
        if not (REAL_DATA / "patterns.json").exists():
            pytest.skip("patterns.json not present.")
        skill = make_skill()
        response = skill.execute("What is the Repository Pattern?")
        assert response.success
        assert "repository" in response.message.lower() or "Repository" in response.message

    def test_strategy_pattern_answered_from_academy(self):
        if not (REAL_DATA / "patterns.json").exists():
            pytest.skip("patterns.json not present.")
        skill = make_skill()
        response = skill.execute("Explain the Strategy Pattern.")
        assert response.success
        assert "strategy" in response.message.lower() or "Strategy" in response.message

    def test_god_object_answered_from_academy(self):
        if not (REAL_DATA / "anti_patterns.json").exists():
            pytest.skip("anti_patterns.json not present.")
        skill = make_skill()
        response = skill.execute("Explain the God Object anti-pattern.")
        assert response.success
        assert "god" in response.message.lower() or "God" in response.message

    def test_list_principles_answered_from_academy(self):
        if not (REAL_DATA / "principles.json").exists():
            pytest.skip("principles.json not present.")
        skill = make_skill()
        response = skill.execute("What engineering principles do you know?")
        assert response.success
        assert "21" in response.message or "principle" in response.message.lower()

    def test_list_design_patterns_answered_from_academy(self):
        if not (REAL_DATA / "patterns.json").exists():
            pytest.skip("patterns.json not present.")
        skill = make_skill()
        response = skill.execute("List the design patterns you know.")
        assert response.success
        assert "pattern" in response.message.lower()

    def test_list_architecture_patterns_answered_from_academy(self):
        if not (REAL_DATA / "architecture_patterns.json").exists():
            pytest.skip("architecture_patterns.json not present.")
        skill = make_skill()
        response = skill.execute("List the architecture patterns you know.")
        assert response.success
        assert "architecture" in response.message.lower()

    def test_list_anti_patterns_answered_from_academy(self):
        if not (REAL_DATA / "anti_patterns.json").exists():
            pytest.skip("anti_patterns.json not present.")
        skill = make_skill()
        response = skill.execute("What anti-patterns do you know?")
        assert response.success
        assert "anti" in response.message.lower() or "pattern" in response.message.lower()

    def test_clean_architecture_answered_from_academy(self):
        if not (REAL_DATA / "architecture_patterns.json").exists():
            pytest.skip("architecture_patterns.json not present.")
        skill = make_skill()
        response = skill.execute("Explain clean architecture.")
        assert response.success
        assert "clean" in response.message.lower() or "architecture" in response.message.lower()

    def test_dependency_injection_answered_from_academy(self):
        if not (REAL_DATA / "patterns.json").exists():
            pytest.skip("patterns.json not present.")
        skill = make_skill()
        response = skill.execute("Explain dependency injection.")
        assert response.success
        assert response.message  # non-empty


# ===========================================================================
# 5. ENGINEERING SKILL — AI fallback
# ===========================================================================

class TestEngineeringSkillAIFallback:
    """Skill falls back to AI when the Academy cannot answer."""

    def test_non_engineering_question_falls_back_to_ai(self):
        ai = make_mock_ai("Here is a poem.")
        skill = make_skill(ai=ai)
        # Force a question the Academy won't match
        response = skill.execute("Write me a haiku about winter.")
        # AI should have been called
        assert ai.ask.called
        assert response.message == "Here is a poem."

    def test_ai_not_called_when_academy_answers(self):
        if not (REAL_DATA / "patterns.json").exists():
            pytest.skip("patterns.json not present.")
        ai = make_mock_ai("AI answer")
        skill = make_skill(ai=ai)
        response = skill.execute("What is the Repository Pattern?")
        # AI must NOT have been called — Academy answered
        ai.ask.assert_not_called()
        assert response.success

    def test_graceful_miss_when_no_ai_available(self):
        skill = make_skill(ai=None)
        response = skill.execute("Write me a haiku about winter.")
        assert response.success
        assert "Academy" in response.message or "specific" in response.message.lower()


# ===========================================================================
# 6. ENGINEERING SKILL — Debug logging
# ===========================================================================

class TestEngineeringSkillLogging:
    """[ENGINEERING] prefix appears in log output."""

    def test_engineering_detected_log_emitted(self, caplog):
        if not (REAL_DATA / "patterns.json").exists():
            pytest.skip("patterns.json not present.")
        skill = make_skill()
        with caplog.at_level(logging.INFO, logger="core.skills.engineering"):
            skill.execute("What is the Repository Pattern?")
        messages = " ".join(caplog.messages)
        assert "[ENGINEERING]" in messages

    def test_match_found_log_emitted(self, caplog):
        if not (REAL_DATA / "patterns.json").exists():
            pytest.skip("patterns.json not present.")
        skill = make_skill()
        with caplog.at_level(logging.INFO, logger="core.skills.engineering"):
            skill.execute("What is the Repository Pattern?")
        messages = " ".join(caplog.messages)
        assert "Match found" in messages

    def test_fallback_log_emitted(self, caplog):
        ai = make_mock_ai()
        skill = make_skill(ai=ai)
        with caplog.at_level(logging.INFO, logger="core.skills.engineering"):
            skill.execute("Write me a poem about robots.")
        messages = " ".join(caplog.messages)
        assert "[ENGINEERING]" in messages
        assert "Falling back" in messages or "No Academy match" in messages


# ===========================================================================
# 7. INTENT ENUM — ENGINEERING exists
# ===========================================================================

class TestIntentEnum:

    def test_engineering_intent_in_enum(self):
        assert Intent.ENGINEERING in list(Intent)

    def test_engineering_intent_is_unique(self):
        values = [i.value for i in Intent]
        assert len(values) == len(set(values))

    def test_all_original_intents_present(self):
        for name in ["GREETING", "IDENTITY", "MEMORY", "REASONING",
                     "TOOL", "EXIT", "UNKNOWN", "ENGINEERING"]:
            assert hasattr(Intent, name), f"Intent.{name} missing"


# ===========================================================================
# 8. SKILL NAME
# ===========================================================================

class TestEngineeringSkillInterface:

    def test_skill_name(self):
        assert make_skill().name == "engineering"

    def test_skill_execute_returns_response(self):
        skill = make_skill(ai=make_mock_ai())
        result = skill.execute("What is the factory pattern?")
        assert isinstance(result, Response)
        assert result.success in (True, False)  # always a Response

    def test_skill_accepts_no_ai(self):
        skill = make_skill(ai=None)
        assert skill.ai is None