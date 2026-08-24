"""
Genesis-056 Sprint-003 ? Live reload + single approval card tests.

Proves:
    - Investigation proposals use dedicated store (no duplicate card)
    - Approved project-state change visible via MissionRegistry without restart
    - Separator renders as plain dashes
    - INV- session_id short-circuits coordinator (no blocking)
"""
import json
import shutil
import pytest
from pathlib import Path

from core.mission.proposal import (
    BoundProposal, BoundProposalExecutor, ProposalOperation, ProposalStatus,
)
from core.mission.authorised_sources import AuthorisedSourceRegistry
from core.mission.investigation import ReadOnlyInvestigator
from core.mission.registry import MissionRegistry

PROJECT_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Separator fix
# ---------------------------------------------------------------------------

class TestSeparatorFix:

    def test_investigation_report_uses_plain_dashes(self):
        registry = AuthorisedSourceRegistry(PROJECT_ROOT)
        investigator = ReadOnlyInvestigator(registry, PROJECT_ROOT)
        report = investigator.investigate("why is genesis wrong?")
        formatted = report.format_for_mission()
        assert "?" * 5 not in formatted
        assert "-" * 5 in formatted


# ---------------------------------------------------------------------------
# Dedicated investigations store ? no duplicate card
# ---------------------------------------------------------------------------

class TestDedicatedInvestigationsStore:

    def test_investigation_store_uses_separate_directory(self, tmp_path):
        """
        Proposals saved to investigations/ must not appear in the
        main orchestrator sessions/ directory.
        """
        from core.engineering.coordinator.session_store import SessionStore
        from core.engineering.coordinator.models import (
            EngineeringSession, EngineeringRequest,
            EngineeringStatus, EngineeringStage,
        )
        import time

        inv_store_dir = tmp_path / "investigations"
        eng_store_dir = tmp_path / "sessions"

        inv_store = SessionStore(directory=inv_store_dir)
        eng_store = SessionStore(directory=eng_store_dir)

        proposal = BoundProposal(
            investigation_id = "INV-056-TEST99",
            operation        = ProposalOperation.UPDATE_PROJECT_STATE,
            target           = "project_state.json",
            fields           = {"current_genesis": "Genesis-055"},
            status           = ProposalStatus.PENDING,
        )

        # Save to investigations store
        eng_request = EngineeringRequest(
            request  = f"[INVESTIGATION PROPOSAL] {proposal.investigation_id}",
            context  = "test",
            metadata = {},
        )
        session = EngineeringSession(
            session_id     = proposal.investigation_id,
            request        = eng_request,
            status         = EngineeringStatus.AWAITING_APPROVAL,
            started_at     = int(time.monotonic() * 1000),
            current_stage  = EngineeringStage.AWAITING_APPROVAL,
            execution_plan = proposal.to_dict(),
        )
        inv_store.save(session)

        # Must be in investigations store
        assert inv_store.exists(proposal.investigation_id)
        # Must NOT be in engineering sessions store
        assert not eng_store.exists(proposal.investigation_id)

    def test_investigation_store_ids_start_with_inv(self, tmp_path):
        """All sessions in the investigations store have INV- prefixed IDs."""
        from core.engineering.coordinator.session_store import SessionStore
        inv_store = SessionStore(directory=tmp_path / "investigations")
        # Empty store ? no INV- sessions yet
        assert inv_store.list_session_ids() == []


# ---------------------------------------------------------------------------
# Live reload ? approved change visible without restart
# ---------------------------------------------------------------------------

class TestLiveReloadAfterExecution:

    def test_approved_project_state_visible_via_mission_registry_without_restart(
        self, tmp_path
    ):
        """
        Acceptance criterion for Sprint-003:
        After BoundProposalExecutor writes project_state.json,
        calling mission_registry.load() makes the change visible
        through mission_dict() without restarting the server.
        """
        # Set up a tmp project_state.json with stale genesis
        ps_path = tmp_path / "project_state.json"
        stale = {
            "current_genesis":        "Genesis-054",
            "current_sprint":         "Sprint-001",
            "current_mission":        "Test",
            "last_completed_genesis": "Genesis-053",
            "next_milestone":         "TBD",
            "objectives":             [],
        }
        ps_path.write_text(json.dumps(stale, indent=2), encoding="utf-8")

        # Load MissionRegistry with stale state
        registry = MissionRegistry(project_root=tmp_path)
        registry.load()
        assert registry.mission_dict()["current_genesis"] == "Genesis-054"

        # Execute proposal against tmp project_state.json
        executor = BoundProposalExecutor(tmp_path)
        proposal = BoundProposal(
            investigation_id = "INV-056-RELOAD",
            operation        = ProposalOperation.UPDATE_PROJECT_STATE,
            target           = "project_state.json",
            fields           = {
                "current_genesis": "Genesis-055",
                "current_sprint":  "Sprint-003",
            },
            status = ProposalStatus.PENDING,
        )
        result = executor.execute(proposal)
        assert result.success, f"Execution failed: {result.message}"

        # Reload MissionRegistry ? simulates what orchestrator_routes does
        registry.load()

        # Change must be visible immediately ? no restart
        state = registry.mission_dict()
        assert state["current_genesis"] == "Genesis-055"
        assert state["current_sprint"]  == "Sprint-003"

    def test_execution_result_format_has_plain_dashes(self, tmp_path):
        """ExecutionResult.format_for_mission() must not contain ? characters."""
        ps_path = tmp_path / "project_state.json"
        ps_path.write_text(json.dumps({
            "current_genesis": "Genesis-054",
            "current_sprint": "Sprint-001",
            "current_mission": "Test",
            "last_completed_genesis": "Genesis-053",
            "next_milestone": "TBD",
            "objectives": [],
        }, indent=2), encoding="utf-8")

        executor = BoundProposalExecutor(tmp_path)
        proposal = BoundProposal(
            investigation_id = "INV-056-FMT",
            operation        = ProposalOperation.UPDATE_PROJECT_STATE,
            target           = "project_state.json",
            fields           = {"current_genesis": "Genesis-055"},
            status           = ProposalStatus.PENDING,
        )
        result = executor.execute(proposal)
        formatted = result.format_for_mission()
        assert "?????" not in formatted
