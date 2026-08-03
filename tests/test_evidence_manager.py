"""
Tests — Engineering Evidence Manager
Genesis-034 Sprint-002
"""

import json
import pytest

from core.engineering.evidence.models import EvidenceSnapshot
from core.engineering.evidence.store import EvidenceStore
from core.engineering.evidence.manager import EvidenceManager


# ── In-memory KE stub ─────────────────────────────────────────────────────────

class _MemoryStore:
    def __init__(self):
        self._records: dict = {}

    def store_memory(self, subject, category, attribute, value, tags=None, **kwargs):
        from datetime import datetime, timezone
        from uuid import uuid4

        class Rec:
            pass

        key = f"{subject}::{attribute}"
        r = Rec()
        r.id = str(uuid4())
        r.subject = subject
        r.category = category
        r.attribute = attribute
        r.value = value
        r.tags = list(tags or [])
        r.created_at = datetime.now(timezone.utc)
        r.updated_at = datetime.now(timezone.utc)
        r.expires_at = None
        self._records[key] = r
        return r

    def recall_memory(self, subject, attribute, category=None):
        return self._records.get(f"{subject}::{attribute}")

    def forget_memory(self, subject, attribute, permanent=False, **kwargs):
        key = f"{subject}::{attribute}"
        if key in self._records:
            del self._records[key]
            return True
        return False

    def update_memory(self, subject, attribute, value, **kwargs):
        key = f"{subject}::{attribute}"
        if key in self._records:
            self._records[key].value = value
        return self._records.get(key)

    def list_memories(self, subject=None, limit=100, **kwargs):
        results = list(self._records.values())
        if subject:
            results = [r for r in results if r.subject == subject]
        return results[:limit]


@pytest.fixture()
def ke():
    return _MemoryStore()


# ── EvidenceSnapshot ──────────────────────────────────────────────────────────

