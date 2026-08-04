"""
Tests — AI Collaboration Framework
Genesis-040 Sprint-001

Tests that ClaudeAIWorker integrates with the Worker OS identically
to internal workers. The key proof: capability-based routing,
Worker OS execution, intelligence observation — all unchanged.
"""

import pytest
from core.ai_workers.base import ExternalAIWorker
from core.ai_workers.claude_worker import ClaudeAIWorker


# ── Minimal Worker OS stubs ───────────────────────────────────────────────────

class _FakeWorkerTask:
    def __init__(self, task_type: str, payload: dict):
        self.task_type = task_type
        self.payload   = payload
        self.task_id   = "task-001"
        self.requester = "test"


class _FakeWorkerResult:
    def __init__(self, success: bool, worker_name: str, data: dict = None):
        self.success     = success
        self.worker_name = worker_name
        self.data        = data or {}
        self.error       = ""
        self.observations    = ()
        self.recommendations = ()
        self.requires_approval = True


# ── ExternalAIWorker contract ─────────────────────────────────────────────────

class TestExternalAIWorkerContract:
    """
    The Worker OS contract requires: name, description, capabilities,
    validate(), execute(). ExternalAIWorker must satisfy all of these.
    """

    def test_claude_worker_has_name(self):
        w = ClaudeAIWorker()
        assert isinstance(w.name, str)
        assert len(w.name) > 0

    def test_claude_worker_name_is_stable(self):
        """Name must be stable — Worker OS uses it for registration."""
        assert ClaudeAIWorker().name == "claude_ai_worker"

    def test_claude_worker_has_description(self):
        w = ClaudeAIWorker()
        assert isinstance(w.description, str)
        assert len(w.description) > 0

    def test_claude_worker_has_capabilities(self):
        w = ClaudeAIWorker()
        assert isinstance(w.capabilities, list)
        assert len(w.capabilities) > 0

    def test_claude_worker_capabilities_are_strings(self):
        for cap in ClaudeAIWorker().capabilities:
            assert isinstance(cap, str)

    def test_claude_worker_validate_accepts_matching_task(self):
        w    = ClaudeAIWorker()
        task = _FakeWorkerTask("implement_feature", {"description": "Build X"})
        assert w.validate(task) is True

    def test_claude_worker_validate_rejects_unknown_task(self):
        w    = ClaudeAIWorker()
        task = _FakeWorkerTask("run_tests", {"description": "Run tests"})
        assert w.validate(task) is False

    def test_claude_worker_is_available_initially(self):
        w = ClaudeAIWorker()
        assert w.is_available is True


# ── Capability registration ───────────────────────────────────────────────────

class TestCapabilityRegistration:
    def test_implement_feature_capability(self):
        assert "implement_feature" in ClaudeAIWorker().capabilities

    def test_review_architecture_capability(self):
        assert "review_architecture" in ClaudeAIWorker().capabilities

    def test_write_tests_capability(self):
        assert "write_tests" in ClaudeAIWorker().capabilities

    def test_explain_code_capability(self):
        assert "explain_code" in ClaudeAIWorker().capabilities

    def test_worker_os_can_find_by_capability(self):
        """
        Simulate WorkerManager.workers_for() — the Worker OS route.
        ClaudeAIWorker registers identically to internal workers.
        """
        workers = [ClaudeAIWorker()]
        result  = [w for w in workers if "implement_feature" in w.capabilities]
        assert len(result) == 1
        assert result[0].name == "claude_ai_worker"


# ── Execution ─────────────────────────────────────────────────────────────────

