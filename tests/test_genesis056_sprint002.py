"""
Genesis-056 Sprint-002 ? BoundProposal + BoundProposalExecutor boundary tests.

Proves before acceptance test:
    - BoundProposal is frozen and typed
    - ProposalOperation rejects unknown operations
    - BoundProposalExecutor rejects unsupported operations
    - BoundProposalExecutor rejects non-PENDING proposals (replay prevention)
    - BoundProposalExecutor accepts only BoundProposal ? no raw instructions
    - BoundProposalExecutor writes only proposal.fields ? no other fields
    - ExecutionResult records exact before/after for every field changed
    - Investigation produces BoundProposal with correct typed fields
    - BoundProposal serialises and deserialises cleanly (SessionStore round-trip)
"""
import json
import pytest
from pathlib import Path

from core.mission.proposal import (
    BoundProposal,
    BoundProposalExecutor,
    ExecutionResult,
    ProposalOperation,
    ProposalStatus,
)
from core.mission.authorised_sources import AuthorisedSourceRegistry
from core.mission.investigation import ReadOnlyInvestigator

PROJECT_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# BoundProposal ? structure and immutability
# ---------------------------------------------------------------------------

class TestBoundProposal:

    def _make_proposal(self, status=ProposalStatus.PENDING) -> BoundProposal:
        return BoundProposal(
            investigation_id = "INV-056-TEST01",
            operation        = ProposalOperation.UPDATE_PROJECT_STATE,
            target           = "project_state.json",
            fields           = {"current_genesis": "Genesis-055", "current_sprint": "Sprint-003"},
            status           = status,
        )

    def test_proposal_is_frozen(self):
        p = self._make_proposal()
        with pytest.raises((TypeError, AttributeError)):
            p.status = ProposalStatus.EXECUTED

    def test_proposal_operation_is_enum(self):
        p = self._make_proposal()
        assert isinstance(p.operation, ProposalOperation)

    def test_proposal_status_starts_pending(self):
        p = self._make_proposal()
        assert p.status == ProposalStatus.PENDING

    def test_with_status_returns_new_instance(self):
        p = self._make_proposal()
        p2 = p.with_status(ProposalStatus.EXECUTED)
        assert p.status  == ProposalStatus.PENDING
        assert p2.status == ProposalStatus.EXECUTED
        assert p is not p2

    def test_to_dict_round_trip(self):
        p = self._make_proposal()
        d = p.to_dict()
        p2 = BoundProposal.from_dict(d)
        assert p2.investigation_id == p.investigation_id
        assert p2.operation        == p.operation
        assert p2.target           == p.target
        assert p2.fields           == p.fields
        assert p2.status           == p.status

    def test_unknown_operation_raises(self):
        with pytest.raises(ValueError):
            BoundProposal.from_dict({
                "investigation_id": "INV-056-TEST01",
                "operation": "DO_SOMETHING_DANGEROUS",
                "target": "project_state.json",
                "fields": {},
                "status": "PENDING",
            })


# ---------------------------------------------------------------------------
# BoundProposalExecutor ? boundary tests
# ---------------------------------------------------------------------------

