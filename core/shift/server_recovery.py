"""
Jarvis ShiftController — Server Recovery (Sprint A)

Controlled infrastructure recovery ONLY.
    - Not code repair.
    - Not configuration modification.
    - Maximum 3 restart attempts.
    - 90-second cooldown between attempts.
    - Locked pre-approved startup command (cannot be modified at runtime).
    - Requires readiness + /chat canary before declaring recovery.

The startup command is locked at implementation time.
Any change to it requires a governed sprint and Chief approval.
"""

from __future__ import annotations

import subprocess
import time
import logging
from dataclasses import dataclass
from enum import Enum, auto

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locked startup command — immutable, not injectable at runtime
# ---------------------------------------------------------------------------

_LOCKED_ENV_VARS: dict[str, str] = {
    "ORCHESTRATOR_TOKEN": "Lucasleo2104#",
    "AGENT_TOKEN_GPT":    "JarvisGPT-Read-2024#",
    "AGENT_TOKEN_CLAUDE": "JarvisClaude-RW-2024#",
    "AGENT_TOKEN_JARVIS": "JarvisInternal-2024#",
}

_LOCKED_STARTUP_COMMAND: list[str] = [
    "python", "-m", "apps.server.server_main"
]

_SERVER_BASE_URL: str = "http://192.168.20.3:5001"
_CANARY_ENDPOINT: str = f"{_SERVER_BASE_URL}/chat"
_MAX_ATTEMPTS:    int = 3
_COOLDOWN_SECS:   int = 90
_CANARY_TIMEOUT:  int = 10


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class RecoveryResult(Enum):
    RECOVERED   = auto()   # server is up, canary passed
    FAILED      = auto()   # all attempts exhausted, server still unresponsive

    def label(self) -> str:
        return self.name


@dataclass(frozen=True)
class RecoveryReport:
    result: RecoveryResult
    attempts_made: int
    detail: str

    @property
    def succeeded(self) -> bool:
        return self.result == RecoveryResult.RECOVERED


# ---------------------------------------------------------------------------
# Canary check
# ---------------------------------------------------------------------------

def _canary_check() -> bool:
    """
    POST /chat with a trivial payload to confirm server is accepting requests.
    Returns True if 200 received, False otherwise.
    """
    try:
        resp = requests.post(
            _CANARY_ENDPOINT,
            json={"message": "ping", "session_id": "shift_canary"},
            timeout=_CANARY_TIMEOUT,
        )
        return resp.status_code == 200
    except Exception as exc:
        logger.warning("[SERVER_RECOVERY] Canary check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Recovery sequence
# ---------------------------------------------------------------------------

class ServerRecovery:
    """
    Controlled server restart sequence.

    Usage:
        recovery = ServerRecovery(repo_root=Path(...))
        report = recovery.attempt()
        if not report.succeeded:
            # HARD STOP — caller's responsibility
    """

    def __init__(self, repo_root: "Path | None" = None) -> None:
        self._repo_root = repo_root
        self._process: subprocess.Popen | None = None

    def attempt(self) -> RecoveryReport:
        """
        Attempt controlled server recovery.

        Returns RecoveryReport — caller must HARD STOP if not succeeded.
        """
        for attempt_num in range(1, _MAX_ATTEMPTS + 1):
            logger.info(
                "[SERVER_RECOVERY] Attempt %d/%d", attempt_num, _MAX_ATTEMPTS
            )

            try:
                self._start_server()
            except Exception as exc:
                logger.error("[SERVER_RECOVERY] Start failed: %s", exc)

            logger.info(
                "[SERVER_RECOVERY] Waiting %ds cooldown...", _COOLDOWN_SECS
            )
            time.sleep(_COOLDOWN_SECS)

            if _canary_check():
                logger.info("[SERVER_RECOVERY] Canary passed — server recovered.")
                return RecoveryReport(
                    result=RecoveryResult.RECOVERED,
                    attempts_made=attempt_num,
                    detail=f"Server recovered on attempt {attempt_num}.",
                )

            logger.warning(
                "[SERVER_RECOVERY] Canary failed after attempt %d.", attempt_num
            )

        return RecoveryReport(
            result=RecoveryResult.FAILED,
            attempts_made=_MAX_ATTEMPTS,
            detail=(
                f"Server unresponsive after {_MAX_ATTEMPTS} attempts. "
                f"HARD STOP required."
            ),
        )

    def _start_server(self) -> None:
        """
        Launch the server using the locked command and locked env vars.
        Does NOT modify the command or environment at runtime.
        """
        import os
        env = os.environ.copy()
        env.update(_LOCKED_ENV_VARS)

        cwd = str(self._repo_root) if self._repo_root else None

        self._process = subprocess.Popen(
            _LOCKED_STARTUP_COMMAND,
            env=env,
            cwd=cwd,
        )
        logger.info(
            "[SERVER_RECOVERY] Started server process PID=%s", self._process.pid
        )
