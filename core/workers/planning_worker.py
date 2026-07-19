"""
Jarvis Planning Worker (Genesis-021 Sprint-004)

Deterministic, goal-aware planning worker.

Analyses a user goal using keyword-based template selection and
produces a structured implementation plan via WorkerResult.

Constraints:
    - No AI calls
    - No repository modification
    - No memory access
    - No Git operations
    - No desktop integration
    - Fully deterministic — same goal always produces same plan

Task type: "plan_implementation"
Payload:
    goal:    str  (required) — what to plan
    context: str  (optional) — additional background
    tags:    list (optional) — classification tags

Template selection:
    select_template(goal) → PlanTemplate
    Templates are chosen by keyword matching on the goal string.
    New templates can be added to _TEMPLATES without changing the API.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plan Template model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanTemplate:
    """
    An immutable planning template.

    Attributes:
        name:         Template identifier.
        complexity:   Low / Medium / High
        steps:        Ordered implementation steps.
        dependencies: Common dependencies for this template type.
        risks:        Common risks for this template type.
    """
    name:         str
    complexity:   str
    steps:        tuple[str, ...]
    dependencies: tuple[str, ...]
    risks:        tuple[str, ...]


# ---------------------------------------------------------------------------
# Planning templates — add new templates here without changing the API
# ---------------------------------------------------------------------------

_TEMPLATES: list[tuple[re.Pattern, PlanTemplate]] = [

    # Bug fix / hotfix
    (
        re.compile(
            r"\b(fix|bug|patch|hotfix|defect|error|issue|regression)\b",
            re.IGNORECASE,
        ),
        PlanTemplate(
            name="bug_fix",
            complexity="Low",
            steps=(
                "Reproduce the issue with a failing test.",
                "Identify root cause via code inspection.",
                "Implement the minimal fix.",
                "Verify the fix resolves the failing test.",
                "Check for related issues in surrounding code.",
                "Update documentation if behaviour changed.",
            ),
            dependencies=("Existing test suite", "Reproduction steps"),
            risks=(
                "Fix may introduce regression in related code.",
                "Root cause may be deeper than the symptom.",
            ),
        ),
    ),

    # Refactor / cleanup
    (
        re.compile(
            r"\b(refactor|cleanup|clean up|restructure|reorganise|reorganize|"
            r"simplify|decouple|extract)\b",
            re.IGNORECASE,
        ),
        PlanTemplate(
            name="refactor",
            complexity="Medium",
            steps=(
                "Define acceptance criteria and scope boundaries.",
                "Ensure existing tests cover the area to be refactored.",
                "Identify code smells and coupling points.",
                "Refactor incrementally — one change at a time.",
                "Run the test suite after each step.",
                "Update documentation to reflect the new structure.",
            ),
            dependencies=("Comprehensive test coverage before starting",
                          "Clear scope definition"),
            risks=(
                "Scope creep — refactoring expanding beyond original intent.",
                "Insufficient test coverage masking regressions.",
                "Breaking changes to public interfaces.",
            ),
        ),
    ),

    # Architecture / framework / system design
    (
        re.compile(
            r"\b(architect|architecture|framework|system|platform|engine|"
            r"infrastructure|foundation|layer|pipeline)\b",
            re.IGNORECASE,
        ),
        PlanTemplate(
            name="architecture",
            complexity="High",
            steps=(
                "Define success criteria and non-functional requirements.",
                "Analyse existing architecture for constraints and integration points.",
                "Design the new architecture with separation of concerns.",
                "Identify and document breaking changes.",
                "Implement a walking skeleton — minimal end-to-end slice.",
                "Migrate existing functionality incrementally.",
                "Validate with comprehensive tests at each layer.",
                "Review and document architectural decisions.",
            ),
            dependencies=("Architecture review sign-off",
                          "Backwards compatibility assessment",
                          "Integration test suite"),
            risks=(
                "Underestimating migration complexity.",
                "Breaking existing consumers of the current architecture.",
                "Insufficient test coverage during transition.",
                "Scope far exceeding initial estimate.",
            ),
        ),
    ),

    # New feature / capability
    (
        re.compile(
            r"\b(feature|capability|implement|add|introduce|create|build|"
            r"develop|new|extend)\b",
            re.IGNORECASE,
        ),
        PlanTemplate(
            name="new_feature",
            complexity="Medium",
            steps=(
                "Define acceptance criteria for the feature.",
                "Analyse the codebase for integration points.",
                "Design the feature interface and data model.",
                "Implement the feature incrementally.",
                "Write unit and integration tests.",
                "Review for edge cases and error handling.",
                "Update documentation.",
            ),
            dependencies=("Acceptance criteria sign-off",
                          "Interface design review"),
            risks=(
                "Integration complexity with existing components.",
                "Scope creep beyond acceptance criteria.",
                "Missing edge cases in initial implementation.",
            ),
        ),
    ),

    # Test / quality
    (
        re.compile(
            r"\b(test|testing|coverage|quality|qa|spec|specification)\b",
            re.IGNORECASE,
        ),
        PlanTemplate(
            name="testing",
            complexity="Low",
            steps=(
                "Identify untested or under-tested areas.",
                "Define test categories: unit, integration, regression.",
                "Write tests for the highest-risk areas first.",
                "Ensure all new tests are deterministic and isolated.",
                "Add to CI pipeline.",
                "Document test strategy.",
            ),
            dependencies=("Clear test scope definition",),
            risks=(
                "Tests that are too tightly coupled to implementation.",
                "Non-deterministic tests causing flaky CI.",
            ),
        ),
    ),

    # Documentation
    (
        re.compile(
            r"\b(document|documentation|docs|readme|guide|manual|wiki)\b",
            re.IGNORECASE,
        ),
        PlanTemplate(
            name="documentation",
            complexity="Low",
            steps=(
                "Identify documentation gaps.",
                "Define the target audience.",
                "Draft documentation structure.",
                "Write content incrementally.",
                "Review for accuracy against the codebase.",
                "Publish and link from relevant entry points.",
            ),
            dependencies=("Subject matter expert review",),
            risks=(
                "Documentation becoming outdated as code evolves.",
                "Inconsistent terminology.",
            ),
        ),
    ),
]

# Default template when no keyword matches
_DEFAULT_TEMPLATE = PlanTemplate(
    name="general",
    complexity="Medium",
    steps=(
        "Define acceptance criteria.",
        "Analyse the existing codebase for context.",
        "Design the solution.",
        "Implement incrementally.",
        "Write tests.",
        "Review, document, and ship.",
    ),
    dependencies=("Clear problem statement",),
    risks=(
        "Underspecified requirements leading to rework.",
        "Integration issues with existing components.",
    ),
)


# ---------------------------------------------------------------------------
# PlanningWorker
# ---------------------------------------------------------------------------

class PlanningWorker(Worker):
    """
    Deterministic, goal-aware planning worker.

    Selects a planning template based on keywords in the goal string
    and produces a structured implementation plan. Fully read-only.
    """

    @property
    def name(self) -> str:
        return "planning"

    @property
    def description(self) -> str:
        return (
            "Deterministic goal-aware planning. Analyses a goal and "
            "produces a structured implementation plan with steps, "
            "complexity, dependencies, and risks."
        )

    @property
    def capabilities(self) -> list[str]:
        return ["plan_implementation"]

    def validate(self, task: WorkerTask) -> bool:
        """Requires task_type match and a non-empty 'goal' in payload."""
        if task.task_type not in self.capabilities:
            return False
        goal = task.payload.get("goal", "")
        return bool(goal and goal.strip())

    def execute(self, task: WorkerTask) -> WorkerResult:
        """
        Generate a deterministic implementation plan for the given goal.

        Args:
            task: WorkerTask with payload["goal"] (required).

        Returns:
            WorkerResult with observations and structured data dict.
        """
        self._begin(task)

        try:
            goal    = task.payload.get("goal", "").strip()
            context = task.payload.get("context", "").strip()
            tags    = task.payload.get("tags", [])

            template = self.select_template(goal)

            logger.info(
                "[PLANNING] Goal=%r → template=%r complexity=%s",
                goal[:60], template.name, template.complexity,
            )

            observations = self._build_observations(goal, template, context)
            data         = self._build_data(goal, template, context, tags)

            result = WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=True,
                observations=tuple(observations),
                recommendations=(
                    f"Review the plan and approve before implementation begins.",
                    f"Estimated complexity: {template.complexity}.",
                ),
                requires_approval=True,
                data=data,
            )
            return self._succeed(result)

        except Exception as exc:
            logger.exception("[PLANNING] Planning failed.")
            return self._fail(task.task_id, str(exc))

    # ------------------------------------------------------------------
    # Template selection — add new templates to _TEMPLATES, not here
    # ------------------------------------------------------------------

    def select_template(self, goal: str) -> PlanTemplate:
        """
        Select a planning template by matching keywords in the goal.

        Checks templates in order — first match wins. Returns the
        default template if no keywords match.

        Args:
            goal: The goal string from the task payload.

        Returns:
            A PlanTemplate instance.
        """
        for pattern, template in _TEMPLATES:
            if pattern.search(goal):
                return template
        return _DEFAULT_TEMPLATE

    # ------------------------------------------------------------------
    # Observation and data builders
    # ------------------------------------------------------------------

    def _build_observations(
        self, goal: str, template: PlanTemplate, context: str
    ) -> list[str]:
        obs = [
            f"Goal: {goal}",
            f"Planning template: {template.name.replace('_', ' ').title()}",
            f"Estimated complexity: {template.complexity}",
            f"Implementation steps ({len(template.steps)}):",
        ]
        for i, step in enumerate(template.steps, 1):
            obs.append(f"  {i}. {step}")

        if template.dependencies:
            obs.append(f"Dependencies: {', '.join(template.dependencies)}")

        if template.risks:
            obs.append("Risks:")
            for risk in template.risks:
                obs.append(f"  • {risk}")

        if context:
            obs.append(f"Context: {context}")

        return obs

    def _build_data(
        self,
        goal: str,
        template: PlanTemplate,
        context: str,
        tags: list,
    ) -> dict[str, Any]:
        return {
            "goal":         goal,
            "template":     template.name,
            "complexity":   template.complexity,
            "steps":        list(template.steps),
            "step_count":   len(template.steps),
            "dependencies": list(template.dependencies),
            "risks":        list(template.risks),
            "context":      context,
            "tags":         list(tags),
        }