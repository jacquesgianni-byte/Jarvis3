"""
Jarvis 3.0 Logger

Provides a shared logger for the entire project.

Genesis-011 Maintenance Patch 002 (logging fix):
    Handlers are now attached to the ROOT logger instead of only the
    APP_NAME logger. Modules that log via logging.getLogger(__name__)
    — the voice layer, the AI layer, and any future module — previously
    routed to the handler-less root logger and their messages vanished.
    Now every log line in the project reaches jarvis.log and the
    console.

    get_logger() is unchanged for callers: it still returns the shared
    APP_NAME logger, which propagates to root.

    The log format gains a %(name)s column so each line shows which
    module produced it (e.g. core.voice.worker).
"""

import logging
from pathlib import Path

from core.config import LOGS_DIR, APP_NAME

# Ensure the logs folder exists
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "jarvis.log"

_root = logging.getLogger()
_root.setLevel(logging.INFO)

# Prevent duplicate handlers if imported multiple times
if not _root.handlers:

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    _root.addHandler(file_handler)
    _root.addHandler(console_handler)

# Keep noisy third-party libraries out of the log now that the root
# logger has handlers. WARNING and above still comes through.
for _noisy in ("httpx", "httpcore", "openai", "urllib3", "comtypes", "pyttsx3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(APP_NAME)


def get_logger():
    """Return the shared Jarvis logger."""
    return logger