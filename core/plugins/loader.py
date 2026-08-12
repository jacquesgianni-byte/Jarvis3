"""
PluginLoader — Genesis-046

Reads plugins/enabled.json and registers each listed plugin's workers
into the supplied WorkerManager (and optionally WorkerFactory).

Contract:
- Plugin failures NEVER prevent Jarvis from starting.
- Adding a plugin = one line in enabled.json, zero changes to Jarvis core.
- Each plugin module must expose get_workers() -> list[Worker].
- Workers follow the existing approval/security boundaries.
- A passthrough builder is registered in WorkerFactory so the existing
  factory invariant (all registered workers are buildable) is preserved.
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from core.plugins.exceptions import PluginLoadError, PluginConfigError

if TYPE_CHECKING:
    from core.workers.manager import WorkerManager
    from core.workers.worker_factory import WorkerFactory

logger = logging.getLogger(__name__)

_DEFAULT_MANIFEST = Path("plugins") / "enabled.json"


class PluginLoader:
    """Loads enabled plugins and registers their workers."""

    def __init__(self, manifest_path: "Path | str | None" = None) -> None:
        self._manifest: Path = (
            Path(manifest_path) if manifest_path else _DEFAULT_MANIFEST
        )

    # ── public ────────────────────────────────────────────────────────────────

    def load_enabled(
        self,
        worker_manager: "WorkerManager",
        worker_factory: "Optional[WorkerFactory]" = None,
    ) -> list[str]:
        """
        Read enabled.json and register each plugin's workers.

        If worker_factory is supplied, a passthrough builder is registered
        for each plugin worker so the factory invariant is preserved.

        Returns a list of successfully loaded plugin names.
        Failures are logged and skipped — Jarvis always starts.
        """
        plugin_names = self._read_manifest()
        loaded: list[str] = []

        for name in plugin_names:
            try:
                self._load_plugin(name, worker_manager, worker_factory)
                loaded.append(name)
                logger.info("Plugin loaded: %s", name)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Plugin '%s' failed to load and will be skipped: %s", name, exc
                )

        logger.info(
            "PluginLoader: %d/%d plugins loaded", len(loaded), len(plugin_names)
        )
        return loaded

    # ── private ───────────────────────────────────────────────────────────────

    def _read_manifest(self) -> list[str]:
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
                f"Plugin manifest must be a JSON object with an 'enabled' list: {self._manifest}"
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
    ) -> None:
        module_path = f"plugins.{name}"
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise PluginLoadError(
                f"Cannot import plugin module '{module_path}': {exc}"
            ) from exc

        if not hasattr(module, "get_workers"):
            raise PluginLoadError(
                f"Plugin '{name}' has no get_workers() function."
            )

        try:
            workers = module.get_workers()
        except Exception as exc:
            raise PluginLoadError(
                f"Plugin '{name}' get_workers() raised an error: {exc}"
            ) from exc

        if not isinstance(workers, list):
            raise PluginLoadError(
                f"Plugin '{name}' get_workers() must return a list."
            )

        for worker in workers:
            worker_manager.register(worker)
            logger.debug("Plugin '%s' registered worker: %s", name, worker.name)

            # Register a passthrough builder so factory invariant holds.
            if worker_factory is not None:
                if not worker_factory.can_create(worker.name):
                    _captured = worker
                    worker_factory.register_builder(
                        worker.name,
                        lambda deps, w=_captured: w,
                    )
                    logger.debug(
                        "Plugin '%s' registered factory builder for: %s",
                        name, worker.name,
                    )
