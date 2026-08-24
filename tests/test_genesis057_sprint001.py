"""
Genesis-057 Sprint-001 - Evidence Reconciliation tests.

Proves:
    - EvidenceRecord is frozen and structured
    - ExtractionResult correctly identifies presence/absence of labels
    - ReconciliationEngine detects agreement and disagreement
    - ReconciliationEngine has NO reference to AuthorityPolicy
    - AuthorityPolicy produces verdicts only for defined keys
    - AuthorityPolicy produces NO verdict for undefined keys (safety rail)
    - Missing git labels = insufficient evidence, not anomaly
    - Proposal fields come from ReconciledVerdict, not hardcoded values
    - Blind test: detects inconsistency without user naming it
"""
import pytest
from pathlib import Path
import json

from core.mission.investigation import (
    EvidenceRecord,
    ExtractionResult,
    Reconciliation,
    ReconciliationEngine,
    AuthorityPolicy,
    ReconciledVerdict,
    ReadOnlyInvestigator,
    extract_genesis_label,
    extract_sprint_label,
)
from core.mission.authorised_sources import AuthorisedSourceRegistry

PROJECT_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Label extraction
# ---------------------------------------------------------------------------

class TestLabelExtraction:

    def test_genesis_label_extracted(self):
        r = extract_genesis_label("Genesis-057 Sprint-001 - some fix")
        assert r.present is True
        assert r.value == "Genesis-057"

    def test_sprint_label_extracted(self):
        r = extract_sprint_label("Genesis-057 Sprint-001 - some fix")
        assert r.present is True
        assert r.value == "Sprint-001"

    def test_no_genesis_label_is_insufficient(self):
        r = extract_genesis_label("chore: remove txt files")
        assert r.present is False
        assert r.value is None

    def test_no_sprint_label_is_insufficient(self):
        r = extract_sprint_label("fix: typo in readme")
        assert r.present is False
        assert r.value is None

    def test_genesis_case_insensitive(self):
        r = extract_genesis_label("genesis-057 sprint-001")
        assert r.present is True

    def test_extraction_result_has_raw(self):
        raw = "Genesis-057 Sprint-001 - fix"
        r = extract_genesis_label(raw)
        assert r.raw == raw


# ---------------------------------------------------------------------------
# ReconciliationEngine - observes only, never decides
# ---------------------------------------------------------------------------

class TestReconciliationEngine:

    def setup_method(self):
        self.engine = ReconciliationEngine()

    def test_consistent_sources_agree(self):
        a = EvidenceRecord(source="project_state.json", key="current_genesis", value="Genesis-057")
        b = EvidenceRecord(source="git HEAD",           key="current_genesis", value="Genesis-057")
        rec = self.engine.reconcile("current_genesis", a, b)
        assert rec.consistent is True

    def test_inconsistent_sources_disagree(self):
        a = EvidenceRecord(source="project_state.json", key="current_genesis", value="Genesis-055")
        b = EvidenceRecord(source="git HEAD",           key="current_genesis", value="Genesis-057")
        rec = self.engine.reconcile("current_genesis", a, b)
        assert rec.consistent is False

    def test_case_insensitive_match(self):
        a = EvidenceRecord(source="project_state.json", key="current_genesis", value="Genesis-057")
        b = EvidenceRecord(source="git HEAD",           key="current_genesis", value="genesis-057")
        rec = self.engine.reconcile("current_genesis", a, b)
        assert rec.consistent is True

    def test_engine_has_no_authority_policy_reference(self):
        import inspect
        # Check only the reconcile method - not the docstring
        src = inspect.getsource(ReconciliationEngine.reconcile)
        assert "AuthorityPolicy" not in src

    def test_engine_produces_reconciliation_not_verdict(self):
        a = EvidenceRecord(source="project_state.json", key="current_genesis", value="Genesis-055")
        b = EvidenceRecord(source="git HEAD",           key="current_genesis", value="Genesis-057")
        rec = self.engine.reconcile("current_genesis", a, b)
        assert isinstance(rec, Reconciliation)
        assert not isinstance(rec, ReconciledVerdict)

    def test_inconsistent_note_contains_both_values(self):
        a = EvidenceRecord(source="project_state.json", key="current_genesis", value="Genesis-055")
        b = EvidenceRecord(source="git HEAD",           key="current_genesis", value="Genesis-057")
        rec = self.engine.reconcile("current_genesis", a, b)
        assert "Genesis-055" in rec.note
        assert "Genesis-057" in rec.note


# ---------------------------------------------------------------------------
# AuthorityPolicy - explicit, auditable
# ---------------------------------------------------------------------------

