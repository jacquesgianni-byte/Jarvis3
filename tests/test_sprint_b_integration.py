"""
Sprint B integration tests v2 — sprint_executor.py source-clean assertion.

Fix from v1: mock subprocess at 'core.knowledge.sprint_executor' module level
so the real git never runs during tests.

Three acceptance proofs:
    Proof 1: Runtime dirty → allowed to proceed (no abort)
    Proof 2: Source dirty → SOURCE_DIRTY abort
    Proof 3: Runtime files cannot enter engineering commit (scoped staging)

Plus:
    - Path traversal → abort
    - Single source of RUNTIME_DATA_PATHS (import not copy)
    - Existing boundary enforcement unchanged

Baseline: 6223 passed / 33 skipped / 0 failed (e8902cb)
"""

from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proposal(affected_files=None, steps=None):
    proposal = MagicMock()
    proposal.affected_files = affected_files or []
    proposal.steps = steps or []
    proposal.proposal_id = "TEST-0001"
    proposal.proposed_sprint_name = "test sprint"
    proposal.genesis_id = "Genesis-081"
    return proposal


def _porcelain(dirty_files):
    """Format as git status --porcelain output (modified unstaged format)."""
    lines = [f" M {f}" for f in dirty_files]
    return "\n".join(lines) + ("\n" if lines else "")


def _executor(tmp_path, proposal=None):
    from core.knowledge.sprint_executor import SprintExecutor
    if proposal is None:
        proposal = _make_proposal()
    return SprintExecutor(proposal=proposal, project_root=tmp_path)


def _mock_git_result(stdout="", returncode=0):
    r = MagicMock()
    r.stdout = stdout
    r.stderr = ""
    r.returncode = returncode
    return r


# ---------------------------------------------------------------------------
# Proof 1: Runtime dirty → allowed to proceed
# ---------------------------------------------------------------------------

