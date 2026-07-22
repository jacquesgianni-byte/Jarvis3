"""
Jarvis Test Configuration (GC-006)

Isolates the test suite from the production knowledge store.

Root cause:
    JsonKnowledgeRepository() with no arguments always resolves to
    data/knowledge.json — the live production database. Every test that
    instantiates Agent() or KnowledgeEngine() without a custom storage
    argument reads from and writes to that file, contaminating:
      - desktop sessions with test memories
      - engineering worker reports with test data
      - knowledge.json with journal records from thousands of test turns

Fix:
    A session-scoped pytest fixture monkey-patches
    JsonKnowledgeRepository.__init__ so that any call with no explicit
    path argument receives a fresh NamedTemporaryFile instead of the
    production path. The patch is applied once per test session and
    reversed automatically when the session ends.

    No test files are modified.
    No production code is modified.
    Runtime behaviour is unchanged — the desktop always uses the real path
    because it never runs under pytest.

Remaining limitations:
    - Tests that explicitly pass the production path string will still
      hit the real file. None currently do, but this should be noted.
    - The temporary file is shared across the entire test session so
      tests that write memories can still affect each other. Per-test
      isolation would require a function-scoped fixture and explicit
      opt-in — that is GC-007 if needed.
"""

import tempfile
import os
import pytest

from core.knowledge_engine.json_storage import JsonKnowledgeRepository, _DEFAULT_STORAGE_PATH


@pytest.fixture(autouse=True, scope="session")
def isolate_knowledge_store(tmp_path_factory):
    """
    Redirect all KnowledgeEngine storage to a temporary file for the
    duration of the test session.

    Automatically applied to every test — no opt-in required.
    The production data/knowledge.json is never touched by tests.
    """
    # Create a temporary directory and knowledge file for this test session
    tmp_dir = tmp_path_factory.mktemp("knowledge")
    tmp_knowledge_path = str(tmp_dir / "knowledge.json")

    # Write an empty valid JSON store so the repository loads cleanly
    with open(tmp_knowledge_path, "w") as f:
        f.write("[]")

    # Save original __init__ and patch it
    original_init = JsonKnowledgeRepository.__init__

    def patched_init(self, path=None):
        # If no path given (or production path given), redirect to temp file
        if path is None or path == _DEFAULT_STORAGE_PATH:
            path = tmp_knowledge_path
        original_init(self, path)

    JsonKnowledgeRepository.__init__ = patched_init

    yield tmp_knowledge_path

    # Restore original __init__ after session
    JsonKnowledgeRepository.__init__ = original_init