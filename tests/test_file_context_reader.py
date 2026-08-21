"""
Genesis-053 Sprint-004 ? FileContextReader Tests

Covers:
  - Successful file read
  - Missing file excluded (no crash)
  - Per-file size limit enforced
  - Total context size limit enforced
  - Absolute path rejected
  - Path traversal (..) rejected
  - Path escaping repo root rejected
  - Empty hints list returns empty dict
  - Malformed/nonexistent hints excluded gracefully
  - Hint extraction from natural language request
  - Hint extraction deduplication
  - Context dict keys are relative paths
"""

from __future__ import annotations
import pathlib
import pytest


def _make_reader(tmp_path):
    from core.engineering.context.file_context_reader import FileContextReader
    return FileContextReader(str(tmp_path))


def _write(tmp_path, rel: str, content: str) -> pathlib.Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestFileContextReaderSuccessfulRead:

    def test_reads_existing_file(self, tmp_path):
        _write(tmp_path, "core/health.py", "def health(): return {'status': 'ok'}")
        result = _make_reader(tmp_path).read(["core/health.py"])
        assert "core/health.py" in result
        assert "health" in result["core/health.py"]

    def test_reads_multiple_files(self, tmp_path):
        _write(tmp_path, "core/a.py", "# a")
        _write(tmp_path, "core/b.py", "# b")
        result = _make_reader(tmp_path).read(["core/a.py", "core/b.py"])
        assert "core/a.py" in result
        assert "core/b.py" in result

    def test_keys_are_relative_paths(self, tmp_path):
        _write(tmp_path, "core/health.py", "# health")
        result = _make_reader(tmp_path).read(["core/health.py"])
        for key in result:
            assert not pathlib.Path(key).is_absolute()

    def test_content_matches_file(self, tmp_path):
        _write(tmp_path, "core/health.py", "SENTINEL_VALUE_XYZ")
        result = _make_reader(tmp_path).read(["core/health.py"])
        assert "SENTINEL_VALUE_XYZ" in result["core/health.py"]


class TestFileContextReaderMissingFiles:

    def test_missing_file_excluded(self, tmp_path):
        result = _make_reader(tmp_path).read(["core/does_not_exist.py"])
        assert "core/does_not_exist.py" not in result

    def test_missing_file_does_not_crash(self, tmp_path):
        result = _make_reader(tmp_path).read(["core/missing.py"])
        assert isinstance(result, dict)

    def test_mix_of_existing_and_missing(self, tmp_path):
        _write(tmp_path, "core/exists.py", "# exists")
        result = _make_reader(tmp_path).read(["core/exists.py", "core/missing.py"])
        assert "core/exists.py" in result
        assert "core/missing.py" not in result

    def test_empty_hints_returns_empty_dict(self, tmp_path):
        result = _make_reader(tmp_path).read([])
        assert result == {}


class TestFileContextReaderPerFileSizeLimit:

    def test_file_within_limit_is_read(self, tmp_path):
        from core.engineering.context.file_context_reader import FILE_SIZE_LIMIT_BYTES
        _write(tmp_path, "core/small.py", "x" * (FILE_SIZE_LIMIT_BYTES - 100))
        result = _make_reader(tmp_path).read(["core/small.py"])
        assert "core/small.py" in result

    def test_file_exceeding_limit_is_excluded(self, tmp_path):
        from core.engineering.context.file_context_reader import FILE_SIZE_LIMIT_BYTES
        _write(tmp_path, "core/huge.py", "x" * (FILE_SIZE_LIMIT_BYTES + 1))
        result = _make_reader(tmp_path).read(["core/huge.py"])
        assert "core/huge.py" not in result

    def test_large_excluded_small_included(self, tmp_path):
        from core.engineering.context.file_context_reader import FILE_SIZE_LIMIT_BYTES
        _write(tmp_path, "core/huge.py", "x" * (FILE_SIZE_LIMIT_BYTES + 1))
        _write(tmp_path, "core/small.py", "# small")
        result = _make_reader(tmp_path).read(["core/huge.py", "core/small.py"])
        assert "core/huge.py" not in result
        assert "core/small.py" in result


class TestFileContextReaderTotalSizeLimit:

    def test_stops_when_total_limit_reached(self, tmp_path):
        from core.engineering.context.file_context_reader import FILE_SIZE_LIMIT_BYTES, TOTAL_SIZE_LIMIT_BYTES
        chunk = "x" * (FILE_SIZE_LIMIT_BYTES - 100)
        files = []
        for i in range(10):
            name = f"core/file_{i}.py"
            _write(tmp_path, name, chunk)
            files.append(name)
        result = _make_reader(tmp_path).read(files)
        assert len(result) < 10

    def test_first_files_included_when_limit_hit(self, tmp_path):
        from core.engineering.context.file_context_reader import FILE_SIZE_LIMIT_BYTES
        chunk = "x" * (FILE_SIZE_LIMIT_BYTES - 100)
        files = []
        for i in range(10):
            name = f"core/file_{i}.py"
            _write(tmp_path, name, chunk)
            files.append(name)
        result = _make_reader(tmp_path).read(files)
        assert "core/file_0.py" in result


class TestFileContextReaderSecurity:

    def test_absolute_path_rejected(self, tmp_path):
        abs_path = str(tmp_path / "core" / "health.py")
        result = _make_reader(tmp_path).read([abs_path])
        assert len(result) == 0

    def test_traversal_path_rejected(self, tmp_path):
        result = _make_reader(tmp_path).read(["../../../etc/passwd"])
        assert len(result) == 0

    def test_traversal_in_subpath_rejected(self, tmp_path):
        result = _make_reader(tmp_path).read(["core/../../../etc/passwd"])
        assert len(result) == 0

    def test_valid_nested_path_accepted(self, tmp_path):
        _write(tmp_path, "core/engineering/coordinator/coordinator.py", "# coord")
        result = _make_reader(tmp_path).read(["core/engineering/coordinator/coordinator.py"])
        assert "core/engineering/coordinator/coordinator.py" in result


class TestFileContextReaderHintExtraction:

    def test_extracts_python_file_path(self):
        from core.engineering.context.file_context_reader import FileContextReader
        hints = FileContextReader.extract_file_hints(
            "Add a comment to core/health.py describing what it does"
        )
        assert "core/health.py" in hints

    def test_extracts_multiple_paths(self):
        from core.engineering.context.file_context_reader import FileContextReader
        hints = FileContextReader.extract_file_hints(
            "Modify core/agent.py and update tests/test_agent.py"
        )
        assert "core/agent.py" in hints
        assert "tests/test_agent.py" in hints

    def test_deduplicates_hints(self):
        from core.engineering.context.file_context_reader import FileContextReader
        hints = FileContextReader.extract_file_hints(
            "Update core/health.py - see core/health.py for context"
        )
        assert hints.count("core/health.py") == 1

    def test_no_paths_returns_list(self):
        from core.engineering.context.file_context_reader import FileContextReader
        hints = FileContextReader.extract_file_hints(
            "Add a comment describing what the health module does"
        )
        assert isinstance(hints, list)

    def test_extracts_nested_path(self):
        from core.engineering.context.file_context_reader import FileContextReader
        hints = FileContextReader.extract_file_hints(
            "Update core/engineering/coordinator/coordinator.py"
        )
        assert "core/engineering/coordinator/coordinator.py" in hints
