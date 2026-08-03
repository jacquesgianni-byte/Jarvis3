"""
Tests — EngineeringReviewWorker
Genesis-033 Sprint-001
"""

import dataclasses
import json
import os
import tempfile

import pytest

from core.engineering.review.models import (
    GenesisReport,
    GenesisStatus,
    Recommendation,
)
from core.engineering.review.review_worker import EngineeringReviewWorker


# ── Shared evidence fixture ────────────────────────────────────────────────────

GENESIS_032_EVIDENCE = {
    "genesis": "032",
    "sprint": "003",
    "status": "complete",
    "commits": ["f57e84f", "83cda59", "7408216"],
    "files_added": [
        "jarvis/core/semantic_recall_engine.py",
        "jarvis/core/relationship_recall_engine.py",
        "jarvis/core/episodic_memory_engine.py",
    ],
    "files_modified": ["jarvis/core/agent.py"],
    "architecture_decisions": [
        {
            "decision": "Provider architecture for recall engines",
            "rationale": "Allows new recall types to be added without modifying core engine",
            "alternatives": ["Monolithic recall handler"],
        },
        {
            "decision": "Episodes assembled from existing KnowledgeEngine — no duplicate storage",
            "rationale": "Single source of truth; episodes are a query view, not stored entities",
            "alternatives": ["Separate episode store"],
        },
    ],
    "tests_added": 49,
    "test_results": {
        "passed": 3387,
        "skipped": 33,
        "failed": 0,
        "warnings": 0,
    },
    "desktop_validation": {
        "status": "passed",
        "scenarios": [
            "Semantic recall — property and group queries",
            "Relationship recall — how_related, who_related, which_group",
            "Episodic recall — labeled episode (Genesis-027)",
            "Episodic recall — temporal episode (yesterday)",
        ],
        "notes": None,
    },
    "technical_debt": [],
    "risks": [],
    "future_improvements": [
        {
            "title": "Day-name episodic recall",
            "description": "Recall episodes by day name (Monday, Tuesday) not just date expressions",
            "priority": "medium",
            "category": "memory",
        },
        {
            "title": "Memory confidence scoring",
            "description": "Weight memories by confidence when assembling recall results",
            "priority": "medium",
            "category": "memory",
        },
        {
            "title": "Contradiction detection",
            "description": "Detect when new memories contradict existing facts",
            "priority": "high",
            "category": "memory",
        },
    ],
    "technical_problem": (
        "Jarvis had no ability to recall related events as coherent episodes "
        "or understand semantic and relationship context across its memory store."
    ),
    "technical_uncertainty": (
        "Whether deterministic grouping of existing memories could produce "
        "coherent episodic recall without AI summarisation."
    ),
    "hypothesis": (
        "A provider architecture over KnowledgeEngine can assemble meaningful "
        "recall results for semantic, relationship, and episodic queries using "
        "only stored tags and metadata."
    ),
    "approach": (
        "Built three layered recall engines (Semantic, Relationship, Episodic) "
        "each using a provider pattern over the existing KnowledgeEngine. "
        "No duplicate storage. Episodes assembled at query time."
    ),
    "experiments": [
        "SemanticRecallEngine with five provider types validated against property and group queries",
        "RelationshipRecallEngine with dual storage format support validated against pet sibling queries",
        "EpisodicMemoryEngine with labeled and temporal providers validated against Genesis-label and date queries",
    ],
    "results": (
        "All three engines passed desktop validation. No AI call required for recall. "
        "Average response time under 100ms."
    ),
    "validation": "3387 automated tests passing. Desktop validation passed all four scenarios.",
    "remaining_unknowns": [
        "Behaviour at scale with hundreds of stored memories",
        "Confidence weighting when multiple memories match the same query",
    ],
    "recommendation": "BEGIN_NEXT_GENESIS",
    "recommendation_reason": (
        "Memory Intelligence trilogy is complete. Semantic, Relationship, and Episodic "
        "recall all validated. No failed tests. No technical debt. Genesis-033 Goal & "
        "Task Intelligence is the logical next capability."
    ),
}


