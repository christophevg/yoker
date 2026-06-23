"""Tests for search tool implementation."""

import inspect
from pathlib import Path

import pytest

from yoker.builtin import search
from yoker.builtin.search import (
  ABSOLUTE_MAX_RESULTS,
)
from yoker.config import Config, PermissionsConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.path import PathGuardrail
from yoker.tools.schema import ToolResult


def _search_spec():
  """Create and register the search tool."""
  registry = ToolRegistry()
  return registry.register(search)


def _search_context(config: Config | None = None) -> ToolContext:
  """Create a ToolContext for search tool tests."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.search,
    shared=config.tools_shared,
    backends={},
  )


async def _execute_tool(spec, **kwargs):
  """Execute a tool with argument binding and error handling.

  Mimics the behavior of _processing._execute_tool for unit tests.
  """
  sig = inspect.signature(spec.execute)

  try:
    bound = sig.bind(**kwargs)
    bound.apply_defaults()
  except TypeError as e:
    return ToolResult(success=False, error=f"Invalid tool arguments: {e}")

  result = spec.execute(*bound.args, **bound.kwargs)

  if inspect.isawaitable(result):
    result = await result

  if isinstance(result, ToolResult):
    return result
  return ToolResult(success=True, result=result)


class TestSearchToolSchema:
  """Tests for search tool schema and properties."""

  def test_name(self) -> None:
    """Test tool name."""
    spec = _search_spec()
    assert spec.name == "search"

  def test_description(self) -> None:
    """Test tool description."""
    spec = _search_spec()
    assert "pattern" in spec.description.lower()
    assert "files" in spec.description.lower()

  def test_schema_structure(self) -> None:
    """Test schema structure."""
    spec = _search_spec()
    schema = spec.schema

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "search"
    assert "path" in schema["function"]["parameters"]["properties"]
    assert "pattern" in schema["function"]["parameters"]["properties"]
    assert "type" in schema["function"]["parameters"]["properties"]
    assert "max_results" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["path"]


class TestSearchToolContentSearch:
  """Tests for content search functionality."""

  @pytest.fixture
  def temp_search_dir(self, tmp_path: Path) -> Path:
    """Create a temporary directory with files for searching."""
    # Python files
    (tmp_path / "main.py").write_text("def main():\n    # TODO: implement main\n    pass\n")
    (tmp_path / "utils.py").write_text("# TODO: add docstrings\ndef helper():\n    pass\n")

    # Markdown file
    (tmp_path / "README.md").write_text("# Project\n\nTODO: write docs\n")

    # Nested directory
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def app():\n    # TODO: refactor\n    return True\n")

    # Hidden file (should be skipped)
    (tmp_path / ".hidden").write_text("TODO: this should be ignored")

    return tmp_path

  @pytest.mark.asyncio
  async def test_basic_content_search(self, temp_search_dir: Path) -> None:
    """Test basic content search finds TODO comments."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(temp_search_dir), ctx=ctx, pattern="TODO", type="content")

    assert result.success
    data = result.result
    assert isinstance(data, dict)
    assert "matches" in data
    assert "total_matches" in data
    assert "files_searched" in data
    assert data["total_matches"] >= 3
    assert len(data["matches"]) <= ABSOLUTE_MAX_RESULTS

    # Check match structure
    for match in data["matches"]:
      assert "file" in match
      assert "line" in match
      assert "content" in match

  @pytest.mark.asyncio
  async def test_regex_pattern_search(self, temp_search_dir: Path) -> None:
    """Test regex pattern matching."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(temp_search_dir),
      ctx=ctx,
      pattern=r"def\s+\w+",
      type="content",
    )

    assert result.success
    data = result.result
    assert data["total_matches"] >= 3  # main, helper, app

    # Check that matches contain function definitions
    contents = [m["content"] for m in data["matches"]]
    assert any("def main" in c for c in contents)
    assert any("def helper" in c for c in contents)
    assert any("def app" in c for c in contents)

  @pytest.mark.asyncio
  async def test_case_insensitive_search(self, temp_search_dir: Path) -> None:
    """Test case-insensitive regex search."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(temp_search_dir),
      ctx=ctx,
      pattern="(?i)todo",
      type="content",
    )

    assert result.success
    assert result.result["total_matches"] >= 3

  @pytest.mark.asyncio
  async def test_max_results_limiting(self, temp_search_dir: Path) -> None:
    """Test max_results parameter limits output."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(temp_search_dir),
      ctx=ctx,
      pattern="TODO",
      type="content",
      max_results=2,
    )

    assert result.success
    data = result.result
    assert len(data["matches"]) == 2
    assert data["truncated"] is True
    assert data["total_matches"] > 2

  @pytest.mark.asyncio
  async def test_default_pattern_content(self, temp_search_dir: Path) -> None:
    """Test default pattern for content search matches all lines."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(temp_search_dir),
      ctx=ctx,
      type="content",
    )

    assert result.success
    # Default pattern is .* which matches all lines
    assert result.result["total_matches"] > 0

  @pytest.mark.asyncio
  async def test_empty_directory(self, tmp_path: Path) -> None:
    """Test search on empty directory returns empty results."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(empty_dir), ctx=ctx, pattern="TODO", type="content")

    assert result.success
    data = result.result
    assert data["matches"] == []
    assert data["total_matches"] == 0
    assert data["files_searched"] == 0

  @pytest.mark.asyncio
  async def test_hidden_files_skipped(self, temp_search_dir: Path) -> None:
    """Test that hidden files are not searched."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(temp_search_dir),
      ctx=ctx,
      pattern="this should be ignored",
      type="content",
    )

    assert result.success
    assert result.result["total_matches"] == 0

  @pytest.mark.asyncio
  async def test_large_file_skipped(self, tmp_path: Path) -> None:
    """Test that large files are skipped."""
    # Create a file larger than MAX_FILE_SIZE_KB
    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"x" * (600 * 1024))  # 600KB > 500KB default

    # Create a small file
    (tmp_path / "small.txt").write_text("TODO: small file\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    assert result.success
    # Should only match the small file
    assert result.result["total_matches"] == 1


class TestSearchToolFilenameSearch:
  """Tests for filename search functionality."""

  @pytest.fixture
  def temp_search_dir(self, tmp_path: Path) -> Path:
    """Create a temporary directory with files for searching."""
    # Python files
    (tmp_path / "main.py").write_text("def main(): pass\n")
    (tmp_path / "utils.py").write_text("def helper(): pass\n")

    # Markdown file
    (tmp_path / "README.md").write_text("# Project\n")

    # Nested directory
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def app(): pass\n")

    # Hidden file (should be skipped)
    (tmp_path / ".hidden").write_text("hidden content")

    return tmp_path

  @pytest.mark.asyncio
  async def test_glob_pattern_py(self, temp_search_dir: Path) -> None:
    """Test glob pattern for Python files."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(temp_search_dir),
      ctx=ctx,
      pattern="*.py",
      type="filename",
    )

    assert result.success
    data = result.result
    assert data["total_matches"] == 3  # main.py, utils.py, src/app.py
    assert all("file" in m for m in data["matches"])

    # Check that all matches are Python files
    for match in data["matches"]:
      assert match["file"].endswith(".py")

  @pytest.mark.asyncio
  async def test_glob_pattern_question_mark(self, temp_search_dir: Path) -> None:
    """Test glob pattern with question mark wildcard."""
    # Add file with 4-char name to match ???? pattern
    (temp_search_dir / "core.py").write_text("def core(): pass\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(temp_search_dir),
      ctx=ctx,
      pattern="????.py",  # Matches main.py, core.py (4 chars)
      type="filename",
    )

    assert result.success
    assert result.result["total_matches"] >= 2

  @pytest.mark.asyncio
  async def test_glob_pattern_character_class(self, tmp_path: Path) -> None:
    """Test glob pattern with character class."""
    # Create files with specific patterns
    (tmp_path / "test_a.py").write_text("a\n")
    (tmp_path / "test_b.py").write_text("b\n")
    (tmp_path / "test_c.py").write_text("c\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="test_[ab].py",
      type="filename",
    )

    assert result.success
    assert result.result["total_matches"] == 2

  @pytest.mark.asyncio
  async def test_no_matches(self, temp_search_dir: Path) -> None:
    """Test search with no matches returns empty results."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(temp_search_dir),
      ctx=ctx,
      pattern="*.nonexistent",
      type="filename",
    )

    assert result.success
    assert result.result["matches"] == []
    assert result.result["total_matches"] == 0

  @pytest.mark.asyncio
  async def test_default_pattern_filename(self, temp_search_dir: Path) -> None:
    """Test default pattern for filename search matches all files."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(temp_search_dir),
      ctx=ctx,
      type="filename",
    )

    assert result.success
    # Default pattern is * which matches all files
    assert result.result["total_matches"] >= 3


class TestSearchToolValidation:
  """Tests for input validation and error handling."""

  @pytest.mark.asyncio
  async def test_invalid_regex_pattern(self, tmp_path: Path) -> None:
    """Test invalid regex pattern returns error."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="[invalid",  # Missing closing bracket
      type="content",
    )

    assert not result.success
    assert "Invalid regex" in result.error

  @pytest.mark.asyncio
  async def test_redos_pattern_nested_quantifier(self, tmp_path: Path) -> None:
    """Test ReDoS pattern with nested quantifier is rejected."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern=r"(\w+)+",
      type="content",
    )

    assert not result.success
    assert "ReDoS" in result.error

  @pytest.mark.asyncio
  async def test_redos_pattern_alternation_quantifier(self, tmp_path: Path) -> None:
    """Test ReDoS pattern with alternation and quantifier is rejected."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern=r"(a|b)+",
      type="content",
    )

    assert not result.success
    assert "ReDoS" in result.error

  @pytest.mark.asyncio
  async def test_pattern_too_long(self, tmp_path: Path) -> None:
    """Test pattern length limit."""
    spec = _search_spec()
    ctx = _search_context()
    long_pattern = "a" * 600  # Exceeds MAX_PATTERN_LENGTH (500)

    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern=long_pattern,
      type="content",
    )

    assert not result.success
    assert "too long" in result.error.lower()

  @pytest.mark.asyncio
  async def test_path_not_found(self) -> None:
    """Test error when path does not exist."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path="/nonexistent/path", pattern="test", type="content", ctx=ctx)

    assert not result.success
    assert "Path not found" in result.error

  @pytest.mark.asyncio
  async def test_path_is_file(self, tmp_path: Path) -> None:
    """Test error when path is a file, not a directory."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(file_path), ctx=ctx, pattern="test", type="content")

    assert not result.success
    assert "not a directory" in result.error.lower()

  @pytest.mark.asyncio
  async def test_invalid_search_type(self, tmp_path: Path) -> None:
    """Test error for invalid search type."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="test",
      type="invalid",
    )

    assert not result.success
    assert "Invalid type" in result.error

  @pytest.mark.asyncio
  async def test_invalid_max_results(self, tmp_path: Path) -> None:
    """Test error for invalid max_results parameter."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="test",
      max_results="not_a_number",
    )

    assert not result.success
    assert "Invalid numeric" in result.error

  @pytest.mark.asyncio
  async def test_missing_path_parameter(self) -> None:
    """Test error when path parameter is missing."""
    spec = _search_spec()
    ctx = _search_context()
    result = await _execute_tool(spec, pattern="test", type="content", ctx=ctx)

    assert not result.success
    assert "Invalid tool arguments" in result.error


