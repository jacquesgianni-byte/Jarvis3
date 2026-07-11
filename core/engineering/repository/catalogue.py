"""
Repository Catalogue (Genesis-016 Sprint 001)

Gives Jarvis a map of where things live in its own project.

Deliberately lightweight — this is a catalogue, not an analyser.
Sprint 001 answers one question: "Where is it?"

What it does:
    * Walks the project tree and records every file.
    * Classifies each file into an architectural layer.
    * Tags files with role keywords (memory, ai, tests, etc.).
    * Answers path-based and role-based lookup queries.

What it deliberately does NOT do:
    * No AST parsing.
    * No symbol extraction.
    * No dependency graphs.
    * No semantic analysis.
    * No file modification of any kind.

Those capabilities belong to later sprints that will earn them
by building on this catalogue first (Earned Authority — Constitution
Principle 1).

Public API:
    catalogue = RepositoryCatalogue(root="/path/to/jarvis3")
    catalogue.build()

    catalogue.find("openai")           # files whose path contains "openai"
    catalogue.find_by_role("memory")   # files tagged with a role
    catalogue.layer("skills")          # all files in a named layer
    catalogue.summary()                # human-readable project overview
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Architectural layer definitions
# Mirrors the Jarvis project structure from the Genesis sprint history.
# ---------------------------------------------------------------------------

_LAYERS: dict[str, list[str]] = {
    "ai":           ["core/ai"],
    "knowledge":    ["core/knowledge_engine"],
    "reasoning":    ["core/reasoning"],
    "skills":       ["core/skills"],
    "conversation": ["core/conversation"],
    "voice":        ["core/voice"],
    "ui":           ["apps/desktop"],
    "engineering":  ["core/engineering"],
    "tests":        ["tests"],
    "data":         ["data"],
    "docs":         ["docs"],
    "settings":     ["core/settings"],
    "tools":        ["core/tools"],
    "models":       ["core/models"],
    "understanding":["core/understanding"],
    "memory":       ["core/memory"],
    "profiles":     ["core/profiles"],
    "services":     ["core/services"],
}

# Role keywords — hints at a file's purpose from its path
_ROLE_KEYWORDS: dict[str, list[str]] = {
    "memory":       ["memory", "knowledge"],
    "reasoning":    ["reasoning", "rules"],
    "ai_provider":  ["openai", "anthropic", "provider"],
    "voice":        ["voice", "tts", "speech"],
    "test":         ["test_"],
    "settings":     ["settings", "config"],
    "skills":       ["skill"],
    "router":       ["router", "intent"],
    "agent":        ["agent"],
    "ui":           ["window", "widget", "desktop", "orb", "sidebar"],
    "telemetry":    ["telemetry"],
    "data":         [".json"],
    "docs":         [".md"],
}

# Files and directories to skip during the walk
_SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules",
              ".pytest_cache"}
_INDEX_EXTENSIONS = {".py", ".json", ".md", ".txt", ".cfg", ".toml"}


@dataclass
class CatalogueEntry:
    """One file in the project catalogue."""

    path: str           # relative to project root (forward slashes)
    size_bytes: int
    layer: str          # architectural layer name
    roles: list[str]    # matched role keywords

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def stem(self) -> str:
        return Path(self.path).stem


class RepositoryCatalogue:
    """
    A navigable file catalogue of the Jarvis project.

    Read-only. Build once at startup; query repeatedly.
    No file is ever created, modified, or deleted by this class.
    """

    def __init__(self, root: str | Path | None = None):
        if root is None:
            # Locate project root relative to this file's position:
            # core/engineering/repository/catalogue.py → ../../.. = root
            root = Path(__file__).resolve().parent.parent.parent.parent
        self.root = Path(root).resolve()
        self._entries: list[CatalogueEntry] = []
        self._built = False
        self._build_ms: float = 0.0

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> "RepositoryCatalogue":
        """
        Walk the project tree and populate the catalogue.

        Skips: __pycache__, .git, hidden directories, .pyc files.
        Indexes: .py, .json, .md, .txt, .cfg, .toml files.
        """
        started = time.perf_counter()
        self._entries = []

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                d for d in dirnames
                if d not in _SKIP_DIRS and not d.startswith(".")
            ]

            for filename in filenames:
                if filename.startswith("."):
                    continue
                abs_path = Path(dirpath) / filename
                if abs_path.suffix not in _INDEX_EXTENSIONS:
                    continue

                rel_path = abs_path.relative_to(self.root).as_posix()
                self._entries.append(CatalogueEntry(
                    path=rel_path,
                    size_bytes=abs_path.stat().st_size,
                    layer=self._classify_layer(rel_path),
                    roles=self._classify_roles(rel_path),
                ))

        self._built = True
        self._build_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "RepositoryCatalogue: catalogued %d files in %.1f ms (root=%s)",
            len(self._entries), self._build_ms, self.root,
        )
        return self

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def find(self, query: str) -> list[CatalogueEntry]:
        """
        Return entries whose path contains the query (case-insensitive).

        Example: catalogue.find("openai")
                 -> [core/ai/providers/openai_provider.py, ...]
        """
        q = query.lower()
        return [e for e in self._entries if q in e.path.lower()]

    def find_by_role(self, role: str) -> list[CatalogueEntry]:
        """
        Return entries tagged with the given role keyword.

        Example: catalogue.find_by_role("memory")
                 -> [core/skills/memory.py, core/knowledge_engine/engine.py]
        """
        return [e for e in self._entries if role in e.roles]

    def layer(self, name: str) -> list[CatalogueEntry]:
        """
        Return all entries in a named architectural layer.

        Example: catalogue.layer("skills")
                 -> all files under core/skills/
        """
        return [e for e in self._entries if e.layer == name]

    def entries(self) -> list[CatalogueEntry]:
        """Return all catalogue entries."""
        return list(self._entries)

    def summary(self) -> str:
        """Human-readable overview — suitable for the Engineering Console."""
        if not self._built:
            return "Catalogue not built yet. Call build() first."

        layer_counts: dict[str, int] = {}
        for e in self._entries:
            layer_counts[e.layer] = layer_counts.get(e.layer, 0) + 1

        lines = [
            "Jarvis OS — Repository Catalogue",
            f"Root:           {self.root}",
            f"Files indexed:  {len(self._entries)} in {self._build_ms:.0f} ms",
            "",
            "Architectural layers:",
        ]
        for name, count in sorted(layer_counts.items()):
            lines.append(f"  {name:<16} {count:>3} file(s)")
        lines += [
            "",
            "Queries: find(query) | find_by_role(role) | layer(name)",
        ]
        return "\n".join(lines)

    def stats(self) -> dict:
        """Return catalogue statistics."""
        return {
            "files": len(self._entries),
            "layers": len({e.layer for e in self._entries}),
            "build_ms": round(self._build_ms, 1),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _classify_layer(self, rel_path: str) -> str:
        for name, prefixes in _LAYERS.items():
            for prefix in prefixes:
                if rel_path.startswith(prefix):
                    return name
        return "other"

    def _classify_roles(self, rel_path: str) -> list[str]:
        path_lower = rel_path.lower()
        return [
            role for role, keywords in _ROLE_KEYWORDS.items()
            if any(kw in path_lower for kw in keywords)
        ]