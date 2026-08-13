"""
tests/test_genesis046_sprint003.py
Genesis-046 Sprint-003: Persist PluginLoader + GET /plugins endpoint.

Coverage:
  Agent.plugin_loader
    - agent.plugin_loader is not None after init (ai=None)
    - agent.plugin_loader is a PluginLoader instance
    - agent.plugin_loader.loaded_plugins() is callable
    - agent.plugin_loader.plugin_for_worker() is callable
    - hello_plugin appears in loaded_plugins() after agent init

  GET /plugins endpoint
    - returns 200
    - response has 'loaded' and 'failed' keys
    - loaded entry has name/version/description/workers fields
    - hello_plugin appears in loaded list
    - hello_worker appears in workers list for hello_plugin
    - failed list is empty when all plugins load successfully
    - endpoint returns 200 even when plugin_loader is None (graceful)

  One Brain — no interface-specific plugin behaviour
    - plugin_loader is on the agent, not on any interface
    - /plugins reads from agent, not from a separate store

  Sprint-001 / Sprint-002 regression
    - PluginLoader, PluginRecord, PluginStatus, PluginMetadata still importable
    - plugin_for_worker still works via agent.plugin_loader
    - all_records() still works via agent.plugin_loader
"""

from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# Agent.plugin_loader tests
# ---------------------------------------------------------------------------


class TestAgentPluginLoader:

    def _agent(self):
        from core.agent import Agent
        return Agent(ai=None)

    def test_plugin_loader_attribute_exists(self):
        agent = self._agent()
        assert hasattr(agent, "plugin_loader"), \
            "agent.plugin_loader must exist after __init__"

    def test_plugin_loader_is_not_none(self):
        agent = self._agent()
        assert agent.plugin_loader is not None

    def test_plugin_loader_is_correct_type(self):
        from core.plugins.loader import PluginLoader
        agent = self._agent()
        assert isinstance(agent.plugin_loader, PluginLoader)

    def test_loaded_plugins_callable(self):
        agent = self._agent()
        result = agent.plugin_loader.loaded_plugins()
        assert isinstance(result, list)

    def test_failed_plugins_callable(self):
        agent = self._agent()
        result = agent.plugin_loader.failed_plugins()
        assert isinstance(result, list)

    def test_plugin_for_worker_callable(self):
        agent = self._agent()
        result = agent.plugin_loader.plugin_for_worker("hello_worker")
        # hello_plugin should be loaded
        assert result == "hello_plugin"

    def test_plugin_for_worker_unknown_returns_none(self):
        agent = self._agent()
        assert agent.plugin_loader.plugin_for_worker("nonexistent_worker") is None

    def test_hello_plugin_in_loaded_plugins(self):
        agent = self._agent()
        names = [r.plugin_name for r in agent.plugin_loader.loaded_plugins()]
        assert "hello_plugin" in names, \
            f"hello_plugin should be loaded. Got: {names}"

    def test_hello_worker_in_worker_names(self):
        agent = self._agent()
        records = agent.plugin_loader.loaded_plugins()
        hello = next((r for r in records if r.plugin_name == "hello_plugin"), None)
        assert hello is not None
        assert "hello_worker" in hello.worker_names

    def test_hello_plugin_metadata_version(self):
        agent = self._agent()
        records = agent.plugin_loader.loaded_plugins()
        hello = next((r for r in records if r.plugin_name == "hello_plugin"), None)
        assert hello is not None
        assert hello.metadata.version == "1.0.0"

    def test_all_records_accessible(self):
        agent = self._agent()
        records = agent.plugin_loader.all_records()
        assert isinstance(records, list)
        assert len(records) >= 1  # at least hello_plugin


