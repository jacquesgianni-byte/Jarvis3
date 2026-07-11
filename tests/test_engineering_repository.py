"""
Genesis-016 Sprint 001 - Repository Catalogue test battery.

Tests that Jarvis can answer "where is it?" about its own project.
No AST parsing, no symbol lookup, no dependency analysis — those
capabilities are deferred to later sprints that will earn them.

Runs standalone: python tests/test_engineering_repository.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.repository.catalogue import RepositoryCatalogue
from core.engineering.coordinator import EngineeringCoordinator

passed = 0
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


print("\n[1] RepositoryCatalogue - build and stats")
cat = RepositoryCatalogue(PROJECT_ROOT).build()
stats = cat.stats()
check("catalogue builds without error", stats["files"] > 0)
check("indexes 50+ files", stats["files"] > 50)
check("maps 8+ layers", stats["layers"] >= 8)
check("build time recorded", stats["build_ms"] >= 0)
print(f"    {stats['files']} files, {stats['layers']} layers in {stats['build_ms']} ms")


print("\n[2] find() - path-based lookup")
openai = cat.find("openai")
check("find('openai') returns results", len(openai) > 0)
check("openai_provider.py is found",
      any("openai_provider" in e.path for e in openai))

memory = cat.find("memory")
check("find('memory') returns results", len(memory) > 0)

reasoning = cat.find("reasoning")
check("find('reasoning') returns results", len(reasoning) > 0)

tests = cat.find("test_")
check("find('test_') finds test files", len(tests) >= 3)


print("\n[3] find_by_role() - semantic role lookup")
providers = cat.find_by_role("ai_provider")
check("find_by_role('ai_provider') finds providers", len(providers) > 0)
check("openai provider has ai_provider role",
      any("openai" in e.path for e in providers))

mem_files = cat.find_by_role("memory")
check("find_by_role('memory') finds memory modules", len(mem_files) > 0)

test_files = cat.find_by_role("test")
check("find_by_role('test') finds test files", len(test_files) >= 3)

skill_files = cat.find_by_role("skills")
check("find_by_role('skills') finds skill modules", len(skill_files) > 0)


print("\n[4] layer() - architectural layer navigation")
skills = cat.layer("skills")
check("layer('skills') returns files", len(skills) > 0)
check("skills files include core/skills/ path",
      any("skills" in e.path for e in skills))

ai_layer = cat.layer("ai")
check("layer('ai') returns files", len(ai_layer) > 0)

test_layer = cat.layer("tests")
check("layer('tests') returns test files", len(test_layer) >= 3)

knowledge = cat.layer("knowledge")
check("layer('knowledge') returns knowledge engine files", len(knowledge) > 0)

reasoning_layer = cat.layer("reasoning")
check("layer('reasoning') returns reasoning files", len(reasoning_layer) > 0)

voice = cat.layer("voice")
check("layer('voice') returns voice files", len(voice) > 0)

ui = cat.layer("ui")
check("layer('ui') returns desktop UI files", len(ui) > 0)


print("\n[5] CatalogueEntry attributes")
provider_files = cat.find("openai_provider")
if provider_files:
    e = provider_files[0]
    check("entry has path", bool(e.path))
    check("entry has layer", bool(e.layer))
    check("entry has roles", isinstance(e.roles, list))
    check("entry has size", e.size_bytes > 0)
    check("entry has name property", bool(e.name))
    check("ai_provider role on openai_provider", "ai_provider" in e.roles)
    check("ai layer on openai_provider", e.layer == "ai")
    print(f"    {e.path}: layer={e.layer}, roles={e.roles}")


print("\n[6] Read-only guarantee")
import inspect
src = inspect.getsource(RepositoryCatalogue)
forbidden = ["open(", ".write(", "os.remove", "shutil", ".unlink(", "os.mkdir"]
check("catalogue contains no write operations",
      not any(op in src for op in forbidden))


print("\n[7] summary() - human-readable output")
summary = cat.summary()
check("summary is non-empty", len(summary) > 50)
check("summary mentions file count", "Files" in summary)
check("summary lists layers", "layers" in summary.lower()
      or "Architectural" in summary)
print(f"    {summary.splitlines()[2]}")


print("\n[8] EngineeringCoordinator integration")
coord = EngineeringCoordinator(PROJECT_ROOT).initialise()

result = coord.find("openai")
check("coordinator.find() returns results", len(result) > 0)

result = coord.find_by_role("reasoning")
check("coordinator.find_by_role() returns results", len(result) > 0)

result = coord.layer("skills")
check("coordinator.layer() returns results", len(result) > 0)

status = coord.status()
check("coordinator.status() is non-empty", len(status) > 50)
check("status names Sprint 001", "Sprint 001" in status)
check("status names next sprint", "Sprint 002" in status or "Git" in status)
check("status notes deferred capabilities", "Deferred" in status or "deferred" in status)

summary = coord.summary()
check("coordinator.summary() works", len(summary) > 50)


print("\n[9] Uninitialised coordinator raises cleanly")
coord2 = EngineeringCoordinator(PROJECT_ROOT)
try:
    coord2.find("anything")
    check("uninitialised raises RuntimeError", False)
except RuntimeError:
    check("uninitialised raises RuntimeError", True)


print(f"\n{'='*60}")
print(f"GENESIS-016 SPRINT 001: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now answer:")
print(f"  find('openai')          -> Where is the OpenAI provider?")
print(f"  find_by_role('memory')  -> Which files own memory?")
print(f"  layer('skills')         -> What files are in the skills layer?")
print(f"  layer('tests')          -> Where are the tests?")
print(f"\nDeferred to later sprints:")
print(f"  Symbol lookup (which file defines MemorySkill?)")
print(f"  Dependency graphs")
print(f"  Semantic code analysis")