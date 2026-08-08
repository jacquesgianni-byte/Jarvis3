"""
FileTypeDetector — detects file type from filename and MIME type.
Returns a standard FileType enum. No parsing logic here.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class FileType(str, Enum):
    PDF   = "pdf"
    TXT   = "txt"
    DOCX  = "docx"
    XLSX  = "xlsx"
    PNG   = "png"
    JPG   = "jpg"
    JSON  = "json"
    PY    = "py"
    ZIP   = "zip"
    UNKNOWN = "unknown"


@dataclass
class DetectedFile:
    filename:   str
    file_type:  FileType
    mime_type:  str
    size_bytes: int
    is_image:   bool
    is_text:    bool
    is_code:    bool
    is_document: bool

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lstrip(".").lower()

    def __repr__(self) -> str:
        return f"DetectedFile({self.filename!r}, type={self.file_type.value})"


# MIME type -> FileType mapping
_MIME_MAP: dict[str, FileType] = {
    "application/pdf":                                                    FileType.PDF,
    "text/plain":                                                         FileType.TXT,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileType.DOCX,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": FileType.XLSX,
    "application/msword":                                                 FileType.DOCX,
    "image/png":                                                          FileType.PNG,
    "image/jpeg":                                                         FileType.JPG,
    "image/jpg":                                                          FileType.JPG,
    "application/json":                                                   FileType.JSON,
    "text/x-python":                                                      FileType.PY,
    "application/x-python-code":                                          FileType.PY,
    "application/zip":                                                    FileType.ZIP,
    "application/x-zip-compressed":                                       FileType.ZIP,
}

# Extension -> FileType fallback
_EXT_MAP: dict[str, FileType] = {
    "pdf":  FileType.PDF,
    "txt":  FileType.TXT,
    "md":   FileType.TXT,
    "docx": FileType.DOCX,
    "doc":  FileType.DOCX,
    "xlsx": FileType.XLSX,
    "xls":  FileType.XLSX,
    "png":  FileType.PNG,
    "jpg":  FileType.JPG,
    "jpeg": FileType.JPG,
    "json": FileType.JSON,
    "py":   FileType.PY,
    "zip":  FileType.ZIP,
}

_IMAGE_TYPES    = {FileType.PNG, FileType.JPG}
_TEXT_TYPES     = {FileType.TXT, FileType.JSON}
_CODE_TYPES     = {FileType.PY}
_DOCUMENT_TYPES = {FileType.PDF, FileType.DOCX, FileType.XLSX}


class FileTypeDetector:
    """Detects file type from filename and MIME type. Pure, stateless."""

    def detect(self, filename: str, mime_type: str = "", size_bytes: int = 0) -> DetectedFile:
        # Try MIME first, then extension
        ft = _MIME_MAP.get(mime_type.lower().strip())
        if ft is None:
            ext = Path(filename).suffix.lstrip(".").lower()
            ft = _EXT_MAP.get(ext, FileType.UNKNOWN)

        return DetectedFile(
            filename    = filename,
            file_type   = ft,
            mime_type   = mime_type,
            size_bytes  = size_bytes,
            is_image    = ft in _IMAGE_TYPES,
            is_text     = ft in _TEXT_TYPES,
            is_code     = ft in _CODE_TYPES,
            is_document = ft in _DOCUMENT_TYPES,
        )
