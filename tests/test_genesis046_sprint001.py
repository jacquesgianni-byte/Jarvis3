"""
tests/test_genesis046_sprint001.py
Genesis-046 Sprint-001: Plugin Ecosystem

Coverage:
  - PluginLoader reads enabled.json and loads plugins
  - HelloWorker satisfies the Worker contract
  - Plugin failures are non-fatal (Jarvis starts regardless)
  - enabled.json with empty list loads zero plugins
  - Missing manifest raises PluginConfigError
  - Malformed manifest raises PluginConfigError
  - Plugin without get_workers() raises PluginLoadError
  - Plugin get_workers() returning non-list raises PluginLoadError
  - WorkerManager receives workers from plugin
  - HelloWorker.execute returns requires_approval=True
  - HelloWorker.validate rejects empty instruction
"""

from __future__ import annotations

import json
import sys
import types
import pathlib
import pytest

# ---------------------------------------------------------------------------
# Stubs — isolate from live Jarvis imports where convenient
# ---------------------------------------------------------------------------


class _StubRegistry:
    """Minimal WorkerRegistry stand-in."""

    def __init__(self):
        self._workers: dict[str, object] = {}

    def register(self, worker):
        self._workers[worker.name] = worker

    def workers(self):
        return list(self._workers.values())


class _StubManager:
    """Minimal WorkerManager stand-in that delegates to _StubRegistry."""

    def __init__(self):
        self._registry = _StubRegistry()

    def register(self, worker):
        self._registry.register(worker)

    def workers(self):
        return self._registry.workers()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(tmp_path: pathlib.Path, enabled: list[str]) -> pathlib.Path:
    p = tmp_path / "enabled.json"
    p.write_text(json.dumps({"enabled": enabled}), encoding="utf-8")
    return p


def _make_hello_module(monkeypatch) -> None:
    """Inject a fake plugins.hello_plugin module so we don't need the real fs."""
    from plugins.hello_plugin.worker import HelloWorker

    fake_pkg = types.ModuleType("plugins")
    fake_sub = types.ModuleType("plugins.hello_plugin")
    fake_sub.get_workers = lambda: [HelloWorker()]

    monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
    monkeypatch.setitem(sys.modules, "plugins.hello_plugin", fake_sub)


# ---------------------------------------------------------------------------
# PluginLoader — manifest parsing
# ---------------------------------------------------------------------------


class TestPluginLoaderManifest:

    def test_missing_manifest_raises_config_error(self, tmp_path):
        from core.plugins.loader import PluginLoader
        from core.plugins.exceptions import PluginConfigError

        loader = PluginLoader(manifest_path=tmp_path / "does_not_exist.json")
        with pytest.raises(PluginConfigError, match="not found"):
            loader.load_enabled(_StubManager())

    def test_malformed_json_raises_config_error(self, tmp_path):
        from core.plugins.loader import PluginLoader
        from core.plugins.exceptions import PluginConfigError

        bad = tmp_path / "enabled.json"
        bad.write_text("{not valid json}", encoding="utf-8")
        loader = PluginLoader(manifest_path=bad)
        with pytest.raises(PluginConfigError, match="not valid JSON"):
            loader.load_enabled(_StubManager())

    def test_missing_enabled_key_raises_config_error(self, tmp_path):
        from core.plugins.loader import PluginLoader
        from core.plugins.exceptions import PluginConfigError

        bad = tmp_path / "enabled.json"
        bad.write_text('{"plugins": []}', encoding="utf-8")
        loader = PluginLoader(manifest_path=bad)
        with pytest.raises(PluginConfigError, match="'enabled' list"):
            loader.load_enabled(_StubManager())

    def test_empty_enabled_list_loads_nothing(self, tmp_path):
        from core.plugins.loader import PluginLoader

        manifest = _make_manifest(tmp_path, [])
        loader = PluginLoader(manifest_path=manifest)
        mgr = _StubManager()
        loaded = loader.load_enabled(mgr)
        assert loaded == []
        assert mgr.workers() == []


# ---------------------------------------------------------------------------
# PluginLoader — plugin loading
# ---------------------------------------------------------------------------


