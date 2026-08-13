"""
PluginLoader — Genesis-046 Sprint-002

Reads plugins/enabled.json, loads each plugin, and registers its workers.

Sprint-002 additions over Sprint-001:
  - Reads plugins/<name>/plugin.json for plugin identity (optional).
  - Reads plugins/<name>/config.json and passes config dict to
    get_workers(config) — plugin owns interpretation entirely.
  - Maintains an in-memory load record (PluginRecord per plugin).
  - Maintains a worker→plugin mapping for future EI attribution.
  - Logs a WARNING when a plugin worker declares a capability already
    claimed by a registered worker (no blocking, no priority system).

Contracts:
  - Plugin failures are NEVER fatal — Jarvis always starts.
  - Adding a plugin = one line in enabled.json, zero Jarvis Core changes.
  - Jarvis Core never interprets plugin-specific config keys.
  - get_workers(config) receives a dict; plugin interprets it.
  - config=None is normalised to {} before passing to the plugin.
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from core.plugins.exceptions import PluginLoadError, PluginConfigError
from core.plugins.models import PluginMetadata, PluginRecord, PluginStatus

if TYPE_CHECKING:
    from core.workers.manager import WorkerManager
    from core.workers.worker_factory import WorkerFactory

logger = logging.getLogger(__name__)

_DEFAULT_MANIFEST = Path("plugins") / "enabled.json"


class PluginLoader:
    """
    Loads enabled plugins and registers their workers.

    Public query API (Sprint-002):
        loaded_plugins()             -> list[PluginRecord]
        failed_plugins()             -> list[PluginRecord]
        all_records()                -> list[PluginRecord]
        plugin_for_worker(name)      -> str | None
    """

    def __init__(self, manifest_path: "Path | str | None" = None) -> None:
        self._manifest: Path = (
            Path(manifest_path) if manifest_path else _DEFAULT_MANIFEST
        )
        self._records: list[PluginRecord] = []
        self._worker_to_plugin: dict[str, str] = {}   # worker_name → plugin_name

    # ── public: load ──────────────────────────────────────────────────────────

    def load_enabled(
        self,
        worker_manager: "WorkerManager",
        worker_factory: "Optional[WorkerFactory]" = None,
    ) -> list[str]:
        """
        Read enabled.json and register each plugin's workers.

        Returns a list of successfully loaded plugin names.
        Failures are logged and recorded — Jarvis always starts.
        """
        self._records.clear()
        self._worker_to_plugin.clear()

        plugin_names = self._read_manifest()

        for name in plugin_names:
            record = self._load_plugin(name, worker_manager, worker_factory)
            self._records.append(record)
            if record.loaded:
                logger.info("Plugin loaded: %s", record)
            else:
                logger.warning("Plugin failed: %s", record)

        loaded = [r.plugin_name for r in self._records if r.loaded]
        failed = [r.plugin_name for r in self._records if r.failed]
        logger.info(
            "PluginLoader: %d loaded, %d failed. loaded=%s failed=%s",
            len(loaded), len(failed), loaded, failed,
        )
        return loaded

    # ── public: query (Sprint-002) ────────────────────────────────────────────

    def loaded_plugins(self) -> list[PluginRecord]:
        """Return records for plugins that loaded successfully."""
        return [r for r in self._records if r.loaded]

    def failed_plugins(self) -> list[PluginRecord]:
        """Return records for plugins that failed to load."""
        return [r for r in self._records if r.failed]

    def all_records(self) -> list[PluginRecord]:
        """Return all load records (loaded + failed)."""
        return list(self._records)

    def plugin_for_worker(self, worker_name: str) -> Optional[str]:
        """
        Return the plugin name that registered a given worker.

        Returns None if the worker was not registered by any plugin
        (i.e. it is a core worker).

        Forward-compatibility seam for Engineering Intelligence attribution.
        """
        return self._worker_to_plugin.get(worker_name)

    # ── private ───────────────────────────────────────────────────────────────

    def _read_manifest(self) -> list[str]:
        """Parse enabled.json and return list of plugin names."""
        if not self._manifest.exists():
            raise PluginConfigError(
                f"Plugin manifest not found: {self._manifest}"
            )
        try:
            data = json.loads(self._manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PluginConfigError(
                f"Plugin manifest is not valid JSON: {self._manifest}"
            ) from exc

        if not isinstance(data, dict) or "enabled" not in data:
            raise PluginConfigError(
                f"Plugin manifest must be a JSON object with an 'enabled' list: "
                f"{self._manifest}"
            )
        plugins = data["enabled"]
        if not isinstance(plugins, list):
            raise PluginConfigError("'enabled' must be a list of plugin names.")
        return [str(p) for p in plugins]

    def _load_plugin(
        self,
        name: str,
        worker_manager: "WorkerManager",
        worker_factory: "Optional[WorkerFactory]",
    ) -> PluginRecord:
        """
        Attempt to load one plugin. Always returns a PluginRecord.
        Never raises — failures are captured in the record.
        """
        metadata = self._read_metadata(name)
        config = self._read_config(name)

        # config read may have produced a PluginConfigError — capture it
        if isinstance(config, PluginConfigError):
            return PluginRecord(
                plugin_name=name,
                status=PluginStatus.FAILED,
                metadata=metadata,
                error=str(config),
            )

        module_path = f"plugins.{name}"
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            return PluginRecord(
                plugin_name=name,
                status=PluginStatus.FAILED,
                metadata=metadata,
                error=f"Cannot import '{module_path}': {exc}",
            )

        if not hasattr(module, "get_workers"):
            return PluginRecord(
                plugin_name=name,
                status=PluginStatus.FAILED,
                metadata=metadata,
                error=f"Plugin '{name}' has no get_workers() function.",
            )

        try:
            workers = module.get_workers(config)
        except TypeError:
            # Backwards compatibility: plugin may not yet accept config arg
            try:
                workers = module.get_workers()
                logger.debug(
                    "Plugin '%s' get_workers() does not accept config — "
                    "update to get_workers(config=None) for Sprint-002 compliance.",
                    name,
                )
            except Exception as exc:
                return PluginRecord(
                    plugin_name=name,
                    status=PluginStatus.FAILED,
                    metadata=metadata,
                    error=f"get_workers() raised: {exc}",
                )
        except Exception as exc:
            return PluginRecord(
                plugin_name=name,
                status=PluginStatus.FAILED,
                metadata=metadata,
                error=f"get_workers(config) raised: {exc}",
            )

        if not isinstance(workers, list):
            return PluginRecord(
                plugin_name=name,
                status=PluginStatus.FAILED,
                metadata=metadata,
                error=f"get_workers() must return a list, got {type(workers).__name__}.",
            )

        registered_names: list[str] = []
        for worker in workers:
            # Capability conflict detection (warning only)
            for cap in getattr(worker, "capabilities", []):
                existing = worker_manager.workers_for(cap)
                if existing:
                    existing_names = [w.name for w in existing]
                    logger.warning(
                        "Plugin '%s' worker '%s' declares capability '%s' "
                        "already claimed by: %s. Both will be registered.",
                        name, worker.name, cap, existing_names,
                    )

            worker_manager.register(worker)
            self._worker_to_plugin[worker.name] = name
            registered_names.append(worker.name)
            logger.debug("Plugin '%s' registered worker: %s", name, worker.name)

            # Passthrough factory builder — preserves factory invariant
            if worker_factory is not None and not worker_factory.can_create(worker.name):
                _w = worker
                worker_factory.register_builder(
                    worker.name,
                    lambda deps, w=_w: w,
                )

        return PluginRecord(
            plugin_name=name,
            status=PluginStatus.LOADED,
            metadata=metadata,
            worker_names=tuple(registered_names),
        )

    def _read_metadata(self, name: str) -> PluginMetadata:
        """
        Read plugins/<name>/plugin.json for identity.
        Returns defaults if file is absent or malformed.
        """
        path = Path("plugins") / name / "plugin.json"
        if not path.exists():
            return PluginMetadata(name=name)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PluginMetadata(
                name=data.get("name", name),
                version=data.get("version", "unknown"),
                description=data.get("description", ""),
            )
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(
                "Plugin '%s' plugin.json is malformed — using defaults: %s", name, exc
            )
            return PluginMetadata(name=name)

    def _read_config(self, name: str) -> "dict | PluginConfigError":
        """
        Read plugins/<name>/config.json.
        Returns empty dict if absent.
        Returns PluginConfigError if file exists but is malformed JSON.
        Plugin is responsible for interpreting all keys.
        """
        path = Path("plugins") / name / "config.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return PluginConfigError(
                    f"Plugin '{name}' config.json must be a JSON object."
                )
            return data
        except json.JSONDecodeError as exc:
            return PluginConfigError(
                f"Plugin '{name}' config.json is not valid JSON: {exc}"
            )
