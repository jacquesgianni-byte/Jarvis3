from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from typing import Dict, Any


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def version_info() -> Dict[str, Any]:
    """
    Return service/version metadata suitable for health and diagnostics endpoints.

    Fields:
    - service: logical service name (env SERVICE_NAME, default "unknown")
    - version: application version string (env APP_VERSION, default "0.0.0-dev")
    - commit: VCS commit SHA (env GIT_COMMIT, default "")
    - branch: VCS branch name (env GIT_BRANCH, default "")
    - build_time: build timestamp ISO 8601 (env BUILD_TIME, defaults to current UTC)
    - python: Python runtime version
    """
    service = os.getenv("SERVICE_NAME", "unknown")
    version = os.getenv("APP_VERSION", "0.0.0-dev")
    commit = os.getenv("GIT_COMMIT", "")
    branch = os.getenv("GIT_BRANCH", "")
    build_time = os.getenv("BUILD_TIME") or _now_utc_iso()

    return {
        "service": service,
        "version": version,
        "commit": commit,
        "branch": branch,
        "build_time": build_time,
        "python": platform.python_version(),
    }
