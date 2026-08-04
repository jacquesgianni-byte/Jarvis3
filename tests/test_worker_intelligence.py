"""
Tests — Knowledge Graph & Worker Intelligence Engine
Genesis-039 Sprint-001
"""

import pytest
from core.worker_intelligence.models import CapabilityRecord, WorkerProfile
from core.worker_intelligence.store import WorkerIntelligenceStore
from core.worker_intelligence.engine import WorkerIntelligenceEngine


# ── In-memory KE stub ─────────────────────────────────────────────────────────

class _MemoryStore:
    def __init__(self):
        self._records: dict = {}

    def store_memory(self, subject, category, attribute, value, tags=None, **kwargs):
        from datetime import datetime, timezone
        from uuid import uuid4
        class Rec: pass
        key = f"{subject}::{attribute}"
        r = Rec()
        r.id = str(uuid4()); r.subject = subject; r.category = category
        r.attribute = attribute; r.value = value; r.tags = list(tags or [])
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


class _FakeWorkerResult:
    def __init__(self, worker_name: str, success: bool):
        self.worker_name = worker_name
        self.success     = success
        self.data        = {}
        self.error       = ""


@pytest.fixture()
def ke():
    return _MemoryStore()


# ── CapabilityRecord ──────────────────────────────────────────────────────────

class TestCapabilityRecord:
    def test_confidence_zero_with_no_executions(self):
        cap = CapabilityRecord(capability="run_tests")
        assert cap.confidence == 0.0

    def test_confidence_100_all_success(self):
        cap = CapabilityRecord(capability="run_tests", executions=5, successes=5)
        assert cap.confidence == 1.0

    def test_confidence_partial(self):
        cap = CapabilityRecord(capability="run_tests", executions=4, successes=3)
        assert cap.confidence == 0.75

    def test_has_data_false_when_no_executions(self):
        cap = CapabilityRecord(capability="run_tests")
        assert cap.has_data is False

    def test_has_data_true_when_executed(self):
        cap = CapabilityRecord(capability="run_tests", executions=1)
        assert cap.has_data is True

    def test_with_execution_success(self):
        cap  = CapabilityRecord(capability="run_tests")
        cap2 = cap.with_execution(success=True)
        assert cap2.executions == 1
        assert cap2.successes  == 1
        assert cap2.failures   == 0
        assert cap.executions  == 0   # original unchanged

    def test_with_execution_failure(self):
        cap  = CapabilityRecord(capability="run_tests")
        cap2 = cap.with_execution(success=False)
        assert cap2.failures == 1
        assert cap2.successes == 0

    def test_is_frozen(self):
        cap = CapabilityRecord(capability="run_tests")
        with pytest.raises((AttributeError, TypeError)):
            cap.executions = 5  # type: ignore


# ── WorkerProfile ─────────────────────────────────────────────────────────────

class TestWorkerProfile:
    def _make_profile(self, execs=10, successes=8) -> WorkerProfile:
        cap = CapabilityRecord("run_tests", executions=execs, successes=successes,
                               failures=execs-successes)
        return WorkerProfile(
            worker_id="suite_runner_worker",
            worker_name="suite_runner_worker",
            description="Runs the test suite.",
            capabilities=(cap,),
            total_executions=execs,
            total_successes=successes,
            total_failures=execs-successes,
            last_seen="2026-08-04T12:00:00",
        )

    def test_overall_confidence(self):
        p = self._make_profile(execs=10, successes=8)
        assert p.overall_confidence == 0.8

    def test_confidence_for_known_capability(self):
        p = self._make_profile(execs=10, successes=8)
        assert p.confidence_for("run_tests") == 0.8

    def test_confidence_for_unknown_capability(self):
        p = self._make_profile()
        assert p.confidence_for("nonexistent") == 0.0

    def test_best_capability(self):
        cap1 = CapabilityRecord("run_tests", executions=10, successes=9)
        cap2 = CapabilityRecord("plan_implementation", executions=5, successes=3)
        p = WorkerProfile(worker_id="w1", worker_name="w1", capabilities=(cap1, cap2))
        assert p.best_capability() == "run_tests"

    def test_has_capability(self):
        p = self._make_profile()
        assert p.has_capability("run_tests") is True
        assert p.has_capability("nonexistent") is False

    def test_to_text_contains_worker_name(self):
        p = self._make_profile()
        assert "suite_runner_worker" in p.to_text()

    def test_to_text_contains_confidence(self):
        p = self._make_profile(execs=10, successes=8)
        assert "80%" in p.to_text()

    def test_is_frozen(self):
        p = self._make_profile()
        with pytest.raises((AttributeError, TypeError)):
            p.worker_name = "changed"  # type: ignore


