"""
Engineering Review Worker — Worker OS Integration
Genesis-033 Integration Sprint

Wraps the EngineeringReviewWorker pipeline as a first-class Worker OS citizen.
Registered with WorkerFactory, executed via WorkerCoordinator.

This class is a thin adapter. All pipeline logic lives in:
    core/engineering/review/review_worker.py  (unchanged)

Capability: "run_engineering_review"

Payload contract:
    task.payload["evidence"]     — full evidence dict (optional, takes precedence)
    task.payload["genesis"]      — genesis number string e.g. "033" (optional)
    task.payload["description"]  — original user request (always present)

Resolution order:
    1. payload["evidence"] present → use directly
    2. payload["genesis"] present → load latest JSON for that genesis
    3. Neither → load most recent review JSON from output_dir
    4. No files found → fail with helpful message

WorkerResult.data:
    {
        "genesis":     str,
        "sprint":      str,
        "markdown":    str,   ← rendered Markdown report
        "json_path":   str,   ← path to persisted JSON
        "md_path":     str,   ← path to persisted Markdown
        "report":      dict,  ← dataclasses.asdict(GenesisReport)
    }
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
from typing import Optional

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = "engineering_reviews"


class EngineeringReviewOSWorker(Worker):
    """
    Worker OS adapter for the EngineeringReview pipeline.

    Registered as "engineering_review_worker".
    Capability: "run_engineering_review".

    The agent never constructs this directly — it flows through:
        EngineeringIntentDetector → TaskPlanner → WorkerCoordinator → here
    """

    def __init__(self, output_dir: str = _DEFAULT_OUTPUT_DIR) -> None:
        super().__init__()
        self._output_dir = output_dir

    # ── Worker contract ────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "engineering_review_worker"

    @property
    def description(self) -> str:
        return (
            "Executes the Engineering Review pipeline for a Genesis. "
            "Produces structured JSON and a rendered Markdown report."
        )

    @property
    def capabilities(self) -> list[str]:
        return ["run_engineering_review"]

    def validate(self, task: WorkerTask) -> bool:
        if task.task_type != "run_engineering_review":
            return False
        # At least one of: evidence dict, genesis number, or reviewable files
        payload = task.payload
        if payload.get("evidence"):
            return True
        if payload.get("genesis"):
            return True
        # Accept if review files exist
        if os.path.isdir(self._output_dir):
            files = self._list_review_files()
            if files:
                return True
        logger.warning(
            "[REVIEW_WORKER] Validation failed: no evidence, genesis, or review files."
        )
        return False

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)

        try:
            evidence = self._resolve_evidence(task)
            if evidence is None:
                return self._fail(
                    task.task_id,
                    "Could not resolve evidence for this review. "
                    "Please provide a genesis number or a full evidence dict.",
                )

            # Import pipeline here to keep this module lightweight at import time
            from core.engineering.review.review_worker import (
                EngineeringReviewWorker as _Pipeline,
            )
            from core.engineering.review.markdown_renderer import MarkdownRenderer

            pipeline = _Pipeline(output_dir=self._output_dir)
            import time as _time
            _t0 = _time.perf_counter()
            report   = pipeline.run(evidence)
            _duration_ms = (_time.perf_counter() - _t0) * 1000

            # Stamp execution metadata onto the report
            from core.engineering.review.models import ExecutionMetadata
            from datetime import datetime, timezone
            report.metadata = ExecutionMetadata(
                duration_ms=round(_duration_ms, 1),
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

            # Render Markdown from the structured report
            renderer = MarkdownRenderer()
            markdown = renderer.render(report)

            # Build file paths (mirrors pipeline naming convention)
            base      = f"genesis_{report.review.genesis}_sprint_{report.review.sprint}"
            json_path = os.path.join(self._output_dir, f"{base}_review.json")
            md_path   = os.path.join(self._output_dir, f"{base}_report.md")

            observations = [
                f"Genesis {report.review.genesis} Sprint {report.review.sprint} reviewed.",
                f"Status: {report.review.status.value}",
                f"Tests: {report.review.test_results.passed} passed, "
                f"{report.review.test_results.failed} failed.",
                f"Recommendation: {report.review.recommendation.value}",
                f"JSON: {json_path}",
                f"Markdown: {md_path}",
            ]

            recommendations = list(report.review.future_improvements or [])

            return self._succeed(WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=True,
                observations=tuple(observations),
                recommendations=tuple(recommendations),
                requires_approval=False,   # review is read-only, no approval needed
                data={
                    "genesis":   report.review.genesis,
                    "sprint":    report.review.sprint,
                    "markdown":  markdown,
                    "json_path": json_path,
                    "md_path":   md_path,
                    "report":    dataclasses.asdict(report),
                },
            ))

        except ValueError as exc:
            return self._fail(task.task_id, f"Review validation error: {exc}")
        except Exception as exc:
            logger.exception("[REVIEW_WORKER] Unexpected error.")
            return self._fail(task.task_id, str(exc))

    # ── Evidence resolution ────────────────────────────────────────────────────

    def _resolve_evidence(self, task: WorkerTask) -> Optional[dict]:
        """
        Resolve evidence from payload, in priority order:
          1. payload["evidence"]  — explicit evidence dict
          2. payload["genesis"]   — load latest JSON for that genesis
          3. fallback             — load most recent JSON in output_dir
        """
        payload = task.payload

        # Priority 1: explicit evidence dict
        evidence = payload.get("evidence")
        if isinstance(evidence, dict) and evidence:
            logger.info("[REVIEW_WORKER] Using explicit evidence dict from payload.")
            return evidence

        # Priority 2: genesis number provided
        genesis = payload.get("genesis", "").strip()
        if genesis:
            return self._load_evidence_for_genesis(genesis)

        # Priority 3: load most recent review file
        return self._load_latest_evidence()

    def _load_evidence_for_genesis(self, genesis: str) -> Optional[dict]:
        """Load the most recent review JSON for a given genesis number."""
        pattern = re.compile(
            rf"^genesis_{re.escape(genesis)}_sprint_\d+_review\.json$",
            re.IGNORECASE,
        )
        matches = [
            f for f in self._list_review_files()
            if pattern.match(os.path.basename(f))
        ]
        if not matches:
            logger.warning(
                "[REVIEW_WORKER] No review JSON found for genesis=%r", genesis
            )
            return None
        # Most recent by modification time
        latest = max(matches, key=os.path.getmtime)
        return self._load_json(latest)

    def _load_latest_evidence(self) -> Optional[dict]:
        """Load the most recently modified review JSON."""
        files = self._list_review_files()
        if not files:
            logger.warning("[REVIEW_WORKER] No review files found in %r", self._output_dir)
            return None
        latest = max(files, key=os.path.getmtime)
        logger.info("[REVIEW_WORKER] Loading latest review: %s", latest)
        return self._load_json(latest)

    def _list_review_files(self) -> list[str]:
        """Return all *_review.json file paths in output_dir."""
        if not os.path.isdir(self._output_dir):
            return []
        return [
            os.path.join(self._output_dir, f)
            for f in os.listdir(self._output_dir)
            if f.endswith("_review.json")
        ]

    def _load_json(self, path: str) -> Optional[dict]:
        """Load and return a JSON file as a dict."""
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            # The persisted file is a GenesisReport dict — extract the review fields
            # and flatten into an evidence-compatible dict
            return self._flatten_report_to_evidence(data)
        except Exception as exc:
            logger.exception("[REVIEW_WORKER] Failed to load %r: %s", path, exc)
            return None

    def _flatten_report_to_evidence(self, report_dict: dict) -> dict:
        """
        Convert a persisted GenesisReport dict back to an evidence dict
        that the EngineeringReviewWorker pipeline can consume.
        """
        review  = report_dict.get("review", {})
        rd      = report_dict.get("rd_evidence", {})
        improv  = report_dict.get("improvements", [])

        tr = review.get("test_results", {})
        dv = review.get("desktop_validation", {})

        return {
            "genesis":               review.get("genesis", ""),
            "sprint":                review.get("sprint", ""),
            "status":                review.get("status", "complete"),
            "commits":               review.get("commits", []),
            "files_added":           review.get("files_added", []),
            "files_modified":        review.get("files_modified", []),
            "architecture_decisions": review.get("architecture_decisions", []),
            "tests_added":           review.get("tests_added", 0),
            "test_results": {
                "passed":   tr.get("passed", 0),
                "skipped":  tr.get("skipped", 0),
                "failed":   tr.get("failed", 0),
                "warnings": tr.get("warnings", 0),
            },
            "desktop_validation": {
                "status":    dv.get("status", "unknown"),
                "scenarios": dv.get("scenarios", []),
                "notes":     dv.get("notes"),
            },
            "technical_debt":      review.get("technical_debt", []),
            "risks":               review.get("risks", []),
            "future_improvements": [
                {
                    "title":       fi.get("title", ""),
                    "description": fi.get("description", ""),
                    "priority":    fi.get("priority", "medium"),
                    "category":    fi.get("category", "general"),
                }
                for fi in improv
            ],
            "technical_problem":     rd.get("technical_problem", ""),
            "technical_uncertainty": rd.get("technical_uncertainty", ""),
            "hypothesis":            rd.get("hypothesis", ""),
            "approach":              rd.get("approach", ""),
            "experiments":           rd.get("experiments", []),
            "results":               rd.get("results", ""),
            "validation":            rd.get("validation", ""),
            "remaining_unknowns":    rd.get("remaining_unknowns", []),
            "recommendation":        review.get("recommendation", "CONTINUE_GENESIS"),
            "recommendation_reason": review.get("recommendation_reason", ""),
        }
