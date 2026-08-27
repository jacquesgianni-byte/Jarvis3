"""
Genesis-063 Sprint-001 - ObjectiveProximityAnalyser tests.

Covers:
    ObjectiveMatch:
        - fields accessible and immutable
        - done flag preserved

    ObjectiveProximityResult:
        - fields accessible and immutable
        - has_overlap True when matches exist
        - has_overlap False when no matches
        - matches sorted by score descending
        - all_scores contains every objective
        - format_for_report() - overlap case
        - format_for_report() - no overlap case
        - format_for_report() never claims semantic understanding
        - format_for_report() never generates recommendation

    ObjectiveProximityAnalyser:
        - returns ObjectiveProximityResult
        - score > 0 when objective words in question
        - score 0 when no overlap
        - short words (<=2 chars) ignored
        - case insensitive matching
        - empty objectives list returns no matches
        - done flag correctly reflected in match
        - all_scores has entry for every objective
        - analyse does not modify objectives
        - observation_id preserved in result
        - question preserved in result

    Realistic scenarios:
        - mission-recommendation question vs current objectives
        - investigation question vs current objectives
        - unrelated question vs objectives
"""
from __future__ import annotations

import pytest
from core.knowledge.objective_proximity import (
    ObjectiveMatch,
    ObjectiveProximityAnalyser,
    ObjectiveProximityResult,
)

OBS_ID = "OBS-TEST01"

SAMPLE_OBJECTIVES = [
    {"text": "Audit all stale dashboard values",       "done": True},
    {"text": "Design MissionRegistry architecture",    "done": True},
    {"text": "Implement MissionRegistry",              "done": True},
    {"text": "Wire dashboard to live sources",         "done": True},
    {"text": "Remove Android hardcoded defaults",      "done": True},
]


class TestObjectiveMatch:

    def test_fields_accessible(self):
        m = ObjectiveMatch(objective_text="Test objective", score=2, done=False)
        assert m.objective_text == "Test objective"
        assert m.score          == 2
        assert m.done           is False

    def test_immutable(self):
        m = ObjectiveMatch(objective_text="Test", score=1, done=True)
        with pytest.raises((AttributeError, TypeError)):
            m.score = 99

    def test_done_flag(self):
        m1 = ObjectiveMatch(objective_text="A", score=1, done=True)
        m2 = ObjectiveMatch(objective_text="B", score=1, done=False)
        assert m1.done is True
        assert m2.done is False


class TestObjectiveProximityResult:

    def _make(self, matches=(), total=5, all_scores=None) -> ObjectiveProximityResult:
        return ObjectiveProximityResult(
            observation_id   = OBS_ID,
            question         = "test question",
            matches          = matches,
            total_objectives = total,
            has_overlap      = len(matches) > 0,
            all_scores       = all_scores or {},
        )

    def test_fields_accessible(self):
        r = self._make()
        assert r.observation_id   == OBS_ID
        assert r.total_objectives == 5
        assert r.has_overlap      is False

    def test_immutable(self):
        r = self._make()
        with pytest.raises((AttributeError, TypeError)):
            r.has_overlap = True

    def test_has_overlap_false_when_no_matches(self):
        r = self._make(matches=())
        assert r.has_overlap is False

    def test_has_overlap_true_when_matches(self):
        m = ObjectiveMatch("Test", 2, False)
        r = self._make(matches=(m,))
        assert r.has_overlap is True

    def test_format_no_overlap_contains_no_overlap_message(self):
        r = self._make()
        text = r.format_for_report()
        assert "no keyword overlap" in text.lower()

    def test_format_overlap_contains_objective_text(self):
        m = ObjectiveMatch("Design MissionRegistry architecture", 2, True)
        r = self._make(matches=(m,), all_scores={"Design MissionRegistry architecture": 2})
        text = r.format_for_report()
        assert "Design MissionRegistry architecture" in text

    def test_format_no_recommendation_in_output(self):
        m = ObjectiveMatch("Build something", 1, False)
        r = self._make(matches=(m,))
        text = r.format_for_report().lower()
        # Must not contain positive recommendation claims
        # ("not a recommendation" is acceptable ? it explicitly denies making one)
        assert "therefore" not in text
        assert "should build" not in text
        assert "next mission should" not in text
        assert "i recommend" not in text

    def test_format_no_semantic_claim(self):
        m = ObjectiveMatch("Design architecture", 1, False)
        r = self._make(matches=(m,))
        text = r.format_for_report().lower()
        assert "semantically related" not in text
        assert "means that" not in text

    def test_format_notes_proximity_only(self):
        r = self._make()
        assert "proximity" in r.format_for_report().lower()