@pytest.fixture()
def tmp_worker():
    """Worker wired to a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield EngineeringReviewWorker(output_dir=tmpdir), tmpdir


# ── run() ──────────────────────────────────────────────────────────────────────

class TestRunReturnType:
    def test_returns_genesis_report(self, tmp_worker):
        worker, _ = tmp_worker
        result = worker.run(GENESIS_032_EVIDENCE)
        assert isinstance(result, GenesisReport)

    def test_review_genesis_matches(self, tmp_worker):
        worker, _ = tmp_worker
        result = worker.run(GENESIS_032_EVIDENCE)
        assert result.review.genesis == "032"

    def test_review_sprint_matches(self, tmp_worker):
        worker, _ = tmp_worker
        result = worker.run(GENESIS_032_EVIDENCE)
        assert result.review.sprint == "003"

    def test_review_status_complete(self, tmp_worker):
        worker, _ = tmp_worker
        result = worker.run(GENESIS_032_EVIDENCE)
        assert result.review.status == GenesisStatus.COMPLETE

    def test_improvements_populated(self, tmp_worker):
        worker, _ = tmp_worker
        result = worker.run(GENESIS_032_EVIDENCE)
        assert len(result.improvements) == 3

    def test_rd_evidence_populated(self, tmp_worker):
        worker, _ = tmp_worker
        result = worker.run(GENESIS_032_EVIDENCE)
        assert result.rd_evidence.technical_problem != ""

    def test_rendered_at_set(self, tmp_worker):
        worker, _ = tmp_worker
        result = worker.run(GENESIS_032_EVIDENCE)
        assert result.rendered_at != ""


# ── _validate() ───────────────────────────────────────────────────────────────

class TestValidation:
    def test_raises_when_failed_tests_and_complete(self, tmp_worker):
        worker, _ = tmp_worker
        bad_evidence = dict(GENESIS_032_EVIDENCE)
        bad_evidence = {**GENESIS_032_EVIDENCE, "test_results": {
            "passed": 3380, "skipped": 33, "failed": 7, "warnings": 0
        }}
        with pytest.raises(ValueError, match="failed test"):
            worker.run(bad_evidence)

    def test_raises_when_recommendation_reason_empty(self, tmp_worker):
        worker, _ = tmp_worker
        bad_evidence = {**GENESIS_032_EVIDENCE, "recommendation_reason": ""}
        with pytest.raises(ValueError, match="recommendation_reason"):
            worker.run(bad_evidence)

    def test_raises_when_genesis_empty(self, tmp_worker):
        worker, _ = tmp_worker
        bad_evidence = {**GENESIS_032_EVIDENCE, "genesis": ""}
        with pytest.raises(ValueError, match="genesis"):
            worker.run(bad_evidence)

    def test_no_error_when_failed_but_in_progress(self, tmp_worker):
        """Failures are allowed if status is not COMPLETE."""
        worker, _ = tmp_worker
        evidence = {
            **GENESIS_032_EVIDENCE,
            "status": "in_progress",
            "test_results": {"passed": 100, "skipped": 0, "failed": 2, "warnings": 0},
        }
        # Should not raise
        result = worker.run(evidence)
        assert isinstance(result, GenesisReport)


# ── _persist() ────────────────────────────────────────────────────────────────

class TestPersist:
    def test_json_file_written(self, tmp_worker):
        worker, tmpdir = tmp_worker
        worker.run(GENESIS_032_EVIDENCE)
        json_path = os.path.join(tmpdir, "genesis_032_sprint_003_review.json")
        assert os.path.exists(json_path)

    def test_markdown_file_written(self, tmp_worker):
        worker, tmpdir = tmp_worker
        worker.run(GENESIS_032_EVIDENCE)
        md_path = os.path.join(tmpdir, "genesis_032_sprint_003_report.md")
        assert os.path.exists(md_path)

    def test_json_is_valid_and_deserialises(self, tmp_worker):
        worker, tmpdir = tmp_worker
        worker.run(GENESIS_032_EVIDENCE)
        json_path = os.path.join(tmpdir, "genesis_032_sprint_003_review.json")
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["review"]["genesis"] == "032"
        assert data["review"]["sprint"] == "003"
        assert data["review"]["status"] == "complete"
        assert data["review"]["test_results"]["passed"] == 3387
        assert data["review"]["test_results"]["failed"] == 0

    def test_markdown_file_non_empty(self, tmp_worker):
        worker, tmpdir = tmp_worker
        worker.run(GENESIS_032_EVIDENCE)
        md_path = os.path.join(tmpdir, "genesis_032_sprint_003_report.md")
        with open(md_path, encoding="utf-8") as fh:
            content = fh.read()
        assert len(content) > 0

    def test_json_contains_improvements(self, tmp_worker):
        worker, tmpdir = tmp_worker
        worker.run(GENESIS_032_EVIDENCE)
        json_path = os.path.join(tmpdir, "genesis_032_sprint_003_review.json")
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert len(data["improvements"]) == 3
        titles = [fi["title"] for fi in data["improvements"]]
        assert "Contradiction detection" in titles

    def test_json_contains_rd_evidence(self, tmp_worker):
        worker, tmpdir = tmp_worker
        worker.run(GENESIS_032_EVIDENCE)
        json_path = os.path.join(tmpdir, "genesis_032_sprint_003_review.json")
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["rd_evidence"]["genesis"] == "032"
        assert data["rd_evidence"]["technical_problem"] != ""

    def test_json_written_before_markdown(self, tmp_worker):
        """JSON mtime must be <= Markdown mtime."""
        worker, tmpdir = tmp_worker
        worker.run(GENESIS_032_EVIDENCE)
        json_path = os.path.join(tmpdir, "genesis_032_sprint_003_review.json")
        md_path   = os.path.join(tmpdir, "genesis_032_sprint_003_report.md")
        assert os.path.getmtime(json_path) <= os.path.getmtime(md_path)

    def test_output_dir_created_automatically(self):
        with tempfile.TemporaryDirectory() as parent:
            new_dir = os.path.join(parent, "auto_created")
            worker = EngineeringReviewWorker(output_dir=new_dir)
            assert os.path.isdir(new_dir)

    def test_recommendation_in_json(self, tmp_worker):
        worker, tmpdir = tmp_worker
        worker.run(GENESIS_032_EVIDENCE)
        json_path = os.path.join(tmpdir, "genesis_032_sprint_003_review.json")
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["review"]["recommendation"] == "BEGIN_NEXT_GENESIS"
