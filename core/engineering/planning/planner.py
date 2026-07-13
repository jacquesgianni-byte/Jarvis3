"""
Engineering Planner (Genesis-016 Sprint 004)

Produces an EngineeringPlan by analysing the repository catalogue
and git state. Read-only — no files are ever created, modified,
or deleted by this module.

Constitutional constraints — this module MUST NEVER:
    * Modify any file.
    * Execute any Git write command.
    * Generate or apply code patches.
    * Approve its own plans.

Planning earns authority before execution.
(Earned Authority — Jarvis Constitution Principle 1)

Pipeline position:
    Repository Catalogue → Git Awareness → EngineeringPlanner
    → EngineeringPlan → EngineeringGuardrails → Chief Approval
"""

import logging
from pathlib import Path

from core.engineering.planning.models import Complexity, EngineeringPlan
from core.engineering.repository.catalogue import RepositoryCatalogue
from core.engineering.git.reader import GitReader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword → layer heuristics
# Maps words likely to appear in a request to architectural layers
# and candidate file patterns.
# ---------------------------------------------------------------------------

_KEYWORD_LAYERS: dict[str, list[str]] = {
    "memory":       ["skills", "knowledge"],
    "knowledge":    ["knowledge"],
    "reasoning":    ["reasoning"],
    "router":       ["other"],          # core/router.py is in 'other' layer
    "intent":       ["other"],
    "skill":        ["skills"],
    "voice":        ["voice"],
    "provider":     ["ai"],
    "openai":       ["ai"],
    "anthropic":    ["ai"],
    "ai":           ["ai"],
    "settings":     ["settings"],
    "config":       ["settings"],
    "test":         ["tests"],
    "ui":           ["ui"],
    "desktop":      ["ui"],
    "window":       ["ui"],
    "agent":        ["other"],
    "telemetry":    ["other"],
    "guardrail":    ["engineering"],
    "planner":      ["engineering"],
    "engineering":  ["engineering"],
    "git":          ["engineering"],
    "catalogue":    ["engineering"],
}

_KEYWORD_RISKS: dict[str, str] = {
    "agent":        "Changes to agent.py affect the entire request pipeline.",
    "router":       "Router changes affect all intent routing — full regression required.",
    "memory":       "Memory changes may affect Knowledge Engine persistence.",
    "knowledge":    "Knowledge Engine changes may corrupt stored facts — back up data/knowledge.json.",
    "settings":     "Settings changes affect all providers — test with both OpenAI and Anthropic.",
    "provider":     "Provider changes affect AI responses — validate with real API calls.",
    "voice":        "Voice changes require manual audio testing.",
    "reasoning":    "Reasoning engine changes affect inference — run full reasoning test suite.",
}

# Abstract validation recommendations — concrete commands are
# mapped by the Testing Engine in Sprint 005.
_VALIDATION_BASE = [
    "Compile Check",
    "Regression Tests",
]

_VALIDATION_BY_LAYER: dict[str, list[str]] = {
    "reasoning":   ["Reasoning Engine Tests", "Reasoning Integration Tests"],
    "knowledge":   ["Knowledge Engine Tests", "Knowledge Data Integrity Check"],
    "ai":          ["AI Provider Tests", "Multi-Provider Validation"],
    "ui":          ["Desktop UI Smoke Test", "Visual Inspection"],
    "voice":       ["Voice Provider Tests", "Audio Output Test"],
    "engineering": ["Engineering Repository Tests", "Git Awareness Tests",
                    "Guardrails Tests"],
    "skills":      ["Skills Integration Tests"],
    "settings":    ["Settings Load Test", "Multi-Provider Validation"],
}

_COMPLEXITY_THRESHOLDS = {
    Complexity.LOW:    (0, 2),
    Complexity.MEDIUM: (3, 5),
    Complexity.HIGH:   (6, 999),
}


