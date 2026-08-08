"""
DocumentReader — interface and implementations for reading uploaded files.
Every file type plugs into the same interface: read(path) -> DocumentContext.
No duplicated parsing logic. One reader per file type.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from apps.server.document_intake.file_type_detector import FileType, DetectedFile


@dataclass
class DocumentContext:
    """
    The result of reading a file. This is what the Agent receives.
    The AI never receives raw file bytes — only extracted content + metadata.
    """
    filename:    str
    file_type:   str
    content:     str                    # Extracted text content
    summary:     str = ""               # Optional pre-summary
    page_count:  int = 0
    word_count:  int = 0
    metadata:    dict = field(default_factory=dict)
    error:       Optional[str] = None
    truncated:   bool = False

    MAX_CONTENT_CHARS = 12_000          # Safety limit before truncation

    @property
    def is_readable(self) -> bool:
        return self.error is None and bool(self.content)

    def to_prompt_context(self) -> str:
        """Format for injection into agent prompt."""
        if not self.is_readable:
            return f"[File: {self.filename} — could not be read: {self.error}]"
        lines = [
            f"[Attached file: {self.filename} ({self.file_type})]",
        ]
        if self.page_count:
            lines.append(f"[Pages: {self.page_count}]")
        if self.word_count:
            lines.append(f"[Words: {self.word_count}]")
        if self.truncated:
            lines.append("[Note: content truncated to first 12,000 characters]")
        lines.append("")
        lines.append(self.content)
        return "\n".join(lines)

    def __repr__(self) -> str:
        status = "ok" if self.is_readable else f"error: {self.error}"
        return f"DocumentContext({self.filename!r}, {self.file_type}, {status})"


class DocumentReader(ABC):
    """Base interface. Every reader must implement read()."""

    @abstractmethod
    def can_read(self, detected: DetectedFile) -> bool:
        """Return True if this reader handles the given file type."""

    @abstractmethod
    def read(self, path: Path, detected: DetectedFile) -> DocumentContext:
        """Read the file and return extracted content."""

    def _truncate(self, text: str) -> tuple[str, bool]:
        limit = DocumentContext.MAX_CONTENT_CHARS
        if len(text) > limit:
            return text[:limit], True
        return text, False


# ── Concrete readers ───────────────────────────────────────────────────────────

class TextReader(DocumentReader):
    """Reads .txt, .md, and .json files."""

    def can_read(self, detected: DetectedFile) -> bool:
        return detected.file_type in (FileType.TXT, FileType.JSON)

    def read(self, path: Path, detected: DetectedFile) -> DocumentContext:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            content, truncated = self._truncate(raw)
            return DocumentContext(
                filename  = detected.filename,
                file_type = detected.file_type.value,
                content   = content,
                word_count = len(raw.split()),
                truncated = truncated,
            )
        except Exception as e:
            return DocumentContext(
                filename=detected.filename, file_type=detected.file_type.value,
                content="", error=str(e)
            )


class CodeReader(DocumentReader):
    """Reads Python source files."""

    def can_read(self, detected: DetectedFile) -> bool:
        return detected.file_type == FileType.PY

    def read(self, path: Path, detected: DetectedFile) -> DocumentContext:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            content, truncated = self._truncate(raw)
            lines = raw.splitlines()
            return DocumentContext(
                filename   = detected.filename,
                file_type  = detected.file_type.value,
                content    = content,
                word_count = len(raw.split()),
                truncated  = truncated,
                metadata   = {"line_count": len(lines)},
            )
        except Exception as e:
            return DocumentContext(
                filename=detected.filename, file_type=detected.file_type.value,
                content="", error=str(e)
            )


class PdfReader(DocumentReader):
    """Reads PDF files using pypdf (graceful fallback if not installed)."""

    def can_read(self, detected: DetectedFile) -> bool:
        return detected.file_type == FileType.PDF

    def read(self, path: Path, detected: DetectedFile) -> DocumentContext:
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            pages  = []
            for page in reader.pages:
                text = page.extract_text() or ""
                pages.append(text)
            raw = "\n\n".join(pages)
            content, truncated = self._truncate(raw)
            return DocumentContext(
                filename   = detected.filename,
                file_type  = detected.file_type.value,
                content    = content,
                page_count = len(reader.pages),
                word_count = len(raw.split()),
                truncated  = truncated,
            )
        except ImportError:
            return DocumentContext(
                filename=detected.filename, file_type=detected.file_type.value,
                content="", error="pypdf not installed. Run: pip install pypdf"
            )
        except Exception as e:
            return DocumentContext(
                filename=detected.filename, file_type=detected.file_type.value,
                content="", error=str(e)
            )


class ImageReader(DocumentReader):
    """
    Placeholder for image files.
    Images are flagged for future vision support — not parsed as text.
    """

    def can_read(self, detected: DetectedFile) -> bool:
        return detected.is_image

    def read(self, path: Path, detected: DetectedFile) -> DocumentContext:
        size_kb = path.stat().st_size // 1024 if path.exists() else 0
        return DocumentContext(
            filename  = detected.filename,
            file_type = detected.file_type.value,
            content   = f"[Image file: {detected.filename}, {size_kb}KB. Vision analysis not yet supported. Pipeline ready for future vision integration.]",
            metadata  = {"size_kb": size_kb, "vision_ready": True},
        )



class DocxReader(DocumentReader):
    """Reads .docx Word documents using python-docx."""

    def can_read(self, detected: DetectedFile) -> bool:
        return detected.file_type == FileType.DOCX

    def read(self, path: Path, detected: DetectedFile) -> DocumentContext:
        try:
            import docx as _docx
            doc        = _docx.Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            raw        = "\n".join(paragraphs)
            content, truncated = self._truncate(raw)
            return DocumentContext(
                filename   = detected.filename,
                file_type  = detected.file_type.value,
                content    = content,
                word_count = len(raw.split()),
                page_count = len(doc.sections),
                truncated  = truncated,
                metadata   = {"paragraph_count": len(paragraphs)},
            )
        except ImportError:
            return DocumentContext(
                filename=detected.filename, file_type=detected.file_type.value,
                content="", error="python-docx not installed. Run: pip install python-docx"
            )
        except Exception as e:
            return DocumentContext(
                filename=detected.filename, file_type=detected.file_type.value,
                content="", error=str(e)
            )

class FallbackReader(DocumentReader):
    """Handles unknown file types gracefully."""

    def can_read(self, detected: DetectedFile) -> bool:
        return True  # Always matches as last resort

    def read(self, path: Path, detected: DetectedFile) -> DocumentContext:
        return DocumentContext(
            filename  = detected.filename,
            file_type = detected.file_type.value,
            content   = "",
            error     = f"No reader available for file type: {detected.file_type.value}",
        )


# ── Reader registry ───────────────────────────────────────────────────────────

class DocumentReaderRegistry:
    """
    Finds the right reader for a file. First match wins.
    Add new readers here as they are implemented.
    """

    def __init__(self):
        self._readers: list[DocumentReader] = [
            TextReader(),
            CodeReader(),
            PdfReader(),
            DocxReader(),
            ImageReader(),
            FallbackReader(),   # Must be last
        ]

    def get_reader(self, detected: DetectedFile) -> DocumentReader:
        for reader in self._readers:
            if reader.can_read(detected):
                return reader
        return FallbackReader()
