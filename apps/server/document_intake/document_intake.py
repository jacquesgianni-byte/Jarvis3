"""
DocumentIntake — orchestrates the upload pipeline.
Receives raw file bytes, stores safely, detects type, extracts content.
Returns DocumentContext ready for Agent injection.
"""

from __future__ import annotations
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from apps.server.document_intake.file_type_detector import FileTypeDetector, DetectedFile
from apps.server.document_intake.document_reader import DocumentReaderRegistry, DocumentContext

logger = logging.getLogger(__name__)

# Temp storage root — uploads/YYYY-MM-DD/UUID_filename
_UPLOAD_ROOT = Path(__file__).parent.parent.parent.parent / "uploads"

# 20MB max file size
MAX_FILE_SIZE = 20 * 1024 * 1024


class UploadResult:
    """Result of a successful upload + intake."""

    def __init__(
        self,
        upload_id:  str,
        detected:   DetectedFile,
        context:    DocumentContext,
        stored_at:  Path,
    ):
        self.upload_id  = upload_id
        self.detected   = detected
        self.context    = context
        self.stored_at  = stored_at

    def to_dict(self) -> dict:
        return {
            "upload_id":    self.upload_id,
            "filename":     self.detected.filename,
            "detected_type": self.detected.file_type.value,
            "mime_type":    self.detected.mime_type,
            "size_bytes":   self.detected.size_bytes,
            "is_image":     self.detected.is_image,
            "readable":     self.context.is_readable,
            "word_count":   self.context.word_count,
            "page_count":   self.context.page_count,
            "error":        self.context.error,
        }

    def __repr__(self) -> str:
        return f"UploadResult({self.upload_id}, {self.detected.filename!r})"


class DocumentIntake:
    """
    Orchestrates the full upload pipeline:
    1. Validate
    2. Store to temp directory
    3. Detect file type
    4. Extract content via reader
    5. Return UploadResult
    """

    def __init__(self):
        self.detector = FileTypeDetector()
        self.registry = DocumentReaderRegistry()
        self.upload_root = _UPLOAD_ROOT

    def process(
        self,
        file_bytes: bytes,
        filename:   str,
        mime_type:  str = "",
    ) -> UploadResult:
        """Main entry point. Returns UploadResult with extracted content."""

        # 1. Validate
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError(f"File too large: {len(file_bytes)} bytes (max {MAX_FILE_SIZE})")
        if not filename:
            raise ValueError("Filename is required")

        # 2. Store safely
        upload_id  = str(uuid.uuid4())[:8]
        date_dir   = datetime.now().strftime("%Y-%m-%d")
        store_dir  = self.upload_root / date_dir
        store_dir.mkdir(parents=True, exist_ok=True)

        safe_name  = self._safe_filename(filename)
        stored_at  = store_dir / f"{upload_id}_{safe_name}"
        stored_at.write_bytes(file_bytes)
        logger.info("[INTAKE] Stored: %s (%d bytes)", stored_at.name, len(file_bytes))

        # 3. Detect
        detected = self.detector.detect(filename, mime_type, len(file_bytes))
        logger.info("[INTAKE] Detected: %s -> %s", filename, detected.file_type.value)

        # 4. Extract
        reader  = self.registry.get_reader(detected)
        context = reader.read(stored_at, detected)
        logger.info(
            "[INTAKE] Read: %s words=%d error=%s",
            filename, context.word_count, context.error
        )

        return UploadResult(
            upload_id = upload_id,
            detected  = detected,
            context   = context,
            stored_at = stored_at,
        )

    def _safe_filename(self, filename: str) -> str:
        """Sanitise filename for safe filesystem storage."""
        import re
        name = Path(filename).name
        name = re.sub(r"[^\w\-_. ]", "_", name)
        return name[:100]   # Truncate long filenames
