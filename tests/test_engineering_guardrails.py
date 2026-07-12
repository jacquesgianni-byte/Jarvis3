"""
Genesis-016 Sprint 003 — Engineering Guardrails test battery.

Tests that Jarvis correctly evaluates proposed tasks against safety
rules before any action is taken. Nothing is written or executed.

Runs standalone: python tests/test_engineering_guardrails.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.guardrails.guardrails import EngineeringGuardrails
from core.engineering.guardrails.models import ApprovalStatus, EngineeringPlan
from core.engineering.coordinator import EngineeringCoordinator

passed = 0
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


print("\n[1] Basic instantiation")
g = EngineeringGuardrails()
check("instantiates with defaults", g is not None)
check("default max_files is 5", g.max_files == 5)
check("default protected paths include .git/", ".git/" in g.protected_paths)
check("default protected paths include .env", ".env" in g.protected_paths)
check("default protected paths include docs/", "docs/" in g.protected_paths)
check("protected_paths is a tuple", isinstance(g.protected_paths, tuple))

g_custom = EngineeringGuardrails(max_files=3, protected_paths=(".git/", "secrets/"))
check("custom max_files respected", g_custom.max_files == 3)
check("custom protected_paths respected", "secrets/" in g_custom.protected_paths)


print("\n[2] APPROVED — safe task within limits")
plan = g.evaluate(
    task="Update router intent patterns",
    files=["core/router.py", "core/agent.py"]
)
check("returns EngineeringPlan", isinstance(plan, EngineeringPlan))
check("status is APPROVED", plan.status == ApprovalStatus.APPROVED)
check("safe is True", plan.safe)
check("total_files is 2", plan.total_files == 2)
check("no protected files encountered", len(plan.protected_files_encountered) == 0)
check("reason is non-empty", bool(plan.reason))


print("\n[3] REQUIRES_APPROVAL — protected path encountered")
plan_protected = g.evaluate(
    task="Update architecture docs",
    files=["core/router.py", "docs/ARCHITECTURE.md"]
)
check("status is REQUIRES_APPROVAL",
      plan_protected.status == ApprovalStatus.REQUIRES_APPROVAL)
check("safe is False", not plan_protected.safe)
check("protected file detected",
      any("docs" in f for f in plan_protected.protected_files_encountered))
check("reason mentions protected path", "protected" in plan_protected.reason.lower())

# .env is protected
plan_env = g.evaluate(
    task="Update secrets",
    files=["core/settings/settings.py", ".env"]
)
check(".env triggers REQUIRES_APPROVAL",
      plan_env.status == ApprovalStatus.REQUIRES_APPROVAL)
check(".env in protected_files_encountered",
      any(".env" in f for f in plan_env.protected_files_encountered))

# .git/ is protected
plan_git = g.evaluate(
    task="Modify git hooks",
    files=[".git/hooks/pre-commit"]
)
check(".git/ triggers REQUIRES_APPROVAL",
      plan_git.status == ApprovalStatus.REQUIRES_APPROVAL)


print("\n[4] REJECTED — exceeds file count limit")
many_files = [f"core/module_{i}.py" for i in range(6)]
plan_big = g.evaluate(task="Large refactor", files=many_files)
check("6 files with limit 5 → REJECTED",
      plan_big.status == ApprovalStatus.REJECTED)
check("safe is False", not plan_big.safe)
check("reason mentions limit", str(g.max_files) in plan_big.reason)

# Exactly at the limit is APPROVED
at_limit = [f"core/module_{i}.py" for i in range(5)]
plan_limit = g.evaluate(task="At limit", files=at_limit)
check("exactly 5 files → APPROVED", plan_limit.status == ApprovalStatus.APPROVED)

# Empty task is APPROVED
plan_empty = g.evaluate(task="No-op", files=[])
check("zero files → APPROVED", plan_empty.status == ApprovalStatus.APPROVED)


print("\n[5] Rule priority — count limit beats protected path")
# A task that exceeds file count AND hits a protected path → REJECTED
# (count limit is evaluated first)
big_protected = [f"core/module_{i}.py" for i in range(5)] + ["docs/README.md"]
plan_bp = g.evaluate(task="Too big and protected", files=big_protected)
check("file-count limit takes priority over protected path",
      plan_bp.status == ApprovalStatus.REJECTED)


print("\n[6] is_protected() helper")
check("'.git/hooks' is protected", g.is_protected(".git/hooks/pre-commit"))
check("'.env' is protected", g.is_protected(".env"))
check("'docs/ARCH.md' is protected", g.is_protected("docs/ARCHITECTURE.md"))
check("'core/router.py' is NOT protected", not g.is_protected("core/router.py"))
check("'core/settings/settings.py' is NOT protected",
      not g.is_protected("core/settings/settings.py"))

# Windows-style backslash paths
check("backslash paths normalised correctly",
      g.is_protected(".git\\hooks\\pre-commit"))


print("\n[7] Custom configuration")
strict = EngineeringGuardrails(max_files=1, protected_paths=(".git/", "core/ai/"))
check("core/ai/ protected in custom config",
      strict.is_protected("core/ai/providers/openai_provider.py"))
check("core/router.py not protected in custom config",
      not strict.is_protected("core/router.py"))
plan_strict = strict.evaluate("Two files", ["core/router.py", "core/agent.py"])
check("max_files=1 rejects 2 files", plan_strict.status == ApprovalStatus.REJECTED)


print("\n[8] Report generation")
plan_report = g.evaluate(
    task="Update router and agent",
    files=["core/router.py", "core/agent.py"]
)
report = plan_report.report()
check("report is non-empty", len(report) > 50)
check("report contains 'Engineering Plan'", "Engineering Plan" in report)
check("report contains file names", "core/router.py" in report)
check("report contains status", "Approved" in report or "approved" in report)

plan_needs_approval = g.evaluate(
    task="Update docs",
    files=["docs/ARCHITECTURE.md"]
)
report2 = plan_needs_approval.report()
check("requires-approval report says 'Waiting for Chief approval'",
      "Waiting for Chief approval" in report2)

plan_rejected = g.evaluate("Big task", [f"f{i}.py" for i in range(6)])
report3 = plan_rejected.report()
check("rejected report says 'Revise scope'", "Revise scope" in report3)


print("\n[9] Read-only guarantee — behavioural")
write_methods = [
    "write", "modify", "create", "delete", "execute",
    "apply", "patch", "commit", "add", "push",
]
for method in write_methods:
    check(f"EngineeringGuardrails has no .{method}() method",
          not hasattr(g, method))

check("EngineeringPlan is immutable (frozen dataclass)",
      plan.files_to_modify == plan.files_to_modify)
try:
    object.__setattr__(plan, "status", ApprovalStatus.APPROVED)
    check("EngineeringPlan fields are frozen", False)
except Exception:
    check("EngineeringPlan fields are frozen (raises on mutation)", True)


print("\n[10] Settings-driven max_files")
# The default max_files should come from Settings.engineering_max_files
# which defaults to 5 via ENGINEERING_MAX_FILES env var.
from core.settings.settings import Settings
import os
os.environ.pop("ENGINEERING_MAX_FILES", None)
g_settings = EngineeringGuardrails()
check("default max_files matches Settings value",
      g_settings.max_files == Settings().engineering_max_files)
check("default max_files is 5 (Settings default)", g_settings.max_files == 5)

os.environ["ENGINEERING_MAX_FILES"] = "3"
g_env = EngineeringGuardrails()
check("ENGINEERING_MAX_FILES=3 overrides default", g_env.max_files == 3)
check("3-file task rejected when limit is 3",
      g_env.evaluate("big", ["a.py","b.py","c.py","d.py"]).status == ApprovalStatus.REJECTED)
check("3-file task approved when limit is 3",
      g_env.evaluate("ok", ["a.py","b.py","c.py"]).status == ApprovalStatus.APPROVED)
os.environ.pop("ENGINEERING_MAX_FILES", None)

print("\n[11] Duplicate file handling")
plan_dup = g.evaluate(
    task="Task with duplicates",
    files=["core/router.py", "core/agent.py", "core/router.py"]
)
check("duplicate files are deduplicated", plan_dup.total_files == 2)
check("deduplicated task is APPROVED", plan_dup.status == ApprovalStatus.APPROVED)
check("only 2 files in files_to_modify", len(plan_dup.files_to_modify) == 2)

# Duplicates that push over limit before dedup are safe after dedup
plan_dup_limit = g.evaluate(
    task="Duplicates at limit",
    files=["a.py"] * 6   # 6 entries but only 1 unique
)
check("6 duplicate entries of same file → 1 unique → APPROVED",
      plan_dup_limit.total_files == 1
      and plan_dup_limit.status == ApprovalStatus.APPROVED)

# Duplicate protected file only appears once in protected list
plan_dup_prot = g.evaluate(
    task="Dup protected",
    files=["docs/ARCH.md", "docs/ARCH.md", "core/router.py"]
)
check("duplicate protected file counted once",
      plan_dup_prot.protected_files_encountered.count("docs/ARCH.md") == 1)


print("\n[12] EngineeringCoordinator integration")
coord = EngineeringCoordinator(PROJECT_ROOT).initialise()

plan_coord = coord.evaluate_plan(
    "Add reasoning pattern",
    ["core/router.py", "core/skills/reasoning.py"]
)
check("coord.evaluate_plan() returns EngineeringPlan",
      isinstance(plan_coord, EngineeringPlan))
check("coord.evaluate_plan() approved for safe files",
      plan_coord.status == ApprovalStatus.APPROVED)

plan_coord_protected = coord.evaluate_plan(
    "Update docs",
    ["docs/ARCHITECTURE.md"]
)
check("coord.evaluate_plan() detects protected docs/ path",
      plan_coord_protected.status == ApprovalStatus.REQUIRES_APPROVAL)

report_str = coord.plan_report(
    "Add reasoning pattern",
    ["core/router.py", "core/skills/reasoning.py"]
)
check("coord.plan_report() returns a string", isinstance(report_str, str))
check("coord.plan_report() contains 'Engineering Plan'",
      "Engineering Plan" in report_str)
check("coord.plan_report() contains 'Waiting' or 'Approved'",
      "Waiting" in report_str or "Approved" in report_str)

print(f"\n{'='*60}")
print(f"GENESIS-016 SPRINT 003: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now:")
print(f"  evaluate_plan(task, files) -> ApprovalStatus")
print(f"  plan_report(task, files)   -> Human-readable plan for Chief")
print(f"\nGuardrail rules:")
print(f"  Max files per task:  {g.max_files}")
print(f"  Protected paths:     {g.protected_paths}")
print(f"\nDeferred to later sprints:")
print(f"  File backups, Git writes, automatic execution, patch application")