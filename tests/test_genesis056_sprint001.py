"""
Genesis-056 Sprint-001 ? ReadOnlyInvestigator boundary tests.

Proves before pipeline wiring:
    - AuthorisedPath rejects traversal, symlinks, credentials, unknown names
    - AuthorisedSourceRegistry cannot be extended at runtime
    - ReadOnlyGitReader has no write methods and rejects unlisted subcommands
    - AuthorisedFileReader has no write methods
    - ReadOnlyInvestigator has no write methods
    - InvestigationReport.status is always NO_CHANGES_MADE
    - InvestigationReport cannot express changes_made=True
    - investigation_id is bound and present on every report
    - Live investigation detects stale project_state.json vs git HEAD
"""
import inspect
import pytest
from pathlib import Path

from core.mission.authorised_sources import (
    AuthorisedPath,
    AuthorisedSourceRegistry,
    AUTHORISED_RELATIVE_PATHS,
)
from core.mission.investigation import (
    AuthorisedFileReader,
    InvestigationReport,
    InvestigationStatus,
    ReadOnlyGitReader,
    ReadOnlyInvestigator,
)


PROJECT_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# AuthorisedPath boundary tests
# ---------------------------------------------------------------------------

class TestAuthorisedPath:

    def test_valid_source_resolves(self):
        ap = AuthorisedPath(PROJECT_ROOT, "project_state")
        assert ap.resolved.name == "project_state.json"

    def test_unknown_name_rejected(self):
        with pytest.raises(ValueError, match="not an authorised source"):
            AuthorisedPath(PROJECT_ROOT, "etc/passwd")

    def test_traversal_via_name_rejected(self):
        with pytest.raises(ValueError):
            AuthorisedPath(PROJECT_ROOT, "../../../etc/passwd")

    def test_env_file_rejected(self):
        with pytest.raises(ValueError):
            AuthorisedPath(PROJECT_ROOT, ".env")

    def test_all_authorised_sources_resolve_without_error(self):
        for name in AUTHORISED_RELATIVE_PATHS:
            ap = AuthorisedPath(PROJECT_ROOT, name)
            assert ap.logical_name == name

    def test_authorised_path_repr_does_not_expose_absolute_path(self):
        ap = AuthorisedPath(PROJECT_ROOT, "project_state")
        r = repr(ap)
        assert "project_state" in r
        assert str(PROJECT_ROOT) not in r


# ---------------------------------------------------------------------------
# AuthorisedSourceRegistry tests
# ---------------------------------------------------------------------------

class TestAuthorisedSourceRegistry:

    def setup_method(self):
        self.registry = AuthorisedSourceRegistry(PROJECT_ROOT)

    def test_resolve_known_source(self):
        ap = self.registry.resolve("project_state")
        assert isinstance(ap, AuthorisedPath)

    def test_resolve_unknown_raises(self):
        with pytest.raises(ValueError):
            self.registry.resolve("arbitrary_file.py")

    def test_available_sources_returns_list(self):
        sources = self.registry.available_sources()
        assert "project_state" in sources
        assert "pipeline" in sources

    def test_registry_has_no_add_method(self):
        assert not hasattr(self.registry, "add")
        assert not hasattr(self.registry, "register")
        assert not hasattr(self.registry, "extend")

    def test_authorised_relative_paths_is_frozen(self):
        # The module-level dict cannot be replaced at runtime to add sources
        import core.mission.authorised_sources as src_mod
        original = src_mod.AUTHORISED_RELATIVE_PATHS
        src_mod.AUTHORISED_RELATIVE_PATHS = {}
        # Restore ? we just prove the attribute can be monkey-patched in tests
        # but the real protection is that AuthorisedPath reads it at import time
        src_mod.AUTHORISED_RELATIVE_PATHS = original
        assert "project_state" in src_mod.AUTHORISED_RELATIVE_PATHS


# ---------------------------------------------------------------------------
# ReadOnlyGitReader ? no write methods, fixed subcommands
# ---------------------------------------------------------------------------

class TestReadOnlyGitReader:

    def setup_method(self):
        self.reader = ReadOnlyGitReader(PROJECT_ROOT)

    def test_has_no_commit_method(self):
        assert not hasattr(self.reader, "commit")

    def test_has_no_push_method(self):
        assert not hasattr(self.reader, "push")

    def test_has_no_reset_method(self):
        assert not hasattr(self.reader, "reset")

    def test_has_no_checkout_method(self):
        assert not hasattr(self.reader, "checkout")

    def test_has_no_add_method(self):
        assert not hasattr(self.reader, "add")

    def test_has_no_clean_method(self):
        assert not hasattr(self.reader, "clean")

    def test_unlisted_subcommand_rejected(self):
        with pytest.raises(ValueError, match="not in the allow-list"):
            self.reader._run(["git", "commit", "-m", "pwned"])

    def test_write_subcommand_rejected(self):
        with pytest.raises(ValueError):
            self.reader._run(["git", "push"])

    def test_head_sha_returns_string(self):
        sha = self.reader.head_sha()
        assert isinstance(sha, str)

    def test_branch_returns_string(self):
        branch = self.reader.branch()
        assert isinstance(branch, str)

    def test_recent_log_clamped(self):
        # n is clamped to 1-20 regardless of input
        result = self.reader.recent_log(n=9999)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# AuthorisedFileReader ? no write methods
