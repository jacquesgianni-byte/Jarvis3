"""
File Intelligence Sprint tests.
"""
import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from apps.server.document_intake.file_type_detector import FileTypeDetector, FileType
from apps.server.document_intake.document_reader import (
    TextReader, CodeReader, ImageReader, FallbackReader,
    DocumentReaderRegistry, DocumentContext,
)
from apps.server.document_intake.document_intake import DocumentIntake

class TestFileTypeDetector:
    def _d(self): return FileTypeDetector()
    def test_detect_pdf_by_mime(self):
        r = self._d().detect("doc.pdf", "application/pdf")
        assert r.file_type == FileType.PDF
        assert r.is_document
    def test_detect_txt_by_mime(self):
        r = self._d().detect("notes.txt", "text/plain")
        assert r.file_type == FileType.TXT
        assert r.is_text
    def test_detect_py_by_mime(self):
        r = self._d().detect("agent.py", "text/x-python")
        assert r.file_type == FileType.PY
        assert r.is_code
    def test_detect_png_by_mime(self):
        r = self._d().detect("photo.png", "image/png")
        assert r.file_type == FileType.PNG
        assert r.is_image
    def test_detect_jpg_by_mime(self):
        r = self._d().detect("photo.jpg", "image/jpeg")
        assert r.file_type == FileType.JPG
        assert r.is_image
    def test_detect_by_extension_fallback(self):
        r = self._d().detect("data.xlsx", "")
        assert r.file_type == FileType.XLSX
    def test_detect_py_by_extension(self):
        r = self._d().detect("script.py", "")
        assert r.file_type == FileType.PY
    def test_detect_json_by_extension(self):
        r = self._d().detect("config.json", "")
        assert r.file_type == FileType.JSON
    def test_detect_unknown(self):
        r = self._d().detect("weird.xyz", "application/octet-stream")
        assert r.file_type == FileType.UNKNOWN
    def test_size_bytes_stored(self):
        r = self._d().detect("file.txt", "text/plain", size_bytes=1024)
        assert r.size_bytes == 1024
    def test_extension_property(self):
        r = self._d().detect("notes.txt", "text/plain")
        assert r.extension == "txt"

class TestDocumentContext:
    def test_is_readable_true(self):
        ctx = DocumentContext(filename="f.txt", file_type="txt", content="hello")
        assert ctx.is_readable
    def test_is_readable_false_on_error(self):
        ctx = DocumentContext(filename="f.txt", file_type="txt", content="", error="oops")
        assert not ctx.is_readable
    def test_to_prompt_context_includes_filename(self):
        ctx = DocumentContext(filename="notes.txt", file_type="txt", content="Hello world")
        prompt = ctx.to_prompt_context()
        assert "notes.txt" in prompt
        assert "Hello world" in prompt
    def test_to_prompt_context_shows_error(self):
        ctx = DocumentContext(filename="bad.pdf", file_type="pdf", content="", error="no reader")
        prompt = ctx.to_prompt_context()
        assert "no reader" in prompt
    def test_truncation_flag_in_prompt(self):
        ctx = DocumentContext(filename="f.txt", file_type="txt", content="x", truncated=True)
        prompt = ctx.to_prompt_context()
        assert "truncated" in prompt

