from __future__ import annotations

import os
import platform
import sys
from typing import Any, Dict, Optional

try:
    from importlib import metadata as importlib_metadata  # Python 3.8+
except Exception:  # pragma: no cover
    importlib_metadata = None  # type: ignore

__all__ = ["version_info"]


def _safe_pkg_version(pkg_name: Optional[str]) -> Optional[str]:
    """Return installed package version or None if unavailable."""
    if not pkg_name or not importlib_metadata:
        return None
    try:
        return importlib_metadata.version(pkg_name)
    except Exception:
        return None


def _first_env(*keys: str) -> Optional[str]:
    for k in keys:
        v = os.environ.get(k)
        if v:
            return v
    return None


def version_info(package_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Return version and runtime metadata for diagnostics.

    Priority for application version:
    1) Explicit package_name argument
    2) APP_PACKAGE environment variable
    3) None if not resolvable
    """
    resolved_pkg = package_name or os.environ.get("APP_PACKAGE")
    app_version = _safe_pkg_version(resolved_pkg)

    info: Dict[str, Any] = {
        "service": os.environ.get("SERVICE_NAME") or resolved_pkg or None,
        "version": app_version,
        "python": sys.version.split(" ")[0],
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "build": {
            "commit": _first_env("GIT_COMMIT", "BUILD_COMMIT", "SOURCE_VERSION"),
            "time": _first_env("BUILD_TIME", "BUILD_TIMESTAMP"),
            "branch": _first_env("GIT_BRANCH", "BRANCH", "SOURCE_BRANCH"),
        },
        "dependencies": {
            # Best-effort versions for common runtimes/frameworks
            "uvicorn": _safe_pkg_version("uvicorn"),
            "gunicorn": _safe_pkg_version("gunicorn"),
            "fastapi": _safe_pkg_version("fastapi"),
            "flask": _safe_pkg_version("flask"),
            "django": _safe_pkg_version("django"),
        },
    }

    return info