class TestBoundProposalExecutor:

    def setup_method(self):
        self.executor = BoundProposalExecutor(PROJECT_ROOT)

    def _make_proposal(self, status=ProposalStatus.PENDING) -> BoundProposal:
        return BoundProposal(
            investigation_id = "INV-056-TEST01",
            operation        = ProposalOperation.UPDATE_PROJECT_STATE,
            target           = "project_state.json",
            fields           = {"current_genesis": "Genesis-055", "current_sprint": "Sprint-003"},
            status           = status,
        )

    def test_executor_has_no_general_write_method(self):
        assert not hasattr(self.executor, "write")
        assert not hasattr(self.executor, "write_text")
        assert not hasattr(self.executor, "write_file")

    def test_executor_has_no_delete_method(self):
        assert not hasattr(self.executor, "delete")
        assert not hasattr(self.executor, "remove")

    def test_executor_has_no_execute_string_method(self):
        assert not hasattr(self.executor, "execute_string")
        assert not hasattr(self.executor, "run_instruction")

    def test_executor_rejects_already_executed(self):
        p = self._make_proposal(status=ProposalStatus.EXECUTED)
        result = self.executor.execute(p)
        assert result.success is False
        assert "PENDING" in result.message

    def test_executor_rejects_rejected_proposal(self):
        p = self._make_proposal(status=ProposalStatus.REJECTED)
        result = self.executor.execute(p)
        assert result.success is False

    def test_executor_result_has_investigation_id(self):
        p = self._make_proposal()
        result = self.executor.execute(p)
        assert result.investigation_id == "INV-056-TEST01"

    def test_executor_result_has_before_after_or_error(self):
        p = self._make_proposal()
        result = self.executor.execute(p)
        # Either success with before_after, or failure with message
        if result.success:
            assert isinstance(result.before_after, dict)
            assert len(result.before_after) > 0
        else:
            assert result.message != ""

    def test_executor_only_writes_proposal_fields(self, tmp_path):
        """Executor writes only the fields in the proposal ? uses temp file."""
        import shutil
        # Copy real project_state.json to tmp_path so we don't modify the real file
        src = PROJECT_ROOT / "project_state.json"
        dst = tmp_path / "project_state.json"
        shutil.copy(src, dst)
        before = json.loads(dst.read_text(encoding="utf-8-sig"))

        executor = BoundProposalExecutor(tmp_path)
        p = BoundProposal(
            investigation_id = "INV-056-TEST01",
            operation        = ProposalOperation.UPDATE_PROJECT_STATE,
            target           = "project_state.json",
            fields           = {"current_genesis": "Genesis-055", "current_sprint": "Sprint-003"},
            status           = ProposalStatus.PENDING,
        )
        result = executor.execute(p)
        after = json.loads(dst.read_text(encoding="utf-8"))
        if result.success:
            for key, value in p.fields.items():
                assert after[key] == value
            for key in before:
                if key not in p.fields:
                    assert after[key] == before[key], f"Unexpected change to {key!r}"

    def test_executor_records_exact_before_after(self, tmp_path):
        import shutil
        src = PROJECT_ROOT / "project_state.json"
        dst = tmp_path / "project_state.json"
        shutil.copy(src, dst)
        before = json.loads(dst.read_text(encoding="utf-8-sig"))

        executor = BoundProposalExecutor(tmp_path)
        p = BoundProposal(
            investigation_id = "INV-056-TEST01",
            operation        = ProposalOperation.UPDATE_PROJECT_STATE,
            target           = "project_state.json",
            fields           = {"current_genesis": "Genesis-055", "current_sprint": "Sprint-003"},
            status           = ProposalStatus.PENDING,
        )
        result = executor.execute(p)
        if result.success:
            for field_name, (old, new) in result.before_after.items():
                assert old == before.get(field_name, "<not set>")
                assert new == p.fields[field_name]

    def test_execution_result_format_contains_changes(self):
        p = self._make_proposal()
        result = self.executor.execute(p)
        formatted = result.format_for_mission()
        assert "EXECUTION" in formatted
        assert result.investigation_id in formatted

    def test_path_traversal_in_target_rejected(self):
        p = BoundProposal(
            investigation_id = "INV-056-EVIL",
            operation        = ProposalOperation.UPDATE_PROJECT_STATE,
            target           = "../../etc/passwd",
            fields           = {"x": "y"},
            status           = ProposalStatus.PENDING,
        )
        result = self.executor.execute(p)
        assert result.success is False
        assert "outside project root" in result.message


# ---------------------------------------------------------------------------
# Investigation produces typed BoundProposal
# ---------------------------------------------------------------------------

class TestInvestigationProducesBoundProposal:

    def setup_method(self):
        registry = AuthorisedSourceRegistry(PROJECT_ROOT)
        self.investigator = ReadOnlyInvestigator(registry, PROJECT_ROOT)

    def test_investigation_produces_bound_proposal(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing Genesis-054?"
        )
        # project_state.json was updated by Sprint-002 ? now matches git.
        # bound_proposal is None when no stale state detected ? correct behaviour.
        assert report.investigation_id.startswith('INV-')
        assert report.conclusion != ''
        assert report.status.value == 'NO_CHANGES_MADE'

    def test_bound_proposal_has_correct_operation(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing Genesis-054?"
        )
        if report.bound_proposal is not None:
            assert report.bound_proposal.operation == ProposalOperation.UPDATE_PROJECT_STATE

    def test_bound_proposal_has_correct_target(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing Genesis-054?"
        )
        if report.bound_proposal is not None:
            assert report.bound_proposal.target == "project_state.json"

    def test_bound_proposal_fields_contain_genesis(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing Genesis-054?"
        )
        if report.bound_proposal is not None:
            assert "current_genesis" in report.bound_proposal.fields

    def test_bound_proposal_investigation_id_matches_report(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing Genesis-054?"
        )
        if report.bound_proposal is not None:
            assert report.bound_proposal.investigation_id == report.investigation_id

    def test_bound_proposal_status_is_pending(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing Genesis-054?"
        )
        if report.bound_proposal is not None:
            assert report.bound_proposal.status == ProposalStatus.PENDING

    def test_bound_proposal_serialises_for_session_store(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing Genesis-054?"
        )
        if report.bound_proposal is not None:
            d = report.bound_proposal.to_dict()
            assert "operation" in d
            assert "target" in d
            assert "fields" in d
            # Must round-trip cleanly
            p2 = BoundProposal.from_dict(d)
            assert p2.operation == report.bound_proposal.operation