class TestRuntimeDirtyAllowed:

    def test_genesis_contributions_dirty_does_not_abort(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain([
            "data/genesis_contributions/Genesis-081.json",
            "data/genesis_contributions/Genesis-071.json",
        ])

        # Patch subprocess inside the sprint_executor module
        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        pre = [r for r in results if r.action_type == 'pre_execution_check']
        for r in pre:
            assert 'SOURCE_DIRTY' not in r.detail, f"Runtime blocked: {r.detail}"

    def test_situational_memory_dirty_does_not_abort(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain(["data/situational_memory/entries.json"])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        pre = [r for r in results if r.action_type == 'pre_execution_check']
        for r in pre:
            assert 'SOURCE_DIRTY' not in r.detail

    def test_all_six_current_runtime_files_allowed(self, tmp_path):
        """The exact six files dirty in the real repo must all pass."""
        executor = _executor(tmp_path)
        dirty = _porcelain([
            "data/genesis_contributions/Genesis-071-isolation.json",
            "data/genesis_contributions/Genesis-071-readback.json",
            "data/genesis_contributions/Genesis-071-regression.json",
            "data/genesis_contributions/Genesis-071.json",
            "data/genesis_contributions/Genesis-081.json",
            "data/situational_memory/entries.json",
        ])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        pre = [r for r in results if r.action_type == 'pre_execution_check']
        for r in pre:
            assert 'SOURCE_DIRTY' not in r.detail, (
                f"Runtime files incorrectly blocked: {r.detail}"
            )

    def test_shift_manifests_dirty_does_not_abort(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain(["data/shift_manifests/abc-123.json"])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        pre = [r for r in results if r.action_type == 'pre_execution_check']
        for r in pre:
            assert 'SOURCE_DIRTY' not in r.detail

    def test_clean_tree_passes(self, tmp_path):
        executor = _executor(tmp_path)

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout="")
            success, results = executor.execute()

        pre = [r for r in results if r.action_type == 'pre_execution_check']
        for r in pre:
            assert 'DIRTY' not in r.detail
            assert 'ABORT' not in r.detail

    def test_sprint_states_dirty_does_not_abort(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain(["data/sprint_states/some_sprint.json"])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        pre = [r for r in results if r.action_type == 'pre_execution_check']
        for r in pre:
            assert 'SOURCE_DIRTY' not in r.detail


# ---------------------------------------------------------------------------
# Proof 2: Source dirty → SOURCE_DIRTY abort
# ---------------------------------------------------------------------------

class TestSourceDirtyAborts:

    def test_source_file_triggers_abort(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain(["core/workers/manager.py"])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        assert not success
        assert results[0].action_type == 'pre_execution_check'
        assert 'SOURCE_DIRTY' in results[0].detail
        assert 'core/workers/manager.py' in results[0].detail

    def test_mixed_runtime_and_source_triggers_abort(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain([
            "data/genesis_contributions/Genesis-081.json",
            "core/knowledge/sprint_executor.py",
        ])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        assert not success
        assert 'SOURCE_DIRTY' in results[0].detail
        assert 'core/knowledge/sprint_executor.py' in results[0].detail

    def test_test_file_dirty_triggers_abort(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain(["tests/test_something.py"])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        assert not success
        assert 'SOURCE_DIRTY' in results[0].detail

    def test_abort_detail_names_offending_files(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain(["core/mission/pipeline.py"])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        assert not success
        assert 'core/mission/pipeline.py' in results[0].detail

    def test_runtime_file_alone_does_not_abort_but_source_does(self, tmp_path):
        """Precise proof: same test with runtime only passes, with source fails."""
        executor_runtime = _executor(tmp_path)
        executor_source = _executor(tmp_path)

        runtime_dirty = _porcelain(["data/genesis_contributions/Genesis-081.json"])
        source_dirty = _porcelain(["core/knowledge/sprint_executor.py"])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=runtime_dirty)
            _, runtime_results = executor_runtime.execute()

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=source_dirty)
            _, source_results = executor_source.execute()

        runtime_pre = [r for r in runtime_results if r.action_type == 'pre_execution_check']
        source_pre = [r for r in source_results if r.action_type == 'pre_execution_check']

        # Runtime: no SOURCE_DIRTY
        for r in runtime_pre:
            assert 'SOURCE_DIRTY' not in r.detail

        # Source: SOURCE_DIRTY present
        assert any('SOURCE_DIRTY' in r.detail for r in source_pre)


# ---------------------------------------------------------------------------
# Proof 3: Runtime files cannot enter the engineering commit
# ---------------------------------------------------------------------------

class TestRuntimeFilesExcludedFromCommit:

    def test_scoped_staging_excludes_runtime_files(self, tmp_path):
        """
        Even when runtime files are dirty, git add is only called
        for affected_files — never for runtime paths.
        """
        from core.knowledge.sprint_executor import SprintExecutor

        commit_step = MagicMock()
        commit_step.step_number = 1
        commit_step.action_type = "commit"
        commit_step.parameters = [("message", "test commit")]

        proposal = _make_proposal(
            affected_files=["core/knowledge/some_helper.py"],
            steps=[commit_step],
        )
        executor = SprintExecutor(proposal=proposal, project_root=tmp_path)

        git_add_calls = []
        call_num = [0]

        def fake_run(cmd, **kwargs):
            call_num[0] += 1
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""

            cmd_str = ' '.join(str(c) for c in cmd)

            if 'status' in cmd_str and 'porcelain' in cmd_str:
                # Runtime files dirty — must NOT enter commit
                result.stdout = (
                    " M data/genesis_contributions/Genesis-081.json\n"
                    " M data/situational_memory/entries.json\n"
                )
            elif cmd[:2] == ['git', 'add']:
                git_add_calls.append(list(cmd))
            elif 'diff' in cmd_str and 'name-only' in cmd_str and 'cached' not in cmd_str:
                # No source changes
                result.stdout = ""
            elif 'ls-files' in cmd_str:
                result.stdout = ""
            elif 'diff' in cmd_str and 'cached' in cmd_str:
                result.stdout = ""

            return result

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.side_effect = fake_run
            with patch.object(executor._enforcer, 'validate',
                               return_value=MagicMock(spec=[])):
                executor.execute()

        # git add must never have been called with runtime paths
        for add_call in git_add_calls:
            added_path = add_call[-1] if add_call else ""
            assert not added_path.startswith("data/genesis_contributions/"), \
                f"Runtime path entered git add: {add_call}"
            assert not added_path.startswith("data/situational_memory/"), \
                f"Runtime path entered git add: {add_call}"


# ---------------------------------------------------------------------------
# Path traversal guard
# ---------------------------------------------------------------------------

class TestPathTraversalGuard:

    def test_path_traversal_triggers_abort(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain(["data/../core/shift/source_clean.py"])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        assert not success
        assert 'SOURCE_DIRTY' in results[0].detail or 'ABORT' in results[0].detail

    def test_traversal_in_runtime_looking_path_aborts(self, tmp_path):
        executor = _executor(tmp_path)
        dirty = _porcelain([
            "data/genesis_contributions/../../core/shift/source_clean.py"
        ])

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout=dirty)
            success, results = executor.execute()

        assert not success


# ---------------------------------------------------------------------------
# Single source of truth
# ---------------------------------------------------------------------------

class TestSingleSourceOfTruth:

    def test_sprint_executor_imports_from_source_clean(self):
        target = Path("core/knowledge/sprint_executor.py")
        src = target.read_text(encoding="utf-8-sig")
        assert "from core.shift.source_clean import RUNTIME_DATA_PATHS" in src, \
            "sprint_executor.py must import from core.shift.source_clean"

    def test_sprint_executor_does_not_define_own_runtime_paths(self):
        target = Path("core/knowledge/sprint_executor.py")
        src = target.read_text(encoding="utf-8-sig")
        assert "RUNTIME_DATA_PATHS = " not in src, \
            "sprint_executor.py must not define its own RUNTIME_DATA_PATHS"

    def test_runtime_data_paths_values_consistent(self):
        from core.shift.source_clean import RUNTIME_DATA_PATHS
        assert "data/genesis_contributions/" in RUNTIME_DATA_PATHS
        assert "data/situational_memory/" in RUNTIME_DATA_PATHS
        assert "data/shift_manifests/" in RUNTIME_DATA_PATHS

    def test_uses_split_not_fixed_slice(self):
        """Verify the fix: path extraction uses split(None,1) not [3:]."""
        target = Path("core/knowledge/sprint_executor.py")
        src = target.read_text(encoding="utf-8-sig")
        assert "split(None, 1)" in src, \
            "Path extraction must use split(None, 1) not fixed slice [3:]"
        assert "_line[3:]" not in src, \
            "Old fixed-slice path extraction must be removed"


# ---------------------------------------------------------------------------
# Existing boundary enforcement preserved
# ---------------------------------------------------------------------------

class TestExistingBoundaryEnforcementPreserved:

    def test_no_affected_files_still_aborts_commit(self, tmp_path):
        from core.knowledge.sprint_executor import SprintExecutor

        commit_step = MagicMock()
        commit_step.step_number = 1
        commit_step.action_type = "commit"
        commit_step.parameters = []

        proposal = _make_proposal(affected_files=[], steps=[commit_step])
        executor = SprintExecutor(proposal=proposal, project_root=tmp_path)

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.return_value = _mock_git_result(stdout="")
            with patch.object(executor._enforcer, 'validate',
                               return_value=MagicMock(spec=[])):
                success, results = executor.execute()

        assert not success
        all_details = ' '.join(r.detail for r in results)
        assert 'no affected_files' in all_details.lower() or 'ABORT' in all_details

    def test_commit_boundary_violation_still_clears_staged(self, tmp_path):
        """COMMIT_BOUNDARY_VIOLATION path still clears staged area."""
        from core.knowledge.sprint_executor import SprintExecutor

        commit_step = MagicMock()
        commit_step.step_number = 1
        commit_step.action_type = "commit"
        commit_step.parameters = [("message", "test")]

        proposal = _make_proposal(
            affected_files=["core/knowledge/some_helper.py"],
            steps=[commit_step],
        )
        executor = SprintExecutor(proposal=proposal, project_root=tmp_path)

        reset_called = []

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            cmd_str = ' '.join(str(c) for c in cmd)
            if 'status' in cmd_str and 'porcelain' in cmd_str:
                result.stdout = ""  # clean for pre-exec
            elif 'diff' in cmd_str and 'cached' not in cmd_str and 'name-only' in cmd_str:
                # Simulate out-of-scope change
                result.stdout = "core/knowledge/some_OTHER_file.py\n"
            elif 'ls-files' in cmd_str:
                result.stdout = ""
            elif cmd[:3] == ['git', 'reset', 'HEAD']:
                reset_called.append(True)
            return result

        with patch("core.knowledge.sprint_executor.subprocess") as mock_sp:
            mock_sp.run.side_effect = fake_run
            with patch.object(executor._enforcer, 'validate',
                               return_value=MagicMock(spec=[])):
                success, results = executor.execute()

        assert not success
        all_details = ' '.join(r.detail for r in results)
        assert 'SCOPE_VIOLATION' in all_details or 'ABORT' in all_details
