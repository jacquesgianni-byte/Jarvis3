from __future__ import annotations
import hashlib, logging, re, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
_DESKTOP_CMD  = [sys.executable, "-m", "apps.desktop.main"]
_DESKTOP_HTTP = "http://localhost:5001"

@dataclass(frozen=True)
class ScopeViolation:
    action_type: str
    reason:      str
    expected:    str
    actual:      str

@dataclass(frozen=True)
class ScopeApproved:
    action_type: str
    step_number: int

class ScopeEnforcer:
    def __init__(self, proposal) -> None:
        self._proposal  = proposal
        self._next_step = 1

    def validate(self, action_type: str, parameters: dict):
        expected = next((s for s in self._proposal.steps if s.step_number == self._next_step), None)
        if expected is None:
            return ScopeViolation(action_type=action_type,
                reason=f"No step {self._next_step} in approved proposal.",
                expected=f"{len(self._proposal.steps)} steps declared.",
                actual=f"Attempted step {self._next_step}.")
        if action_type != expected.action_type:
            return ScopeViolation(action_type=action_type,
                reason="Action type does not match approved step.",
                expected=expected.action_type, actual=action_type)
        declared = dict(expected.parameters)
        for k, v in parameters.items():
            if k in declared and declared[k] != v:
                return ScopeViolation(action_type=action_type,
                    reason=f"Parameter {k!r} does not match approved value.",
                    expected=declared[k], actual=v)
        self._next_step += 1
        return ScopeApproved(action_type=action_type, step_number=expected.step_number)

    @property
    def all_steps_validated(self) -> bool:
        return self._next_step > len(self._proposal.steps)

@dataclass(frozen=True)
class RegistryWriteResult:
    success:         bool
    descriptor_name: str
    file_path:       str
    file_hash_after: str
    error:           str = ""

class InvestigationRegistryWriter:
    _AUTHORISED = "core/mission/investigation_registry.py"
    _ANCHOR     = "# Future investigations registered here:"

    def __init__(self, project_root: Path) -> None:
        self._root   = project_root
        self._target = project_root / self._AUTHORISED

    def write_descriptor(self, name, display_name, description, question_keywords, evidence_sources=("project_state",)):
        def fail(msg): return RegistryWriteResult(success=False, descriptor_name=name, file_path=str(self._target), file_hash_after="", error=msg)
        if not name or not re.match(r"^[a-z][a-z0-9_]*$", name):
            return fail(f"Invalid descriptor name {name!r} -- must be lowercase snake_case.")
        if not question_keywords:
            return fail("question_keywords must be non-empty.")
        if not self._target.exists():
            return fail(f"Authorised target file not found: {self._target}")
        orig = self._target.read_text(encoding="utf-8-sig")
        if self._ANCHOR not in orig:
            return fail("Anchor not found in registry file.")
        chk = f"name         = \"{name}\""
        if chk in orig:
            return fail(f"Descriptor {name!r} is already registered.")
        kw  = ",\n        ".join(f"\"{k}\"" for k in question_keywords)
        es  = ",\n        ".join(f"\"{s}\"" for s in evidence_sources)
        blk = (
            "_register(InvestigationDescriptor(\n"
            f"    name         = \"{name}\",\n"
            f"    display_name = \"{display_name}\",\n"
            f"    description  = (\n        \"{description}\"\n    ),\n"
            f"    question_keywords = (\n        {kw},\n    ),\n"
            f"    evidence_sources = (\n        {es},\n    ),\n"
            "))\n\n" + self._ANCHOR
        )
        new = orig.replace(self._ANCHOR, blk)
        self._target.write_text(new, encoding="utf-8")
        h = hashlib.sha256(new.encode("utf-8")).hexdigest()[:16]
        return RegistryWriteResult(success=True, descriptor_name=name, file_path=str(self._target), file_hash_after=h)

@dataclass(frozen=True)
class DesktopValidationResult:
    passed:           bool
    criterion_type:   str
    test_input:       str
    expected_outcome: str
    actual_response:  str
    timed_out:        bool = False
    error:            str  = ""

    def format_for_report(self) -> str:
        status = "PASS" if self.passed else ("TIMEOUT" if self.timed_out else "FAIL")
        return f"Desktop validation: {status}"

