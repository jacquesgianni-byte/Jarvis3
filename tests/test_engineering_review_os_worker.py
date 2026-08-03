"""
Tests — EngineeringReviewOSWorker (Worker OS Integration)
Genesis-033 Integration Sprint

Tests the Worker OS wrapper: contract, validation, execution, evidence resolution.
Does not test the underlying pipeline (already covered by test_engineering_review_worker_g033.py).
"""

import dataclasses
import json
import os
import tempfile

import pytest

from core.workers.engineering_review_worker import EngineeringReviewOSWorker
from core.workers.models import WorkerTask, WorkerResult


# ── Minimal evidence fixture ───────────────────────────────────────────────────

_EVIDENCE = {
    "genesis": "033",
    "sprint": "002",
    "status": "complete",
    "commits": ["0dcba34"],
    "files_added": ["core/goal_intelligence/engine.py"],
    "files_modified": ["core/agent.py"],
    "architecture_decisions": [],
    "tests_added": 92,
    "test_results": {"passed": 3543, "skipped": 33, "failed": 0, "warnings": 0},
    "desktop_validation": {
        "status": "passed",
        "scenarios": ["Goal declaration stored", "Status recall shows hierarchy"],
        "notes": None,
    },
    "technical_debt": [],
    "risks": [],
    "future_improvements": [
        {
            "title": "Fix tag mutation bug",
            "description": "Deactivation is a no-op due to KE update_memory not accepting tags",
            "priority": "high",
            "category": "correctness",
        }
    ],
    "technical_problem": "No structured work hierarchy.",
    "technical_uncertainty": "Whether KE tags can represent three-level hierarchy.",
    "hypothesis": "Yes, with deterministic detector and tag storage.",
    "approach": "GoalIntelligenceEngine facade over three trackers.",
    "experiments": ["Five desktop validation scenarios passed."],
    "results": "All scenarios passed.",
    "validation": "3543 tests passing.",
    "remaining_unknowns": ["Tag mutation behaviour at scale."],
    "recommendation": "ENTER_STABILISATION",
    "recommendation_reason": "Tag mutation bug must be fixed before Genesis-034.",
}


def _make_task(payload: dict, task_type: str = "run_engineering_review") -> WorkerTask:
    return WorkerTask(task_type=task_type, payload=payload, requester="test")


# ── Worker contract ────────────────────────────────────────────────────────────

class TestWorkerContract:
    def test_name(self):
        w = EngineeringReviewOSWorker()
        assert w.name == "engineering_review_worker"

    def test_description_non_empty(self):
        w = EngineeringReviewOSWorker()
        assert len(w.description) > 0

    def test_capabilities(self):
        w = EngineeringReviewOSWorker()
        assert "run_engineering_review" in w.capabilities

    def test_is_available_initially(self):
        w = EngineeringReviewOSWorker()
        assert w.is_available is True


# ── Validation ─────────────────────────────────────────────────────────────────

