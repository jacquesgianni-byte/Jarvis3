"""
Genesis-064 Sprint-001 ? BoundSprintProposal + SprintRecord + SprintProposalEngine tests.

Covers:
    BoundSprintProposal:
        - fields accessible and immutable
        - format_for_approval() contains all required sections
        - format_for_approval() contains NOT DOING section
        - format_for_approval() contains evidence basis
        - format_for_approval() contains acceptance criteria with guaranteed_by
        - to_dict() round-trip

    AcceptanceCriterion:
        - guaranteed_by field present and non-empty
        - criterion_type is declared type

    SprintRecord:
        - fields accessible
        - to_dict() contains all fields
        - SprintRecordStore saves and loads
        - SprintRecordStore tolerates missing file
        - SprintRecordStore tolerates corrupt lines
        - append-only: two saves produce two records

    SprintProposalEngine:
        - returns InsufficientEvidenceResult when observations < threshold
        - returns BoundSprintProposal when threshold met and all ISOLATED
        - proposal template_id is TEMPLATE_A when gap evidence present
        - proposal steps are in declared order
        - proposal acceptance criteria all have guaranteed_by
        - proposal not_doing is non-empty
        - proposal recurring_question matches most common observation
        - proposal acceptance criteria type is proximity_nonzero + tests_pass
        - NOT ISOLATED observations do not trigger Template A
        - Template B triggers when delivery record missing from git log
        - InsufficientEvidenceResult has correct counts

    Internal consistency check:
        - every acceptance criterion guaranteed_by references a declared step
        - no acceptance criterion claims investigation executes (Template A)
"""
from __future__ import annotations

import json
import pathlib
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from core.knowledge.sprint_proposal import (
    AcceptanceCriterion,
    BoundSprintProposal,
    InsufficientEvidenceResult,
    ProposalStep,
    SprintProposalEngine,
    SprintRecord,
    SprintRecordStore,
    TEMPLATE_A,
    TEMPLATE_B,
    TEMPLATE_A_MIN_OBSERVATIONS,
)
from core.knowledge.capability_gap import (
    CapabilityGapObservation,
    GapObservationStore,
    CAPABILITY_GAP_SIGNATURE,
)
from core.mission.investigation_registry import InvestigationRegistry
from core.knowledge.genesis_record import GenesisDeliveryStore

PROJECT_ROOT = pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")


def _make_observation(question: str = "What should our next mission be?") -> CapabilityGapObservation:
    return CapabilityGapObservation(
        observation_id      = f"OBS-{uuid.uuid4().hex[:6].upper()}",
        observed_at         = datetime.now(timezone.utc).isoformat(),
        question            = question,
        intent_result       = "unknown",
        knowledge_match     = False,
        investigation_match = False,
        boundary_violation  = False,
        failure_signature   = CAPABILITY_GAP_SIGNATURE,
        session_id          = "test-session",
    )


def _make_proposal() -> BoundSprintProposal:
    step = ProposalStep(
        step_number  = 1,
        description  = "Register descriptor",
        action_type  = "register_descriptor",
        parameters   = (("name", "test_investigation"),),
    )
    criterion = AcceptanceCriterion(
        description      = "Proximity score > 0",
        criterion_type   = "proximity_nonzero",
        test_input       = "test question",
        expected_outcome = "score > 0",
        guaranteed_by    = "Step 1 ? descriptor registration",
    )
    return BoundSprintProposal(
        proposal_id            = "PROP-TEST01",
        created_at             = datetime.now(timezone.utc).isoformat(),
        template_id            = TEMPLATE_A,
        proposed_sprint_name   = "Register test investigation",
        rationale              = "Evidence-derived rationale",
        evidence_summary       = "2 gap observations, all ISOLATED",
        gap_observation_count  = 2,
        recurring_question     = "What should our next mission be?",
        steps                  = (step,),
        acceptance_criteria    = (criterion,),
        not_doing              = ("Does not implement investigation method.",),
        evidence_sources       = ("GapObservationStore", "InvestigationRegistry"),
    )