class DesktopValidationRunner:
    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def run(self, spec) -> DesktopValidationResult:
        declared = getattr(spec, "command", "")
        expected = " ".join(_DESKTOP_CMD)
        if declared != expected:
            return DesktopValidationResult(passed=False, criterion_type="command_whitelist",
                test_input=declared, expected_outcome=expected,
                actual_response="", error="Command not in whitelist -- execution refused.")
        proc = None
        try:
            proc = subprocess.Popen(_DESKTOP_CMD, cwd=str(self._root),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            import httpx
            try:
                resp = httpx.post(f"{_DESKTOP_HTTP}/chat",
                    json={"message": spec.test_message}, timeout=spec.timeout_seconds)
                rt = resp.json().get("response", "")
            except Exception as e:
                rt = f"HTTP error: {e}"
            passed = spec.expected_contains.lower() in rt.lower()
            return DesktopValidationResult(passed=passed, criterion_type="response_contains",
                test_input=spec.test_message,
                expected_outcome=f"response contains {spec.expected_contains!r}",
                actual_response=rt)
        except Exception as e:
            return DesktopValidationResult(passed=False, criterion_type="response_contains",
                test_input=getattr(spec,"test_message",""), expected_outcome="",
                actual_response="", error=str(e))
        finally:
            if proc:
                try: proc.terminate(); proc.wait(timeout=5)
                except Exception: proc.kill()

@dataclass
class ExecutionStepResult:
    step_number: int
    action_type: str
    success:     bool
    detail:      str
    commit_sha:  str = ""

class SprintExecutor:
    def __init__(self, proposal, project_root: Path, mission_registry=None) -> None:
        self._proposal = proposal
        self._root     = project_root
        self._enforcer = ScopeEnforcer(proposal)
        self._writer   = InvestigationRegistryWriter(project_root)
        self._desktop  = DesktopValidationRunner(project_root)

    def execute(self):
        results = []
        for step in self._proposal.steps:
            params = dict(step.parameters)
            check  = self._enforcer.validate(step.action_type, params)
            if isinstance(check, ScopeViolation):
                results.append(ExecutionStepResult(step_number=step.step_number,
                    action_type=step.action_type, success=False,
                    detail=f"SCOPE VIOLATION: {check.reason} Expected={check.expected!r} Actual={check.actual!r}"))
                return False, results
            result = self._dispatch(step, params)
            results.append(result)
            if not result.success:
                return False, results
        return True, results

    def _dispatch(self, step, params):
        if step.action_type == "register_descriptor":
            return self._do_register(step, params)
        elif step.action_type == "run_tests":
            return self._do_tests(step)
        elif step.action_type == "commit":
            return self._do_commit(step, params)
        elif step.action_type == "add_record":
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=False, detail="add_record requires manual population. Stopping.")
        return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
            success=False, detail=f"Unknown action_type {step.action_type!r} -- not in executor whitelist.")

    def _do_register(self, step, params):
        name = params.get("name", "")
        kws  = tuple(k.strip() for k in params.get("keywords","").split(",") if k.strip())
        r    = self._writer.write_descriptor(
            name=name, display_name=name.replace("_"," ").title(),
            description=f"Investigation for {name.replace(chr(95),chr(32))} questions.",
            question_keywords=kws,
            evidence_sources=tuple(s.strip() for s in params.get("evidence_sources","project_state").split(",")))
        if not r.success:
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=False, detail=f"Registry write failed: {r.error}")
        return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
            success=True,
            detail=f"Registered {name!r} in investigation_registry.py (hash={r.file_hash_after}). NOTE: descriptor only -- implementation deferred.")

    def _do_tests(self, step):
        try:
            proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-x", "-q"],
                cwd=str(self._root), capture_output=True, text=True, timeout=300)
            ok  = proc.returncode == 0
            out = proc.stdout[-500:] if proc.stdout else proc.stderr[-500:]
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=ok, detail=f"Tests {chr(39)}PASSED{chr(39)} if ok else {chr(39)}FAILED{chr(39)}. {out}")
        except Exception as e:
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=False, detail=f"Test error: {e}")

    def _do_commit(self, step, params):
        msg = params.get("message", f"Genesis-064: {self._proposal.proposed_sprint_name}")
        try:
            subprocess.run(["git","add","-A"], cwd=str(self._root), check=True, capture_output=True, timeout=30)
            subprocess.run(["git","commit","-m",msg], cwd=str(self._root), check=True, capture_output=True, timeout=30)
            sha = subprocess.run(["git","rev-parse","--short","HEAD"],
                cwd=str(self._root), capture_output=True, text=True, timeout=10).stdout.strip()
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=True, detail=f"Committed: {msg!r} ({sha})", commit_sha=sha)
        except Exception as e:
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=False, detail=f"Commit error: {e}")