class EngineeringPlanner:
    """
    Analyses a request against the live repository state and produces
    an immutable EngineeringPlan.

    Read-only. Never modifies files, never writes to git.
    """

    def __init__(
        self,
        catalogue: RepositoryCatalogue,
        git_reader: GitReader,
    ):
        """
        Args:
            catalogue:   Built RepositoryCatalogue (Sprint 001).
            git_reader:  GitReader for current repo state (Sprint 002).
        """
        self.catalogue = catalogue
        self.git = git_reader

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_plan(self, request: str) -> EngineeringPlan:
        """
        Analyse a request and return an immutable EngineeringPlan.

        Args:
            request: Natural-language description of the engineering task.

        Returns:
            EngineeringPlan — immutable, ready for guardrail evaluation.
            Never raises.
        """
        request = request.strip()
        keywords = self._extract_keywords(request)

        # Identify likely layers
        layers = self._identify_layers(keywords)

        # Find candidate files from catalogue
        candidates = self._find_candidates(keywords, layers)

        # Find dependency files (related but not directly changed)
        dependencies = self._find_dependencies(layers, candidates)

        # Estimate complexity from file count
        complexity = self._estimate_complexity(len(candidates))

        # Build validation steps
        validation = self._build_validation(layers)

        # Identify risks
        risks = self._identify_risks(keywords, layers)

        # Build objective from request
        objective = self._derive_objective(request)

        # Build summary
        summary = self._build_summary(
            request, candidates, layers, complexity, risks
        )

        plan = EngineeringPlan(
            objective=objective,
            request=request,
            candidate_files=tuple(candidates),
            layers_involved=tuple(sorted(set(layers))),
            dependencies=tuple(dependencies),
            complexity=complexity,
            estimated_file_count=len(candidates),
            validation_steps=tuple(validation),
            risks=tuple(risks),
            summary=summary,
        )

        logger.info(
            "EngineeringPlanner: plan created | complexity=%s | "
            "files=%d | layers=%s",
            complexity.value,
            len(candidates),
            ", ".join(sorted(set(layers))) or "unknown",
        )
        return plan

    # ------------------------------------------------------------------
    # Internals — all read-only
    # ------------------------------------------------------------------

    def _extract_keywords(self, request: str) -> list[str]:
        """Extract meaningful words from the request."""
        stop = {
            "the", "a", "an", "to", "for", "in", "of", "and", "or",
            "is", "are", "was", "be", "with", "that", "this", "it",
            "add", "update", "change", "fix", "modify", "implement",
            "create", "build", "make", "write", "improve", "refactor",
            "new", "old", "current", "existing", "all", "any", "some",
        }
        return [
            w.lower().rstrip("s")   # basic singular form
            for w in request.replace("/", " ").split()
            if len(w) > 2 and w.lower() not in stop
        ]

    def _identify_layers(self, keywords: list[str]) -> list[str]:
        """Map keywords to architectural layers."""
        layers = []
        for kw in keywords:
            for pattern, layer_list in _KEYWORD_LAYERS.items():
                if pattern in kw or kw in pattern:
                    layers.extend(layer_list)
        return layers or ["other"]

    def _find_candidates(
        self, keywords: list[str], layers: list[str]
    ) -> list[str]:
        """Find files likely to change using catalogue queries."""
        found: dict[str, int] = {}   # path → relevance score

        # Search by keyword in path
        for kw in keywords:
            for entry in self.catalogue.find(kw):
                if entry.path.endswith(".py"):
                    found[entry.path] = found.get(entry.path, 0) + 2

        # Search by layer
        for layer in set(layers):
            for entry in self.catalogue.layer(layer):
                if entry.path.endswith(".py"):
                    found[entry.path] = found.get(entry.path, 0) + 1

        # Sort by relevance, cap at 8 to keep plans focused
        ranked = sorted(found.items(), key=lambda x: x[1], reverse=True)
        return [path for path, _ in ranked[:8]]

    def _find_dependencies(
        self, layers: list[str], candidates: list[str]
    ) -> list[str]:
        """Find related files that may need awareness but not direct change."""
        deps: set[str] = set()

        # Always include the test files for affected layers
        for layer in set(layers):
            role = layer if layer != "other" else None
            if role:
                for entry in self.catalogue.find_by_role("test"):
                    if role in entry.path.lower():
                        deps.add(entry.path)

        # Always flag the agent and router as dependencies
        # (almost everything flows through them)
        for entry in self.catalogue.find("agent.py"):
            if entry.path not in candidates:
                deps.add(entry.path)
        for entry in self.catalogue.find("router.py"):
            if entry.path not in candidates:
                deps.add(entry.path)

        # Remove anything already in candidates
        return sorted(deps - set(candidates))[:6]

    def _estimate_complexity(self, file_count: int) -> Complexity:
        for complexity, (low, high) in _COMPLEXITY_THRESHOLDS.items():
            if low <= file_count <= high:
                return complexity
        return Complexity.HIGH

    def _build_validation(self, layers: list[str]) -> list[str]:
        steps = list(_VALIDATION_BASE)
        seen = set()
        for layer in set(layers):
            for step in _VALIDATION_BY_LAYER.get(layer, []):
                if step not in seen:
                    steps.append(step)
                    seen.add(step)
        return steps

    def _identify_risks(
        self, keywords: list[str], layers: list[str]
    ) -> list[str]:
        risks: list[str] = []
        seen: set[str] = set()
        for kw in keywords:
            for pattern, risk in _KEYWORD_RISKS.items():
                if pattern in kw or kw in pattern:
                    if risk not in seen:
                        risks.append(risk)
                        seen.add(risk)
        # Git state risk
        git_status = self.git.status()
        if git_status.available and git_status.dirty:
            risks.append(
                f"Repository is dirty ({len(git_status.modified)} modified, "
                f"{len(git_status.untracked)} untracked). "
                "Consider committing before starting."
            )
        return risks

    def _derive_objective(self, request: str) -> str:
        """Produce a clean one-line objective from the request."""
        # Capitalise first letter, ensure it ends with a period
        obj = request.strip()
        if obj and not obj.endswith("."):
            obj += "."
        return obj[:120]   # cap length

    def _build_summary(
        self,
        request: str,
        candidates: list[str],
        layers: list[str],
        complexity: Complexity,
        risks: list[str],
    ) -> str:
        layer_str = (
            ", ".join(sorted(set(layers))) if layers else "unknown"
        )
        risk_note = (
            f" {len(risks)} risk(s) identified." if risks else ""
        )
        return (
            f"Task requires changes across {len(candidates)} file(s) "
            f"in the {layer_str} layer(s). "
            f"Estimated complexity: {complexity.value}.{risk_note}"
        )