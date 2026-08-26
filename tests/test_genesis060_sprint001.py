"""
Genesis-060 Sprint-001 - CapabilityGapObservation + GapObservationStore tests.

Covers:
    CapabilityGapObservation:
        - fields accessible and immutable
        - derive_failure_signature() produces canonical string
        - is_genuine_capability_gap() true only for Type 2 failures
        - is_genuine_capability_gap() false for boundary violation (Type 3)
        - is_genuine_capability_gap() false when investigation matched
        - is_genuine_capability_gap() false when knowledge matched
        - to_dict() / from_dict() round-trip

    GapObservationStore:
        - record() accepts genuine capability gaps
        - record() rejects boundary violations
        - record() rejects observations where investigation matched
        - record() rejects observations where knowledge matched
        - all_observations() returns recorded observations
        - observations_by_signature() filters correctly
        - capability_gap_count() counts only genuine gaps
        - is_reportable_gap() false below threshold
        - is_reportable_gap() true at threshold
        - recent_capability_gaps() returns most recent N
        - persists to disk (file created)
        - loads from disk on construction
        - tolerates missing file
        - tolerates corrupt lines in journal
        - CAPABILITY_GAP_SIGNATURE constant is correct canonical value
"""
from __future__ import annotations

import json
import pathlib
import uuid
import pytest
from datetime import datetime, timezone

from core.knowledge.capability_gap import (
    CapabilityGapObservation,
    GapObservationStore,
    CAPABILITY_GAP_SIGNATURE,
    RECURRENCE_THRESHOLD,
)

PROJECT_ROOT = pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")


def _make_observation(
    intent="unknown",
    knowledge_match=False,
    investigation_match=False,
    boundary_violation=False,
    question="What should our next mission be?",
    session_id="test-session",
) -> CapabilityGapObservation:
    sig = CapabilityGapObservation.derive_failure_signature(
        intent_result=intent,
        knowledge_match=knowledge_match,
        investigation_match=investigation_match,
        boundary_violation=boundary_violation,
    )
    return CapabilityGapObservation(
        observation_id      = f"OBS-{uuid.uuid4().hex[:6].upper()}",
        observed_at         = datetime.now(timezone.utc).isoformat(),
        question            = question,
        intent_result       = intent,
        knowledge_match     = knowledge_match,
        investigation_match = investigation_match,
        boundary_violation  = boundary_violation,
        failure_signature   = sig,
        session_id          = session_id,
    )


class TestCapabilityGapObservation:

    def test_fields_accessible(self):
        obs = _make_observation()
        assert obs.intent_result       == "unknown"
        assert obs.knowledge_match     is False
        assert obs.investigation_match is False
        assert obs.boundary_violation  is False
        assert obs.question            == "What should our next mission be?"

    def test_immutable(self):
        obs = _make_observation()
        with pytest.raises((AttributeError, TypeError)):
            obs.intent_result = "investigate"

    def test_derive_failure_signature_canonical(self):
        sig = CapabilityGapObservation.derive_failure_signature(
            intent_result="unknown",
            knowledge_match=False,
            investigation_match=False,
            boundary_violation=False,
        )
        assert sig == CAPABILITY_GAP_SIGNATURE

    def test_derive_failure_signature_with_boundary(self):
        sig = CapabilityGapObservation.derive_failure_signature(
            intent_result="unknown",
            knowledge_match=False,
            investigation_match=False,
            boundary_violation=True,
        )
        assert "boundary=yes" in sig

    def test_is_genuine_capability_gap_true(self):
        obs = _make_observation()
        assert obs.is_genuine_capability_gap() is True

    def test_is_genuine_capability_gap_false_boundary_violation(self):
        obs = _make_observation(boundary_violation=True)
        assert obs.is_genuine_capability_gap() is False

    def test_is_genuine_capability_gap_false_investigation_matched(self):
        obs = _make_observation(investigation_match=True, intent="investigate")
        assert obs.is_genuine_capability_gap() is False

    def test_is_genuine_capability_gap_false_knowledge_matched(self):
        obs = _make_observation(knowledge_match=True, intent="read_knowledge")
        assert obs.is_genuine_capability_gap() is False

    def test_is_genuine_capability_gap_false_known_intent(self):
        obs = _make_observation(intent="read_current")
        assert obs.is_genuine_capability_gap() is False

    def test_to_dict_round_trip(self):
        obs = _make_observation()
        d   = obs.to_dict()
        obs2 = CapabilityGapObservation.from_dict(d)
        assert obs == obs2

    def test_to_dict_contains_all_fields(self):
        obs = _make_observation()
        d   = obs.to_dict()
        for field in [
            "observation_id", "observed_at", "question",
            "intent_result", "knowledge_match", "investigation_match",
            "boundary_violation", "failure_signature", "session_id",
        ]:
            assert field in d

    def test_capability_gap_signature_constant(self):
        assert CAPABILITY_GAP_SIGNATURE == (
            "intent=unknown+knowledge=no+investigation=no+boundary=no"
        )


