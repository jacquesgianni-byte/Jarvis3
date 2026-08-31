"""
AI Collaboration Framework -- Claude AI Worker
Genesis-040 Sprint-001 / Genesis-041 Sprint-005

Extended in Sprint-005 to produce both:
  - Human-readable engineering report (for review)
  - Machine-readable ExecutionPlan (for deterministic execution)

After human approval, the pipeline operates exclusively on ExecutionPlan.
No AI calls after approval. No natural-language parsing at execution time.
Execution is deterministic, auditable, and fully reproducible.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from core.ai_workers.base import ExternalAIWorker
from core.engineering.execution.execution_plan import (
    ExecutionPlan,
    FileAction,
    FileOperation,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a specialist engineering worker in the Jarvis engineering system. "
    "You have been assigned a specific task by the Planning Engine. "
    "Provide a precise, structured response. "
    "Do not add preamble or caveats -- respond directly to the task. "
    "Your output will be reviewed by a human before any action is taken."
)

_CAPABILITY_FRAMING = {
    "implement_feature": (
        "Produce a concise implementation plan only. "
        "List the key files to create or modify, the primary design decisions, "
        "and any risks. Maximum 200 words. Do not write code."
    ),
    "review_architecture": (
        "Produce a concise architecture review. "
        "Identify strengths, weaknesses, and up to three recommendations. "
        "Maximum 200 words."
    ),
    "write_tests": (
        "Produce a concise test plan. "
        "List the key test cases, their purpose, and expected outcomes. "
        "Maximum 200 words. Do not write code."
    ),
    "explain_code": (
        "Produce a concise explanation. "
        "Cover purpose, key components, and notable patterns. "
        "Maximum 200 words."
    ),
}

_PLAN_PROMPT = """

