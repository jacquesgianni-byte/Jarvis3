# Engineering Subsystem

## Purpose

Provide the infrastructure that allows Jarvis to understand, modify,
test, and safely evolve its own codebase.

This package follows the Jarvis Constitution.

---

## Capability Ladder

Every capability is earned by demonstrating the previous one works.
No sprint begins until the previous one is frozen.

| Sprint | Capability | Status |
|--------|-----------|--------|
| 001 | Repository Catalogue | ✅ Active |
| 002 | Git Reader | Planned |
| 003 | Engineering Guardrails | Planned |
| 004 | Code Planner | Planned |
| 005 | Test Runner | Planned |
| 006 | Debug Loop | Planned |

---

## Sprint 001 — Repository Catalogue

### Current Scope

- File discovery across the project tree
- Layer classification (ai, skills, reasoning, voice, ui, tests, ...)
- Role tagging (memory, ai_provider, router, agent, ...)
- Path-based and role-based file lookup

### Entry Point

```python
from core.engineering.coordinator import EngineeringCoordinator

coord = EngineeringCoordinator().initialise()
coord.find("openai")            # Where is the OpenAI provider?
coord.find_by_role("memory")    # Which files own memory?
coord.layer("skills")           # What files are in the skills layer?
coord.layer("tests")            # Where are the tests?
```

### Deliberately Deferred

- AST parsing
- Symbol extraction
- Dependency graphs
- Natural language repository queries
- Any form of file modification

---

## Constitutional Principles

1. **Earned Authority** — capability precedes responsibility
2. **Developer Leverage** — every sprint reduces manual engineering work
3. **Compound Progress** — each sprint makes the next one easier
4. **Evidence Before Assumption** — instrument, measure, then change