from __future__ import annotations
import pathlib, shutil, pytest
from unittest.mock import MagicMock

from core.knowledge.sprint_executor import (
    ScopeEnforcer, ScopeApproved, ScopeViolation,
    InvestigationRegistryWriter, RegistryWriteResult,
    SprintExecutor, DesktopValidationRunner, DesktopValidationResult,
)
from core.knowledge.sprint_proposal import (
    BoundSprintProposal, ProposalStep, AcceptanceCriterion, TEMPLATE_A,
)

PROJECT_ROOT = pathlib.Path(r"C:\\Users\\ljmas\\Desktop\\jarvis3")


def _step(n, action_type, **params):
    return ProposalStep(step_number=n, description=f"Step {n}",
        action_type=action_type, parameters=tuple(params.items()))


def _proposal(steps):
    return BoundSprintProposal(
        proposal_id="PROP-TEST", created_at="now", template_id=TEMPLATE_A,
        proposed_sprint_name="Test sprint", rationale="test",
        evidence_summary="test", gap_observation_count=2,
        recurring_question="test question", steps=tuple(steps),
        acceptance_criteria=(), not_doing=("Does not implement.",),
        evidence_sources=("GapObservationStore",),
    )


class TestScopeEnforcer:

    def test_approves_correct_action(self):
        p = _proposal([_step(1, "register_descriptor", name="test_inv")])
        e = ScopeEnforcer(p)
        r = e.validate("register_descriptor", {"name": "test_inv"})
        assert isinstance(r, ScopeApproved)
        assert r.step_number == 1

    def test_rejects_wrong_action_type(self):
        p = _proposal([_step(1, "register_descriptor", name="test_inv")])
        e = ScopeEnforcer(p)
        r = e.validate("run_tests", {})
        assert isinstance(r, ScopeViolation)
        assert "Action type" in r.reason

    def test_rejects_wrong_sequence(self):
        p = _proposal([_step(1, "register_descriptor", name="x"), _step(2, "run_tests")])
        e = ScopeEnforcer(p)
        r = e.validate("run_tests", {})
        assert isinstance(r, ScopeViolation)

    def test_rejects_wrong_parameters(self):
        p = _proposal([_step(1, "register_descriptor", name="approved")])
        e = ScopeEnforcer(p)
        r = e.validate("register_descriptor", {"name": "different"})
        assert isinstance(r, ScopeViolation)
        assert "Parameter" in r.reason

    def test_all_steps_validated(self):
        p = _proposal([_step(1, "register_descriptor", name="x")])
        e = ScopeEnforcer(p)
        e.validate("register_descriptor", {"name": "x"})
        assert e.all_steps_validated is True

    def test_not_validated_before_complete(self):
        p = _proposal([_step(1, "register_descriptor", name="x"), _step(2, "run_tests")])
        e = ScopeEnforcer(p)
        e.validate("register_descriptor", {"name": "x"})
        assert e.all_steps_validated is False

    def test_scope_violation_frozen(self):
        v = ScopeViolation(action_type="x", reason="r", expected="e", actual="a")
        with pytest.raises((AttributeError, TypeError)):
            v.reason = "other"