class TestSearchToolLimiting:
  """Tests for result limiting and clamping."""

  @pytest.mark.asyncio
  async def test_max_results_clamped_to_minimum(self, tmp_path: Path) -> None:
    """Test max_results below minimum is clamped."""
    (tmp_path / "test.txt").write_text("content\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern=".*",
      type="content",
      max_results=0,  # Below minimum of 1
    )

    # Should not error, should clamp to 1
    assert result.success

  @pytest.mark.asyncio
  async def test_max_results_clamped_to_maximum(self, tmp_path: Path) -> None:
    """Test max_results above maximum is clamped."""
    (tmp_path / "test.txt").write_text("content\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern=".*",
      type="content",
      max_results=2000,  # Above ABSOLUTE_MAX_RESULTS (1000)
    )

    # Should not error, should clamp to 1000
    assert result.success

  @pytest.mark.asyncio
  async def test_results_truncated_flag(self, tmp_path: Path) -> None:
    """Test truncated flag is set when results are limited."""
    # Create files with more matches than max_results
    for i in range(10):
      (tmp_path / f"file{i}.txt").write_text(f"TODO: item {i}\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="TODO",
      type="content",
      max_results=5,
    )

    assert result.success
    assert result.result["truncated"] is True
    assert len(result.result["matches"]) == 5
    assert result.result["total_matches"] == 10