class TestTextReader:
    def test_can_read_txt(self):
        detected = FileTypeDetector().detect("notes.txt", "text/plain")
        assert TextReader().can_read(detected)
    def test_reads_content(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("Hello Jarvis", encoding="utf-8")
        detected = FileTypeDetector().detect("notes.txt", "text/plain")
        ctx = TextReader().read(f, detected)
        assert ctx.is_readable
        assert "Hello Jarvis" in ctx.content
        assert ctx.word_count == 2
    def test_error_on_missing_file(self):
        detected = FileTypeDetector().detect("missing.txt", "text/plain")
        ctx = TextReader().read(Path("/nonexistent/missing.txt"), detected)
        assert not ctx.is_readable
        assert ctx.error is not None

class TestCodeReader:
    def test_can_read_py(self):
        detected = FileTypeDetector().detect("agent.py", "text/x-python")
        assert CodeReader().can_read(detected)
    def test_reads_python_file(self, tmp_path):
        f = tmp_path / "agent.py"
        f.write_text("def hello():\n    return 42\n", encoding="utf-8")
        detected = FileTypeDetector().detect("agent.py", "text/x-python")
        ctx = CodeReader().read(f, detected)
        assert ctx.is_readable
        assert "def hello" in ctx.content
        assert ctx.metadata.get("line_count") == 2

class TestImageReader:
    def test_can_read_png(self):
        detected = FileTypeDetector().detect("photo.png", "image/png")
        assert ImageReader().can_read(detected)
    def test_image_returns_placeholder(self, tmp_path):
        f = tmp_path / "photo.png"
        f.write_bytes(b"fake_png_bytes")
        detected = FileTypeDetector().detect("photo.png", "image/png")
        ctx = ImageReader().read(f, detected)
        assert ctx.is_readable
        assert ctx.metadata.get("vision_ready") is True

class TestDocumentReaderRegistry:
    def test_returns_text_reader_for_txt(self):
        detected = FileTypeDetector().detect("notes.txt", "text/plain")
        reader = DocumentReaderRegistry().get_reader(detected)
        assert isinstance(reader, TextReader)
    def test_returns_code_reader_for_py(self):
        detected = FileTypeDetector().detect("agent.py", "text/x-python")
        reader = DocumentReaderRegistry().get_reader(detected)
        assert isinstance(reader, CodeReader)
    def test_returns_image_reader_for_png(self):
        detected = FileTypeDetector().detect("photo.png", "image/png")
        reader = DocumentReaderRegistry().get_reader(detected)
        assert isinstance(reader, ImageReader)
    def test_returns_fallback_for_unknown(self):
        detected = FileTypeDetector().detect("weird.xyz", "")
        reader = DocumentReaderRegistry().get_reader(detected)
        assert isinstance(reader, FallbackReader)

class TestDocumentIntake:
    def test_process_txt_file(self, tmp_path, monkeypatch):
        intake = DocumentIntake()
        monkeypatch.setattr(intake, "upload_root", tmp_path)
        result = intake.process(b"Hello Jarvis", "notes.txt", "text/plain")
        assert result.upload_id
        assert result.detected.file_type.value == "txt"
        assert result.context.is_readable
        assert "Hello Jarvis" in result.context.content
    def test_process_py_file(self, tmp_path, monkeypatch):
        intake = DocumentIntake()
        monkeypatch.setattr(intake, "upload_root", tmp_path)
        result = intake.process(b"def hello(): return 42", "agent.py", "text/x-python")
        assert result.detected.file_type.value == "py"
        assert result.context.is_readable
    def test_process_image_file(self, tmp_path, monkeypatch):
        intake = DocumentIntake()
        monkeypatch.setattr(intake, "upload_root", tmp_path)
        result = intake.process(b"fake_png", "photo.png", "image/png")
        assert result.detected.is_image
        assert result.context.is_readable
        assert result.context.metadata.get("vision_ready") is True
    def test_process_stores_file(self, tmp_path, monkeypatch):
        intake = DocumentIntake()
        monkeypatch.setattr(intake, "upload_root", tmp_path)
        result = intake.process(b"test content", "test.txt", "text/plain")
        assert result.stored_at.exists()
    def test_process_rejects_oversized_file(self, tmp_path, monkeypatch):
        intake = DocumentIntake()
        monkeypatch.setattr(intake, "upload_root", tmp_path)
        big = b"x" * (21 * 1024 * 1024)
        with pytest.raises(ValueError, match="too large"):
            intake.process(big, "huge.txt", "text/plain")
    def test_to_dict_has_required_keys(self, tmp_path, monkeypatch):
        intake = DocumentIntake()
        monkeypatch.setattr(intake, "upload_root", tmp_path)
        result = intake.process(b"data", "data.txt", "text/plain")
        d = result.to_dict()
        for key in ("upload_id", "filename", "detected_type", "readable"):
            assert key in d