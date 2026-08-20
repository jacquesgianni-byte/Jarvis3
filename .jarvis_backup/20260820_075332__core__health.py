from __future__ import annotations

import os
import platform
import subprocess
from typing import Any, Dict, Optional

try:  # Python 3.8+
    from importlib.metadata import version as pkg_version  # type: ignore
except Exception:  # pragma: no cover
    pkg_version = None  # type: ignore

__all__ = ["version_info"]


def _read_git_commit() -> str:
    """Best-effort retrieval of current git commit (short). Returns 'unknown' on failure."""
    try:
        # Avoid blocking and noisy errors
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=0.5,
        )
        commit = out.decode().strip()
        return commit if commit else "unknown"
    except Exception:
        return "unknown"


def _resolve_version(package_name: Optional[str]) -> str:
    # 1) Environment override
    env_ver = os.getenv("APP_VERSION")
    if env_ver:
        return env_ver
    # 2) Package metadata if available and package specified
    if package_name and pkg_version:
        try:
            return pkg_version(package_name)  # type: ignore
        except Exception:
            pass
    # 3) Fallback
    return "0.0.0+unknown"


def version_info(package_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Return a dictionary with application version diagnostics.

    Precedence:
    - version: APP_VERSION env > package metadata (if package_name provided) > fallback
    - commit: GIT_COMMIT env > git rev-parse > unknown
    - build_time: BUILD_TIME env > unknown

    Args:
        package_name: Optional distribution/package name to query metadata.

    Returns:
        Dict[str, Any]: {service, version, commit, build_time, python_version, runtime}
    """
    service = os.getenv("SERVICE_NAME", "unknown-service")
    version = _resolve_version(package_name)
    commit = os.getenv("GIT_COMMIT") or _read_git_commit()
    build_time = os.getenv("BUILD_TIME", "unknown")

    info = {
        "service": service,
        "version": version,
        "commit": commit,
        "build_time": build_time,
        "python_version": platform.python_version(),
        "runtime": platform.python_implementation(),
    }
    return info