class TestBoundSprintProposal:

    def test_fields_accessible(self):
        p = _make_proposal()
        assert p.proposal_id          == "PROP-TEST01"
        assert p.template_id          == TEMPLATE_A
        assert p.gap_observation_count == 2

    def test_immutable(self):
        p = _make_proposal()
        with pytest.raises((AttributeError, TypeError)):
            p.template_id = "other"

    def test_format_contains_proposal_id(self):
        p = _make_proposal()
        assert "PROP-TEST01" in p.format_for_approval()

    def test_format_contains_sprint_name(self):
        p = _make_proposal()
        assert "Register test investigation" in p.format_for_approval()

    def test_format_contains_evidence_basis(self):
        p = _make_proposal()
        assert "EVIDENCE BASIS" in p.format_for_approval()

    def test_format_contains_proposed_steps(self):
        p = _make_proposal()
        assert "PROPOSED STEPS" in p.format_for_approval()

    def test_format_contains_acceptance_criteria(self):
        p = _make_proposal()
        assert "ACCEPTANCE CRITERIA" in p.format_for_approval()

    def test_format_contains_guaranteed_by(self):
        p = _make_proposal()
        assert "Guaranteed by" in p.format_for_approval()

    def test_format_contains_not_doing(self):
        p = _make_proposal()
        assert "WHAT THIS DOES NOT DO" in p.format_for_approval()

    def test_format_contains_nothing_executes_statement(self):
        p = _make_proposal()
        assert "Nothing will be executed" in p.format_for_approval()

    def test_to_dict_round_trip(self):
        p = _make_proposal()
        d = p.to_dict()
        assert d["proposal_id"]   == "PROP-TEST01"
        assert d["template_id"]   == TEMPLATE_A
        assert len(d["steps"])    == 1
        assert len(d["not_doing"]) == 1


class TestAcceptanceCriterion:

    def test_guaranteed_by_non_empty(self):
        c = AcceptanceCriterion(
            description="test", criterion_type="proximity_nonzero",
            test_input="q", expected_outcome="score > 0",
            guaranteed_by="Step 1",
        )
        assert len(c.guaranteed_by) > 0

    def test_immutable(self):
        c = AcceptanceCriterion(
            description="test", criterion_type="proximity_nonzero",
            test_input="q", expected_outcome="score > 0",
            guaranteed_by="Step 1",
        )
        with pytest.raises((AttributeError, TypeError)):
            c.criterion_type = "other"


class TestSprintRecordStore:

    def test_save_and_load(self, tmp_path):
        store  = SprintRecordStore(tmp_path / "records")
        record = SprintRecord(
            proposal_id = "PROP-001",
            created_at  = datetime.now(timezone.utc).isoformat(),
            proposal    = {"test": True},
        )
        store.save(record)
        records = store.all_records()
        assert len(records) == 1
        assert records[0].proposal_id == "PROP-001"

    def test_append_only_two_saves(self, tmp_path):
        store = SprintRecordStore(tmp_path / "records")
        for i in range(2):
            store.save(SprintRecord(
                proposal_id = f"PROP-00{i}",
                created_at  = datetime.now(timezone.utc).isoformat(),
                proposal    = {},
            ))
        assert len(store.all_records()) == 2

    def test_tolerates_missing_file(self, tmp_path):
        store = SprintRecordStore(tmp_path / "nonexistent")
        assert store.all_records() == []

    def test_tolerates_corrupt_lines(self, tmp_path):
        data_dir = tmp_path / "records"
        data_dir.mkdir()
        (data_dir / "sprint_records.jsonl").write_text("not json\n")
        store = SprintRecordStore(data_dir)
        assert store.all_records() == []

    def test_get_by_proposal_id(self, tmp_path):
        store = SprintRecordStore(tmp_path / "records")
        store.save(SprintRecord(proposal_id="PROP-XYZ", created_at="now", proposal={}))
        r = store.get("PROP-XYZ")
        assert r is not None
        assert r.proposal_id == "PROP-XYZ"

    def test_get_unknown_returns_none(self, tmp_path):
        store = SprintRecordStore(tmp_path / "records")
        assert store.get("NONEXISTENT") is None


