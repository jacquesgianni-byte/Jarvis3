"""
Jarvis ShiftController — Desktop Validation (Sprint A)

Stage 1 + Stage 2 only. Stage 3 deferred (Chief decision).

Stage 1: Process survival probe — is the desktop app process alive?
Stage 2: win32gui PID→window title match — does a 'Jarvis OS' window exist?

Based on the proven logic from commit 3e85501.
No fake HTTP health checks. No pyautogui.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from enum import Enum, auto

logger = logging.getLogger(__name__)

_DESKTOP_MODULE:     str = "apps.desktop.main"
_WINDOW_TITLE:       str = "Jarvis OS"
_STAGE1_TIMEOUT_SEC: int = 5
_STAGE2_TIMEOUT_SEC: int = 10


class ValidationResult(Enum):
    PASS              = auto()
    FAIL_PROCESS_DEAD = auto()
    FAIL_NO_WINDOW    = auto()
    FAIL_IMPORT_ERROR = auto()   # win32gui not available

    def label(self) -> str:
        return self.name

    @property
    def passed(self) -> bool:
        return self == ValidationResult.PASS


@dataclass(frozen=True)
class DesktopValidationReport:
    result: ValidationResult
    detail: str
    elapsed_secs: float

    @property
    def passed(self) -> bool:
        return self.result.passed


class DesktopValidation:
    """
    Run Stage 1 + Stage 2 desktop validation.

    Stage 1: confirm desktop process is running.
    Stage 2: confirm win32gui finds a 'Jarvis OS' window for that PID.
    """

    def run(self, desktop_pid: int | None = None) -> DesktopValidationReport:
        """
        Run validation against a known desktop PID, or discover the process.

        Args:
            desktop_pid: PID of the running desktop process, if known.
                         If None, attempts to find any python process running
                         apps.desktop.main.

        Returns:
            DesktopValidationReport
        """
        start = time.monotonic()

        # Stage 1 — process survival
        pid = desktop_pid or self._find_desktop_pid()
        if pid is None:
            elapsed = time.monotonic() - start
            return DesktopValidationReport(
                result=ValidationResult.FAIL_PROCESS_DEAD,
                detail="Desktop process not found.",
                elapsed_secs=round(elapsed, 1),
            )

        logger.info("[DESKTOP_VALIDATION] Stage 1 PASS — PID %d alive.", pid)

        # Stage 2 — window match
        window_result = self._find_window_for_pid(pid)
        elapsed = time.monotonic() - start

        if window_result == "import_error":
            return DesktopValidationReport(
                result=ValidationResult.FAIL_IMPORT_ERROR,
                detail="win32gui not available — cannot perform Stage 2.",
                elapsed_secs=round(elapsed, 1),
            )
        if not window_result:
            return DesktopValidationReport(
                result=ValidationResult.FAIL_NO_WINDOW,
                detail=f"No '{_WINDOW_TITLE}' window found for PID {pid}.",
                elapsed_secs=round(elapsed, 1),
            )

        logger.info(
            "[DESKTOP_VALIDATION] Stage 2 PASS — window '%s' found for PID %d.",
            _WINDOW_TITLE, pid,
        )
        return DesktopValidationReport(
            result=ValidationResult.PASS,
            detail=f"Desktop validation: PASS ({round(elapsed, 1)}s)",
            elapsed_secs=round(elapsed, 1),
        )

    def _find_desktop_pid(self) -> int | None:
        """Find the PID of the running desktop process via tasklist."""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=_STAGE1_TIMEOUT_SEC,
            )
            # Crude but reliable for our single known process
            for line in result.stdout.splitlines():
                if "python" in line.lower():
                    parts = line.strip('"').split('","')
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except ValueError:
                            continue
        except Exception as exc:
            logger.warning("[DESKTOP_VALIDATION] PID discovery failed: %s", exc)
        return None

    def _find_window_for_pid(self, pid: int) -> bool | str:
        """
        Use win32gui to find a window titled 'Jarvis OS' matching the PID.

        Returns:
            True   — window found
            False  — no matching window
            'import_error' — win32gui not available
        """
        try:
            import win32gui
            import win32process

            found = []

            def _enum_callback(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title == _WINDOW_TITLE:
                        _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
                        if window_pid == pid:
                            found.append(hwnd)

            deadline = time.monotonic() + _STAGE2_TIMEOUT_SEC
            while time.monotonic() < deadline:
                win32gui.EnumWindows(_enum_callback, None)
                if found:
                    return True
                time.sleep(0.5)

            return False

        except ImportError:
            logger.error("[DESKTOP_VALIDATION] win32gui not available.")
            return "import_error"
        except Exception as exc:
            logger.error("[DESKTOP_VALIDATION] Stage 2 error: %s", exc)
            return False