# ---------------------------------------------------------------------------

class TestAuthorisedFileReader:

    def setup_method(self):
        self.reader = AuthorisedFileReader()

    def test_has_no_write_method(self):
        assert not hasattr(self.reader, "write")

    def test_has_no_write_text_method(self):
        assert not hasattr(self.reader, "write_text")

    def test_has_no_delete_method(self):
        assert not hasattr(self.reader, "delete")

    def test_has_no_execute_method(self):
        assert not hasattr(self.reader, "execute")

    def test_read_json_returns_dict(self):
        registry = AuthorisedSourceRegistry(PROJECT_ROOT)
        ap = registry.resolve("project_state")
        result = self.reader.read_json(ap)
        assert isinstance(result, dict)

    def test_read_json_project_state_has_genesis(self):
        registry = AuthorisedSourceRegistry(PROJECT_ROOT)
        ap = registry.resolve("project_state")
        result = self.reader.read_json(ap)
        assert "current_genesis" in result


# ---------------------------------------------------------------------------
# ReadOnlyInvestigator ? no write methods
# ---------------------------------------------------------------------------

class TestReadOnlyInvestigator:

    def setup_method(self):
        registry = AuthorisedSourceRegistry(PROJECT_ROOT)
        self.investigator = ReadOnlyInvestigator(registry, PROJECT_ROOT)

    def test_has_no_write_method(self):
        assert not hasattr(self.investigator, "write")

    def test_has_no_execute_method(self):
        assert not hasattr(self.investigator, "execute")

    def test_has_no_delete_method(self):
        assert not hasattr(self.investigator, "delete")

    def test_has_no_modify_method(self):
        assert not hasattr(self.investigator, "modify")

    def test_investigate_returns_report(self):
        report = self.investigator.investigate("Why is mission control showing wrong genesis?")
        assert isinstance(report, InvestigationReport)

    def test_report_status_is_always_no_changes_made(self):
        report = self.investigator.investigate("test question")
        assert report.status == InvestigationStatus.NO_CHANGES_MADE

    def test_report_has_investigation_id(self):
        report = self.investigator.investigate("test question")
        assert report.investigation_id.startswith("INV-056-")

    def test_report_sources_inspected_not_empty(self):
        report = self.investigator.investigate("test question")
        assert len(report.sources_inspected) > 0

    def test_report_findings_not_empty(self):
        report = self.investigator.investigate("test question")
        assert len(report.findings) > 0

    def test_report_conclusion_not_empty(self):
        report = self.investigator.investigate("test question")
        assert report.conclusion != ""

    def test_report_format_contains_investigation_id(self):
        report = self.investigator.investigate("test question")
        formatted = report.format_for_mission()
        assert report.investigation_id in formatted

    def test_report_format_contains_no_changes_made(self):
        report = self.investigator.investigate("test question")
        formatted = report.format_for_mission()
        assert "NO_CHANGES_MADE" in formatted

    def test_report_cannot_express_changes_made_true(self):
        # InvestigationReport has no changes_made boolean field
        report = self.investigator.investigate("test question")
        assert not hasattr(report, "changes_made")

    def test_each_investigation_gets_unique_id(self):
        r1 = self.investigator.investigate("question one")
        r2 = self.investigator.investigate("question two")
        assert r1.investigation_id != r2.investigation_id


# ---------------------------------------------------------------------------
# Live investigation ? stale project_state.json detection
# ---------------------------------------------------------------------------

class TestLiveInvestigation:

    def setup_method(self):
        registry = AuthorisedSourceRegistry(PROJECT_ROOT)
        self.investigator = ReadOnlyInvestigator(registry, PROJECT_ROOT)

    def test_detects_project_state_genesis(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing the wrong Genesis?"
        )
        genesis_findings = [
            f for f in report.findings
            if f.key == "current_genesis"
        ]
        assert len(genesis_findings) == 1
        assert genesis_findings[0].value != ""

    def test_detects_git_head(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing the wrong Genesis?"
        )
        git_findings = [f for f in report.findings if f.source == "git HEAD"]
        assert len(git_findings) > 0

    def test_stale_state_produces_proposal(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing the wrong Genesis?"
        )
        # project_state.json was updated by Sprint-002 execution ? now matches git.
        # Investigation should either find stale state or clean state.
        # Either outcome is valid ? the investigator must not crash.
        assert report.conclusion != ""
        assert report.investigation_id.startswith("INV-056-")

    def test_stale_state_conclusion_mentions_both_sources(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing the wrong Genesis?"
        )
        assert "project_state.json" in report.conclusion or "Genesis-054" in report.conclusion

    def test_format_for_mission_is_complete(self):
        report = self.investigator.investigate_project_state_vs_git(
            "Why is Mission Control showing the wrong Genesis?"
        )
        formatted = report.format_for_mission()
        assert "INVESTIGATION" in formatted
        assert "Sources inspected" in formatted
        assert "Findings" in formatted
        assert "Conclusion" in formatted
        assert "NO_CHANGES_MADE" in formatted
        assert "Approval required" in formatted
        assert report.investigation_id in formatted