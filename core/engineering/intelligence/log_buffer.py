"""
Session Log Buffer — Genesis-045 Sprint-001

In-memory log handler that captures Jarvis log lines during
an analysis cycle. Attached at cycle start, detached and read
at cycle end. No file I/O.

The buffer decouples the engineering analysis cycle from
application lifetime and platform lifecycle events.
"""

from __future__ import annotations

import logging
from typing import Optional


class SessionLogBuffer(logging.Handler):
    """
    In-memory log handler that captures Jarvis log lines.

    Attached to the root Jarvis logger at session start.
    Detached and drained at the end of each analysis cycle.

    Usage:
        buffer = SessionLogBuffer()
        buffer.attach()
        ...  N turns  ...
        lines = buffer.drain()   # returns lines, resets buffer
        buffer.attach()          # ready for next cycle

    Thread-safe via the standard logging Handler lock.
    """

    def __init__(self) -> None:
        super().__init__()
        self._lines: list[str] = []
        self._attached: bool = False

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.acquire()
            try:
                self._lines.append(msg)
            finally:
                self.release()
        except Exception:
            self.handleError(record)

    def attach(self) -> None:
        """Attach to the root logger — captures all Jarvis log output."""
        if not self._attached:
            logging.getLogger().addHandler(self)
            self._attached = True

    def detach(self) -> None:
        """Detach from the root logger."""
        if self._attached:
            logging.getLogger().removeHandler(self)
            self._attached = False

    def drain(self) -> list[str]:
        """
        Return all captured lines and reset the buffer.
        Does NOT detach — call attach() separately if needed for next cycle.
        """
        self.acquire()
        try:
            lines = list(self._lines)
            self._lines = []
        finally:
            self.release()
        return lines

    def line_count(self) -> int:
        """Current number of buffered lines."""
        self.acquire()
        try:
            return len(self._lines)
        finally:
            self.release()

    def reset(self) -> None:
        """Clear buffered lines without returning them."""
        self.acquire()
        try:
            self._lines = []
        finally:
            self.release()