class TestPluginLoaderLoad:

    def test_hello_plugin_loads_successfully(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader

        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        _make_hello_module(monkeypatch)
        loader = PluginLoader(manifest_path=manifest)
        mgr = _StubManager()
        loaded = loader.load_enabled(mgr)
        assert "hello_plugin" in loaded
        assert len(mgr.workers()) == 1
        assert mgr.workers()[0].name == "hello_worker"

    def test_missing_plugin_module_is_skipped(self, tmp_path, monkeypatch):
        """Non-existent plugin is logged and skipped — does not raise."""
        from core.plugins.loader import PluginLoader

        manifest = _make_manifest(tmp_path, ["no_such_plugin"])
        # ensure module doesn't accidentally exist
        monkeypatch.setitem(sys.modules, "plugins.no_such_plugin", None)
        loader = PluginLoader(manifest_path=manifest)
        mgr = _StubManager()
        # Must not raise
        loaded = loader.load_enabled(mgr)
        assert loaded == []
        assert mgr.workers() == []

    def test_plugin_without_get_workers_is_skipped(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader

        manifest = _make_manifest(tmp_path, ["bad_plugin"])
        fake_pkg = types.ModuleType("plugins")
        fake_bad = types.ModuleType("plugins.bad_plugin")
        # deliberately no get_workers attribute
        monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
        monkeypatch.setitem(sys.modules, "plugins.bad_plugin", fake_bad)

        loader = PluginLoader(manifest_path=manifest)
        mgr = _StubManager()
        loaded = loader.load_enabled(mgr)
        assert loaded == []

    def test_plugin_get_workers_returning_non_list_is_skipped(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader

        manifest = _make_manifest(tmp_path, ["bad_plugin2"])
        fake_pkg = types.ModuleType("plugins")
        fake_bad = types.ModuleType("plugins.bad_plugin2")
        fake_bad.get_workers = lambda: "not a list"
        monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
        monkeypatch.setitem(sys.modules, "plugins.bad_plugin2", fake_bad)

        loader = PluginLoader(manifest_path=manifest)
        mgr = _StubManager()
        loaded = loader.load_enabled(mgr)
        assert loaded == []

    def test_one_bad_plugin_does_not_prevent_good_plugin(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader

        manifest = _make_manifest(tmp_path, ["bad_first", "hello_plugin"])
        fake_pkg = types.ModuleType("plugins")
        fake_bad = types.ModuleType("plugins.bad_first")
        # no get_workers — will fail
        fake_sub = types.ModuleType("plugins.hello_plugin")
        from plugins.hello_plugin.worker import HelloWorker
        fake_sub.get_workers = lambda: [HelloWorker()]

        monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
        monkeypatch.setitem(sys.modules, "plugins.bad_first", fake_bad)
        monkeypatch.setitem(sys.modules, "plugins.hello_plugin", fake_sub)

        loader = PluginLoader(manifest_path=manifest)
        mgr = _StubManager()
        loaded = loader.load_enabled(mgr)

        assert "hello_plugin" in loaded
        assert "bad_first" not in loaded
        assert len(mgr.workers()) == 1


# ---------------------------------------------------------------------------
# HelloWorker — Worker contract
# ---------------------------------------------------------------------------


class TestHelloWorker:

    def _worker(self):
        from plugins.hello_plugin.worker import HelloWorker
        return HelloWorker()

    def _task(self, instruction: str = "ping"):
        from core.workers.models import WorkerTask
        return WorkerTask(task_type="plugin_demo", payload={"instruction": instruction})

    def test_name(self):
        assert self._worker().name == "hello_worker"

    def test_description_non_empty(self):
        assert self._worker().description.strip() != ""

    def test_capabilities_non_empty(self):
        caps = self._worker().capabilities
        assert isinstance(caps, list)
        assert len(caps) > 0

    def test_validate_accepts_non_empty_instruction(self):
        assert self._worker().validate(self._task("hello")) is True

    def test_validate_rejects_empty_instruction(self):
        assert self._worker().validate(self._task("")) is False

    def test_validate_rejects_whitespace_only(self):
        assert self._worker().validate(self._task("   ")) is False

    def test_execute_returns_success(self):
        result = self._worker().execute(self._task("ping"))
        assert result.success is True

    def test_execute_output_contains_instruction(self):
        result = self._worker().execute(self._task("test-instruction"))
        assert "test-instruction" in result.observations[0]

    def test_execute_requires_approval_is_true(self):
        """Security boundary: plugin workers must never bypass approval."""
        result = self._worker().execute(self._task("anything"))
        assert result.requires_approval is True


# ---------------------------------------------------------------------------
# Plugin exceptions
# ---------------------------------------------------------------------------


class TestPluginExceptions:

    def test_plugin_load_error_is_plugin_error(self):
        from core.plugins.exceptions import PluginLoadError, PluginError
        assert issubclass(PluginLoadError, PluginError)

    def test_plugin_config_error_is_plugin_error(self):
        from core.plugins.exceptions import PluginConfigError, PluginError
        assert issubclass(PluginConfigError, PluginError)

    def test_plugin_error_is_exception(self):
        from core.plugins.exceptions import PluginError
        assert issubclass(PluginError, Exception)


# ---------------------------------------------------------------------------
# Integration: agent.py has PluginLoader call
# ---------------------------------------------------------------------------


class TestAgentIntegration:

    def test_agent_imports_plugin_loader(self):
        """agent.py must reference PluginLoader (checked via source text)."""
        agent_path = pathlib.Path("core/agent.py")
        if not agent_path.exists():
            pytest.skip("core/agent.py not found (run from repo root)")
        src = agent_path.read_text(encoding="utf-8")
        assert "PluginLoader" in src, "agent.py must reference PluginLoader"

    def test_agent_calls_load_enabled(self):
        """agent.py must call load_enabled()."""
        agent_path = pathlib.Path("core/agent.py")
        if not agent_path.exists():
            pytest.skip("core/agent.py not found (run from repo root)")
        src = agent_path.read_text(encoding="utf-8")
        assert "load_enabled" in src, "agent.py must call load_enabled()"
