"""
Tests — ExecutionPlan + ClaudeAIWorker Plan Extension
Genesis-041 Sprint-005

Covers:
  FileOperation   — immutability, to_dict/from_dict
  ExecutionPlan   — operations, to_worker_plan, from_dict
  ClaudeAIWorker  — _extract_plan, _post_process, execute with plan
  Integration     — plan flows through to WorkerResult.data
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# FileOperation tests
# ---------------------------------------------------------------------------

class TestFileOperation:

    def test_create_operation(self):
        from core.engineering.execution.execution_plan import FileOperation, FileAction
        op = FileOperation(
            path="core/auth.py",
            action=FileAction.CREATE,
            content="# auth module\n",
            reason="New auth module",
        )
        assert op.path == "core/auth.py"
        assert op.action == FileAction.CREATE
        assert op.content == "# auth module\n"
        assert op.reason == "New auth module"

    def test_modify_operation(self):
        from core.engineering.execution.execution_plan import FileOperation, FileAction
        op = FileOperation(path="core/agent.py", action=FileAction.MODIFY, content="# modified\n")
        assert op.action == FileAction.MODIFY

    def test_delete_operation(self):
        from core.engineering.execution.execution_plan import FileOperation, FileAction
        op = FileOperation(path="core/old.py", action=FileAction.DELETE, content="")
        assert op.action == FileAction.DELETE
        assert op.content == ""

    def test_is_immutable(self):
        from core.engineering.execution.execution_plan import FileOperation, FileAction
        op = FileOperation("x.py", FileAction.CREATE, "")
        with pytest.raises((AttributeError, TypeError)):
            op.path = "hacked"  # type: ignore[misc]

    def test_to_dict(self):
        from core.engineering.execution.execution_plan import FileOperation, FileAction
        op = FileOperation("core/x.py", FileAction.CREATE, "# content", "reason")
        d = op.to_dict()
        assert d["path"] == "core/x.py"
        assert d["action"] == "create"
        assert d["content"] == "# content"
        assert d["reason"] == "reason"

    def test_from_dict_roundtrip(self):
        from core.engineering.execution.execution_plan import FileOperation, FileAction
        op = FileOperation("core/x.py", FileAction.MODIFY, "# mod", "why")
        restored = FileOperation.from_dict(op.to_dict())
        assert restored.path == op.path
        assert restored.action == op.action
        assert restored.content == op.content


# ---------------------------------------------------------------------------
# ExecutionPlan tests
# ---------------------------------------------------------------------------

class TestExecutionPlan:

    def _make_plan(self):
        from core.engineering.execution.execution_plan import (
            ExecutionPlan, FileOperation, FileAction,
        )
        return ExecutionPlan.create(
            capability="implement_feature",
            description="Add JWT auth",
            operations=[
                FileOperation("core/auth.py", FileAction.CREATE, "# auth\n", "new file"),
                FileOperation("core/agent.py", FileAction.MODIFY, "# agent\n", "update"),
                FileOperation("core/old.py", FileAction.DELETE, "", "remove old"),
            ],
        )

    def test_create(self):
        plan = self._make_plan()
        assert plan.capability == "implement_feature"
        assert plan.description == "Add JWT auth"
        assert len(plan.operations) == 3
        assert not plan.is_empty

    def test_empty(self):
        from core.engineering.execution.execution_plan import ExecutionPlan
        plan = ExecutionPlan.empty("implement_feature", "desc")
        assert plan.is_empty
        assert len(plan.operations) == 0

    def test_is_immutable(self):
        plan = self._make_plan()
        with pytest.raises((AttributeError, TypeError)):
            plan.capability = "hacked"  # type: ignore[misc]

    def test_files_to_create(self):
        plan = self._make_plan()
        creates = plan.files_to_create
        assert len(creates) == 1
        assert creates[0]["path"] == "core/auth.py"
        assert creates[0]["content"] == "# auth\n"

    def test_files_to_modify(self):
        plan = self._make_plan()
        modifies = plan.files_to_modify
        assert len(modifies) == 1
        assert modifies[0]["path"] == "core/agent.py"

    def test_files_to_delete(self):
        plan = self._make_plan()
        deletes = plan.files_to_delete
        assert len(deletes) == 1
        assert deletes[0] == "core/old.py"

    def test_to_worker_plan(self):
        plan = self._make_plan()
        wp = plan.to_worker_plan()
        assert "files_to_create" in wp
        assert "files_to_modify" in wp
        assert "files_to_delete" in wp
        assert len(wp["files_to_create"]) == 1
        assert len(wp["files_to_modify"]) == 1
        assert len(wp["files_to_delete"]) == 1

    def test_to_dict_from_dict_roundtrip(self):
        from core.engineering.execution.execution_plan import ExecutionPlan
        plan = self._make_plan()
        restored = ExecutionPlan.from_dict(plan.to_dict())
        assert restored.capability == plan.capability
        assert restored.description == plan.description
        assert len(restored.operations) == len(plan.operations)
        assert restored.operations[0].path == plan.operations[0].path
        assert restored.operations[0].action == plan.operations[0].action

    def test_summary(self):
        plan = self._make_plan()
        s = plan.summary()
        assert "create" in s
        assert "modify" in s
        assert "delete" in s

    def test_plan_id_unique(self):
        from core.engineering.execution.execution_plan import ExecutionPlan
        p1 = ExecutionPlan.empty()
        p2 = ExecutionPlan.empty()
        assert p1.plan_id != p2.plan_id


# ---------------------------------------------------------------------------
# ClaudeAIWorker — plan extraction
# ---------------------------------------------------------------------------

class TestClaudeAIWorkerPlanExtraction:

    def _worker(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        return ClaudeAIWorker(ai_client=None)

    def test_extract_plan_from_json_block(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker()
        response = """