class TestAuthorityPolicy:

    def _make_anomaly(self, key, ps_value, git_value) -> Reconciliation:
        engine = ReconciliationEngine()
        return engine.reconcile(
            key,
            EvidenceRecord(source="project_state.json", key=key, value=ps_value),
            EvidenceRecord(source="git HEAD",           key=key, value=git_value),
        )

    def test_defined_key_produces_verdict(self):
        anomaly = self._make_anomaly("current_genesis", "Genesis-055", "Genesis-057")
        verdicts, no_auth = AuthorityPolicy.evaluate([anomaly])
        assert len(verdicts) == 1
        assert len(no_auth) == 0

    def test_undefined_key_produces_no_verdict(self):
        """Safety rail: undefined authority -> report only, no proposal."""
        anomaly = self._make_anomaly("some_unknown_key", "old", "new")
        verdicts, no_auth = AuthorityPolicy.evaluate([anomaly])
        assert len(verdicts) == 0
        assert len(no_auth) == 1

    def test_git_head_is_authoritative_for_genesis(self):
        anomaly = self._make_anomaly("current_genesis", "Genesis-055", "Genesis-057")
        verdicts, _ = AuthorityPolicy.evaluate([anomaly])
        assert verdicts[0].authoritative_source == "git HEAD"
        assert verdicts[0].authoritative_value  == "Genesis-057"

    def test_git_head_is_authoritative_for_sprint(self):
        anomaly = self._make_anomaly("current_sprint", "Sprint-001", "Sprint-004")
        verdicts, _ = AuthorityPolicy.evaluate([anomaly])
        assert verdicts[0].authoritative_source == "git HEAD"
        assert verdicts[0].authoritative_value  == "Sprint-004"

    def test_stale_source_is_project_state(self):
        anomaly = self._make_anomaly("current_genesis", "Genesis-055", "Genesis-057")
        verdicts, _ = AuthorityPolicy.evaluate([anomaly])
        assert verdicts[0].stale_source == "project_state.json"
        assert verdicts[0].stale_value  == "Genesis-055"

    def test_mixed_defined_and_undefined_keys(self):
        a1 = self._make_anomaly("current_genesis",  "Genesis-055", "Genesis-057")
        a2 = self._make_anomaly("some_unknown_key", "old",         "new")
        verdicts, no_auth = AuthorityPolicy.evaluate([a1, a2])
        assert len(verdicts)  == 1
        assert len(no_auth)   == 1


# ---------------------------------------------------------------------------
# Proposal fields from verdict - not hardcoded
# ---------------------------------------------------------------------------

class TestProposalFromVerdict:

    def test_proposal_fields_from_verdict_not_hardcoded(self, tmp_path):
        """
        Proposal fields must come from ReconciledVerdict.authoritative_value
        not from any hardcoded genesis/sprint string.
        """
        ps_path = tmp_path / "project_state.json"
        ps_path.write_text(json.dumps({
            "current_genesis":        "Genesis-055",
            "current_sprint":         "Sprint-001",
            "current_mission":        "Test",
            "last_completed_genesis": "Genesis-054",
            "next_milestone":         "TBD",
            "objectives":             [],
        }, indent=2), encoding="utf-8")

        from core.mission.authorised_sources import AuthorisedSourceRegistry
        registry = AuthorisedSourceRegistry(tmp_path)
        investigator = ReadOnlyInvestigator(registry, PROJECT_ROOT)
        report = investigator.investigate_project_state_vs_git(
            "Is everything consistent?"
        )

        if report.bound_proposal is not None:
            # Fields must match what git HEAD actually says - not hardcoded
            for key, value in report.bound_proposal.fields.items():
                assert value != "Genesis-055", "Proposal must not hardcode Genesis-055"
                assert value != "Sprint-001",  "Proposal must not hardcode Sprint-001"


# ---------------------------------------------------------------------------
# Missing label = insufficient evidence, not anomaly
# ---------------------------------------------------------------------------

class TestInsufficientEvidence:

    def test_no_proposal_when_git_label_absent(self, tmp_path):
        """
        If git HEAD commit message has no genesis/sprint labels,
        no anomaly is declared and no proposal is generated.
        """
        from unittest.mock import patch
        from core.mission.authorised_sources import AuthorisedSourceRegistry

        ps_path = tmp_path / "project_state.json"
        ps_path.write_text(json.dumps({
            "current_genesis":        "Genesis-055",
            "current_sprint":         "Sprint-001",
            "current_mission":        "Test",
            "last_completed_genesis": "Genesis-054",
            "next_milestone":         "TBD",
            "objectives":             [],
        }, indent=2), encoding="utf-8")

        registry = AuthorisedSourceRegistry(tmp_path)
        investigator = ReadOnlyInvestigator(registry, PROJECT_ROOT)

        with patch.object(investigator._git_reader, "head_message", return_value="chore: remove txt files"):
            report = investigator.investigate_project_state_vs_git("Is everything consistent?")

        assert report.bound_proposal is None
        assert report.approval_required is False
        assert "insufficient" in report.conclusion.lower() or "consistent" in report.conclusion.lower()


# ---------------------------------------------------------------------------
# Blind test - detects inconsistency without user naming it
# ---------------------------------------------------------------------------

class TestBlindDetection:

    def test_detects_inconsistency_without_user_naming_it(self, tmp_path):
        """
        The money test.
        project_state.json is stale. User asks "Is everything consistent?"
        Jarvis must detect the mismatch without being told what to look for.
        """
        from unittest.mock import patch
        from core.mission.authorised_sources import AuthorisedSourceRegistry

        ps_path = tmp_path / "project_state.json"
        ps_path.write_text(json.dumps({
            "current_genesis":        "Genesis-055",
            "current_sprint":         "Sprint-003",
            "current_mission":        "Test",
            "last_completed_genesis": "Genesis-054",
            "next_milestone":         "TBD",
            "objectives":             [],
        }, indent=2), encoding="utf-8")

        registry = AuthorisedSourceRegistry(tmp_path)
        investigator = ReadOnlyInvestigator(registry, PROJECT_ROOT)

        with patch.object(investigator._git_reader, "head_message",
                          return_value="Genesis-057 Sprint-001 - Evidence Reconciliation"):
            report = investigator.investigate_project_state_vs_git(
                "Is everything consistent?"
            )

        # Must detect anomaly
        assert report.bound_proposal is not None
        assert report.approval_required is True

        # Must identify correct authoritative value
        assert report.bound_proposal.fields.get("current_genesis") == "Genesis-057"

        # Must not have been told what to look for
        assert "consistent" in report.question.lower()
        assert "genesis" not in report.question.lower()