class TestEvidenceSnapshot:
    def test_to_dict_contains_genesis(self):
        snap = EvidenceSnapshot(genesis="034")
        d = snap.to_dict()
        assert d["genesis"] == "034"

    def test_to_dict_contains_all_required_fields(self):
        snap = EvidenceSnapshot(genesis="034")
        d = snap.to_dict()
        required = [
            "genesis", "sprint", "status", "commits", "files_added",
            "files_modified", "test_results", "desktop_validation",
            "recommendation", "recommendation_reason",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"

    def test_is_reviewable_false_without_reason(self):
        snap = EvidenceSnapshot(genesis="034")
        assert snap.is_reviewable() is False

    def test_is_reviewable_true_with_reason(self):
        snap = EvidenceSnapshot(
            genesis="034",
            recommendation_reason="All tests passing.",
        )
        assert snap.is_reviewable() is True

    def test_is_reviewable_false_without_genesis(self):
        snap = EvidenceSnapshot(genesis="", recommendation_reason="Done.")
        assert snap.is_reviewable() is False


# ── EvidenceStore ─────────────────────────────────────────────────────────────

class TestEvidenceStore:
    def test_initialise_creates_genesis_record(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        assert store.has_evidence("034") is True

    def test_append_commit_stored(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        store.append_commit("034", "abc1234")
        snap = store.snapshot("034")
        assert "abc1234" in snap.commits

    def test_append_commit_deduplicates(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        store.append_commit("034", "abc1234")
        store.append_commit("034", "abc1234")
        snap = store.snapshot("034")
        assert snap.commits.count("abc1234") == 1

    def test_multiple_commits_stored(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        store.append_commit("034", "abc1234")
        store.append_commit("034", "def5678")
        snap = store.snapshot("034")
        assert "abc1234" in snap.commits
        assert "def5678" in snap.commits

    def test_set_test_results(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        store.set_test_results("034", passed=3613, skipped=33, failed=0)
        snap = store.snapshot("034")
        assert snap.test_results["passed"] == 3613
        assert snap.test_results["failed"] == 0

    def test_set_files(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        store.set_files("034",
            files_added=["core/engineering/evidence/manager.py"],
            files_modified=["core/agent.py"],
        )
        snap = store.snapshot("034")
        assert "core/engineering/evidence/manager.py" in snap.files_added
        assert "core/agent.py" in snap.files_modified

    def test_set_desktop_validation(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        store.set_desktop_validation("034", "passed", ["Scenario 1", "Scenario 2"])
        snap = store.snapshot("034")
        assert snap.desktop_validation["status"] == "passed"
        assert "Scenario 1" in snap.desktop_validation["scenarios"]

    def test_set_recommendation(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        store.set_recommendation("034", "BEGIN_NEXT_GENESIS", "All done.")
        snap = store.snapshot("034")
        assert snap.recommendation == "BEGIN_NEXT_GENESIS"
        assert snap.recommendation_reason == "All done."

    def test_snapshot_missing_genesis_returns_defaults(self, ke):
        store = EvidenceStore(ke)
        snap = store.snapshot("099")
        assert snap.genesis == "099"
        assert snap.commits == []
        assert snap.test_results["passed"] == 0

    def test_has_evidence_false_for_unknown(self, ke):
        store = EvidenceStore(ke)
        assert store.has_evidence("099") is False

    def test_set_field_generic(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        store.set_field("034", "technical_problem", "No evidence system existed.")
        snap = store.snapshot("034")
        assert snap.technical_problem == "No evidence system existed."

    def test_append_to_list_field(self, ke):
        store = EvidenceStore(ke)
        store.initialise("034")
        store.append_to_list_field("034", "experiments", "Experiment A")
        store.append_to_list_field("034", "experiments", "Experiment B")
        snap = store.snapshot("034")
        assert "Experiment A" in snap.experiments
        assert "Experiment B" in snap.experiments


# ── EvidenceManager ───────────────────────────────────────────────────────────

class TestEvidenceManager:
    def test_open_initialises_evidence(self, ke):
        mgr = EvidenceManager(ke)
        mgr.open("034")
        assert mgr.has_evidence("034") is True

    def test_record_field(self, ke):
        mgr = EvidenceManager(ke)
        mgr.open("034")
        mgr.record("034", "technical_problem", "Evidence was never collected.")
        snap = mgr.snapshot("034")
        assert "Evidence" in snap.technical_problem

    def test_record_desktop_validation(self, ke):
        mgr = EvidenceManager(ke)
        mgr.open("034")
        mgr.record_desktop_validation(
            "034", "passed",
            ["Open Genesis-034 sets active", "Close Genesis-034 runs review"],
        )
        snap = mgr.snapshot("034")
        assert snap.desktop_validation["status"] == "passed"

    def test_record_recommendation(self, ke):
        mgr = EvidenceManager(ke)
        mgr.open("034")
        mgr.record_recommendation("034", "BEGIN_NEXT_GENESIS", "Sprint complete.")
        snap = mgr.snapshot("034")
        assert snap.recommendation == "BEGIN_NEXT_GENESIS"
        assert snap.recommendation_reason == "Sprint complete."

    def test_snapshot_is_reviewable_after_recommendation(self, ke):
        mgr = EvidenceManager(ke)
        mgr.open("034")
        mgr.record_recommendation("034", "BEGIN_NEXT_GENESIS", "Done.")
        snap = mgr.snapshot("034")
        assert snap.is_reviewable() is True

    def test_snapshot_to_dict_passable_to_worker(self, ke):
        """snapshot().to_dict() must contain all evidence worker fields."""
        mgr = EvidenceManager(ke)
        mgr.open("034")
        mgr.record_recommendation("034", "BEGIN_NEXT_GENESIS", "Done.")
        d = mgr.snapshot("034").to_dict()
        assert d["genesis"] == "034"
        assert "test_results" in d
        assert "desktop_validation" in d
        assert "recommendation" in d

    def test_collect_worker_result_extracts_test_counts(self, ke):
        mgr = EvidenceManager(ke)
        mgr.open("034")

        class FakeResult:
            data = {"passed": 3613, "skipped": 33, "failed": 0, "warnings": 0}

        mgr.collect_worker_result("034", FakeResult())
        snap = mgr.snapshot("034")
        assert snap.test_results["passed"] == 3613
        assert snap.test_results["failed"] == 0

    def test_collect_worker_result_coordinator_format(self, ke):
        """Also handles coordinator-wrapped results."""
        mgr = EvidenceManager(ke)
        mgr.open("034")

        class FakeResult:
            data = {
                "results": {
                    "suite_runner_worker": {
                        "passed": 100, "skipped": 5, "failed": 0
                    }
                }
            }

        mgr.collect_worker_result("034", FakeResult())
        snap = mgr.snapshot("034")
        assert snap.test_results["passed"] == 100

    def test_mark_complete_sets_status(self, ke):
        mgr = EvidenceManager(ke)
        mgr.open("034")
        mgr.mark_complete("034")
        snap = mgr.snapshot("034")
        assert snap.status == "complete"

    def test_has_evidence_false_for_unknown(self, ke):
        mgr = EvidenceManager(ke)
        assert mgr.has_evidence("099") is False


# ── Integration: EvidenceManager → EvidenceSnapshot → worker dict ─────────────

class TestEvidenceToWorkerIntegration:
    def test_full_evidence_snapshot_passable_as_evidence(self, ke):
        """Full lifecycle: open → record → snapshot → to_dict → worker-ready."""
        mgr = EvidenceManager(ke)
        mgr.open("034", sprint="002")
        mgr._store.append_commit("034", "ae7df07")
        mgr._store.set_test_results("034", passed=3613, skipped=33, failed=0)
        mgr.record_desktop_validation(
            "034", "passed",
            ["Open Genesis-034 sets active", "Close Genesis-034 runs review",
             "Already closed returns graceful message",
             "Open while active blocks with message"],
        )
        mgr.record_recommendation(
            "034", "BEGIN_NEXT_GENESIS",
            "Engineering Lifecycle Manager complete. All desktop scenarios pass."
        )
        mgr.mark_complete("034")

        snap = mgr.snapshot("034")
        d = snap.to_dict()

        assert d["genesis"] == "034"
        assert d["sprint"] == "002"
        assert d["status"] == "complete"
        assert "ae7df07" in d["commits"]
        assert d["test_results"]["passed"] == 3613
        assert d["desktop_validation"]["status"] == "passed"
        assert d["recommendation"] == "BEGIN_NEXT_GENESIS"
        assert snap.is_reviewable() is True