class TestValidation:
    def test_valid_with_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            assert w.validate(task) is True

    def test_valid_with_genesis_and_review_file(self):
        with tempfile.TemporaryDirectory() as d:
            # Write a dummy review file
            path = os.path.join(d, "genesis_033_sprint_002_review.json")
            with open(path, "w") as f:
                json.dump({"review": {"genesis": "033", "sprint": "002",
                    "status": "complete", "commits": [], "files_added": [],
                    "files_modified": [], "architecture_decisions": [],
                    "tests_added": 0,
                    "test_results": {"passed": 0, "skipped": 0, "failed": 0, "warnings": 0},
                    "desktop_validation": {"status": "passed", "scenarios": [], "notes": None},
                    "technical_debt": [], "risks": [], "future_improvements": [],
                    "recommendation": "CONTINUE_GENESIS", "recommendation_reason": "test"},
                    "rd_evidence": {"genesis": "033", "technical_problem": "",
                    "technical_uncertainty": "", "hypothesis": "", "approach": "",
                    "experiments": [], "results": "", "validation": "", "remaining_unknowns": []},
                    "improvements": [], "rendered_at": "2026-08-03T00:00:00"}, f)
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"genesis": "033"})
            assert w.validate(task) is True

    def test_invalid_wrong_task_type(self):
        w = EngineeringReviewOSWorker()
        task = _make_task({"evidence": _EVIDENCE}, task_type="plan_implementation")
        assert w.validate(task) is False

    def test_invalid_no_evidence_no_genesis_no_files(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({})
            assert w.validate(task) is False


# ── Execution with explicit evidence ───────────────────────────────────────────

class TestExecutionWithEvidence:
    def test_returns_worker_result(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert isinstance(result, WorkerResult)

    def test_success_true(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert result.success is True

    def test_worker_name_correct(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert result.worker_name == "engineering_review_worker"

    def test_data_contains_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert "markdown" in result.data
            assert len(result.data["markdown"]) > 0

    def test_data_contains_genesis(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert result.data["genesis"] == "033"

    def test_data_contains_json_path(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert "json_path" in result.data
            assert os.path.exists(result.data["json_path"])

    def test_data_contains_md_path(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert "md_path" in result.data
            assert os.path.exists(result.data["md_path"])

    def test_observations_non_empty(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert len(result.observations) > 0

    def test_requires_approval_false(self):
        """Reviews are read-only — no approval needed."""
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert result.requires_approval is False

    def test_markdown_contains_recommendation(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert "ENTER_STABILISATION" in result.data["markdown"]

    def test_markdown_contains_genesis_number(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            result = w.execute(task)
            assert "033" in result.data["markdown"]

    def test_worker_available_after_execution(self):
        """Worker resets to available after completing a task."""
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"evidence": _EVIDENCE})
            w.execute(task)
            assert w.is_available is True


# ── Evidence resolution from file ─────────────────────────────────────────────

class TestEvidenceResolution:
    def _write_review_file(self, directory: str, genesis: str = "033", sprint: str = "002"):
        """Write a minimal review JSON to the given directory."""
        content = {
            "review": {
                "genesis": genesis, "sprint": sprint,
                "status": "complete", "commits": ["abc"],
                "files_added": ["core/agent.py"], "files_modified": [],
                "architecture_decisions": [], "tests_added": 10,
                "test_results": {"passed": 100, "skipped": 0, "failed": 0, "warnings": 0},
                "desktop_validation": {"status": "passed", "scenarios": ["Test"], "notes": None},
                "technical_debt": [], "risks": [], "future_improvements": [],
                "recommendation": "BEGIN_NEXT_GENESIS",
                "recommendation_reason": "All done.",
            },
            "rd_evidence": {
                "genesis": genesis, "technical_problem": "Problem.",
                "technical_uncertainty": "Uncertainty.", "hypothesis": "Hypothesis.",
                "approach": "Approach.", "experiments": ["Experiment."],
                "results": "Results.", "validation": "Validation.",
                "remaining_unknowns": [],
            },
            "improvements": [],
            "rendered_at": "2026-08-03T00:00:00",
        }
        path = os.path.join(directory, f"genesis_{genesis}_sprint_{sprint}_review.json")
        with open(path, "w") as f:
            json.dump(content, f)
        return path

    def test_load_by_genesis_number(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_review_file(d, genesis="033", sprint="002")
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"genesis": "033"})
            result = w.execute(task)
            assert result.success is True
            assert result.data["genesis"] == "033"

    def test_load_latest_when_no_genesis_specified(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_review_file(d, genesis="033", sprint="002")
            w = EngineeringReviewOSWorker(output_dir=d)
            task = _make_task({"description": "Run an engineering review"})
            result = w.execute(task)
            assert result.success is True

    def test_fail_when_no_evidence_and_no_files(self):
        with tempfile.TemporaryDirectory() as d:
            w = EngineeringReviewOSWorker(output_dir=d)
            # validate() will fail first, but test execute() directly
            task = WorkerTask(
                task_type="run_engineering_review",
                payload={"description": "Run a review"},
                requester="test",
            )
            # Force execute without validate
            w._status = w._status  # keep idle
            result = w.execute(task)
            assert result.success is False

    def test_evidence_takes_priority_over_genesis(self):
        """Explicit evidence dict should be used even if genesis also present."""
        with tempfile.TemporaryDirectory() as d:
            self._write_review_file(d, genesis="032", sprint="003")
            w = EngineeringReviewOSWorker(output_dir=d)
            # Evidence says 033, file says 032 — evidence wins
            task = _make_task({"evidence": _EVIDENCE, "genesis": "032"})
            result = w.execute(task)
            assert result.success is True
            assert result.data["genesis"] == "033"  # from evidence, not file