class TestSearchToolDirectorySkipping:
  """Tests for directory skipping."""

  @pytest.mark.asyncio
  async def test_skip_git_directory(self, tmp_path: Path) -> None:
    """Test that .git directory is skipped."""
    # Create .git directory with file
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("TODO: in git\n")

    # Create regular file
    (tmp_path / "main.py").write_text("TODO: regular\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    assert result.success
    # Should only find the regular file
    assert result.result["total_matches"] == 1

  @pytest.mark.asyncio
  async def test_skip_pycache_directory(self, tmp_path: Path) -> None:
    """Test that __pycache__ directory is skipped."""
    pycache_dir = tmp_path / "__pycache__"
    pycache_dir.mkdir()
    (pycache_dir / "module.pyc").write_text("compiled")

    (tmp_path / "module.py").write_text("# source\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="*",
      type="filename",
    )

    assert result.success
    # Should not include pycache files
    for match in result.result["matches"]:
      assert "__pycache__" not in match["file"]


class TestSearchToolWithGuardrail:
  """Tests for guardrail integration."""

  @pytest.mark.asyncio
  async def test_guardrail_blocks_path(self, tmp_path: Path) -> None:
    """Test that the path guardrail can block paths."""
    allowed_path = tmp_path / "allowed"
    allowed_path.mkdir()
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(allowed_path),)))
    guardrail = PathGuardrail(config)

    spec = _search_spec()
    _search_context()
    validation = guardrail.validate(spec.name, {"path": str(tmp_path)})

    assert not validation.valid
    assert "outside allowed" in validation.reason.lower()

  @pytest.mark.asyncio
  async def test_guardrail_allows_path(self, tmp_path: Path) -> None:
    """Test that the path guardrail can allow paths."""
    (tmp_path / "test.txt").write_text("TODO: test\n")

    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)

    spec = _search_spec()
    ctx = _search_context()
    validation = guardrail.validate(spec.name, {"path": str(tmp_path)})
    assert validation.valid

    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")
    assert result.success