# ── WorkerIntelligenceStore ───────────────────────────────────────────────────

class TestWorkerIntelligenceStore:
    def test_record_first_execution(self, ke):
        store = WorkerIntelligenceStore(ke)
        profile = store.record_execution("suite_runner_worker", "run_tests", True)
        assert profile.total_executions == 1
        assert profile.total_successes  == 1

    def test_record_failure(self, ke):
        store = WorkerIntelligenceStore(ke)
        profile = store.record_execution("suite_runner_worker", "run_tests", False)
        assert profile.total_failures == 1
        assert profile.confidence_for("run_tests") == 0.0

    def test_multiple_executions_accumulate(self, ke):
        store = WorkerIntelligenceStore(ke)
        store.record_execution("suite_runner_worker", "run_tests", True)
        store.record_execution("suite_runner_worker", "run_tests", True)
        store.record_execution("suite_runner_worker", "run_tests", False)
        profile = store.get_profile("suite_runner_worker")
        assert profile.total_executions == 3
        assert profile.total_successes  == 2
        assert profile.total_failures   == 1
        assert abs(profile.confidence_for("run_tests") - 0.6667) < 0.001

    def test_get_profile_none_for_unknown(self, ke):
        store = WorkerIntelligenceStore(ke)
        assert store.get_profile("unknown_worker") is None

    def test_all_profiles_multiple_workers(self, ke):
        store = WorkerIntelligenceStore(ke)
        store.record_execution("worker_a", "cap_a", True)
        store.record_execution("worker_b", "cap_b", False)
        profiles = store.all_profiles()
        names = {p.worker_name for p in profiles}
        assert "worker_a" in names
        assert "worker_b" in names

    def test_profiles_for_capability(self, ke):
        store = WorkerIntelligenceStore(ke)
        store.record_execution("w1", "run_tests", True)
        store.record_execution("w2", "run_tests", True)
        store.record_execution("w3", "plan_implementation", True)
        profiles = store.profiles_for_capability("run_tests")
        names = {p.worker_name for p in profiles}
        assert "w1" in names
        assert "w2" in names
        assert "w3" not in names

    def test_has_profile(self, ke):
        store = WorkerIntelligenceStore(ke)
        assert store.has_profile("suite_runner_worker") is False
        store.record_execution("suite_runner_worker", "run_tests", True)
        assert store.has_profile("suite_runner_worker") is True

    def test_serialise_deserialise_roundtrip(self, ke):
        store = WorkerIntelligenceStore(ke)
        store.record_execution("w1", "run_tests", True)
        store.record_execution("w1", "run_tests", True)
        p = store.get_profile("w1")
        assert p.total_executions == 2
        assert p.confidence_for("run_tests") == 1.0


# ── WorkerIntelligenceEngine ──────────────────────────────────────────────────