After your explanation, produce a JSON execution plan in this exact format:
```json
{
  "operations": [
    {
      "action": "create|modify|delete",
      "path": "relative/path/from/repo/root.py",
      "content": "full file content here (empty for delete)",
      "reason": "one line reason"
    }
  ]
}
```
IMPORTANT: For implementation requests you MUST provide real file operations with actual file content. The operations list must NOT be empty. Include the complete new or modified file content in the content field.
If you genuinely cannot determine the file operations, output:
```json
{"operations": []}
```
Output the JSON block last, after your explanation."""

_PLAN_CAPABILITIES = frozenset({"implement_feature", "write_tests"})


class ClaudeAIWorker(ExternalAIWorker):
    """
    External AI worker backed by the Jarvis AI client.

    Produces both:
      - Human-readable report (result.data["response"])
      - Machine-readable ExecutionPlan (result.data["execution_plan"])

    After human approval, execution operates exclusively on ExecutionPlan.
    No AI calls after approval.
    """

    def __init__(self, ai_client=None) -> None:
        super().__init__()
        self._ai = ai_client

    def execute(self, task) -> "WorkerResult":
        """
        Execute the task, then extract and attach ExecutionPlan to result.data.
        """
        # Stamp capability into payload
        task_type = task.task_type or ""
        _prefix = "ai_collab_"
        if task_type.startswith(_prefix):
            cap = task_type[len(_prefix):]
            if cap in self.capabilities:
                from core.workers.models import WorkerTask
                payload = dict(task.payload)
                payload["capability_used"] = cap
                task = WorkerTask(
                    task_type=cap,
                    payload=payload,
                    requester=task.requester,
                )

        # Run base execution (calls _call_ai internally)
        result = super().execute(task)

        # Extract ExecutionPlan from the response and merge into data
        capability = task.payload.get("capability_used", task.task_type)
        response = result.data.get("response", "")
        post = self._post_process(response, {"capability_used": capability,
                                             "description": task.payload.get("description", "")})
        # WorkerResult is frozen — rebuild with merged data
        from core.workers.models import WorkerResult as _WR
        merged_data = dict(result.data)
        merged_data.update(post)
        return _WR(
            task_id=result.task_id,
            worker_name=result.worker_name,
            success=result.success,
            observations=result.observations,
            recommendations=result.recommendations,
            requires_approval=result.requires_approval,
            completed_at=result.completed_at,
            error=result.error,
            data=merged_data,
        )

    @property
    def name(self) -> str:
        return "claude_ai_worker"

    @property
    def description(self) -> str:
        return (
            "External AI worker for implementation, architecture review, "
            "test writing, and code explanation. "
            "Produces human report + machine-readable ExecutionPlan. "
            "All outputs require human approval."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "implement_feature",
            "review_architecture",
            "write_tests",
            "explain_code",
        ]

    _SPRINT_TOOLS = [
        {
            "name": "read_sprint_handoff",
            "description": "Read the Sprint Handoff record. Returns approved scope, evidence, acceptance criteria, Genesis association, and all agent contributions including GPT architecture review.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string", "description": "Sprint proposal ID e.g. PROP-5C666E"}
                },
                "required": ["proposal_id"],
            },
        },
        {
            "name": "record_sprint_contribution",
            "description": "Record Claude implementation contribution to the sprint project record. Append-only.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "proposal_id":   {"type": "string"},
                    "role":          {"type": "string", "enum": ["implementation", "architecture"]},
                    "summary":       {"type": "string"},
                    "decision":      {"type": "string"},
                    "artifact":      {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["proposal_id", "role", "summary"],
            },
        },
    ]

    def _execute_sprint_tool(self, tool_name, tool_input, server_base_url):
        import requests as _r, os as _o, json as _j
        tok = _o.getenv("AGENT_TOKEN_CLAUDE", "")
        if tool_name == "read_sprint_handoff":
            pid = tool_input.get("proposal_id", "").strip()
            try:
                return _r.get(f"{server_base_url}/sprint/handoff/{pid}", headers={"X-Agent-Token": tok}, timeout=10).text
            except Exception as e:
                return f'{{"error":"{e}"}}'
        elif tool_name == "record_sprint_contribution":
            pid = tool_input.get("proposal_id", "").strip()
            try:
                payload = {"proposal_id": pid, "role": tool_input.get("role","implementation"),
                           "summary": tool_input.get("summary",""), "decision": tool_input.get("decision"),
                           "artifact": tool_input.get("artifact"), "evidence_refs": tool_input.get("evidence_refs",[])}
                return _r.post(f"{server_base_url}/sprint/contribute",
                    headers={"X-Agent-Token": tok, "Content-Type": "application/json"},
                    data=_j.dumps(payload), timeout=10).text
            except Exception as e:
                return f'{{"error":"{e}"}}'
        return f'{{"error":"Unknown tool {tool_name}"}}'

    def answer_sprint_question(self, proposal_id, question, server_base_url="http://localhost:5001"):
        import anthropic as _a, os as _o
        client = _a.Anthropic(api_key=_o.getenv("ANTHROPIC_API_KEY",""))
        system = ("You are Claude, an implementation agent in Jarvis OS. "
                  "Use read_sprint_handoff to read the project record, then answer honestly. "
                  "Use record_sprint_contribution to record your result. "
                  "You do NOT approve sprints or expand scope.")
        messages = [{"role": "user", "content": question}]
        for _ in range(5):
            resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=2000,
                system=system, tools=self._SPRINT_TOOLS, messages=messages)
            texts, tools = [], []
            for b in resp.content:
                if b.type == "text": texts.append(b.text)
                elif b.type == "tool_use": tools.append(b)
            if not tools:
                return "\n".join(texts)
            messages.append({"role": "assistant", "content": resp.content})
            results = [{"type":"tool_result","tool_use_id":t.id,
                        "content":self._execute_sprint_tool(t.name,t.input,server_base_url)} for t in tools]
            messages.append({"role": "user", "content": results})
        return "Max iterations reached."


    def produce_implementation_plan(self, proposal_id, server_base_url="http://localhost:5001"):
        """
        Genesis-067 Experiment 2 — Phase 2.

        Reads the sprint record and GPT architecture contribution autonomously,
        then produces a structured implementation plan.

        Returns a dict with:
            exact_file       — the single file to be modified
            exact_change     — precise description of the change
            rationale        — why this change satisfies the approved scope
            expected_outcome — what will be true after the change
            gpt_ref          — reference to GPT's architecture contribution
            sprint_ref       — the proposal_id this plan is bound to
            plan_text        — full human-readable plan for phone approval

        Does NOT modify any source file.
        Does NOT advance sprint state.
        Records itself as a Claude contribution in the project record.
        """
        import anthropic as _a, os as _o
        client = _a.Anthropic(api_key=_o.getenv("ANTHROPIC_API_KEY", ""))

        system = (
            "You are Claude, an implementation agent in Jarvis OS. "
            "Your ONLY job right now is to read the sprint record and produce "
            "a structured implementation plan. "
            "You must NOT modify any file. You must NOT expand the approved scope. "
            "You must NOT approve your own plan. "
            "Read the sprint handoff, identify GPT's architecture contribution, "
            "derive exactly what file to change and exactly what change to make, "
            "then record your implementation plan as a contribution. "
            "If the approved scope is insufficient to safely implement the change, "
            "say so explicitly and stop. "
            "IMPORTANT: You MUST end your response with EXACTLY this labelled block "
            "(all five lines, no markdown, no bold, no backticks around the labels): "
            "EXACT_FILE: <filename only, e.g. investigation_registry.py>\n"
            "EXACT_CHANGE: <one sentence describing the precise change>\n"
            "RATIONALE: <one sentence>\n"
            "EXPECTED_OUTCOME: <one sentence>\n"
            "GPT_REF: <contribution ID, e.g. CONTRIB-F89BD982>"
        )

        question = (
            f"Read the sprint handoff for {proposal_id}. "
            "Identify GPT's architecture contribution and the approved scope. "
            "Produce your implementation plan. "
            "Then record it as a contribution with role=implementation. "
            "Finally, end your response with the five labelled lines exactly as instructed."
        )

        messages = [{"role": "user", "content": question}]
        final_text = ""

        for _ in range(8):
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=3000,
                system=system, tools=self._SPRINT_TOOLS, messages=messages
            )
            texts, tools = [], []
            for b in resp.content:
                if b.type == "text":
                    texts.append(b.text)
                elif b.type == "tool_use":
                    tools.append(b)

            if not tools:
                final_text = "\n".join(texts)
                break

            messages.append({"role": "assistant", "content": resp.content})
            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": t.id,
                    "content": self._execute_sprint_tool(t.name, t.input, server_base_url),
                }
                for t in tools
            ]
            messages.append({"role": "user", "content": results})
            final_text = "\n".join(texts)

        # Parse structured fields from the plan text.
        #
        # Claude is instructed to end its response with a labelled block:
        #   EXACT_FILE: investigation_registry.py
        #   EXACT_CHANGE: Add one InvestigationDescriptor entry.
        #   RATIONALE: Satisfies Step 1 of approved scope.
        #   EXPECTED_OUTCOME: closest_score > 0 for recurring question.
        #   GPT_REF: CONTRIB-F89BD982
        #
        # Primary extractor targets this enforced format.
        # Fallback handles numbered-header formats from earlier runs.
        import re as _re

        def _extract_labelled(label, txt):
            """Extract from enforced LABEL: value format (case-insensitive)."""
            m = _re.search(
                rf"^{_re.escape(label)}\s*:\s*(.+?)\s*$",
                txt, _re.IGNORECASE | _re.MULTILINE,
            )
            return m.group(1).strip() if m else ""

        def _extract_header_code(label, txt):
            """Fallback: ### (N) `label` + fenced code block."""
            m = _re.search(
                rf"###\s*\(\d+\)\s*`{_re.escape(label)}`\s*\n+```[^\n]*\n([^`]+?)```",
                txt, _re.IGNORECASE,
            )
            return m.group(1).strip() if m else ""

        def _extract_header_prose(label, txt):
            """Fallback: ### (N) `label` + prose, first substantive line."""
            m = _re.search(
                rf"###\s*\(\d+\)\s*`{_re.escape(label)}`\s*\n+(.*?)(?=\n###|\Z)",
                txt, _re.IGNORECASE | _re.DOTALL,
            )
            if m:
                for line in m.group(1).strip().splitlines():
                    line = _re.sub(r"[`*`]{1,2}", "", line.strip().lstrip("-*>").strip())
                    if line and not line.startswith("```"):
                        return line.strip()
            return ""

        def _extract_field(label, txt):
            return (
                _extract_labelled(label, txt)
                or _extract_header_code(label, txt)
                or _extract_header_prose(label, txt)
            )

        exact_file       = _extract_field("EXACT_FILE", final_text)
        exact_change     = _extract_field("EXACT_CHANGE", final_text)
        rationale        = _extract_field("RATIONALE", final_text)
        expected_outcome = _extract_field("EXPECTED_OUTCOME", final_text)
        gpt_ref          = _extract_field("GPT_REF", final_text)

        # Governance rule: incomplete plan is never actionable.
        # Both critical fields must be populated — if either is empty the plan
        # cannot be presented for approval and must not advance state.
        if not exact_file or not exact_change:
            plan_status = "INCOMPLETE_PLAN"
            logger.warning(
                "[ClaudeAIWorker] Implementation plan for %s is INCOMPLETE — "
                "exact_file=%r exact_change=%r. Plan will not be actionable.",
                proposal_id, exact_file, exact_change,
            )
        else:
            plan_status = "AWAITING_CHIEF_APPROVAL"

        plan = {
            "proposal_id":      proposal_id,
            "exact_file":       exact_file,
            "exact_change":     exact_change,
            "rationale":        rationale,
            "expected_outcome": expected_outcome,
            "gpt_ref":          gpt_ref,
            "sprint_ref":       proposal_id,
            "plan_text":        final_text,
            "status":           plan_status,
        }

        logger.info(
            "[ClaudeAIWorker] Implementation plan produced for %s. "
            "File: %r. Status: AWAITING_CHIEF_APPROVAL.",
            proposal_id, plan["exact_file"],
        )
        return plan

    def _call_ai(self, prompt: str, context: dict) -> str:
        if self._ai is None:
            logger.warning("[CLAUDE_AI_WORKER] No AI client -- returning placeholder.")
            return self._placeholder_response(prompt, context)
        try:
            capability = context.get("capability_used", "implement_feature")
            framing = _CAPABILITY_FRAMING.get(capability, _CAPABILITY_FRAMING["implement_feature"])
            plan_suffix = _PLAN_PROMPT if capability in _PLAN_CAPABILITIES else ""
            file_context = context.get("file_context", {})
            file_context_block = ""
            if file_context:
                lines = ["\n\n### Current File Contents (read from repository)"]
                for path, content in file_context.items():
                    lines.append(f"\n#### {path}\n```\n{content}\n```")
                file_context_block = "\n".join(lines)
            full_prompt = (_SYSTEM_PROMPT + "\n\n" + framing + "\n\n"
                           + prompt + file_context_block + plan_suffix)
            response = self._ai.ask(full_prompt)
            if not getattr(response, "success", True):
                logger.warning("[CLAUDE_AI_WORKER] AI failure (cap=%s) -- placeholder.", capability)
                return self._placeholder_response(prompt, context)
            message = getattr(response, "message", "") or ""
            if not message.strip():
                logger.warning("[CLAUDE_AI_WORKER] Empty message (cap=%s) -- placeholder.", capability)
                return self._placeholder_response(prompt, context)
            return message
        except Exception as exc:
            logger.exception("[CLAUDE_AI_WORKER] AI call failed.")
            return "AI call failed: " + str(exc)

    def _placeholder_response(self, prompt: str, context: dict) -> str:
        capability = context.get("capability_used", "implement_feature")
        description = context.get("description", prompt[:100])
        return (
            "[ClaudeAIWorker -- " + capability + "]\n\n"
            "Task: " + description + "\n\n"
            "Status: AI response unavailable. "
            "This worker is registered and operational. "
            "The engineering review gate will still execute.\n\n"
            "Requires human approval before any action is taken."
        )

    def _post_process(self, raw_response: str, context: dict) -> dict:
        capability = context.get("capability_used", "implement_feature")
        if capability not in _PLAN_CAPABILITIES:
            return {"execution_plan": ExecutionPlan.empty(capability).to_dict()}
        plan = self._extract_plan(raw_response, capability, context)
        return {"execution_plan": plan.to_dict()}

    def _extract_plan(self, response: str, capability: str, context: dict) -> ExecutionPlan:
        description = context.get("description", "")

        # -- Layer 1: fenced ```json ... ``` block (preferred) --
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
        raw_json = fenced.group(1) if fenced else None

        # -- Layer 2: bare JSON object containing "operations" --
        if raw_json is None:
            # Find every {...} blob that contains the word "operations" and
            # pick the last one (AI often writes prose before the plan).
            bare_candidates = re.findall(
                r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*)(?=\s*(?:$|\n\n|\Z))",
                response,
                re.DOTALL,
            )
            # Simpler fallback: grab the substring from the last '{' that
            # contains '"operations"' to the matching '}'.
            idx = response.rfind('"operations"')
            if idx != -1:
                start = response.rfind("{", 0, idx)
                if start != -1:
                    # Walk forward to find the balanced closing brace
                    depth, end = 0, start
                    for i, ch in enumerate(response[start:], start):
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                end = i
                                break
                    raw_json = response[start:end + 1]

        if raw_json is None:
            logger.info("[CLAUDE_AI_WORKER] No JSON plan block found for cap=%s", capability)
            return ExecutionPlan.empty(capability, description)

        # -- Layer 3: parse and validate --
        try:
            data = json.loads(raw_json)
            ops_raw = data.get("operations", [])
            if not ops_raw:
                logger.info(
                    "[CLAUDE_AI_WORKER] JSON plan has no operations for cap=%s. Raw response:\n%s",
                    capability, response,
                )
                return ExecutionPlan.empty(capability, description)
            operations = []
            for op in ops_raw:
                try:
                    operations.append(FileOperation(
                        path=op["path"],
                        action=FileAction(op.get("action", "create")),
                        content=op.get("content", ""),
                        reason=op.get("reason", ""),
                    ))
                except (KeyError, ValueError) as e:
                    logger.warning("[CLAUDE_AI_WORKER] Skipping malformed op: %s", e)
            plan = ExecutionPlan.create(capability, description, operations)
            # -- Layer 4: validate round-trip --
            try:
                ExecutionPlan.from_dict(plan.to_dict())
                logger.info(
                    "[CLAUDE_AI_WORKER] Extracted valid plan: %s ops for cap=%s",
                    len(operations), capability,
                )
            except Exception as ve:
                logger.warning("[CLAUDE_AI_WORKER] Plan validation failed: %s", ve)
                return ExecutionPlan.empty(capability, description)
            return plan
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("[CLAUDE_AI_WORKER] Plan parse failed: %s", e)
            return ExecutionPlan.empty(capability, description)