class TestGapObservationStore:

    def test_record_genuine_gap(self, tmp_path):
        store = GapObservationStore(tmp_path)
        obs   = _make_observation()
        store.record(obs)
        assert len(store.all_observations()) == 1

    def test_record_rejects_boundary_violation(self, tmp_path):
        store = GapObservationStore(tmp_path)
        obs   = _make_observation(boundary_violation=True)
        store.record(obs)
        assert len(store.all_observations()) == 0

    def test_record_rejects_investigation_match(self, tmp_path):
        store = GapObservationStore(tmp_path)
        obs   = _make_observation(investigation_match=True, intent="investigate")
        store.record(obs)
        assert len(store.all_observations()) == 0

    def test_record_rejects_knowledge_match(self, tmp_path):
        store = GapObservationStore(tmp_path)
        obs   = _make_observation(knowledge_match=True, intent="read_knowledge")
        store.record(obs)
        assert len(store.all_observations()) == 0

    def test_all_observations_returns_list(self, tmp_path):
        store = GapObservationStore(tmp_path)
        assert isinstance(store.all_observations(), list)

    def test_observations_by_signature(self, tmp_path):
        store = GapObservationStore(tmp_path)
        obs1  = _make_observation()
        obs2  = _make_observation(question="Different question")
        store.record(obs1)
        store.record(obs2)
        result = store.observations_by_signature(CAPABILITY_GAP_SIGNATURE)
        assert len(result) == 2

    def test_capability_gap_count(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        store.record(_make_observation())
        assert store.capability_gap_count() == 2

    def test_is_reportable_gap_below_threshold(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        assert store.is_reportable_gap(CAPABILITY_GAP_SIGNATURE) is False

    def test_is_reportable_gap_at_threshold(self, tmp_path):
        store = GapObservationStore(tmp_path)
        for _ in range(RECURRENCE_THRESHOLD):
            store.record(_make_observation())
        assert store.is_reportable_gap(CAPABILITY_GAP_SIGNATURE) is True

    def test_recent_capability_gaps(self, tmp_path):
        store = GapObservationStore(tmp_path)
        for i in range(4):
            store.record(_make_observation(question=f"Question {i}"))
        recent = store.recent_capability_gaps(n=2)
        assert len(recent) == 2
        assert recent[-1].question == "Question 3"

    def test_persists_to_disk(self, tmp_path):
        store = GapObservationStore(tmp_path)
        store.record(_make_observation())
        journal = tmp_path / "capability_gap_observations.jsonl"
        assert journal.exists()
        lines = [l for l in journal.read_text().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_loads_from_disk(self, tmp_path):
        store1 = GapObservationStore(tmp_path)
        store1.record(_make_observation(question="Persisted question"))
        store2 = GapObservationStore(tmp_path)
        assert len(store2.all_observations()) == 1
        assert store2.all_observations()[0].question == "Persisted question"

    def test_tolerates_missing_file(self, tmp_path):
        store = GapObservationStore(tmp_path / "nonexistent_subdir")
        assert len(store.all_observations()) == 0

    def test_tolerates_corrupt_lines(self, tmp_path):
        journal = tmp_path / "capability_gap_observations.jsonl"
        journal.write_text("this is not json\n", encoding="utf-8")
        store = GapObservationStore(tmp_path)
        assert len(store.all_observations()) == 0

    def test_append_only_does_not_overwrite(self, tmp_path):
        store1 = GapObservationStore(tmp_path)
        store1.record(_make_observation(question="First"))
        store2 = GapObservationStore(tmp_path)
        store2.record(_make_observation(question="Second"))
        store3 = GapObservationStore(tmp_path)
        assert len(store3.all_observations()) == 2

    def test_recurrence_threshold_constant(self):
        assert RECURRENCE_THRESHOLD >= 2
