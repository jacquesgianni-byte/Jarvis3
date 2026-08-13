"""
tests/test_genesis046_sprint002.py
Genesis-046 Sprint-002: Plugin Identity, Configuration, Load Record,
Worker→Plugin Mapping, Capability Conflict Warning.

Coverage:
  PluginMetadata
    - defaults when plugin.json absent
    - reads name/version/description from plugin.json
    - malformed plugin.json falls back to defaults (non-fatal)

  PluginRecord
    - loaded record has correct fields
    - failed record has correct fields
    - loaded/failed properties
    - __str__ representations

  PluginStatus
    - LOADED / FAILED labels

  PluginLoader — load record
    - loaded_plugins() returns only LOADED records
    - failed_plugins() returns only FAILED records
    - all_records() returns both
    - failed plugin name and error captured correctly

  PluginLoader — config
    - absent config.json → empty dict passed to get_workers
    - present config.json → dict passed to get_workers
    - malformed config.json → plugin FAILED (non-fatal)
    - config.json with non-object root → plugin FAILED (non-fatal)

  PluginLoader — worker→plugin mapping
    - plugin_for_worker returns correct plugin name
    - plugin_for_worker returns None for unknown worker

  PluginLoader — capability conflict warning
    - WARNING logged when duplicate capability detected

  HelloWorker — Sprint-002 contract
    - get_workers(config=None) accepted
    - get_workers({}) accepted
    - config dict reaches HelloWorker
    - greeting override via config works
    - get_workers() with no args still works (backwards compat)

  Sprint-001 regression
    - all Sprint-001 behaviours preserved
"""

from __future__ import annotations

import json
import logging
import sys
import types
import pathlib
import pytest

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubRegistry:
    def __init__(self):
        self._workers: dict[str, object] = {}
        self._capabilities: dict[str, list] = {}

    def register(self, worker):
        self._workers[worker.name] = worker
        for cap in getattr(worker, "capabilities", []):
            self._capabilities.setdefault(cap, []).append(worker)

    def workers(self):
        return list(self._workers.values())

    def workers_for(self, cap):
        return self._capabilities.get(cap, [])


class _StubManager:
    def __init__(self):
        self._registry = _StubRegistry()

    def register(self, worker):
        self._registry.register(worker)

    def workers(self):
        return self._registry.workers()

    def workers_for(self, cap):
        return self._registry.workers_for(cap)

    def all_workers(self):
        return self._registry.workers()


class _StubFactory:
    def __init__(self):
        self._builders = {}

    def can_create(self, name):
        return name in self._builders

    def register_builder(self, name, builder):
        self._builders[name] = builder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(tmp_path: pathlib.Path, enabled: list[str]) -> pathlib.Path:
    p = tmp_path / "enabled.json"
    p.write_text(json.dumps({"enabled": enabled}), encoding="utf-8")
    return p


def _inject_hello(monkeypatch):
    """Inject real hello_plugin module into sys.modules."""
    from plugins.hello_plugin.worker import HelloWorker

    fake_pkg = types.ModuleType("plugins")
    fake_sub = types.ModuleType("plugins.hello_plugin")

    def get_workers(config=None):
        if config is None:
            config = {}
        return [HelloWorker(config=config)]

    fake_sub.get_workers = get_workers
    monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
    monkeypatch.setitem(sys.modules, "plugins.hello_plugin", fake_sub)


# ---------------------------------------------------------------------------
# PluginStatus
# ---------------------------------------------------------------------------


class TestPluginStatus:

    def test_loaded_label(self):
        from core.plugins.models import PluginStatus
        assert PluginStatus.LOADED.label() == "Loaded"

    def test_failed_label(self):
        from core.plugins.models import PluginStatus
        assert PluginStatus.FAILED.label() == "Failed"


# ---------------------------------------------------------------------------
# PluginMetadata
# ---------------------------------------------------------------------------