class TestInvestigationRegistryWriter:

    def _setup(self, tmp_path):
        reg_src = PROJECT_ROOT / "core" / "mission" / "investigation_registry.py"
        reg_dir = tmp_path / "core" / "mission"
        reg_dir.mkdir(parents=True)
        shutil.copy(reg_src, reg_dir / "investigation_registry.py")
        return InvestigationRegistryWriter(tmp_path)

    def test_rejects_invalid_name(self, tmp_path):
        w = InvestigationRegistryWriter(tmp_path)
        r = w.write_descriptor(name="Bad Name!", display_name="X",
            description="X", question_keywords=("test",))
        assert r.success is False
        assert "Invalid descriptor name" in r.error

    def test_rejects_empty_keywords(self, tmp_path):
        w = InvestigationRegistryWriter(tmp_path)
        r = w.write_descriptor(name="test_inv", display_name="X",
            description="X", question_keywords=())
        assert r.success is False
        assert "non-empty" in r.error

    def test_rejects_missing_file(self, tmp_path):
        w = InvestigationRegistryWriter(tmp_path)
        r = w.write_descriptor(name="test_inv", display_name="X",
            description="X", question_keywords=("test",))
        assert r.success is False
        assert "not found" in r.error

    def test_writes_descriptor(self, tmp_path):
        w = self._setup(tmp_path)
        r = w.write_descriptor(name="test_sprint_inv", display_name="Test Sprint",
            description="A test.", question_keywords=("test sprint", "sprint test"))
        assert r.success is True
        assert r.descriptor_name == "test_sprint_inv"
        assert len(r.file_hash_after) > 0

    def test_descriptor_in_file_after_write(self, tmp_path):
        w = self._setup(tmp_path)
        w.write_descriptor(name="check_inv", display_name="Check",
            description="Check.", question_keywords=("check",))
        content = (tmp_path / "core" / "mission" / "investigation_registry.py").read_text()
        assert "check_inv" in content

    def test_rejects_duplicate(self, tmp_path):
        w = self._setup(tmp_path)
        w.write_descriptor(name="dup_inv", display_name="X",
            description="X", question_keywords=("dup",))
        r = w.write_descriptor(name="dup_inv", display_name="Y",
            description="Y", question_keywords=("dup2",))
        assert r.success is False
        assert "already registered" in r.error

    def test_only_modifies_authorised_file(self, tmp_path):
        w = self._setup(tmp_path)
        sentinel = tmp_path / "core" / "mission" / "investigation.py"
        sentinel.write_text("# sentinel", encoding="utf-8")
        mtime = sentinel.stat().st_mtime
        w.write_descriptor(name="boundary_inv", display_name="X",
            description="X", question_keywords=("boundary",))
        assert sentinel.stat().st_mtime == mtime


class TestDesktopValidationRunner:

    def test_rejects_non_whitelisted_command(self):
        r = DesktopValidationRunner(PROJECT_ROOT)
        spec = MagicMock()
        spec.command = "python -m some.other.app"
        result = r.run(spec)
        assert result.passed is False
        assert "whitelist" in result.error.lower()

    def test_rejects_arbitrary_command(self):
        r = DesktopValidationRunner(PROJECT_ROOT)
        spec = MagicMock()
        spec.command = "rm -rf /"
        result = r.run(spec)
        assert result.passed is False

    def test_result_frozen(self):
        res = DesktopValidationResult(passed=True, criterion_type="t",
            test_input="q", expected_outcome="x", actual_response="x")
        with pytest.raises((AttributeError, TypeError)):
            res.passed = False


class TestSprintExecutorScopeEnforcement:

    def test_stops_on_scope_violation(self, tmp_path):
        p = _proposal([_step(1, "register_descriptor", name="approved",
            keywords="test", evidence_sources="project_state")])
        ex = SprintExecutor(p, tmp_path)
        ex._enforcer = MagicMock()
        ex._enforcer.validate.return_value = ScopeViolation(
            action_type="register_descriptor", reason="Test violation",
            expected="approved", actual="other")
        ok, results = ex.execute()
        assert ok is False
        assert "SCOPE VIOLATION" in results[0].detail

    def test_register_does_not_touch_investigation_py(self, tmp_path):
        reg_src = PROJECT_ROOT / "core" / "mission" / "investigation_registry.py"
        reg_dir = tmp_path / "core" / "mission"
        reg_dir.mkdir(parents=True)
        shutil.copy(reg_src, reg_dir / "investigation_registry.py")
        sentinel = reg_dir / "investigation.py"
        sentinel.write_text("# sentinel", encoding="utf-8")
        mtime = sentinel.stat().st_mtime
        p = _proposal([_step(1, "register_descriptor",
            name="scope_test_inv", keywords="scope test",
            evidence_sources="project_state")])
        SprintExecutor(p, tmp_path).execute()
        assert sentinel.stat().st_mtime == mtime
        assert "# sentinel" in sentinel.read_text()

    def test_unknown_action_stops(self, tmp_path):
        p = _proposal([_step(1, "delete_all_files")])
        ex = SprintExecutor(p, tmp_path)
        ex._enforcer = MagicMock()
        ex._enforcer.validate.return_value = ScopeApproved(
            action_type="delete_all_files", step_number=1)
        ok, results = ex.execute()
        assert ok is False
        assert "whitelist" in results[0].detail.lower() or "Unknown" in results[0].detail