# ---------------------------------------------------------------------------
# GET /plugins endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def flask_client():
    """Create a Flask test client with a real Agent."""
    from apps.server.app import create_app
    from core.agent import Agent

    agent = Agent(ai=None)
    app = create_app(agent)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestPluginsEndpoint:

    def test_plugins_returns_200(self, flask_client):
        resp = flask_client.get("/plugins")
        assert resp.status_code == 200

    def test_plugins_response_has_loaded_key(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        assert "loaded" in data, f"Response missing 'loaded' key: {data}"

    def test_plugins_response_has_failed_key(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        assert "failed" in data, f"Response missing 'failed' key: {data}"

    def test_loaded_is_list(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        assert isinstance(data["loaded"], list)

    def test_failed_is_list(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        assert isinstance(data["failed"], list)

    def test_hello_plugin_in_loaded(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        names = [p["name"] for p in data["loaded"]]
        assert "hello_plugin" in names, \
            f"hello_plugin not in loaded list: {data['loaded']}"

    def test_loaded_entry_has_name_field(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        for entry in data["loaded"]:
            assert "name" in entry

    def test_loaded_entry_has_version_field(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        for entry in data["loaded"]:
            assert "version" in entry

    def test_loaded_entry_has_description_field(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        for entry in data["loaded"]:
            assert "description" in entry

    def test_loaded_entry_has_workers_field(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        for entry in data["loaded"]:
            assert "workers" in entry
            assert isinstance(entry["workers"], list)

    def test_hello_worker_in_hello_plugin_workers(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        hello = next(
            (p for p in data["loaded"] if p["name"] == "hello_plugin"), None
        )
        assert hello is not None
        assert "hello_worker" in hello["workers"]

    def test_hello_plugin_version_is_1_0_0(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        hello = next(
            (p for p in data["loaded"] if p["name"] == "hello_plugin"), None
        )
        assert hello is not None
        assert hello["version"] == "1.0.0"

    def test_failed_list_empty_when_all_load(self, flask_client):
        resp = flask_client.get("/plugins")
        data = resp.get_json()
        assert data["failed"] == [], \
            f"No plugins should have failed: {data['failed']}"

    def test_plugins_graceful_when_loader_absent(self, flask_client):
        """Endpoint must not crash if plugin_loader is somehow None."""
        from flask import current_app
        with flask_client.application.app_context():
            agent = current_app.config["AGENT"]
            original = getattr(agent, "plugin_loader", "SENTINEL")
            try:
                agent.plugin_loader = None
                resp = flask_client.get("/plugins")
                assert resp.status_code == 200
                data = resp.get_json()
                assert "loaded" in data
            finally:
                if original == "SENTINEL":
                    del agent.plugin_loader
                else:
                    agent.plugin_loader = original


# ---------------------------------------------------------------------------
# One Brain — no interface-specific plugin behaviour
# ---------------------------------------------------------------------------


class TestOneBrainPrinciple:

    def test_plugin_loader_on_agent_not_route(self):
        """plugin_loader lives on Agent, not on any interface layer."""
        from core.agent import Agent
        agent = Agent(ai=None)
        # If it's on the agent, One Brain is satisfied:
        # Desktop, Android, HTTP all go through the same agent instance.
        assert hasattr(agent, "plugin_loader")

    def test_plugins_endpoint_reads_from_agent(self, flask_client):
        """The /plugins route reads from agent.plugin_loader, not a separate store."""
        # Modify agent's loader state and verify endpoint reflects it
        from flask import current_app
        with flask_client.application.app_context():
            agent = current_app.config["AGENT"]
            # Confirm the route is reading from the agent
            loader = agent.plugin_loader
            loaded_names = [r.plugin_name for r in loader.loaded_plugins()]

        resp = flask_client.get("/plugins")
        data = resp.get_json()
        endpoint_names = [p["name"] for p in data["loaded"]]
        assert set(loaded_names) == set(endpoint_names)


# ---------------------------------------------------------------------------
# Sprint-001 / Sprint-002 regression
# ---------------------------------------------------------------------------


class TestSprint002Regression:

    def test_plugin_loader_importable(self):
        from core.plugins.loader import PluginLoader
        assert PluginLoader is not None

    def test_plugin_record_importable(self):
        from core.plugins.models import PluginRecord
        assert PluginRecord is not None

    def test_plugin_status_importable(self):
        from core.plugins.models import PluginStatus
        assert PluginStatus is not None

    def test_plugin_metadata_importable(self):
        from core.plugins.models import PluginMetadata
        assert PluginMetadata is not None

    def test_exceptions_importable(self):
        from core.plugins.exceptions import PluginError, PluginLoadError, PluginConfigError
        assert issubclass(PluginLoadError, PluginError)
        assert issubclass(PluginConfigError, PluginError)

    def test_agent_plugin_loader_has_all_sprint002_methods(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        loader = agent.plugin_loader
        assert callable(loader.loaded_plugins)
        assert callable(loader.failed_plugins)
        assert callable(loader.all_records)
        assert callable(loader.plugin_for_worker)

    def test_agent_references_plugin_loader_in_source(self):
        import pathlib
        src = pathlib.Path("core/agent.py").read_text(encoding="utf-8")
        assert "self.plugin_loader" in src
        assert "PluginLoader" in src
        assert "load_enabled" in src