class TestPluginMetadata:

    def test_defaults(self):
        from core.plugins.models import PluginMetadata
        m = PluginMetadata()
        assert m.name == "unknown"
        assert m.version == "unknown"
        assert m.description == ""

    def test_custom_values(self):
        from core.plugins.models import PluginMetadata
        m = PluginMetadata(name="foo", version="2.0.0", description="A plugin")
        assert m.name == "foo"
        assert m.version == "2.0.0"
        assert m.description == "A plugin"

    def test_immutable(self):
        from core.plugins.models import PluginMetadata
        m = PluginMetadata(name="foo")
        with pytest.raises((AttributeError, TypeError)):
            m.name = "bar"


# ---------------------------------------------------------------------------
# PluginRecord
# ---------------------------------------------------------------------------


class TestPluginRecord:

    def _loaded_record(self):
        from core.plugins.models import PluginRecord, PluginStatus, PluginMetadata
        return PluginRecord(
            plugin_name="hello_plugin",
            status=PluginStatus.LOADED,
            metadata=PluginMetadata(name="hello_plugin", version="1.0.0"),
            worker_names=("hello_worker",),
        )

    def _failed_record(self):
        from core.plugins.models import PluginRecord, PluginStatus, PluginMetadata
        return PluginRecord(
            plugin_name="bad_plugin",
            status=PluginStatus.FAILED,
            metadata=PluginMetadata(name="bad_plugin"),
            error="Import failed",
        )

    def test_loaded_property_true(self):
        assert self._loaded_record().loaded is True

    def test_loaded_property_false_when_failed(self):
        assert self._failed_record().loaded is False

    def test_failed_property_true(self):
        assert self._failed_record().failed is True

    def test_failed_property_false_when_loaded(self):
        assert self._loaded_record().failed is False

    def test_loaded_str(self):
        s = str(self._loaded_record())
        assert "LOADED" in s
        assert "hello_plugin" in s

    def test_failed_str(self):
        s = str(self._failed_record())
        assert "FAILED" in s
        assert "bad_plugin" in s

    def test_worker_names_tuple(self):
        r = self._loaded_record()
        assert isinstance(r.worker_names, tuple)
        assert "hello_worker" in r.worker_names

    def test_immutable(self):
        r = self._loaded_record()
        with pytest.raises((AttributeError, TypeError)):
            r.plugin_name = "other"


# ---------------------------------------------------------------------------
# PluginLoader — metadata reading
# ---------------------------------------------------------------------------


class TestPluginLoaderMetadata:

    def test_missing_plugin_json_uses_defaults(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        _inject_hello(monkeypatch)
        # No plugin.json — monkeypatch Path to point to tmp_path
        monkeypatch.chdir(tmp_path)
        (tmp_path / "plugins" / "hello_plugin").mkdir(parents=True)
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())
        records = loader.loaded_plugins()
        assert len(records) == 1
        assert records[0].metadata.name == "hello_plugin"
        assert records[0].metadata.version == "unknown"

    def test_valid_plugin_json_read(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        _inject_hello(monkeypatch)
        monkeypatch.chdir(tmp_path)
        plugin_dir = tmp_path / "plugins" / "hello_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "hello_plugin", "version": "1.0.0",
                        "description": "Test plugin"}),
            encoding="utf-8",
        )
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())
        records = loader.loaded_plugins()
        assert records[0].metadata.version == "1.0.0"
        assert records[0].metadata.description == "Test plugin"

    def test_malformed_plugin_json_uses_defaults_and_loads(self, tmp_path, monkeypatch):
        """Malformed plugin.json → defaults used, plugin still loads."""
        from core.plugins.loader import PluginLoader
        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        _inject_hello(monkeypatch)
        monkeypatch.chdir(tmp_path)
        plugin_dir = tmp_path / "plugins" / "hello_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text("{not valid json}", encoding="utf-8")
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())
        # Plugin still loads despite bad plugin.json
        assert len(loader.loaded_plugins()) == 1
        assert loader.loaded_plugins()[0].metadata.version == "unknown"


