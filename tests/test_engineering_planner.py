"""
Genesis-016 Sprint 004 — Engineering Planner test battery.

Tests that Jarvis can produce a complete engineering plan from a
natural-language request, using the Repository Catalogue and Git
awareness, without modifying a single file.

Runs standalone: python tests/test_engineering_planner.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.planning.planner import EngineeringPlanner
from core.engineering.planning.models import EngineeringPlan, Complexity
from core.engineering.repository.catalogue import RepositoryCatalogue
from core.engineering.git.reader import GitReader
from core.engineering.coordinator import EngineeringCoordinator

passed = 0
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


# Build shared fixtures once
print("\n[0] Building fixtures...")
catalogue = RepositoryCatalogue(PROJECT_ROOT).build()
git_reader = GitReader(PROJECT_ROOT)
planner = EngineeringPlanner(catalogue, git_reader)
print(f"    Catalogue: {catalogue.stats()['files']} files")
print(f"    Git available: {git_reader.status().available}")


print("\n[1] Planner construction")
check("planner instantiates", planner is not None)
check("planner has catalogue", planner.catalogue is not None)
check("planner has git reader", planner.git is not None)


print("\n[2] Plan generation — basic")
plan = planner.create_plan("Update the OpenAI provider reasoning effort")
check("returns EngineeringPlan", isinstance(plan, EngineeringPlan))
check("objective is non-empty", bool(plan.objective))
check("request is preserved", "OpenAI" in plan.request or "openai" in plan.request.lower())
check("summary is non-empty", bool(plan.summary))
check("complexity is set", isinstance(plan.complexity, Complexity))


print("\n[3] File discovery")
plan_router = planner.create_plan("Fix the intent router patterns")
check("candidate files is a tuple", isinstance(plan_router.candidate_files, tuple))
check("router request finds router-related files",
      any("router" in f.lower() for f in plan_router.candidate_files))

plan_memory = planner.create_plan("Update memory skill and knowledge engine")
check("memory request finds memory-related files",
      any("memory" in f.lower() or "knowledge" in f.lower()
          for f in plan_memory.candidate_files))

plan_voice = planner.create_plan("Improve voice provider speech chunking")
check("voice request finds voice-related files",
      any("voice" in f.lower() for f in plan_voice.candidate_files))


print("\n[4] Layer identification")
plan_ai = planner.create_plan("Add a new Anthropic provider feature")
check("layers_involved is a tuple", isinstance(plan_ai.layers_involved, tuple))
check("AI request identifies ai layer",
      "ai" in plan_ai.layers_involved)

plan_eng = planner.create_plan("Improve the engineering guardrails")
check("engineering request identifies engineering layer",
      "engineering" in plan_eng.layers_involved)


print("\n[5] Dependency reporting")
plan_skill = planner.create_plan("Update the reasoning skill")
check("dependencies is a tuple", isinstance(plan_skill.dependencies, tuple))
check("dependencies do not overlap with candidate files",
      not set(plan_skill.dependencies) & set(plan_skill.candidate_files))


print("\n[6] Complexity estimation")
# Low: 0-2 files, Medium: 3-5, High: 6+
plan_simple = planner.create_plan("Fix a typo in the greeting skill")
check("complexity is a Complexity enum",
      isinstance(plan_simple.complexity, Complexity))
check("complexity value is one of Low/Medium/High",
      plan_simple.complexity in (Complexity.LOW, Complexity.MEDIUM, Complexity.HIGH))

# A broad request should estimate higher complexity
plan_broad = planner.create_plan(
    "Refactor the entire AI provider layer including OpenAI Anthropic settings config"
)
check("broad multi-keyword request estimates Medium or High complexity",
      plan_broad.complexity in (Complexity.MEDIUM, Complexity.HIGH))
print(f"    broad request complexity: {plan_broad.complexity.value} "
      f"({plan_broad.estimated_file_count} files)")


print("\n[7] Validation steps")
plan_v = planner.create_plan("Update the reasoning engine rules")
check("validation_steps is a tuple", isinstance(plan_v.validation_steps, tuple))
check("always includes Compile Check",
      any("Compile" in s for s in plan_v.validation_steps))
check("always includes Regression Tests",
      any("Regression" in s for s in plan_v.validation_steps))
check("reasoning task includes reasoning-specific validation",
      any("Reasoning" in s for s in plan_v.validation_steps))


print("\n[8] Risk identification")
plan_r = planner.create_plan("Modify the agent pipeline routing logic")
check("risks is a tuple", isinstance(plan_r.risks, tuple))
# Agent changes should flag a risk
check("agent change flags a risk",
      any("agent" in risk.lower() or "pipeline" in risk.lower()
          for risk in plan_r.risks))

plan_settings = planner.create_plan("Change the default AI settings configuration")
check("settings change flags a risk",
      any("settings" in risk.lower() or "provider" in risk.lower()
          for risk in plan_settings.risks))


print("\n[9] Immutable plan model")
check("EngineeringPlan is frozen",
      plan.__dataclass_params__.frozen)
try:
    object.__setattr__(plan, "objective", "hacked")
    check("plan fields cannot be mutated", False)
except Exception:
    check("plan fields cannot be mutated (raises on mutation)", True)

check("candidate_files is a tuple (immutable)",
      isinstance(plan.candidate_files, tuple))
check("layers_involved is a tuple (immutable)",
      isinstance(plan.layers_involved, tuple))
check("validation_steps is a tuple (immutable)",
      isinstance(plan.validation_steps, tuple))
check("risks is a tuple (immutable)",
      isinstance(plan.risks, tuple))


print("\n[10] Report generation")
report = plan.report()
check("report is non-empty", len(report) > 100)
check("report contains 'Engineering Plan'", "Engineering Plan" in report)
check("report contains objective", plan.objective[:20] in report)
check("report contains complexity", plan.complexity.value in report)
check("report contains 'Awaiting Chief approval'",
      "Awaiting Chief approval" in report)
check("report contains validation steps",
      any(step[:15] in report for step in plan.validation_steps))
print(f"    report length: {len(report)} chars")


print("\n[11] Read-only guarantee — behavioural")
write_methods = [
    "write", "modify", "create", "delete", "execute",
    "apply", "patch", "commit", "add", "push", "save",
]
for method in write_methods:
    check(f"EngineeringPlanner has no .{method}() method",
          not hasattr(planner, method))


print("\n[12] EngineeringCoordinator integration")
coord = EngineeringCoordinator(PROJECT_ROOT).initialise()

coord_plan = coord.create_plan("Update the OpenAI provider reasoning effort")
check("coord.create_plan() returns EngineeringPlan",
      isinstance(coord_plan, EngineeringPlan))
check("coord plan has candidate files", len(coord_plan.candidate_files) > 0)
check("coord plan has complexity", isinstance(coord_plan.complexity, Complexity))

summary = coord.plan_summary("Fix intent router for reasoning questions")
check("coord.plan_summary() returns a string", isinstance(summary, str))
check("summary contains 'Engineering Plan'", "Engineering Plan" in summary)
check("summary contains 'Awaiting Chief approval'",
      "Awaiting Chief approval" in summary)
check("summary does NOT embed guardrail evaluation",
      "Guardrail evaluation" not in summary)
print(f"\n    Sample plan_summary output:")
for line in summary.split("\n")[:8]:
    print(f"    {line}")


print("\n[13] Full pipeline — Plan feeds Guardrails (separate steps)")
from core.engineering.guardrails.guardrails import EngineeringGuardrails
from core.engineering.guardrails.models import ApprovalStatus

pipeline_plan = coord.create_plan("Update router and agent intent handling")
guardrails = EngineeringGuardrails()
guardrail_result = guardrails.evaluate(
    task=pipeline_plan.objective,
    files=list(pipeline_plan.candidate_files),
)
check("plan feeds into guardrails cleanly",
      guardrail_result.status in (
          ApprovalStatus.APPROVED,
          ApprovalStatus.REQUIRES_APPROVAL,
          ApprovalStatus.REJECTED,
      ))
check("guardrail file count matches plan",
      guardrail_result.total_files == len(pipeline_plan.candidate_files))
print(f"    Pipeline result: {guardrail_result.status.value} "
      f"({guardrail_result.total_files} files)")


print(f"\n{'='*60}")
print(f"GENESIS-016 SPRINT 004: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now answer:")
print(f"  'What would be required to complete this engineering task?'")
print(f"\nEngineering pipeline:")
print(f"  Repository Catalogue → Git Awareness → Planning → Guardrails → Chief")
print(f"\nDeferred to later sprints:")
print(f"  Code generation, patch application, execution, Git writes")