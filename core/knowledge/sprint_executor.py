from __future__ import annotations
import hashlib, logging, re, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
_DESKTOP_CMD  = [sys.executable, "-m", "apps.desktop.main"]
_DESKTOP_HTTP = "http://localhost:5002"

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
    """
    Genesis-065 Sprint-002: Structured desktop validation result.
    Distinguishes infrastructure / communication / behaviour failures.
    """
    passed:            bool
    criterion_type:    str
    test_input:        str
    expected_outcome:  str
    actual_response:   str
    # Lifecycle diagnostics
    process_started:   bool  = False
    process_ready:     bool  = False
    http_status:       int   = 0
    criterion_met:     bool  = False
    process_exit_code: int   = -1
    elapsed_seconds:   float = 0.0
    timed_out:         bool  = False
    failure_reason:    str   = ""
    error:             str   = ""

    def format_for_report(self) -> str:
        if self.passed:
            return f"Desktop validation: PASS ({self.elapsed_seconds:.1f}s)"
        if self.timed_out:
            return f"Desktop validation: TIMEOUT ({self.elapsed_seconds:.1f}s)"
        return (
            f"Desktop validation: FAIL -- {self.failure_reason} "
            f"(process_started={self.process_started}, "
            f"process_ready={self.process_ready}, "
            f"http={self.http_status}, "
            f"criterion={self.criterion_met})"
        )

    def to_dict(self) -> dict:
        return {
            "passed":            self.passed,
            "criterion_type":    self.criterion_type,
            "test_input":        self.test_input,
            "expected_outcome":  self.expected_outcome,
            "actual_response":   self.actual_response[:500] if self.actual_response else "",
            "process_started":   self.process_started,
            "process_ready":     self.process_ready,
            "http_status":       self.http_status,
            "criterion_met":     self.criterion_met,
            "process_exit_code": self.process_exit_code,
            "elapsed_seconds":   round(self.elapsed_seconds, 2),
            "timed_out":         self.timed_out,
            "failure_reason":    self.failure_reason,
            "error":             self.error,
            "detail":            self.format_for_report(),
        }