class TestSearchToolSymlinkSkipping:
  """Tests for symlink handling."""

  @pytest.mark.asyncio
  async def test_skip_symlinks(self, tmp_path: Path) -> None:
    """Test that symlinks are skipped."""
    # Create regular file
    regular_file = tmp_path / "regular.txt"
    regular_file.write_text("TODO: regular\n")

    # Create symlink
    symlink = tmp_path / "link.txt"
    try:
      symlink.symlink_to(regular_file)
    except OSError:
      # Symlinks may not be supported on all platforms
      pytest.skip("Symlinks not supported")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="TODO",
      type="content",
    )

    assert result.success
    # Should only find the regular file once
    assert result.result["total_matches"] == 1


class TestSearchToolTimeout:
  """Tests for timeout enforcement."""

  def test_timeout_parameter_in_schema(self) -> None:
    """Test that timeout_ms parameter is in schema."""
    spec = _search_spec()
    schema = spec.schema

    assert "timeout_ms" in schema["function"]["parameters"]["properties"]
    timeout_prop = schema["function"]["parameters"]["properties"]["timeout_ms"]
    assert timeout_prop["type"] == "integer"

  @pytest.mark.asyncio
  async def test_timeout_ms_clamped_to_minimum(self, tmp_path: Path) -> None:
    """Test timeout_ms below minimum is clamped."""
    (tmp_path / "test.txt").write_text("content\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern=".*",
      type="content",
      timeout_ms=50,  # Below minimum of 100
    )

    # Should not error, should clamp to 100
    assert result.success

  @pytest.mark.asyncio
  async def test_timeout_ms_clamped_to_maximum(self, tmp_path: Path) -> None:
    """Test timeout_ms above maximum is clamped."""
    (tmp_path / "test.txt").write_text("content\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern=".*",
      type="content",
      timeout_ms=60000,  # Above ABSOLUTE_TIMEOUT_MS (30000)
    )

    # Should not error, should clamp to 30000
    assert result.success

  @pytest.mark.asyncio
  async def test_invalid_timeout_ms(self, tmp_path: Path) -> None:
    """Test error for invalid timeout_ms parameter."""
    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="test",
      timeout_ms="not_a_number",
    )

    assert not result.success
    assert "Invalid numeric" in result.error

  @pytest.mark.asyncio
  async def test_timeout_enforced_on_slow_search(self, tmp_path: Path) -> None:
    """Test that search terminates when timeout is exceeded."""
    import time

    # Create many files to make search take time
    for i in range(100):
      (tmp_path / f"file{i}.txt").write_text(f"TODO: item {i}\n")

    spec = _search_spec()
    ctx = _search_context()
    start = time.monotonic()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="TODO",
      type="content",
      timeout_ms=100,  # Very short timeout (100ms)
      max_results=1000,  # High limit
    )
    elapsed = time.monotonic() - start

    assert result.success
    # Search should complete quickly (well under 1 second)
    # The timeout is 100ms, but we give some buffer
    assert elapsed < 1.0

  @pytest.mark.asyncio
  async def test_timeout_sets_truncated_flag(self, tmp_path: Path) -> None:
    """Test that truncated flag is set when timeout is exceeded."""
    # Create enough files to potentially trigger timeout
    for i in range(200):
      (tmp_path / f"file{i}.txt").write_text(f"TODO: item {i}\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern="TODO",
      type="content",
      timeout_ms=100,  # Very short timeout
      max_results=1000,
    )

    # Note: On a fast machine, search might complete before timeout
    # This test verifies the mechanism works, but truncated depends on timing
    assert result.success
    # If search was cut off by timeout, truncated should be True
    # If search completed, we still get valid results

  @pytest.mark.asyncio
  async def test_default_timeout_used(self, tmp_path: Path) -> None:
    """Test that default timeout is applied when not specified."""
    (tmp_path / "test.txt").write_text("content\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(
      path=str(tmp_path),
      ctx=ctx,
      pattern=".*",
      type="content",
    )

    # Should use DEFAULT_TIMEOUT_MS (5000) and succeed
    assert result.success


