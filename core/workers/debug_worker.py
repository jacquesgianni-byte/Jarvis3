"""
Jarvis Debug Worker (Genesis-027 Sprint-001)

Adapts the existing SessionAnalysisWorker into the Worker contract.

Responsibilities:
    - Accept a WorkerTask with task_type="analyse_session"
    - Delegate analysis to SessionAnalysisWorker
    - Return a structured WorkerResult

Design constraints:
    - Does NOT modify SessionAnalysisWorker
    - Adapter pattern only — wraps existing functionality
    - No AI calls
    - No file I/O (log lines supplied in task payload)
    - Read-only analysis

Task payload:
    {
        "log_lines": list[str]   # raw log lines from jarvis.log
    }

Result data:
    {
        "health_score":    int,
        "session_turns":   int,
        "successes":       list[str],
        "issues":          list[dict],
        "summary":         str,
    }

Genesis-027 Sprint-001.
"""

from __future__ import annotations

import logging

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask
from core.workers.session_analysis_worker import SessionAnalysisWorker

logger = logging.getLogger(__name__)


class DebugWorker(Worker):
    """
    Analyses Jarvis session logs and produces a structured engineering report.

    Wraps SessionAnalysisWorker (Genesis-W001) in the standard Worker
    contract so it integrates with WorkerManager and WorkerOrchestrator.

    Capabilities:
        analyse_session — analyse a list of log lines
    """

    def __init__(self) -> None:
        super().__init__()
        self._analyser = SessionAnalysisWorker()

    # ------------------------------------------------------------------
    # Worker contract
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "debug_worker"

    @property
    def description(self) -> str:
        return (
            "Analyses Jarvis desktop session logs. Detects routing problems, "
            "memory issues, performance bottlenecks, and exceptions. "
            "Returns a structured engineering report with health score."
        )

    @property
    def capabilities(self) -> list[str]:
        return ["analyse_session"]

    def validate(self, task: WorkerTask) -> bool:
        """
        Validate that the task contains log_lines in the payload.

        Returns False if:
            - task_type is not "analyse_session"
            - payload is missing "log_lines"
            - log_lines is not a list
        """
        if task.task_type != "analyse_session":
            return False
        log_lines = task.payload.get("log_lines")
        if not isinstance(log_lines, list):
            logger.warning(
                "[DEBUG_WORKER] Invalid payload: expected log_lines list, got %r",
                type(log_lines).__name__,
            )
            return False
        return True

    def execute(self, task: WorkerTask) -> WorkerResult:
        """
        Analyse session log lines and return an engineering report.

        Args:
            task: WorkerTask with payload["log_lines"] = list[str]

        Returns:
            WorkerResult with health score, successes, issues, and summary.
        """
        self._begin(task)

        try:
            log_lines: list[str] = task.payload["log_lines"]

            logger.info(
                "[DEBUG_WORKER] Analysing %d log lines.", len(log_lines)
            )

            report = self._analyser.analyse_session(log_lines)

            # Convert EngineeringReport to WorkerResult
            issue_dicts = [
                {
                    "severity":     issue.severity.value,
                    "category":     issue.category.value,
                    "title":        issue.title,
                    "description":  issue.description,
                    "evidence":     list(issue.evidence),
                    "confidence":   issue.confidence,
                    "likely_files": issue.likely_files,
                    "recommendation": issue.recommendation,
                }
                for issue in report.issues
            ]

            observations = [report.summary] + report.successes
            recommendations = [
                f"[{i['severity']}] {i['title']}: {i['recommendation']}"
                for i in issue_dicts
            ]

            return self._succeed(WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=True,
                observations=tuple(observations),
                recommendations=tuple(recommendations),
                requires_approval=False,
                data={
                    "health_score":  report.health_score,
                    "session_turns": report.session_turns,
                    "successes":     report.successes,
                    "issues":        issue_dicts,
                    "summary":       report.summary,
                },
            ))

        except Exception as exc:
            logger.exception("[DEBUG_WORKER] Analysis failed.")
            return self._fail(task.task_id, str(exc))