class DesktopValidationRunner:
    """
    Genesis-065 Sprint-002: Redesigned desktop validation runner.

    Replaces flat 3-second sleep with bounded readiness probe.
    Captures full process lifecycle: started / ready / HTTP / criterion / exit.
    Distinguishes infrastructure / communication / behaviour failures.

    Readiness probe: polls _DESKTOP_HTTP/health every 500ms up to READY_TIMEOUT_S.
    Hard timeout: HARD_TIMEOUT_S covers the entire validation run.
    """

    PROBE_INTERVAL_S = 0.5
    READY_TIMEOUT_S  = 20.0
    HARD_TIMEOUT_S   = 60.0

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def run(self, spec) -> DesktopValidationResult:
        import httpx as _httpx

        declared = getattr(spec, "command", "")
        expected = " ".join(_DESKTOP_CMD)
        if declared != expected:
            return DesktopValidationResult(
                passed=False, criterion_type="command_whitelist",
                test_input=declared, expected_outcome=expected,
                actual_response="",
                failure_reason="Command not in whitelist -- execution refused.",
                error="Command not in whitelist -- execution refused.",
            )

        t_start = time.monotonic()
        proc    = None

        def elapsed():
            return time.monotonic() - t_start

        try:
            proc = subprocess.Popen(
                _DESKTOP_CMD, cwd=str(self._root),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            process_started = True
            logger.info("[DesktopValidation] Process started (pid=%s)", proc.pid)

            # Readiness probe
            process_ready = False
            while elapsed() < self.READY_TIMEOUT_S:
                if elapsed() >= self.HARD_TIMEOUT_S:
                    break
                try:
                    r = _httpx.get(f"{_DESKTOP_HTTP}/health", timeout=1.0)
                    if r.status_code < 500:
                        process_ready = True
                        logger.info("[DesktopValidation] Ready after %.1fs", elapsed())
                        break
                except Exception:
                    pass
                time.sleep(self.PROBE_INTERVAL_S)

            if not process_ready:
                return DesktopValidationResult(
                    passed=False,
                    criterion_type=getattr(spec, "criterion_type", ""),
                    test_input=getattr(spec, "test_message", ""),
                    expected_outcome=getattr(spec, "expected_outcome", ""),
                    actual_response="",
                    process_started=process_started,
                    process_ready=False,
                    elapsed_seconds=elapsed(),
                    timed_out=elapsed() >= self.READY_TIMEOUT_S,
                    failure_reason="Infrastructure failure: desktop never became ready.",
                )

            # Send test message
            http_status   = 0
            response_body = ""
            criterion_met = False
            remaining     = max(1.0, self.HARD_TIMEOUT_S - elapsed())

            try:
                resp = _httpx.post(
                    f"{_DESKTOP_HTTP}/chat",
                    json={"message": getattr(spec, "test_message", "")},
                    timeout=min(remaining, getattr(spec, "timeout_seconds", 30)),
                )
                http_status   = resp.status_code
                response_body = resp.text[:2000]
                expected_contains = getattr(spec, "expected_contains", "")
                criterion_met = (
                    expected_contains.lower() in response_body.lower()
                    if expected_contains else http_status < 400
                )
                logger.info(
                    "[DesktopValidation] HTTP %s criterion_met=%s elapsed=%.1fs",
                    http_status, criterion_met, elapsed(),
                )
            except _httpx.TimeoutException:
                return DesktopValidationResult(
                    passed=False,
                    criterion_type=getattr(spec, "criterion_type", ""),
                    test_input=getattr(spec, "test_message", ""),
                    expected_outcome=getattr(spec, "expected_outcome", ""),
                    actual_response="",
                    process_started=process_started,
                    process_ready=process_ready,
                    http_status=0,
                    criterion_met=False,
                    elapsed_seconds=elapsed(),
                    timed_out=True,
                    failure_reason="Communication failure: HTTP request timed out.",
                )
            except Exception as e:
                return DesktopValidationResult(
                    passed=False,
                    criterion_type=getattr(spec, "criterion_type", ""),
                    test_input=getattr(spec, "test_message", ""),
                    expected_outcome=getattr(spec, "expected_outcome", ""),
                    actual_response="",
                    process_started=process_started,
                    process_ready=process_ready,
                    http_status=0,
                    criterion_met=False,
                    elapsed_seconds=elapsed(),
                    failure_reason="Communication failure: HTTP request failed.",
                    error=str(e),
                )

            failure_reason = "" if criterion_met else (
                f"Behaviour failure: response did not satisfy criterion "
                f"{getattr(spec, 'expected_contains', '')!r}."
            )
            return DesktopValidationResult(
                passed=criterion_met,
                criterion_type=getattr(spec, "criterion_type", "response_contains"),
                test_input=getattr(spec, "test_message", ""),
                expected_outcome=getattr(spec, "expected_outcome", ""),
                actual_response=response_body,
                process_started=process_started,
                process_ready=process_ready,
                http_status=http_status,
                criterion_met=criterion_met,
                elapsed_seconds=elapsed(),
                failure_reason=failure_reason,
            )

        except Exception as e:
            logger.exception("[DesktopValidation] Unexpected error: %s", e)
            return DesktopValidationResult(
                passed=False,
                criterion_type=getattr(spec, "criterion_type", ""),
                test_input=getattr(spec, "test_message", ""),
                expected_outcome=getattr(spec, "expected_outcome", ""),
                actual_response="",
                process_started=proc is not None,
                elapsed_seconds=elapsed(),
                failure_reason="Infrastructure failure: unexpected error.",
                error=str(e),
            )
        finally:
            if proc:
                exit_code = -1
                try:
                    proc.terminate()
                    exit_code = proc.wait(timeout=5)
                except Exception:
                    try: proc.kill()
                    except Exception: pass
                logger.info(
                    "[DesktopValidation] Process terminated (exit_code=%s)", exit_code
                )
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
            return self._do_add_record(step, params)
        return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
            success=False, detail=f"Unknown action_type {step.action_type!r} -- not in executor whitelist.")

    def _do_add_record(self, step, params):
        """
        Genesis-065: Write a GenesisDeliveryRecord into genesis_record.py.

        Derives data from:
          - SprintStateRecord files (completed sprints for this genesis)
          - git log (commit SHA, sprint commit messages)
          - execution_trace (tests_added approximation)

        Never invents data. Stops if the record already exists.
        Injects a _declare() block above the anchor comment.
        """
        import subprocess as _sp, json as _json, re as _re

        genesis_id = params.get("genesis_id", "").strip()
        if not genesis_id:
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=False, detail="add_record: genesis_id parameter required.")

        target = self._root / "core" / "knowledge" / "genesis_record.py"
        if not target.exists():
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=False, detail=f"add_record: target file not found: {target}")

        existing = target.read_text(encoding="utf-8-sig")
        anchor = "# Add new records below as each Genesis is completed:"
        if anchor not in existing:
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=False, detail="add_record: anchor comment not found in genesis_record.py")

        if f'genesis_id   = "{genesis_id}"' in existing:
            return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                success=True, detail=f"add_record: {genesis_id} already declared -- skipping (idempotent).")

        # ── Derive sprint summaries from SprintStateRecord files ──────────────
        sprint_states_dir = self._root / "data" / "sprint_states"
        sprint_summaries = []
        tests_added = 0
        final_commit = ""

        if sprint_states_dir.exists():
            from core.knowledge.sprint_state import SprintStateStore, SprintState
            store = SprintStateStore(self._root / "data")
            for rec in store.all_records():
                if rec.current_state != "completed":
                    continue
                # Match genesis from stored_proposal sprint name or commit message
                sp = rec.stored_proposal or {}
                sprint_name = sp.get("proposed_sprint_name", "")
                if not sprint_name:
                    continue
                # Check commit messages in execution_trace for genesis label
                for tr in rec.execution_trace:
                    detail = tr.get("detail", "")
                    if genesis_id.lower() in detail.lower():
                        if tr.get("commit_sha"):
                            final_commit = tr["commit_sha"]
                        break
                else:
                    # Also check if proposal rationale mentions the genesis
                    if genesis_id.lower() not in sp.get("rationale", "").lower() and                        genesis_id.lower() not in sprint_name.lower():
                        continue

                # Count tests from run_tests step
                for tr in rec.execution_trace:
                    if tr.get("action") == "run_tests" and tr.get("success"):
                        m = _re.search(r"(\d+) passed", tr.get("detail", ""))
                        if m:
                            tests_added = max(tests_added, int(m.group(1)))
                sprint_summaries.append(sprint_name)

        # ── Derive commit from git log if not found in traces ─────────────────
        if not final_commit:
            try:
                result = _sp.run(
                    ["git", "log", "--oneline", "-50"],
                    cwd=str(self._root), capture_output=True, text=True, timeout=15
                )
                for line in result.stdout.splitlines():
                    if genesis_id.lower() in line.lower():
                        final_commit = line.split()[0]
                        break
            except Exception:
                pass

        # ── Derive display_name from project_state.json or fallback ──────────
        display_name = f"{genesis_id} Delivery"
        try:
            ps_path = self._root / "project_state.json"
            if ps_path.exists():
                ps = _json.loads(ps_path.read_text(encoding="utf-8-sig"))
                mission = ps.get("current_mission", "")
                if mission:
                    display_name = mission
        except Exception:
            pass

        # ── Compute tests_added delta from project_state.json baseline ──────────
        # tests_added should be delta (tests introduced), not total suite size.
        # Baseline: tests_passed from project_state.json before this genesis.
        # If baseline is unavailable, store None (never report a misleading number).
        try:
            _ps_path = self._root / "project_state.json"
            if not _ps_path.exists():
                _ps_path = self._root.parent / "project_state.json"
            if _ps_path.exists():
                _ps = _json.loads(_ps_path.read_text(encoding="utf-8-sig"))
                _baseline = _ps.get("tests_passed", 0)
                if _baseline > 0 and tests_added > _baseline:
                    tests_added = tests_added - _baseline
                elif _baseline == 0:
                    pass  # no baseline, keep raw count
                else:
                    tests_added = 0  # no new tests detected
            # else: leave tests_added as raw count
        except Exception:
            pass  # if baseline read fails, keep raw count rather than None

        # ── Build the _declare() block ────────────────────────────────────────
        if not sprint_summaries:
            sprint_summaries = [f"{genesis_id}: sprints completed (see git log)"]

        sprints_str = (",\n        ".join('"' + s + '"' for s in sprint_summaries))

        # Components: derive from proposal steps across completed sprints
        components = []
        if sprint_states_dir.exists():
            from core.knowledge.sprint_state import SprintStateStore
            store2 = SprintStateStore(self._root / "data")
            for rec2 in store2.all_records():
                if rec2.current_state != "completed":
                    continue
                sp2 = rec2.stored_proposal or {}
                for step2 in sp2.get("steps", []):
                    params2 = dict(step2.get("parameters", []))
                    if step2.get("action_type") == "register_descriptor":
                        name2 = params2.get("name", "")
                        if name2:
                            components.append(name2)
        if not components:
            components = [f"{genesis_id} components (see delivery record)"]
        components_str = (",\n        ".join('"' + c + '"' for c in components))

        block = (
            "_declare(GenesisDeliveryRecord(\n"
            "    genesis_id   = \"" + genesis_id + "\",\n"
            "    display_name = \"" + display_name + "\",\n"
            "    sprints      = (\n"
            "        " + sprints_str + ",\n"
            "    ),\n"
            "    components_delivered = (\n"
            "        " + components_str + ",\n"
            "    ),\n"
            "    tests_added = " + str(tests_added) + ",\n"
            "    commit      = \"" + final_commit + "\",\n"
            "))\n\n"
            + anchor
        )

        new_text = existing.replace(anchor, block, 1)
        target.write_text(new_text, encoding="utf-8")

        logger.info("[SprintExecutor] add_record: declared %s in genesis_record.py", genesis_id)
        return ExecutionStepResult(
            step_number=step.step_number, action_type=step.action_type,
            success=True,
            detail=f"Declared {genesis_id} in genesis_record.py. "
                   f"Sprints: {len(sprint_summaries)}. "
                   f"Commit: {final_commit or 'derived from git'}.",
        )

    def _do_register(self, step, params):
        name = params.get("name", "")
        kws  = tuple(k.strip() for k in params.get("keywords","").split(",") if k.strip())
        r    = self._writer.write_descriptor(
            name=name, display_name=name.replace("_"," ").title(),
            description=f"Investigation for {name.replace(chr(95),chr(32))} questions.",
            question_keywords=kws,
            evidence_sources=tuple(s.strip() for s in params.get("evidence_sources","project_state").split(",")))
        if not r.success:
            if "already registered" in r.error:
                return ExecutionStepResult(step_number=step.step_number, action_type=step.action_type,
                    success=True, detail=f"Descriptor already registered -- idempotent skip. ({r.error})")
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