class TestExecution:
    def test_execute_without_ai_returns_placeholder(self):
        """Worker executes even without a live AI client."""
        w      = ClaudeAIWorker(ai_client=None)
        task   = _FakeWorkerTask(
            "implement_feature",
            {"description": "Implement the GoalEngine.", "objective": "Build GoalEngine"}
        )
        result = w.execute(task)
        assert result.success is True
        assert "response" in result.data
        assert len(result.data["response"]) > 0

    def test_execute_always_requires_approval(self):
        """requires_approval must always be True — permanent design principle."""
        w      = ClaudeAIWorker(ai_client=None)
        task   = _FakeWorkerTask("implement_feature", {"description": "Build X"})
        result = w.execute(task)
        assert result.requires_approval is True

    def test_execute_records_capability_used(self):
        w      = ClaudeAIWorker(ai_client=None)
        task   = _FakeWorkerTask("implement_feature", {"description": "Build X"})
        result = w.execute(task)
        assert result.data.get("capability_used") != ""

    def test_execute_records_worker_name(self):
        w      = ClaudeAIWorker(ai_client=None)
        task   = _FakeWorkerTask("implement_feature", {"description": "Build X"})
        result = w.execute(task)
        assert result.data.get("worker_name") == "claude_ai_worker"

    def test_execute_with_mock_ai_client(self):
        """Worker uses injected AI client when available."""
        class MockAI:
            def ask(self, prompt):
                from core.models.response import Response
                return Response(success=True, message="Mock AI response: here is the implementation.")

        w      = ClaudeAIWorker(ai_client=MockAI())
        task   = _FakeWorkerTask("implement_feature", {"description": "Build X"})
        result = w.execute(task)
        assert result.success is True
        assert "Mock AI response" in result.data["response"]

    def test_execute_sets_worker_available_after_completion(self):
        """Worker resets to available after execution."""
        w    = ClaudeAIWorker(ai_client=None)
        task = _FakeWorkerTask("implement_feature", {"description": "Build X"})
        w.execute(task)
        assert w.is_available is True


# ── Worker OS integration ─────────────────────────────────────────────────────

class TestWorkerOSIntegration:
    """
    These tests prove that ClaudeAIWorker integrates with the Worker OS
    identically to internal workers. No special-casing anywhere.
    """

    def test_worker_registered_in_fake_manager(self):
        """WorkerManager can register ClaudeAIWorker like any worker."""
        workers: dict = {}
        w = ClaudeAIWorker()
        workers[w.name] = w
        assert "claude_ai_worker" in workers

    def test_worker_found_by_capability_in_fake_manager(self):
        """WorkerManager.workers_for() finds ClaudeAIWorker by capability."""
        all_workers = [ClaudeAIWorker()]
        found = [w for w in all_workers if "implement_feature" in w.capabilities]
        assert found[0].name == "claude_ai_worker"

    def test_worker_result_compatible_with_coordinator(self):
        """WorkerResult from ClaudeAIWorker has all fields coordinator expects."""
        w      = ClaudeAIWorker(ai_client=None)
        task   = _FakeWorkerTask("implement_feature", {"description": "Build X"})
        result = w.execute(task)
        # Coordinator expects these fields
        assert hasattr(result, "success")
        assert hasattr(result, "worker_name")
        assert hasattr(result, "data")
        assert hasattr(result, "observations")
        assert hasattr(result, "recommendations")
        assert hasattr(result, "requires_approval")

    def test_worker_intelligence_can_observe_result(self):
        """WorkerIntelligenceEngine.observe() works with ClaudeAIWorker result."""
        from core.worker_intelligence.engine import WorkerIntelligenceEngine

        class FakeKE:
            def __init__(self): self._r = {}
            def store_memory(self, subject, category, attribute, value, tags=None, **kw):
                from datetime import datetime, timezone; from uuid import uuid4
                class R: pass
                r = R(); r.subject=subject; r.category=category; r.attribute=attribute
                r.value=value; r.tags=list(tags or []); r.created_at=datetime.now(timezone.utc)
                r.updated_at=datetime.now(timezone.utc); r.expires_at=None; r.id=str(uuid4())
                self._r[f'{subject}::{attribute}'] = r; return r
            def recall_memory(self, subject, attribute, **kw): return self._r.get(f'{subject}::{attribute}')
            def forget_memory(self, subject, attribute, permanent=False, **kw):
                self._r.pop(f'{subject}::{attribute}', None); return True
            def update_memory(self, subject, attribute, value, **kw):
                k = f'{subject}::{attribute}'
                if k in self._r: self._r[k].value = value
                return self._r.get(k)
            def list_memories(self, subject=None, limit=100, **kw):
                r = list(self._r.values())
                if subject: r = [x for x in r if x.subject == subject]
                return r[:limit]

        ke  = FakeKE()
        eng = WorkerIntelligenceEngine(ke)
        w   = ClaudeAIWorker(ai_client=None)
        task   = _FakeWorkerTask("implement_feature", {"description": "Build X"})
        result = w.execute(task)

        eng.observe(result, "implement_feature")

        profile = eng.profile("claude_ai_worker")
        assert profile is not None
        assert profile.confidence_for("implement_feature") == 1.0

    def test_collision_engine_can_plan_for_ai_worker(self):
        """
        WorkerCollaborationEngine.resolve_capability() finds ClaudeAIWorker.
        This is the Genesis-040 proof: external AI = just another worker.
        """
        from core.collaboration.engine import WorkerCollaborationEngine

        class FakeWorker:
            def __init__(self, name, caps):
                self.name = name; self.capabilities = caps
                self.description = name; self.is_available = True

        class FakeManager:
            def __init__(self):
                self._w = {"claude_ai_worker": ClaudeAIWorker()}
            def workers_for(self, cap):
                return [w for w in self._w.values() if cap in w.capabilities]
            def all_workers(self): return list(self._w.values())

        class FakeCoord:
            def register_workflow(self, t, n): pass
            def run(self, task):
                from core.workers.models import WorkerResult
                return WorkerResult(task_id=task.task_id, worker_name="claude_ai_worker",
                                   success=True, observations=(), recommendations=(),
                                   requires_approval=True)

        mgr  = FakeManager()
        eng  = WorkerCollaborationEngine(mgr, FakeCoord())
        cap  = eng.resolve_capability("implement_feature")

        assert cap.available is True
        assert cap.worker_name == "claude_ai_worker"