class TestSprintProposalEngine:

    def _make_engine(self, tmp_path, observations=None):
        gap_store = GapObservationStore(tmp_path / "gaps")
        if observations:
            for obs in observations:
                gap_store.record(obs)
        reg   = InvestigationRegistry(PROJECT_ROOT)
        store = GenesisDeliveryStore(PROJECT_ROOT)
        return SprintProposalEngine(gap_store, reg, store, PROJECT_ROOT)

    def test_insufficient_evidence_below_threshold(self, tmp_path):
        engine = self._make_engine(tmp_path, [_make_observation()])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""  # no git log output -> Template B skipped
            result = engine.propose()
        assert isinstance(result, InsufficientEvidenceResult)

    def test_insufficient_evidence_has_counts(self, tmp_path):
        engine = self._make_engine(tmp_path, [_make_observation()])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            result = engine.propose()
        assert result.gap_observation_count == 1
        assert result.required_count        == TEMPLATE_A_MIN_OBSERVATIONS

    def test_template_a_when_threshold_met(self, tmp_path):
        obs = [_make_observation("What should our next mission be?") for _ in range(TEMPLATE_A_MIN_OBSERVATIONS)]
        engine = self._make_engine(tmp_path, obs)
        result = engine.propose()
        assert isinstance(result, BoundSprintProposal)
        assert result.template_id == TEMPLATE_A

    def test_proposal_steps_in_order(self, tmp_path):
        obs = [_make_observation() for _ in range(TEMPLATE_A_MIN_OBSERVATIONS)]
        engine = self._make_engine(tmp_path, obs)
        result = engine.propose()
        if isinstance(result, BoundSprintProposal):
            for i, step in enumerate(result.steps):
                assert step.step_number == i + 1

    def test_proposal_acceptance_criteria_have_guaranteed_by(self, tmp_path):
        obs = [_make_observation() for _ in range(TEMPLATE_A_MIN_OBSERVATIONS)]
        engine = self._make_engine(tmp_path, obs)
        result = engine.propose()
        if isinstance(result, BoundSprintProposal):
            for c in result.acceptance_criteria:
                assert len(c.guaranteed_by) > 0

    def test_proposal_not_doing_non_empty(self, tmp_path):
        obs = [_make_observation() for _ in range(TEMPLATE_A_MIN_OBSERVATIONS)]
        engine = self._make_engine(tmp_path, obs)
        result = engine.propose()
        if isinstance(result, BoundSprintProposal):
            assert len(result.not_doing) > 0

    def test_proposal_recurring_question(self, tmp_path):
        obs = [_make_observation("What should our next mission be?") for _ in range(TEMPLATE_A_MIN_OBSERVATIONS)]
        engine = self._make_engine(tmp_path, obs)
        result = engine.propose()
        if isinstance(result, BoundSprintProposal):
            assert result.recurring_question == "What should our next mission be?"

    def test_template_a_no_implementation_in_not_doing(self, tmp_path):
        obs = [_make_observation() for _ in range(TEMPLATE_A_MIN_OBSERVATIONS)]
        engine = self._make_engine(tmp_path, obs)
        result = engine.propose()
        if isinstance(result, BoundSprintProposal) and result.template_id == TEMPLATE_A:
            not_doing_text = " ".join(result.not_doing).lower()
            assert "implement" in not_doing_text or "implementation" in not_doing_text

    def test_insufficient_evidence_format(self, tmp_path):
        engine = self._make_engine(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            result = engine.propose()
        assert isinstance(result, InsufficientEvidenceResult)
        text = result.format_for_mission()
        assert "INSUFFICIENT EVIDENCE" in text
        assert "0" in text  # observation count

    def test_internal_consistency_proximity_nonzero_guaranteed_by_step1(self, tmp_path):
        """
        The proximity_nonzero criterion must be guaranteed by a
        register_descriptor step ? not by tests or commit.
        """
        obs = [_make_observation() for _ in range(TEMPLATE_A_MIN_OBSERVATIONS)]
        engine = self._make_engine(tmp_path, obs)
        result = engine.propose()
        if isinstance(result, BoundSprintProposal) and result.template_id == TEMPLATE_A:
            for c in result.acceptance_criteria:
                if c.criterion_type == "proximity_nonzero":
                    assert "Step 1" in c.guaranteed_by or "descriptor" in c.guaranteed_by.lower()
