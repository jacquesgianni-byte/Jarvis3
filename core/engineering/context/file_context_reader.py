"""
Genesis-053 Sprint-004 - FileContextReader
Reads targeted repository files for AI planning context.
Repo-root bounded. Per-file 32KB limit. Total 128KB limit.
"""
from __future__ import annotations
import logging, os, re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)
FILE_SIZE_LIMIT_BYTES  =  32 * 1024
TOTAL_SIZE_LIMIT_BYTES = 128 * 1024

class FileContextReader:
    def __init__(self, repo_root: str) -> None:
        self._repo_root = Path(repo_root).resolve()

    def read(self, paths: List[str]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        total_bytes = 0
        for rel_path in paths:
            rel_path = rel_path.strip()
            if os.path.isabs(rel_path):
                logger.warning("[FILE_CONTEXT_READER] Rejected absolute path: %r", rel_path)
                continue
            if ".." in rel_path:
                logger.warning("[FILE_CONTEXT_READER] Rejected traversal path: %r", rel_path)
                continue
            abs_path = (self._repo_root / rel_path).resolve()
            try:
                abs_path.relative_to(self._repo_root)
            except ValueError:
                logger.warning("[FILE_CONTEXT_READER] Path escapes repo root: %r", rel_path)
                continue
            if not abs_path.is_file():
                logger.warning("[FILE_CONTEXT_READER] File not found: %r", rel_path)
                continue
            file_size = abs_path.stat().st_size
            if file_size > FILE_SIZE_LIMIT_BYTES:
                logger.warning("[FILE_CONTEXT_READER] File too large (%d bytes), skipping: %r", file_size, rel_path)
                continue
            if total_bytes + file_size > TOTAL_SIZE_LIMIT_BYTES:
                logger.warning("[FILE_CONTEXT_READER] Total limit reached at %d bytes. Skipping: %r", total_bytes, rel_path)
                break
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
                result[rel_path] = content
                total_bytes += file_size
                logger.info("[FILE_CONTEXT_READER] Read %r (%d bytes)", rel_path, file_size)
            except Exception as exc:
                logger.warning("[FILE_CONTEXT_READER] Could not read %r: %s", rel_path, exc)
        logger.info("[FILE_CONTEXT_READER] Done: %d file(s), %d bytes total.", len(result), total_bytes)
        return result

    @staticmethod
    def extract_file_hints(request: str) -> List[str]:
        pattern = re.compile(r"(?<!\w)((?:[\w\-]+/)+[\w\-]+\.[\w]+)(?!\w)")
        matches = pattern.findall(request)
        seen: Dict[str, None] = {}
        for m in matches:
            if m not in seen:
                seen[m] = None
        return list(seen.keys())