# ---------------------------------------------------------------------------
# PluginLoader — config
# ---------------------------------------------------------------------------


class TestPluginLoaderConfig:

    def test_absent_config_json_passes_empty_dict(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader

        received_configs = []

        fake_pkg = types.ModuleType("plugins")
        fake_sub = types.ModuleType("plugins.hello_plugin")

        def get_workers(config=None):
            received_configs.append(config)
            from plugins.hello_plugin.worker import HelloWorker
            return [HelloWorker()]

        fake_sub.get_workers = get_workers
        monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
        monkeypatch.setitem(sys.modules, "plugins.hello_plugin", fake_sub)

        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        monkeypatch.chdir(tmp_path)
        (tmp_path / "plugins" / "hello_plugin").mkdir(parents=True)

        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        assert received_configs == [{}]

    def test_valid_config_json_passed_to_get_workers(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader

        received_configs = []

        fake_pkg = types.ModuleType("plugins")
        fake_sub = types.ModuleType("plugins.hello_plugin")

        def get_workers(config=None):
            received_configs.append(config)
            from plugins.hello_plugin.worker import HelloWorker
            return [HelloWorker()]

        fake_sub.get_workers = get_workers
        monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
        monkeypatch.setitem(sys.modules, "plugins.hello_plugin", fake_sub)

        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        monkeypatch.chdir(tmp_path)
        plugin_dir = tmp_path / "plugins" / "hello_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "config.json").write_text(
            json.dumps({"greeting": "Howdy!"}), encoding="utf-8"
        )

        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        assert received_configs == [{"greeting": "Howdy!"}]

    def test_malformed_config_json_fails_plugin(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        _inject_hello(monkeypatch)

        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        monkeypatch.chdir(tmp_path)
        plugin_dir = tmp_path / "plugins" / "hello_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "config.json").write_text("{bad json}", encoding="utf-8")

        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        assert len(loader.failed_plugins()) == 1
        assert "config.json" in loader.failed_plugins()[0].error.lower() or \
               "valid json" in loader.failed_plugins()[0].error.lower()

    def test_non_object_config_json_fails_plugin(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        _inject_hello(monkeypatch)

        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        monkeypatch.chdir(tmp_path)
        plugin_dir = tmp_path / "plugins" / "hello_plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "config.json").write_text("[1, 2, 3]", encoding="utf-8")

        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        assert len(loader.failed_plugins()) == 1


# ---------------------------------------------------------------------------
# PluginLoader — load record
# ---------------------------------------------------------------------------


class TestPluginLoaderLoadRecord:

    def test_loaded_plugins_returns_loaded_only(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        _inject_hello(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "plugins" / "hello_plugin").mkdir(parents=True)

        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        records = loader.loaded_plugins()
        assert len(records) == 1
        assert records[0].plugin_name == "hello_plugin"
        assert records[0].loaded is True

    def test_failed_plugins_returns_failed_only(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader

        manifest = _make_manifest(tmp_path, ["no_such_plugin"])
        monkeypatch.setitem(sys.modules, "plugins.no_such_plugin", None)

        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        assert len(loader.failed_plugins()) == 1
        assert loader.failed_plugins()[0].plugin_name == "no_such_plugin"
        assert loader.failed_plugins()[0].failed is True

    def test_failed_record_contains_error_message(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        manifest = _make_manifest(tmp_path, ["no_such_plugin"])
        monkeypatch.setitem(sys.modules, "plugins.no_such_plugin", None)
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())
        assert loader.failed_plugins()[0].error != ""

    def test_all_records_returns_both(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        _inject_hello(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "plugins" / "hello_plugin").mkdir(parents=True)

        # Add a second broken plugin
        fake_pkg = sys.modules.get("plugins") or types.ModuleType("plugins")
        fake_bad = types.ModuleType("plugins.bad_plugin")
        # no get_workers
        monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
        monkeypatch.setitem(sys.modules, "plugins.bad_plugin", fake_bad)

        manifest = _make_manifest(tmp_path, ["hello_plugin", "bad_plugin"])
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        all_r = loader.all_records()
        assert len(all_r) == 2
        statuses = {r.plugin_name: r.loaded for r in all_r}
        assert statuses["hello_plugin"] is True
        assert statuses["bad_plugin"] is False

    def test_empty_manifest_produces_no_records(self, tmp_path):
        from core.plugins.loader import PluginLoader
        manifest = _make_manifest(tmp_path, [])
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())
        assert loader.all_records() == []

    def test_worker_names_in_loaded_record(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        _inject_hello(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "plugins" / "hello_plugin").mkdir(parents=True)

        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        record = loader.loaded_plugins()[0]
        assert "hello_worker" in record.worker_names


# ---------------------------------------------------------------------------
# PluginLoader — worker→plugin mapping
# ---------------------------------------------------------------------------


class TestPluginLoaderWorkerMapping:

    def test_plugin_for_worker_returns_plugin_name(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        _inject_hello(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "plugins" / "hello_plugin").mkdir(parents=True)

        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        assert loader.plugin_for_worker("hello_worker") == "hello_plugin"

    def test_plugin_for_worker_returns_none_for_unknown(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        _inject_hello(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "plugins" / "hello_plugin").mkdir(parents=True)

        manifest = _make_manifest(tmp_path, ["hello_plugin"])
        loader = PluginLoader(manifest_path=manifest)
        loader.load_enabled(_StubManager())

        assert loader.plugin_for_worker("coding_worker") is None
        assert loader.plugin_for_worker("nonexistent") is None


# ---------------------------------------------------------------------------
# PluginLoader — capability conflict warning
# ---------------------------------------------------------------------------


class TestCapabilityConflictWarning:

    def test_conflict_logs_warning(self, tmp_path, monkeypatch, caplog):
        from core.plugins.loader import PluginLoader
        from core.workers.models import WorkerTask, WorkerResult
        from core.workers.base import Worker

        # Plugin A: declares capability "shared_cap"
        class WorkerA(Worker):
            @property
            def name(self): return "worker_a"
            @property
            def description(self): return "A"
            @property
            def capabilities(self): return ["shared_cap"]
            def validate(self, task): return True
            def execute(self, task):
                self._begin(task)
                return self._succeed(WorkerResult(
                    task_id=task.task_id, worker_name=self.name,
                    success=True, requires_approval=True,
                ))

        # Plugin B: also declares capability "shared_cap"
        class WorkerB(Worker):
            @property
            def name(self): return "worker_b"
            @property
            def description(self): return "B"
            @property
            def capabilities(self): return ["shared_cap"]
            def validate(self, task): return True
            def execute(self, task):
                self._begin(task)
                return self._succeed(WorkerResult(
                    task_id=task.task_id, worker_name=self.name,
                    success=True, requires_approval=True,
                ))

        fake_pkg = types.ModuleType("plugins")
        fake_a = types.ModuleType("plugins.plugin_a")
        fake_b = types.ModuleType("plugins.plugin_b")
        fake_a.get_workers = lambda config=None: [WorkerA()]
        fake_b.get_workers = lambda config=None: [WorkerB()]
        monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
        monkeypatch.setitem(sys.modules, "plugins.plugin_a", fake_a)
        monkeypatch.setitem(sys.modules, "plugins.plugin_b", fake_b)

        manifest = _make_manifest(tmp_path, ["plugin_a", "plugin_b"])
        loader = PluginLoader(manifest_path=manifest)

        with caplog.at_level(logging.WARNING, logger="core.plugins.loader"):
            loader.load_enabled(_StubManager())

        # Both should load
        assert len(loader.loaded_plugins()) == 2
        # Warning should mention the conflict
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("shared_cap" in m for m in warning_messages), \
            f"Expected capability conflict warning. Got: {warning_messages}"


# ---------------------------------------------------------------------------
# HelloWorker — Sprint-002 contract
# ---------------------------------------------------------------------------


class TestHelloWorkerSprint002:

    def _task(self, instruction="ping"):
        from core.workers.models import WorkerTask
        return WorkerTask(task_type="plugin_demo", payload={"instruction": instruction})

    def test_get_workers_accepts_none(self):
        from plugins.hello_plugin import get_workers
        workers = get_workers(None)
        assert len(workers) == 1

    def test_get_workers_accepts_empty_dict(self):
        from plugins.hello_plugin import get_workers
        workers = get_workers({})
        assert len(workers) == 1

    def test_get_workers_no_args_backwards_compat(self):
        from plugins.hello_plugin import get_workers
        workers = get_workers()
        assert len(workers) == 1

    def test_config_greeting_override(self):
        from plugins.hello_plugin.worker import HelloWorker
        worker = HelloWorker(config={"greeting": "Howdy!"})
        result = worker.execute(self._task("test"))
        assert "Howdy!" in result.observations[0]

    def test_default_greeting_when_no_config(self):
        from plugins.hello_plugin.worker import HelloWorker
        worker = HelloWorker()
        result = worker.execute(self._task("test"))
        assert "Hello from HelloWorker!" in result.observations[0]

    def test_requires_approval_still_true(self):
        from plugins.hello_plugin.worker import HelloWorker
        worker = HelloWorker(config={"greeting": "Hi!"})
        result = worker.execute(self._task("anything"))
        assert result.requires_approval is True


# ---------------------------------------------------------------------------
# Sprint-001 regression
# ---------------------------------------------------------------------------


class TestSprint001Regression:

    def test_missing_manifest_still_raises_config_error(self, tmp_path):
        from core.plugins.loader import PluginLoader
        from core.plugins.exceptions import PluginConfigError
        loader = PluginLoader(manifest_path=tmp_path / "nope.json")
        with pytest.raises(PluginConfigError):
            loader.load_enabled(_StubManager())

    def test_plugin_without_get_workers_still_fails(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        fake_pkg = types.ModuleType("plugins")
        fake_bad = types.ModuleType("plugins.bad_plugin")
        monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
        monkeypatch.setitem(sys.modules, "plugins.bad_plugin", fake_bad)
        manifest = _make_manifest(tmp_path, ["bad_plugin"])
        loader = PluginLoader(manifest_path=manifest)
        loaded = loader.load_enabled(_StubManager())
        assert loaded == []
        assert len(loader.failed_plugins()) == 1

    def test_one_bad_plugin_does_not_prevent_good_plugin(self, tmp_path, monkeypatch):
        from core.plugins.loader import PluginLoader
        _inject_hello(monkeypatch)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "plugins" / "hello_plugin").mkdir(parents=True)

        fake_pkg = sys.modules.get("plugins") or types.ModuleType("plugins")
        fake_bad = types.ModuleType("plugins.bad_first")
        monkeypatch.setitem(sys.modules, "plugins", fake_pkg)
        monkeypatch.setitem(sys.modules, "plugins.bad_first", fake_bad)

        manifest = _make_manifest(tmp_path, ["bad_first", "hello_plugin"])
        loader = PluginLoader(manifest_path=manifest)
        loaded = loader.load_enabled(_StubManager())

        assert "hello_plugin" in loaded
        assert "bad_first" not in loaded

    def test_agent_references_plugin_loader(self):
        agent_path = pathlib.Path("core/agent.py")
        if not agent_path.exists():
            pytest.skip("Run from repo root")
        src = agent_path.read_text(encoding="utf-8")
        assert "PluginLoader" in src
        assert "load_enabled" in src

    def test_exceptions_hierarchy_intact(self):
        from core.plugins.exceptions import PluginError, PluginLoadError, PluginConfigError
        assert issubclass(PluginLoadError, PluginError)
        assert issubclass(PluginConfigError, PluginError)
        assert issubclass(PluginError, Exception)