Here is my implementation plan for OAuth login.

```json
{
  "operations": [
    {
      "action": "create",
      "path": "core/auth/oauth.py",
      "content": "# OAuth module\\n",
      "reason": "New OAuth implementation"
    },
    {
      "action": "modify",
      "path": "core/agent.py",
      "content": "# updated agent\\n",
      "reason": "Wire OAuth into agent"
    }
  ]
}
```
"""
        plan = w._extract_plan(response, "implement_feature", {"description": "Add OAuth"})
        assert not plan.is_empty
        assert len(plan.operations) == 2
        assert plan.operations[0].path == "core/auth/oauth.py"
        assert plan.operations[1].path == "core/agent.py"
        from core.engineering.execution.execution_plan import FileAction
        assert plan.operations[0].action == FileAction.CREATE
        assert plan.operations[1].action == FileAction.MODIFY

    def test_extract_plan_no_json_returns_empty(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker()
        plan = w._extract_plan("No JSON here", "implement_feature", {})
        assert plan.is_empty

    def test_extract_plan_empty_operations(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker()
        response = '```json\n{"operations": []}\n```'
        plan = w._extract_plan(response, "implement_feature", {})
        assert plan.is_empty

    def test_extract_plan_malformed_json(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker()
        response = '```json\n{not valid json}\n```'
        plan = w._extract_plan(response, "implement_feature", {})
        assert plan.is_empty  # graceful fallback

    def test_extract_plan_skips_malformed_ops(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker()
        response = '''```json
{
  "operations": [
    {"action": "create", "path": "good.py", "content": "# ok"},
    {"action": "invalid_action", "path": "bad.py", "content": ""}
  ]
}
```'''
        plan = w._extract_plan(response, "implement_feature", {})
        # Valid op included, invalid skipped
        assert len(plan.operations) == 1
        assert plan.operations[0].path == "good.py"

    def test_non_plan_capability_returns_empty_plan(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker()
        result = w._post_process("Some review text", {"capability_used": "review_architecture"})
        plan_dict = result.get("execution_plan", {})
        from core.engineering.execution.execution_plan import ExecutionPlan
        plan = ExecutionPlan.from_dict(plan_dict)
        assert plan.is_empty

    def test_plan_capability_extracts_plan(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker()
        response = '''Plan text here.
```json
{"operations": [{"action": "create", "path": "x.py", "content": "# x"}]}
```'''
        result = w._post_process(response, {"capability_used": "implement_feature", "description": "Add X"})
        plan_dict = result.get("execution_plan", {})
        from core.engineering.execution.execution_plan import ExecutionPlan
        plan = ExecutionPlan.from_dict(plan_dict)
        assert not plan.is_empty
        assert plan.operations[0].path == "x.py"


# ---------------------------------------------------------------------------
# ClaudeAIWorker — execute with plan in result
# ---------------------------------------------------------------------------

class TestClaudeAIWorkerExecuteWithPlan:

    def _make_task(self, capability="implement_feature", description="Add OAuth"):
        from core.workers.models import WorkerTask
        return WorkerTask(
            task_type=f"ai_collab_{capability}",
            payload={"description": description, "capability_used": capability},
            requester="test",
        )

    def test_execute_without_ai_includes_plan_key(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker(ai_client=None)
        result = w.execute(self._make_task())
        # Even without AI, result.data should have execution_plan key
        assert "execution_plan" in result.data

    def test_execute_with_ai_response_containing_plan(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        ai_response = MagicMock()
        ai_response.success = True
        ai_response.message = '''Here is the plan.
```json
{"operations": [{"action": "create", "path": "core/new.py", "content": "# new"}]}
```'''
        mock_ai = MagicMock()
        mock_ai.ask.return_value = ai_response

        w = ClaudeAIWorker(ai_client=mock_ai)
        result = w.execute(self._make_task())

        assert result.success
        assert "execution_plan" in result.data
        from core.engineering.execution.execution_plan import ExecutionPlan
        plan = ExecutionPlan.from_dict(result.data["execution_plan"])
        assert not plan.is_empty
        assert plan.operations[0].path == "core/new.py"

    def test_execute_review_capability_has_empty_plan(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        ai_response = MagicMock()
        ai_response.success = True
        ai_response.message = "Here is the architecture review."
        mock_ai = MagicMock()
        mock_ai.ask.return_value = ai_response

        w = ClaudeAIWorker(ai_client=mock_ai)
        result = w.execute(self._make_task("review_architecture", "Review auth"))

        assert result.success
        assert "execution_plan" in result.data
        from core.engineering.execution.execution_plan import ExecutionPlan
        plan = ExecutionPlan.from_dict(result.data["execution_plan"])
        assert plan.is_empty  # review doesn't produce a plan

    def test_execute_always_requires_approval(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker(ai_client=None)
        result = w.execute(self._make_task())
        assert result.requires_approval is True

    def test_execute_response_key_still_present(self):
        from core.ai_workers.claude_worker import ClaudeAIWorker
        w = ClaudeAIWorker(ai_client=None)
        result = w.execute(self._make_task())
        assert "response" in result.data


# ---------------------------------------------------------------------------
# Plan → worker_plan bridge
# ---------------------------------------------------------------------------

class TestPlanToWorkerPlan:

    def test_to_worker_plan_format(self):
        from core.engineering.execution.execution_plan import (
            ExecutionPlan, FileOperation, FileAction,
        )
        plan = ExecutionPlan.create(
            "implement_feature", "desc",
            [
                FileOperation("core/new.py", FileAction.CREATE, "# new\n"),
                FileOperation("core/agent.py", FileAction.MODIFY, "# mod\n"),
                FileOperation("core/old.py", FileAction.DELETE, ""),
            ],
        )
        wp = plan.to_worker_plan()

        # Verify PlanValidator-compatible format
        assert wp["files_to_create"] == [{"path": "core/new.py", "content": "# new\n"}]
        assert wp["files_to_modify"] == [{"path": "core/agent.py", "content": "# mod\n"}]
        assert wp["files_to_delete"] == ["core/old.py"]

    def test_empty_plan_produces_empty_worker_plan(self):
        from core.engineering.execution.execution_plan import ExecutionPlan
        plan = ExecutionPlan.empty()
        wp = plan.to_worker_plan()
        assert wp["files_to_create"] == []
        assert wp["files_to_modify"] == []
        assert wp["files_to_delete"] == []
