"""
conftest.py â€” Genesis-016 Maintenance Patch 004

Pytest collection configuration for Jarvis OS.

STANDALONE GENESIS VALIDATION SUITES
These files contain executable module-level code and are intentionally
excluded from pytest collection. Run them directly when needed:

    python tests/test_<name>.py

Adding a new standalone suite: append its path to collect_ignore below.

GENUINE PYTEST SUITES (collected normally)
    tests/test_edge_cases.py
    tests/test_interrupt_engine.py
    tests/test_knowledge_engine.py
"""

# Prevent pytest from scanning core/ source files for test classes
collect_ignore_glob = ["core/*.py", "core/**/*.py"]

collect_ignore = [

    # Genesis-015 â€” AI Provider validation
    "tests/test_anthropic_provider.py",

    # Genesis-013 â€” Reasoning Engine validation
    "tests/test_reasoning_engine.py",
    "tests/test_reasoning_integration.py",

    # Genesis-012 â€” Normalizer validation
    "tests/test_normalizer.py",

    # Genesis-016 Sprint 001 â€” Repository Catalogue
    "tests/test_engineering_repository.py",

    # Genesis-016 Sprint 002 â€” Git Awareness
    "tests/test_engineering_git.py",

    # Genesis-016 Sprint 003 â€” Engineering Guardrails
    "tests/test_engineering_guardrails.py",

    # Genesis-016 Sprint 004 â€” Engineering Planner
    "tests/test_engineering_planner.py",

    # Genesis-016 Sprint 005 â€” Engineering Test Runner
    "tests/test_engineering_testing.py",

    # Genesis-017 Sprint 001 â€” Engineering Debugging
    "tests/test_engineering_debugging.py",

        # Genesis-019 Sprint 001 â€” Engineering Academy
    "tests/test_engineering_academy.py",

    # Future sprints: add new standalone suites here.

]