class TestObjectiveProximityAnalyser:

    def test_returns_result(self):
        a = ObjectiveProximityAnalyser(SAMPLE_OBJECTIVES)
        r = a.analyse("What should our next mission be?", OBS_ID)
        assert isinstance(r, ObjectiveProximityResult)

    def test_score_positive_when_overlap(self):
        a = ObjectiveProximityAnalyser([{"text": "Design the dashboard", "done": False}])
        r = a.analyse("Why is the dashboard not working?", OBS_ID)
        assert r.has_overlap is True
        assert r.all_scores["Design the dashboard"] > 0

    def test_score_zero_when_no_overlap(self):
        a = ObjectiveProximityAnalyser([{"text": "Implement MissionRegistry", "done": False}])
        r = a.analyse("What is the capital of France?", OBS_ID)
        assert r.has_overlap is False
        assert r.all_scores["Implement MissionRegistry"] == 0

    def test_short_words_ignored(self):
        """Words of 2 chars or less are not counted."""
        a = ObjectiveProximityAnalyser([{"text": "Do it now", "done": False}])
        r = a.analyse("Do it now please", OBS_ID)
        # "Do", "it" are <=2 chars ? only "now" counts
        assert r.all_scores["Do it now"] <= 1

    def test_case_insensitive(self):
        a = ObjectiveProximityAnalyser([{"text": "Design Architecture", "done": False}])
        r = a.analyse("design architecture review", OBS_ID)
        assert r.all_scores["Design Architecture"] > 0

    def test_empty_objectives_no_matches(self):
        a = ObjectiveProximityAnalyser([])
        r = a.analyse("What should we work on?", OBS_ID)
        assert r.has_overlap      is False
        assert r.total_objectives == 0

    def test_done_flag_reflected_in_match(self):
        a = ObjectiveProximityAnalyser([{"text": "Implement dashboard", "done": True}])
        r = a.analyse("dashboard implementation status", OBS_ID)
        if r.matches:
            assert r.matches[0].done is True

    def test_all_scores_has_every_objective(self):
        a = ObjectiveProximityAnalyser(SAMPLE_OBJECTIVES)
        r = a.analyse("some question", OBS_ID)
        for obj in SAMPLE_OBJECTIVES:
            assert obj["text"] in r.all_scores

    def test_matches_sorted_by_score_descending(self):
        objs = [
            {"text": "Design dashboard architecture review", "done": False},
            {"text": "dashboard",                           "done": False},
        ]
        a = ObjectiveProximityAnalyser(objs)
        r = a.analyse("dashboard architecture review", OBS_ID)
        if len(r.matches) >= 2:
            assert r.matches[0].score >= r.matches[1].score

    def test_observation_id_preserved(self):
        a = ObjectiveProximityAnalyser(SAMPLE_OBJECTIVES)
        r = a.analyse("test", "MY-OBS-ID")
        assert r.observation_id == "MY-OBS-ID"

    def test_question_preserved(self):
        a = ObjectiveProximityAnalyser(SAMPLE_OBJECTIVES)
        r = a.analyse("What should our next mission be?", OBS_ID)
        assert r.question == "What should our next mission be?"

    def test_analyser_does_not_modify_objectives(self):
        objs = [{"text": "Test objective", "done": False}]
        a    = ObjectiveProximityAnalyser(objs)
        a.analyse("test question", OBS_ID)
        assert objs[0]["text"] == "Test objective"
        assert objs[0]["done"] is False

    def test_mission_recommendation_question_vs_sample_objectives(self):
        """
        Realistic scenario: mission-recommendation question vs current objectives.
        May score zero or low ? that is the honest result.
        """
        a = ObjectiveProximityAnalyser(SAMPLE_OBJECTIVES)
        r = a.analyse("What should our next mission be?", OBS_ID)
        assert isinstance(r, ObjectiveProximityResult)
        assert r.total_objectives == len(SAMPLE_OBJECTIVES)
        # Do NOT assert a specific score ? the result is evidence, not expected output

    def test_dashboard_question_vs_sample_objectives(self):
        """Dashboard question should overlap with dashboard-related objectives."""
        a = ObjectiveProximityAnalyser(SAMPLE_OBJECTIVES)
        r = a.analyse("Why is the dashboard showing wrong values?", OBS_ID)
        assert r.has_overlap is True