class TestObserve:
    def test_observe_records_success(self, ke):
        eng    = WorkerIntelligenceEngine(ke)
        result = _FakeWorkerResult("suite_runner_worker", success=True)
        eng.observe(result, "run_tests")
        p = eng.profile("suite_runner_worker")
        assert p is not None
        assert p.total_successes == 1

    def test_observe_records_failure(self, ke):
        eng    = WorkerIntelligenceEngine(ke)
        result = _FakeWorkerResult("suite_runner_worker", success=False)
        eng.observe(result, "run_tests")
        p = eng.profile("suite_runner_worker")
        assert p.total_failures == 1

    def test_observe_none_result_safe(self, ke):
        eng = WorkerIntelligenceEngine(ke)
        eng.observe(None, "run_tests")   # must not raise

    def test_observe_no_worker_name_safe(self, ke):
        eng = WorkerIntelligenceEngine(ke)
        class Bad: worker_name = ""; success = True; data = {}
        eng.observe(Bad(), "run_tests")  # must not raise


class TestQueries:
    def _seed(self, ke, worker: str, cap: str, successes: int, failures: int):
        store = WorkerIntelligenceStore(ke)
        for _ in range(successes):
            store.record_execution(worker, cap, True)
        for _ in range(failures):
            store.record_execution(worker, cap, False)

    def test_best_worker_for_returns_highest_confidence(self, ke):
        self._seed(ke, "w1", "run_tests", 9, 1)   # 90%
        self._seed(ke, "w2", "run_tests", 5, 5)   # 50%
        eng = WorkerIntelligenceEngine(ke)
        best = eng.best_worker_for("run_tests")
        assert best is not None
        assert best.worker_name == "w1"

    def test_best_worker_for_none_when_no_data(self, ke):
        eng = WorkerIntelligenceEngine(ke)
        assert eng.best_worker_for("nonexistent_cap") is None

    def test_rank_workers_for_sorted_descending(self, ke):
        self._seed(ke, "w1", "run_tests", 3, 7)   # 30%
        self._seed(ke, "w2", "run_tests", 9, 1)   # 90%
        self._seed(ke, "w3", "run_tests", 6, 4)   # 60%
        eng     = WorkerIntelligenceEngine(ke)
        ranked  = eng.rank_workers_for("run_tests")
        names   = [p.worker_name for p in ranked]
        confs   = [p.confidence_for("run_tests") for p in ranked]
        assert names == ["w2", "w3", "w1"]
        assert confs == sorted(confs, reverse=True)

    def test_reviewer_for_excludes_self(self, ke):
        self._seed(ke, "coding_worker",  "run_engineering_review", 5, 0)
        self._seed(ke, "review_worker",  "run_engineering_review", 8, 1)
        eng      = WorkerIntelligenceEngine(ke)
        reviewer = eng.reviewer_for("review_worker")
        assert reviewer is not None
        assert reviewer.worker_name != "review_worker"
        assert reviewer.worker_name == "coding_worker"

    def test_reviewer_for_none_when_no_reviewers(self, ke):
        eng = WorkerIntelligenceEngine(ke)
        assert eng.reviewer_for("some_worker") is None

    def test_all_profiles_sorted_by_confidence(self, ke):
        self._seed(ke, "w1", "run_tests", 2, 8)   # 20%
        self._seed(ke, "w2", "run_tests", 9, 1)   # 90%
        eng      = WorkerIntelligenceEngine(ke)
        profiles = eng.all_profiles()
        confs    = [p.overall_confidence for p in profiles]
        assert confs == sorted(confs, reverse=True)


class TestCanHandle:
    def setup_method(self):
        self.eng = WorkerIntelligenceEngine(_MemoryStore())

    def test_worker_intelligence(self):
        assert self.eng.can_handle("Worker intelligence") is True

    def test_worker_profiles(self):
        assert self.eng.can_handle("Worker profiles") is True

    def test_who_is_best_for(self):
        assert self.eng.can_handle("Who is best for run_tests?") is True

    def test_which_worker_for(self):
        assert self.eng.can_handle("Which worker for plan_implementation?") is True

    def test_show_profile_for(self):
        assert self.eng.can_handle("Show profile for suite_runner_worker") is True

    def test_unrelated(self):
        assert self.eng.can_handle("Engineering briefing.") is False
        assert self.eng.can_handle("What should we do next?") is False

    def test_worker_stats(self):
        assert self.eng.can_handle("Worker stats") is True


