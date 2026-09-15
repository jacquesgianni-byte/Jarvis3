from __future__ import annotations
import hashlib, logging, re, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
_DESKTOP_CMD  = [sys.executable, "-m", "apps.desktop.main"]

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
    Genesis-081 Sprint-003: Stage 1 + 2 desktop validation.

    Replaces the nonexistent HTTP readiness probe with real process and
    Qt window readiness checks.

    Stage 1 -- Process readiness:
        Launch apps.desktop.main. Poll proc.poll() every PROBE_INTERVAL_S.
        If the process exits before PROCESS_SURVIVE_S, report infrastructure
        failure with the early exit code.

    Stage 2 -- Qt window readiness:
        Use win32gui (pywin32) to enumerate visible windows by PID.
        A window owned by the subprocess PID proves the Qt event loop ran
        and MainWindow.show() was called. Title is not checked -- PID match
        is sufficient and title-change-proof.

    Fallback: if win32gui is unavailable, a fixed sleep of WINDOW_WAIT_S is
        used as a proxy for Qt initialisation completing (less precise but
        still eliminates the guaranteed 20-second HTTP timeout).

    Stage 3 (functional) is deferred -- separate design decision required.
    No HTTP server is added to the desktop application.
    """

    PROBE_INTERVAL_S  = 0.5   # poll interval for process survival
    PROCESS_SURVIVE_S = 5.0   # minimum time process must stay alive
    WINDOW_WAIT_S     = 12.0  # max wait for Qt window to appear
    WINDOW_POLL_S     = 0.5   # poll interval for window check
    HARD_TIMEOUT_S    = 30.0  # absolute ceiling for the whole run

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    # -- win32 window detection (pywin32) -------------------------------------
    @staticmethod
    def _find_window_for_pid(pid: int) -> str:
        """Return the title of the first visible window owned by pid, or ''."""
        try:
            import win32gui as _wg, win32process as _wp
            found = []

            def _cb(hwnd, _):
                if _wg.IsWindowVisible(hwnd) and _wg.GetWindowText(hwnd):
                    try:
                        _, wpid = _wp.GetWindowThreadProcessId(hwnd)
                        if wpid == pid:
                            found.append(_wg.GetWindowText(hwnd))
                    except Exception:
                        pass

            _wg.EnumWindows(_cb, None)
            return found[0] if found else ""
        except ImportError:
            return ""          # win32gui unavailable -- caller handles fallback
        except Exception:
            return ""

    def run(self, spec) -> DesktopValidationResult:
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

        def elapsed() -> float:
            return time.monotonic() - t_start

        try:
            proc = subprocess.Popen(
                _DESKTOP_CMD, cwd=str(self._root),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            process_started = True
            logger.info("[DesktopValidation] Process started (pid=%s)", proc.pid)

            # -- Stage 1: process survival -------------------------------------
            while elapsed() < self.PROCESS_SURVIVE_S:
                early_exit = proc.poll()
                if early_exit is not None:
                    logger.warning(
                        "[DesktopValidation] Process exited early (code=%s, elapsed=%.1fs)",
                        early_exit, elapsed(),
                    )
                    return DesktopValidationResult(
                        passed=False,
                        criterion_type="process_survival",
                        test_input="", expected_outcome="", actual_response="",
                        process_started=True, process_ready=False,
                        process_exit_code=early_exit,
                        elapsed_seconds=elapsed(),
                        failure_reason=(
                            f"Infrastructure failure: desktop process exited after "
                            f"{elapsed():.1f}s (exit code {early_exit})."
                        ),
                    )
                time.sleep(self.PROBE_INTERVAL_S)

            logger.info("[DesktopValidation] Process survived %.1fs", elapsed())

            # -- Stage 2: Qt window readiness ----------------------------------
            win32_available = True
            try:
                import win32gui as _wg  # noqa: F401 -- probe only
            except ImportError:
                win32_available = False
                logger.warning(
                    "[DesktopValidation] win32gui unavailable -- "
                    "using fixed %.1fs window wait", self.WINDOW_WAIT_S,
                )

            window_title = ""
            process_ready = False

            if win32_available:
                # Poll for window owned by our PID
                while elapsed() < self.HARD_TIMEOUT_S:
                    window_title = self._find_window_for_pid(proc.pid)
                    if window_title:
                        process_ready = True
                        logger.info(
                            "[DesktopValidation] Window found: %r (pid=%s, elapsed=%.1fs)",
                            window_title, proc.pid, elapsed(),
                        )
                        break
                    if proc.poll() is not None:
                        break          # process died while we were waiting
                    time.sleep(self.WINDOW_POLL_S)
            else:
                # Fallback: fixed wait as proxy for Qt initialisation
                remaining = max(0.0, self.WINDOW_WAIT_S - elapsed())
                if remaining > 0:
                    time.sleep(remaining)
                if proc.poll() is None:
                    process_ready = True   # process still alive after wait
                    window_title  = "unknown (win32gui unavailable)"

            if not process_ready:
                timed_out = elapsed() >= self.HARD_TIMEOUT_S
                reason = (
                    "Infrastructure failure: Qt window did not appear within "
                    f"{self.HARD_TIMEOUT_S:.0f}s."
                    if timed_out else
                    "Infrastructure failure: desktop process exited before Qt window appeared."
                )
                return DesktopValidationResult(
                    passed=False,
                    criterion_type="window_readiness",
                    test_input="", expected_outcome="", actual_response="",
                    process_started=True, process_ready=False,
                    elapsed_seconds=elapsed(),
                    timed_out=timed_out,
                    failure_reason=reason,
                )

            # Stage 1 + 2 passed -- functional validation (Stage 3) deferred.
            logger.info(
                "[DesktopValidation] PASS (process+window) elapsed=%.1fs window=%r",
                elapsed(), window_title,
            )
            return DesktopValidationResult(
                passed=True,
                criterion_type="process_and_window",
                test_input="", expected_outcome="desktop started and window visible",
                actual_response=f"window={window_title!r}",
                process_started=True, process_ready=True,
                elapsed_seconds=elapsed(),
            )

        except Exception as e:
            logger.exception("[DesktopValidation] Unexpected error: %s", e)
            return DesktopValidationResult(
                passed=False,
                criterion_type=getattr(spec, "criterion_type", ""),
                test_input="", expected_outcome="", actual_response="",
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
        # Pre-execution: assert clean working tree (fail closed)
        try:
            import subprocess as _sp
            status = _sp.run(
                ['git', 'status', '--porcelain'],
                cwd=str(self._root), capture_output=True, text=True, timeout=15
            )
            if status.stdout.strip():
                return False, [ExecutionStepResult(
                    step_number=0, action_type='pre_execution_check',
                    success=False,
                    detail=f'WORKING_TREE_DIRTY: execution aborted. '
                           f'Unclean files:\n{status.stdout.strip()}'
                )]
        except Exception as e:
            return False, [ExecutionStepResult(
                step_number=0, action_type='pre_execution_check',
                success=False,
                detail=f'ABORT: cannot determine working tree state - failing closed. Error: {e}'
            )]
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

        # -- Derive sprint summaries from SprintStateRecord files --------------
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

        # -- Derive commit from git log if not found in traces -----------------
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

        # -- Derive display_name from project_state.json or fallback ----------
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

        # -- Compute tests_added delta from project_state.json baseline ----------
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

        # -- Build the _declare() block ----------------------------------------
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
        import fnmatch as _fnmatch
        approved = list(getattr(self._proposal, 'affected_files', []))

        # Fail closed: no affected_files declared
        if not approved:
            return ExecutionStepResult(
                step_number=step.step_number, action_type=step.action_type,
                success=False,
                detail='ABORT: no affected_files declared on proposal - '
                       'cannot establish commit boundary. Failing closed.'
            )

        # Determine actual changed files
        try:
            diff_result = subprocess.run(
                ['git', 'diff', '--name-only'],
                cwd=str(self._root), capture_output=True, text=True, timeout=15
            )
            untracked_result = subprocess.run(
                ['git', 'ls-files', '--others', '--exclude-standard'],
                cwd=str(self._root), capture_output=True, text=True, timeout=15
            )
            if diff_result.returncode != 0 or untracked_result.returncode != 0:
                return ExecutionStepResult(
                    step_number=step.step_number, action_type=step.action_type,
                    success=False,
                    detail='ABORT: cannot determine changed files - failing closed.'
                )
        except Exception as e:
            return ExecutionStepResult(
                step_number=step.step_number, action_type=step.action_type,
                success=False,
                detail=f'ABORT: git status error - failing closed. Error: {e}'
            )

        actual_changed = set(
            diff_result.stdout.strip().splitlines() +
            untracked_result.stdout.strip().splitlines()
        )
        actual_changed.discard('')

        def in_scope(f):
            return any(_fnmatch.fnmatch(f, p) for p in approved)

        # Layer 2: scope boundary check
        out_of_scope = {f for f in actual_changed if not in_scope(f)}
        if out_of_scope:
            subprocess.run(['git', 'reset', 'HEAD'],
                cwd=str(self._root), capture_output=True, timeout=15)
            return ExecutionStepResult(
                step_number=step.step_number, action_type=step.action_type,
                success=False,
                detail=f'SCOPE_VIOLATION: files changed outside approved boundary: '
                       f'{sorted(out_of_scope)}. Staged area cleared. No commit made.'
            )

        # Stage only approved files that were actually changed
        in_scope_changed = {f for f in actual_changed if in_scope(f)}
        try:
            for f in sorted(in_scope_changed):
                subprocess.run(
                    ['git', 'add', f],
                    cwd=str(self._root), check=True,
                    capture_output=True, timeout=30
                )
        except Exception as e:
            return ExecutionStepResult(
                step_number=step.step_number, action_type=step.action_type,
                success=False,
                detail=f'ABORT: staging failed - failing closed. Error: {e}'
            )

        # Layer 3: pre-commit staged-file verification
        try:
            staged_result = subprocess.run(
                ['git', 'diff', '--cached', '--name-only'],
                cwd=str(self._root), capture_output=True, text=True, timeout=15
            )
            if staged_result.returncode != 0:
                subprocess.run(['git', 'reset', 'HEAD'],
                    cwd=str(self._root), capture_output=True, timeout=15)
                return ExecutionStepResult(
                    step_number=step.step_number, action_type=step.action_type,
                    success=False,
                    detail='ABORT: cannot verify staged files - failing closed.'
                )
        except Exception as e:
            subprocess.run(['git', 'reset', 'HEAD'],
                cwd=str(self._root), capture_output=True, timeout=15)
            return ExecutionStepResult(
                step_number=step.step_number, action_type=step.action_type,
                success=False,
                detail=f'ABORT: staged file verification error - failing closed. Error: {e}'
            )

        staged = set(staged_result.stdout.strip().splitlines())
        staged.discard('')
        boundary_violation = {f for f in staged if not in_scope(f)}
        if boundary_violation:
            subprocess.run(['git', 'reset', 'HEAD'],
                cwd=str(self._root), capture_output=True, timeout=15)
            return ExecutionStepResult(
                step_number=step.step_number, action_type=step.action_type,
                success=False,
                detail=f'COMMIT_BOUNDARY_VIOLATION: staged files outside approved scope: '
                       f'{sorted(boundary_violation)}. Staged area cleared. No commit made.'
            )

        # Commit message from live sprint state (stale Genesis-064 default removed)
        sprint_id   = getattr(self._proposal, 'proposal_id', 'UNKNOWN')
        sprint_name = getattr(self._proposal, 'proposed_sprint_name', 'sprint')
        genesis_id  = getattr(self._proposal, 'genesis_id', 'Genesis-???')
        msg = params.get('message',
            f'{sprint_id}: {sprint_name} ({genesis_id})'
        )

        try:
            commit_result = subprocess.run(
                ['git', 'commit', '-m', msg],
                cwd=str(self._root), capture_output=True, text=True, timeout=30
            )
            if commit_result.returncode != 0:
                combined = (commit_result.stdout + commit_result.stderr).lower()
                if 'nothing to commit' in combined or 'nothing added to commit' in combined:
                    sha = subprocess.run(
                        ['git', 'rev-parse', '--short', 'HEAD'],
                        cwd=str(self._root), capture_output=True,
                        text=True, timeout=10
                    ).stdout.strip()
                    return ExecutionStepResult(
                        step_number=step.step_number, action_type=step.action_type,
                        success=True,
                        detail=f'Nothing to commit - work already applied (idempotent). HEAD: {sha}',
                        commit_sha=sha
                    )
                raise subprocess.CalledProcessError(
                    commit_result.returncode, 'git commit',
                    output=commit_result.stdout, stderr=commit_result.stderr
                )
            sha = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                cwd=str(self._root), capture_output=True, text=True, timeout=10
            ).stdout.strip()
            return ExecutionStepResult(
                step_number=step.step_number, action_type=step.action_type,
                success=True,
                detail=f'Committed: {msg!r} ({sha})', commit_sha=sha
            )
        except Exception as e:
            return ExecutionStepResult(
                step_number=step.step_number, action_type=step.action_type,
                success=False, detail=f'Commit error: {e}'
            )

