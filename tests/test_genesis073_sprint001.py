"""
Genesis-073 Sprint-001 -- Foundation A: SituationalMemoryStore
17 focused tests covering:
    Store   (5): create, append, overwrite/correct, persist-reload, category filter
    Pipeline(4): valid JSON extraction, category mapping, malformed graceful, no-client safe
    API     (8): POST store 201, GET query 200, PATCH correct 200, auth 401 x3, bad body 400 x2
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.knowledge.situational_memory import (
    VALID_CATEGORIES,
    MemoryEntry,
    MemoryExtractionPipeline,
    SituationalMemoryStore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path: Path) -> SituationalMemoryStore:
    return SituationalMemoryStore(tmp_path)


def _make_entry(category="decision", content="We will use Python.") -> MemoryEntry:
    return MemoryEntry.create(category=category, content=content)


def _flask_app(mem_store):
    """Minimal Flask app wired with a real SituationalMemoryStore."""
    os.environ.setdefault("ORCHESTRATOR_TOKEN", "test-token")
    from apps.server.app import create_app
    app = create_app(agent=MagicMock())
    app.config["situational_memory_store"] = mem_store
    app.config["TESTING"] = True
    return app


TOKEN_HEADER = {"X-Orchestrator-Token": "test-token"}


# ===========================================================================
# STORE TESTS (5)
# ===========================================================================

class TestMemoryEntryCreate:
    """ST-01: MemoryEntry.create() produces valid entry with correct fields."""

    def test_create_valid(self):
        entry = MemoryEntry.create(category="decision", content="Use Flask.")
        assert entry.category == "decision"
        assert entry.content == "Use Flask."
        assert entry.active is True
        assert len(entry.id) == 36          # UUID4
        assert "T" in entry.timestamp       # ISO-8601

    def test_create_invalid_category_raises(self):
        with pytest.raises(ValueError, match="Unknown category"):
            MemoryEntry.create(category="nonsense", content="x")

    def test_all_five_categories_accepted(self):
        for cat in VALID_CATEGORIES:
            e = MemoryEntry.create(category=cat, content="test")
            assert e.category == cat


class TestSituationalMemoryStoreAppend:
    """ST-02: store() appends entries; get_all() returns them."""

    def test_append_and_retrieve(self, tmp_path):
        s = _store(tmp_path)
        e1 = _make_entry("decision", "Use Python.")
        e2 = _make_entry("question", "Which framework?")
        s.store(e1)
        s.store(e2)
        all_entries = s.get_all()
        assert len(all_entries) == 2
        ids = {e.id for e in all_entries}
        assert e1.id in ids and e2.id in ids


class TestSituationalMemoryStoreCorrect:
    """ST-03: correct() overwrites content; active flag preserved."""

    def test_correct_content(self, tmp_path):
        s = _store(tmp_path)
        e = _make_entry("decision", "Old content.")
        s.store(e)
        updated = s.correct(e.id, category=None, content="New content.")
        assert updated is not None
        assert updated.content == "New content."
        assert updated.active is True           # flag preserved
        assert updated.category == "decision"   # unchanged

    def test_correct_category(self, tmp_path):
        s = _store(tmp_path)
        e = _make_entry("question", "Not sure yet.")
        s.store(e)
        updated = s.correct(e.id, category="unresolved", content=None)
        assert updated.category == "unresolved"

    def test_correct_nonexistent_returns_none(self, tmp_path):
        s = _store(tmp_path)
        result = s.correct("no-such-id", category=None, content="x")
        assert result is None

    def test_correct_invalid_category_raises(self, tmp_path):
        s = _store(tmp_path)
        e = _make_entry()
        s.store(e)
        with pytest.raises(ValueError):
            s.correct(e.id, category="bogus", content=None)


class TestSituationalMemoryStorePersistReload:
    """ST-04: entries survive a store reload (disk persistence)."""

    def test_persist_and_reload(self, tmp_path):
        s1 = _store(tmp_path)
        e = _make_entry("intention", "Ship by Friday.")
        s1.store(e)
        # New store instance -- re-reads from disk
        s2 = _store(tmp_path)
        reloaded = s2.get_all()
        assert len(reloaded) == 1
        assert reloaded[0].id == e.id
        assert reloaded[0].content == "Ship by Friday."


class TestSituationalMemoryStoreCategoryFilter:
    """ST-05: get_all(category=...) returns only matching entries."""

    def test_category_filter(self, tmp_path):
        s = _store(tmp_path)
        s.store(_make_entry("decision", "A"))
        s.store(_make_entry("question", "B"))
        s.store(_make_entry("decision", "C"))
        decisions = s.get_all(category="decision")
        assert len(decisions) == 2
        questions = s.get_all(category="question")
        assert len(questions) == 1

    def test_active_only_filter(self, tmp_path):
        s = _store(tmp_path)
        e = _make_entry("constraint", "No GPU.")
        s.store(e)
        s.deactivate(e.id)
        active = s.get_all(active_only=True)
        assert len(active) == 0
        all_inc = s.get_all(active_only=False)
        assert len(all_inc) == 1


# ===========================================================================
# PIPELINE TESTS (4)
# ===========================================================================

class TestMemoryExtractionPipelineValidJSON:
    """PL-01: _parse() accepts valid JSON array and returns MemoryEntry list."""

    def test_parse_valid_json(self):
        pipeline = MemoryExtractionPipeline(ai_client=None)
        raw = json.dumps([
            {"category": "decision", "content": "Use SQLite."},
            {"category": "constraint", "content": "No cloud storage."},
        ])
        entries = pipeline._parse(raw)
        assert len(entries) == 2
        assert entries[0].category == "decision"
        assert entries[1].category == "constraint"


class TestMemoryExtractionPipelineCategoryMapping:
    """PL-02: All five categories are mapped correctly by _parse()."""

    def test_all_categories_mapped(self):
        pipeline = MemoryExtractionPipeline(ai_client=None)
        items = [{"category": c, "content": f"Content for {c}."} for c in VALID_CATEGORIES]
        entries = pipeline._parse(json.dumps(items))
        assert len(entries) == len(VALID_CATEGORIES)
        returned_cats = {e.category for e in entries}
        assert returned_cats == VALID_CATEGORIES


class TestMemoryExtractionPipelineMalformed:
    """PL-03: Malformed/bad JSON is handled gracefully -- returns []."""

    def test_malformed_json_returns_empty(self):
        pipeline = MemoryExtractionPipeline(ai_client=None)
        assert pipeline._parse("this is not json") == []

    def test_missing_fields_skipped(self):
        pipeline = MemoryExtractionPipeline(ai_client=None)
        raw = json.dumps([{"category": "decision"}])   # no content
        entries = pipeline._parse(raw)
        assert entries == []

    def test_invalid_category_skipped(self):
        pipeline = MemoryExtractionPipeline(ai_client=None)
        raw = json.dumps([{"category": "banana", "content": "irrelevant"}])
        entries = pipeline._parse(raw)
        assert entries == []

    def test_fenced_json_stripped(self):
        pipeline = MemoryExtractionPipeline(ai_client=None)
        fence_open = '```json'
        fence_close = '```'
        inner = json.dumps([{"category": "intention", "content": "Do X."}])
        raw = fence_open + chr(10) + inner + chr(10) + fence_close
        entries = pipeline._parse(raw)
        assert len(entries) == 1


class TestMemoryExtractionPipelineNoClient:
    """PL-04: No AI client -- extract() returns [] safely, never raises."""

    def test_no_client_returns_empty(self):
        pipeline = MemoryExtractionPipeline(ai_client=None)
        result = pipeline.extract("We decided to use Python for the backend.")
        assert result == []

    def test_empty_text_returns_empty(self):
        pipeline = MemoryExtractionPipeline(ai_client=MagicMock())
        assert pipeline.extract("") == []
        assert pipeline.extract("   ") == []


# ===========================================================================
# API ENDPOINT TESTS (8)
# ===========================================================================

@pytest.fixture()
def client(tmp_path):
    os.environ["ORCHESTRATOR_TOKEN"] = "test-token"
    app = _flask_app(_store(tmp_path))
    with app.test_client() as c:
        yield c


class TestMemoryStoreEndpoint:
    """API-01: POST /memory/situational returns 201 with correct shape."""

    def test_store_returns_201(self, client):
        r = client.post(
            "/memory/situational",
            json={"category": "decision", "content": "Deploy on Fridays only."},
            headers=TOKEN_HEADER,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["ok"] is True
        assert data["category"] == "decision"
        assert "id" in data
        assert "timestamp" in data

    def test_store_missing_category_400(self, client):
        r = client.post(
            "/memory/situational",
            json={"content": "Something important."},
            headers=TOKEN_HEADER,
        )
        assert r.status_code == 400

    def test_store_invalid_category_400(self, client):
        r = client.post(
            "/memory/situational",
            json={"category": "banana", "content": "test"},
            headers=TOKEN_HEADER,
        )
        assert r.status_code == 400

    def test_store_no_auth_401(self, client):
        r = client.post(
            "/memory/situational",
            json={"category": "decision", "content": "x"},
        )
        assert r.status_code == 401


class TestMemoryQueryEndpoint:
    """API-02: GET /memory/situational returns 200 with entries list."""

    def test_query_returns_200(self, client):
        client.post(
            "/memory/situational",
            json={"category": "constraint", "content": "No GPU."},
            headers=TOKEN_HEADER,
        )
        r = client.get("/memory/situational", headers=TOKEN_HEADER)
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["count"] == 1
        assert data["entries"][0]["category"] == "constraint"

    def test_query_category_filter(self, client):
        client.post("/memory/situational",
                    json={"category": "decision", "content": "A"}, headers=TOKEN_HEADER)
        client.post("/memory/situational",
                    json={"category": "question", "content": "B"}, headers=TOKEN_HEADER)
        r = client.get("/memory/situational?category=decision", headers=TOKEN_HEADER)
        data = r.get_json()
        assert data["count"] == 1
        assert data["entries"][0]["category"] == "decision"

    def test_query_no_auth_401(self, client):
        r = client.get("/memory/situational")
        assert r.status_code == 401


class TestMemoryCorrectEndpoint:
    """API-03: PATCH /memory/situational/<id> returns 200 with updated entry."""

    def test_correct_returns_200(self, client):
        r = client.post(
            "/memory/situational",
            json={"category": "question", "content": "Old?"},
            headers=TOKEN_HEADER,
        )
        entry_id = r.get_json()["id"]
        r2 = client.patch(
            f"/memory/situational/{entry_id}",
            json={"content": "New answer."},
            headers=TOKEN_HEADER,
        )
        assert r2.status_code == 200
        data = r2.get_json()
        assert data["ok"] is True
        assert data["entry"]["content"] == "New answer."
        assert data["entry"]["active"] is True   # flag preserved

    def test_correct_not_found_404(self, client):
        r = client.patch(
            "/memory/situational/no-such-id",
            json={"content": "x"},
            headers=TOKEN_HEADER,
        )
        assert r.status_code == 404

    def test_correct_no_auth_401(self, client):
        r = client.patch("/memory/situational/any-id", json={"content": "x"})
        assert r.status_code == 401

    def test_correct_nothing_to_update_400(self, client):
        r = client.post(
            "/memory/situational",
            json={"category": "intention", "content": "Ship it."},
            headers=TOKEN_HEADER,
        )
        entry_id = r.get_json()["id"]
        r2 = client.patch(
            f"/memory/situational/{entry_id}",
            json={},   # neither category nor content
            headers=TOKEN_HEADER,
        )
        assert r2.status_code == 400