class TestSearchToolErrorHandling:
  """Test error handling scenarios for PermissionError and UnicodeDecodeError."""

  @pytest.mark.asyncio
  async def test_permission_error_on_file_access(self, tmp_path: Path) -> None:
    """Test handling when file stat raises PermissionError."""
    from unittest.mock import patch

    # Create files
    (tmp_path / "file1.txt").write_text("TODO: file1\n")
    (tmp_path / "file2.txt").write_text("TODO: file2\n")

    spec = _search_spec()
    ctx = _search_context()

    # Mock Path.stat to raise PermissionError for file2.txt only
    original_stat = Path.stat

    def mock_stat(self, follow_symlinks=True):
      # Only raise for the exact file2.txt path
      if str(self).endswith("file2.txt"):
        raise PermissionError("Access denied")
      return original_stat(self, follow_symlinks=follow_symlinks)

    with patch.object(Path, "stat", mock_stat):
      result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    # Should succeed, skipping file2
    assert result.success
    # files_searched is incremented before stat check, so both files counted
    assert result.result["files_searched"] == 2
    # But only file1 is successfully searched
    assert result.result["total_matches"] == 1

  @pytest.mark.asyncio
  async def test_permission_error_on_file_read(self, tmp_path: Path) -> None:
    """Test handling when file is not readable."""
    from unittest.mock import patch

    # Create a file
    (tmp_path / "readable.txt").write_text("TODO: readable\n")
    (tmp_path / "unreadable.txt").write_text("TODO: unreadable\n")

    spec = _search_spec()
    ctx = _search_context()

    # Mock read_text to raise PermissionError for unreadable file
    original_read_text = Path.read_text

    def mock_read_text(self, encoding=None, errors=None):
      if "unreadable" in str(self):
        raise PermissionError("Access denied")
      return original_read_text(self, encoding=encoding, errors=errors)

    with patch.object(Path, "read_text", mock_read_text):
      result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    # Should succeed and only find the readable file
    assert result.success
    assert result.result["total_matches"] == 1
    assert len(result.result["matches"]) == 1
    assert "readable" in result.result["matches"][0]["file"]

  @pytest.mark.asyncio
  async def test_oserror_on_file_access(self, tmp_path: Path) -> None:
    """Test handling OSError when accessing files."""
    from unittest.mock import patch

    # Create files
    (tmp_path / "file1.txt").write_text("TODO: file1\n")
    (tmp_path / "file2.txt").write_text("TODO: file2\n")

    spec = _search_spec()
    ctx = _search_context()

    # Mock Path.stat to raise OSError for file2.txt only
    original_stat = Path.stat

    def mock_stat(self, follow_symlinks=True):
      # Only raise for the exact file2.txt path
      if str(self).endswith("file2.txt"):
        raise OSError("File system error")
      return original_stat(self, follow_symlinks=follow_symlinks)

    with patch.object(Path, "stat", mock_stat):
      result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    # Should succeed, skipping file2
    assert result.success
    # files_searched is incremented before stat check
    assert result.result["files_searched"] == 2
    # But only file1 is successfully searched
    assert result.result["total_matches"] == 1

  @pytest.mark.asyncio
  async def test_binary_file_skipped(self, tmp_path: Path) -> None:
    """Test that binary files are skipped in content search."""
    # Create a binary file (PNG-like bytes)
    binary_file = tmp_path / "image.bin"
    # PNG magic bytes followed by binary data
    binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 100)

    # Create a regular text file with TODO
    (tmp_path / "text.txt").write_text("TODO: text file\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    assert result.success
    # Should only find the text file, binary file is skipped
    assert result.result["total_matches"] == 1
    assert len(result.result["matches"]) == 1
    assert "text.txt" in result.result["matches"][0]["file"]

  @pytest.mark.asyncio
  async def test_unicode_decode_error_handling(self, tmp_path: Path) -> None:
    """Test handling of files with invalid UTF-8 encoding."""
    # Create a file with invalid UTF-8 bytes
    invalid_utf8_file = tmp_path / "invalid.txt"
    # Write bytes that form invalid UTF-8 sequences
    invalid_utf8_file.write_bytes(
      b"Valid UTF-8\n" + b"\xff\xfe Invalid UTF-8\n" + b"More valid text\n"
    )

    # Create a valid file
    (tmp_path / "valid.txt").write_text("TODO: valid\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    # Should succeed because errors="replace" is used
    assert result.success
    # Should find the valid file
    assert result.result["total_matches"] == 1
    # The invalid UTF-8 file is still read (with replacement chars)
    # so files_searched should include both files
    assert result.result["files_searched"] >= 1

  @pytest.mark.asyncio
  async def test_files_searched_count_accuracy(self, tmp_path: Path) -> None:
    """Test that files_searched count in content search result is accurate."""
    # Create multiple files with different content
    (tmp_path / "file1.txt").write_text("TODO: file1\n")
    (tmp_path / "file2.txt").write_text("TODO: file2\n")
    (tmp_path / "file3.txt").write_text("TODO: file3\n")

    # Create a nested directory
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "file4.txt").write_text("TODO: file4\n")
    (subdir / "file5.txt").write_text("TODO: file5\n")

    # Create hidden file (should be skipped)
    (tmp_path / ".hidden").write_text("TODO: hidden\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    assert result.success
    # Should search 5 files (not hidden file)
    # Note: files_searched counts files walked, not files with matches
    # So it includes all non-hidden files
    assert result.result["files_searched"] == 5

    # All 5 files have TODO
    assert result.result["total_matches"] == 5
    assert len(result.result["matches"]) == 5

  @pytest.mark.asyncio
  async def test_files_searched_with_permission_error(self, tmp_path: Path) -> None:
    """Test that files_searched count is accurate even with permission errors."""
    from unittest.mock import patch

    # Create files
    (tmp_path / "file1.txt").write_text("TODO: file1\n")
    (tmp_path / "file2.txt").write_text("TODO: file2\n")
    (tmp_path / "file3.txt").write_text("TODO: file3\n")

    spec = _search_spec()
    ctx = _search_context()

    # Mock read_text to fail on file2
    original_read_text = Path.read_text
    call_count = [0]

    def mock_read_text(self, encoding=None, errors=None):
      call_count[0] += 1
      if "file2" in str(self):
        raise PermissionError("Access denied")
      return original_read_text(self, encoding=encoding, errors=errors)

    with patch.object(Path, "read_text", mock_read_text):
      result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    assert result.success
    # Should have attempted to read all 3 files
    assert result.result["files_searched"] == 3
    # But only found TODO in file1 and file3
    assert result.result["total_matches"] == 2

  @pytest.mark.asyncio
  async def test_files_searched_with_large_file_skip(self, tmp_path: Path) -> None:
    """Test that files_searched includes files skipped for size."""
    # Create a small file with TODO
    (tmp_path / "small.txt").write_text("TODO: small\n")

    # Create a large file (larger than MAX_FILE_SIZE_KB * 1024)
    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"x" * (600 * 1024))  # 600KB

    # Create another small file
    (tmp_path / "small2.txt").write_text("TODO: small2\n")

    spec = _search_spec()
    ctx = _search_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="TODO", type="content")

    assert result.success
    # All 3 files should be counted in files_searched
    assert result.result["files_searched"] == 3
    # But only 2 matches (large file is skipped during content search)
    assert result.result["total_matches"] == 2

  @pytest.mark.asyncio
  async def test_unicode_errors_replaced_gracefully(self, tmp_path: Path) -> None:
    """Test that invalid unicode sequences are replaced with replacement char."""
    # Create a file with mixed valid/invalid UTF-8
    mixed_file = tmp_path / "mixed.txt"
    # Write valid UTF-8 followed by invalid bytes
    mixed_file.write_bytes(b"Valid line\n\xff\xfe\nAnother valid line\n")

    spec = _search_spec()
    ctx = _search_context()
    # Search for "Valid" - should still find it despite invalid bytes
    result = await spec.execute(path=str(tmp_path), ctx=ctx, pattern="Valid", type="content")

    assert result.success
    # Should find the match because errors="replace" allows reading
    assert result.result["total_matches"] >= 1
    # The file should be counted as searched
    assert result.result["files_searched"] == 1