class TestHandle:
    def test_handle_no_data_returns_helpful_message(self, ke):
        eng      = WorkerIntelligenceEngine(ke)
        response = eng.handle("Worker intelligence")
        assert "No worker intelligence data yet" in response or \
               "Worker Intelligence" in response

    def test_handle_who_is_best_with_data(self, ke):
        store = WorkerIntelligenceStore(ke)
        store.record_execution("suite_runner_worker", "run_tests", True)
        store.record_execution("suite_runner_worker", "run_tests", True)
        eng      = WorkerIntelligenceEngine(ke)
        response = eng.handle("Who is best for run_tests?")
        assert "suite_runner_worker" in response

    def test_handle_profile_for_known_worker(self, ke):
        store = WorkerIntelligenceStore(ke)
        store.record_execution("suite_runner_worker", "run_tests", True)
        eng      = WorkerIntelligenceEngine(ke)
        response = eng.handle("Profile for suite_runner_worker")
        assert "suite_runner_worker" in response

    def test_handle_profile_for_unknown_worker(self, ke):
        eng      = WorkerIntelligenceEngine(ke)
        response = eng.handle("Profile for unknown_worker")
        assert "No profile" in response or "unknown_worker" in response


# ── Desktop validation scenarios ──────────────────────────────────────────────

class TestDesktopScenarios:
    def test_scenario_1_observe_execution(self, ke):
        """Worker executes → intelligence recorded automatically."""
        eng    = WorkerIntelligenceEngine(ke)
        result = _FakeWorkerResult("suite_runner_worker", success=True)
        eng.observe(result, "run_tests")
        p = eng.profile("suite_runner_worker")
        assert p is not None
        assert p.confidence_for("run_tests") == 1.0

    def test_scenario_2_best_worker_for_capability(self, ke):
        """Two workers with different confidence → best one returned."""
        store = WorkerIntelligenceStore(ke)
        for _ in range(9): store.record_execution("w_good", "run_tests", True)
        store.record_execution("w_good", "run_tests", False)    # 90%
        for _ in range(5): store.record_execution("w_ok", "run_tests", True)
        for _ in range(5): store.record_execution("w_ok", "run_tests", False)  # 50%
        eng  = WorkerIntelligenceEngine(ke)
        best = eng.best_worker_for("run_tests")
        assert best.worker_name == "w_good"

    def test_scenario_3_reviewer_selection(self, ke):
        """Engineering review worker found for reviewer_for query."""
        store = WorkerIntelligenceStore(ke)
        store.record_execution("engineering_review_worker",
                               "run_engineering_review", True)
        eng      = WorkerIntelligenceEngine(ke)
        reviewer = eng.reviewer_for("coding_worker")
        assert reviewer is not None
        assert reviewer.worker_name == "engineering_review_worker"

    def test_scenario_4_worker_ranking(self, ke):
        """Three workers ranked by capability confidence."""
        store = WorkerIntelligenceStore(ke)
        store.record_execution("w1", "run_tests", True)
        store.record_execution("w1", "run_tests", False)  # 50%
        for _ in range(3): store.record_execution("w2", "run_tests", True)  # 100%
        store.record_execution("w3", "run_tests", True)
        store.record_execution("w3", "run_tests", True)
        store.record_execution("w3", "run_tests", False)  # 67%
        eng    = WorkerIntelligenceEngine(ke)
        ranked = eng.rank_workers_for("run_tests")
        assert ranked[0].worker_name == "w2"
        assert ranked[-1].worker_name == "w1"

    def test_genesis_040_readiness(self, ke):
        """External AI worker observed → appears in intelligence graph."""
        eng    = WorkerIntelligenceEngine(ke)
        result = _FakeWorkerResult("claude_ai_worker", success=True)
        eng.observe(result, "implement_feature")
        best = eng.best_worker_for("implement_feature")
        assert best is not None
        assert best.worker_name == "claude_ai_worker"
        assert best.confidence_for("implement_feature") == 1.0
