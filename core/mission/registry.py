"""
Jarvis OS Mission Registry — Genesis-054 Sprint-001

Single authoritative source for project identity and mission state.
Reads project_state.json (committed, human-maintained).
Receives live test results from SuiteRunnerWorker (push model).
Reads live Git for commit/branch.

Owned values:
    current_genesis, current_sprint, current_mission,
    last_completed_genesis, next_milestone, objectives,
    progress_percent (derived), tests_passed/skipped/failed,
    last_commit, last_commit_message, branch

NOT owned (stays in SystemRegistry):
    uptime, workers_online, memory_records, ai_provider, status
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Objective:
    text: str
    done: bool


@dataclass
class TestResult:
    passed:     int = 0
    skipped:    int = 0
    failed:     int = 0
    commit_sha: str = ""   # SHA that was actually tested


@dataclass
class ProjectState:
    current_genesis:        str             = ""
    current_sprint:         str             = ""
    current_mission:        str             = ""
    last_completed_genesis: str             = ""
    next_milestone:         str             = ""
    objectives:             List[Objective] = field(default_factory=list)


def _git_info() -> dict:
    try:
        commit = subprocess.check_output(
            ["git", "log", "-1", "--format=%h|||%s"],
            cwd=".", stderr=subprocess.DEVNULL, text=True
        ).strip()
        parts  = commit.split("|||", 1)
        sha    = parts[0] if parts else ""
        msg    = parts[1] if len(parts) > 1 else ""
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=".", stderr=subprocess.DEVNULL, text=True
        ).strip()
        return {"sha": sha, "message": msg, "branch": branch}
    except Exception:
        return {"sha": "", "message": "", "branch": "main"}


class MissionRegistry:
    """
    Authoritative source for project identity and mission state.
    Injected into the Flask app at startup.
    """

    def __init__(self, project_root: Path):
        self._root        = project_root
        self._state       = ProjectState()
        self._test_result = TestResult()
        self._loaded      = False

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def load(self) -> None:
        """
        Read project_state.json from repo root.
        Called once at server startup.
        Raises FileNotFoundError if file is missing — fail loudly.
        """
        path = self._root / "project_state.json"
        if not path.exists():
            raise FileNotFoundError(
                f"[MissionRegistry] project_state.json not found at {path}. "
                "Create it before starting the server."
            )
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        self._state = ProjectState(
            current_genesis        = data.get("current_genesis", ""),
            current_sprint         = data.get("current_sprint", ""),
            current_mission        = data.get("current_mission", ""),
            last_completed_genesis = data.get("last_completed_genesis", ""),
            next_milestone         = data.get("next_milestone", ""),
            objectives             = [
                Objective(text=o["text"], done=o["done"])
                for o in data.get("objectives", [])
            ],
        )
        self._loaded = True
        logger.info(
            "[MissionRegistry] Loaded: %s %s — %d objectives",
            self._state.current_genesis,
            self._state.current_sprint,
            len(self._state.objectives),
        )

    # ------------------------------------------------------------------
    # Test result ingestion (push from SuiteRunnerWorker)
    # ------------------------------------------------------------------

    def record_test_result(
        self,
        passed:     int,
        skipped:    int,
        failed:     int,
        commit_sha: str,
    ) -> None:
        """
        Called by SuiteRunnerWorker after every pytest run.
        Stores result in memory only — never writes to project_state.json.
        """
        self._test_result = TestResult(
            passed=passed,
            skipped=skipped,
            failed=failed,
            commit_sha=commit_sha,
        )
        logger.info(
            "[MissionRegistry] Test result recorded: %d passed / %d skipped / %d failed @ %s",
            passed, skipped, failed, commit_sha,
        )

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------

    def _progress_percent(self) -> int:
        """Derive progress from objective completion. Never stored."""
        objectives = self._state.objectives
        if not objectives:
            return 0
        done = sum(1 for o in objectives if o.done)
        return round(done / len(objectives) * 100)

    # ------------------------------------------------------------------
    # Public dict (consumed by /dashboard)
    # ------------------------------------------------------------------

    def mission_dict(self) -> dict:
        """
        Full mission + engineering snapshot.
        Git is queried live on every call.
        """
        git = _git_info()
        return {
            # Project identity
            "current_genesis":        self._state.current_genesis,
            "current_sprint":         self._state.current_sprint,
            "current_mission":        self._state.current_mission,
            "last_completed_genesis": self._state.last_completed_genesis,
            "next_milestone":         self._state.next_milestone,
            # Objectives + derived progress
            "objectives":             [
                {"text": o.text, "done": o.done}
                for o in self._state.objectives
            ],
            "progress_percent":       self._progress_percent(),
            # Test results (pushed by SuiteRunnerWorker)
            "tests_passed":           self._test_result.passed,
            "tests_skipped":          self._test_result.skipped,
            "tests_failed":           self._test_result.failed,
            "tests_commit":           self._test_result.commit_sha,
            # Live Git
            "last_commit":            git["sha"],
            "last_commit_message":    git["message"],
            "branch":                 git["branch"],
        }
