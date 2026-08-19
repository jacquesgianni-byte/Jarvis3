"""
Genesis-053 Sprint-001 — Engineering Session Store

Persistent JSON store for EngineeringSessions.

Design constraints:
    - One JSON file per session under data/orchestrator/sessions/
    - Writes on every lifecycle transition (after suspend, approve, reject, complete)
    - Loads only AWAITING_APPROVAL sessions on startup (resumable sessions only)
    - Never raises on load — corrupted files are logged and skipped
    - Thread-safety: single-threaded (matches coordinator design)
    - The store does NOT modify sessions — it reads and writes only
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_STORE_DIR = pathlib.Path("data") / "orchestrator" / "sessions"


class SessionStore:
    """
    Persistent JSON store for EngineeringSessions.

    Usage:
        store = SessionStore()                    # default path
        store = SessionStore(directory="custom/path")

        store.save(session)                       # write/overwrite session file
        sessions = store.load_resumable()         # load AWAITING_APPROVAL sessions
        store.delete(session_id)                  # remove a session file
        store.exists(session_id)                  # check file presence
        store.list_session_ids()                  # all persisted session IDs
    """

    def __init__(
        self,
        directory: Optional[pathlib.Path] = None,
    ) -> None:
        self._dir = pathlib.Path(directory) if directory is not None else _DEFAULT_STORE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        logger.info("[SESSION_STORE] Initialised at: %s", self._dir.resolve())

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, session) -> bool:
        """
        Persist a session to disk.

        Args:
            session: An EngineeringSession instance with a to_dict() method.

        Returns:
            True if saved successfully, False on error.
        """
        try:
            data = session.to_dict()
            path = self._path_for(session.session_id)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.debug(
                "[SESSION_STORE] Saved session %s (stage=%s)",
                session.session_id[:8],
                session.current_stage.value,
            )
            return True
        except Exception:
            logger.exception(
                "[SESSION_STORE] Failed to save session %s",
                getattr(session, "session_id", "?"),
            )
            return False

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_resumable(self) -> List:
        """
        Load all AWAITING_APPROVAL sessions from disk.

        Called on coordinator startup to restore sessions that survived
        a server restart.

        Returns:
            List of restored EngineeringSession instances.
            Corrupted files are skipped with a warning.
        """
        from .models import EngineeringSession, EngineeringStatus

        sessions = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                status_str = data.get("status", "")
                if status_str != EngineeringStatus.AWAITING_APPROVAL.value:
                    # Only restore sessions that need a human decision
                    continue
                session = EngineeringSession.from_dict(data)
                sessions.append(session)
                logger.info(
                    "[SESSION_STORE] Restored resumable session %s",
                    session.session_id[:8],
                )
            except Exception:
                logger.warning(
                    "[SESSION_STORE] Skipping corrupted session file: %s",
                    path.name,
                    exc_info=True,
                )
        logger.info(
            "[SESSION_STORE] Loaded %d resumable session(s) from %s",
            len(sessions),
            self._dir,
        )
        return sessions

    def load(self, session_id: str) -> Optional:
        """
        Load a single session by ID.

        Returns:
            Restored EngineeringSession, or None if not found or corrupt.
        """
        from .models import EngineeringSession

        path = self._path_for(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return EngineeringSession.from_dict(data)
        except Exception:
            logger.warning(
                "[SESSION_STORE] Failed to load session %s", session_id[:8], exc_info=True
            )
            return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def delete(self, session_id: str) -> bool:
        """Delete the persisted file for a session. Returns True if deleted."""
        path = self._path_for(session_id)
        if path.exists():
            path.unlink()
            logger.debug("[SESSION_STORE] Deleted session %s", session_id[:8])
            return True
        return False

    def exists(self, session_id: str) -> bool:
        """Return True if a persisted file exists for this session_id."""
        return self._path_for(session_id).exists()

    def list_session_ids(self) -> List[str]:
        """Return all persisted session IDs (from filenames)."""
        return [p.stem for p in sorted(self._dir.glob("*.json"))]

    @property
    def directory(self) -> pathlib.Path:
        return self._dir

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _path_for(self, session_id: str) -> pathlib.Path:
        # Sanitise: strip characters that are unsafe in filenames
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self._dir / f"{safe_id}.json"

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("*.json")))
        return f"SessionStore(dir={self._dir!r}, files={count})"