# ── Design principle verification ─────────────────────────────────────────────

class TestDesignPrinciples:
    def test_jarvis_routes_by_capability_not_name(self):
        """
        The system routes to ClaudeAIWorker via 'implement_feature',
        not via 'claude_ai_worker'. Model name is irrelevant to routing.
        """
        workers = {"claude_ai_worker": ClaudeAIWorker()}
        # Route by capability
        found = [w for w in workers.values() if "implement_feature" in w.capabilities]
        # Name only matters for registration, not routing
        assert len(found) == 1
        # If we swap to a different model, only the worker class changes
        assert found[0].capabilities == ClaudeAIWorker().capabilities

    def test_requires_approval_is_always_true(self):
        """No autonomous code changes — permanent design principle."""
        w    = ClaudeAIWorker(ai_client=None)
        task = _FakeWorkerTask("implement_feature", {"description": "X"})
        r    = w.execute(task)
        assert r.requires_approval is True

    def test_swapping_model_requires_zero_system_changes(self):
        """
        Proof: if we replace ClaudeAIWorker with HypotheticalGPTWorker,
        nothing above the ai_workers package needs to change.
        """
        class HypotheticalGPTWorker(ExternalAIWorker):
            @property
            def name(self): return "gpt_ai_worker"
            @property
            def description(self): return "GPT-based worker"
            @property
            def capabilities(self): return ["implement_feature", "review_architecture"]
            def _call_ai(self, prompt, context): return "GPT response"

        gpt = HypotheticalGPTWorker()
        # Same capabilities — same routing
        assert "implement_feature" in gpt.capabilities
        # Different name — transparent to routing layer
        assert gpt.name != "claude_ai_worker"
        # Validates and executes identically
        task = _FakeWorkerTask("implement_feature", {"description": "X"})
        assert gpt.validate(task) is True
        result = gpt.execute(task)
        assert result.requires_approval is True
