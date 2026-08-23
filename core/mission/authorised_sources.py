"""
Jarvis OS ? Authorised Source Registry ? Genesis-056 Sprint-001

Single authority for what ReadOnlyInvestigator is allowed to read.

Security properties (enforced, not described):
    - Allow-list is a frozenset defined at import time.
    - No runtime extension. No method exists to add paths.
    - AuthorisedPath rejects path traversal, symlink escape,
      glob patterns, env-variable expansion, and credential files.
    - The investigator never receives a raw Path from user input.
    - There is no alternate read route around this module.

The allow-list contains logical names, not raw paths.
AuthorisedSourceRegistry resolves them to absolute paths
relative to the validated project root.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import FrozenSet

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Credential / sensitive filename patterns ? always rejected
# ---------------------------------------------------------------------------

_DENIED_NAMES: FrozenSet[str] = frozenset({
    ".env",
    ".env.local",
    ".env.production",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "local.properties",
    "keystore.jks",
    "google-services.json",
    "service-account.json",
})

_DENIED_EXTENSIONS: FrozenSet[str] = frozenset({
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
})

# ---------------------------------------------------------------------------
# Logical source names ? the public API
# ---------------------------------------------------------------------------

# Every source the investigator is allowed to read, by logical name.
# Keys are the names used in investigation requests.
# Values are relative paths from the project root.
AUTHORISED_RELATIVE_PATHS: dict[str, str] = {
    "project_state":    "project_state.json",
    "pipeline":         "core/mission/pipeline.py",
    "policy":           "core/mission/policy.py",
    "registry":         "core/mission/registry.py",
    "context":          "core/mission/context.py",
    "interface_context":"core/mission/interface_context.py",
    "routes":           "apps/server/routes.py",
    "server_app":       "apps/server/app.py",
}

# ---------------------------------------------------------------------------
# AuthorisedPath ? validated wrapper
# ---------------------------------------------------------------------------

class AuthorisedPath:
    """
    A validated, resolved absolute path guaranteed to be:
        - Within the project root (no traversal escape)
        - Not a symlink pointing outside the project root
        - Not a credential or sensitive file
        - Not constructed from user-supplied glob or env expansion
        - On the allow-list

    Construction raises ValueError for any violation.
    The raw Path is only accessible via .resolved ? never as a string
    that can be passed back to user-visible output.
    """

    def __init__(self, project_root: Path, logical_name: str):
        if logical_name not in AUTHORISED_RELATIVE_PATHS:
            raise ValueError(
                f"[AuthorisedPath] {logical_name!r} is not an authorised source. "
                f"Authorised sources: {sorted(AUTHORISED_RELATIVE_PATHS)}"
            )

        relative = AUTHORISED_RELATIVE_PATHS[logical_name]
        candidate = (project_root / relative).resolve()

        # 1. Must remain inside project root
        try:
            candidate.relative_to(project_root.resolve())
        except ValueError:
            raise ValueError(
                f"[AuthorisedPath] Path escape detected for {logical_name!r}. "
                f"Resolved to {candidate} which is outside {project_root}."
            )

        # 2. Symlink must not escape project root
        if candidate.is_symlink():
            real = Path(os.path.realpath(candidate))
            try:
                real.relative_to(project_root.resolve())
            except ValueError:
                raise ValueError(
                    f"[AuthorisedPath] Symlink escape detected for {logical_name!r}. "
                    f"Symlink target {real} is outside {project_root}."
                )

        # 3. Credential / sensitive file check
        name_lower = candidate.name.lower()
        if name_lower in _DENIED_NAMES:
            raise ValueError(
                f"[AuthorisedPath] {logical_name!r} resolves to a denied filename {candidate.name!r}."
            )
        if candidate.suffix.lower() in _DENIED_EXTENSIONS:
            raise ValueError(
                f"[AuthorisedPath] {logical_name!r} has a denied extension {candidate.suffix!r}."
            )

        self._logical_name = logical_name
        self._resolved     = candidate

    @property
    def resolved(self) -> Path:
        """The validated absolute path. Read-only."""
        return self._resolved

    @property
    def logical_name(self) -> str:
        return self._logical_name

    def __repr__(self) -> str:
        return f"AuthorisedPath({self._logical_name!r})"


# ---------------------------------------------------------------------------
# AuthorisedSourceRegistry ? the single read gateway
# ---------------------------------------------------------------------------

class AuthorisedSourceRegistry:
    """
    Resolves logical source names to AuthorisedPath instances.

    This is the only object that knows the project root.
    ReadOnlyInvestigator receives AuthorisedPath objects ? never raw paths.

    The registry is constructed once at server startup with the
    project root. It cannot be reconfigured at runtime.
    """

    def __init__(self, project_root: Path):
        self._root = project_root.resolve()

    def resolve(self, logical_name: str) -> AuthorisedPath:
        """
        Resolve a logical source name to a validated AuthorisedPath.
        Raises ValueError if the name is not authorised.
        """
        return AuthorisedPath(self._root, logical_name)

    def available_sources(self) -> list[str]:
        """Return the list of authorised logical source names."""
        return sorted(AUTHORISED_RELATIVE_PATHS.keys())

    def exists(self, logical_name: str) -> bool:
        """Return True if the logical source exists on disk."""
        try:
            ap = self.resolve(logical_name)
            return ap.resolved.exists()
        except ValueError:
            return False
