"""
Jarvis 3.0 Configuration

This module defines the core configuration used throughout Jarvis.
It contains project paths, version information, and application metadata.
"""

from pathlib import Path


# ---------------------------------------------------------------------
# Project Information
# ---------------------------------------------------------------------

APP_NAME = "Jarvis"
VERSION = "3.0.0-alpha"
AUTHOR = "Ludovic Jacques"


# ---------------------------------------------------------------------
# Project Paths
# ---------------------------------------------------------------------

# Root of the project
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Standard folders
APPS_DIR = PROJECT_ROOT / "apps"
CORE_DIR = PROJECT_ROOT / "core"
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"
PLUGINS_DIR = PROJECT_ROOT / "plugins"
TESTS_DIR = PROJECT_ROOT / "tests"


# ---------------------------------------------------------------------
# Data folders
# ---------------------------------------------------------------------

LOGS_DIR = DATA_DIR / "logs"
MEMORY_DIR = DATA_DIR / "memory"
CACHE_DIR = DATA_DIR / "cache"
CONVERSATIONS_DIR = DATA_DIR / "conversations"


# Genesis-047 Sprint-001: Timeline retention window in days.
# Set to 0 to disable purge entirely (development only).
TIMELINE_RETENTION_DAYS: int = 90

# Default retention window for implicit user-world events (FactType.EVENT).
# Events are time-bounded by nature — this is policy, not architecture.
# Different event types may eventually use different windows; this is the
# safe default. Set to 0 to disable event memory persistence entirely.
EVENT_MEMORY_RETENTION_DAYS: int = 30


def print_config():
    """Display the current Jarvis configuration."""
    print(f"{APP_NAME} {VERSION}")
    print(f"Project Root : {PROJECT_ROOT}")
    print(f"Data Folder  : {DATA_DIR}")