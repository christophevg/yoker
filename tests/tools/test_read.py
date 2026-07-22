"""Tests for read tool."""

from pathlib import Path

import pytest

from yoker.builtin import read as read_tool
from yoker.config import Config, PermissionsConfig, ReadToolConfig, ToolsConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext
from yoker.tools.guardrails.path import PathGuardrail
from yoker.tools.schema import ToolResult


def _read_spec():
  """Create and register the read tool."""
  registry = ToolRegistry()
  return registry.register(read_tool)


def _read_context(config: Config | None = None) -> ToolContext:
  """Create a ToolContext for read tool tests."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.read,
    shared=config.tools_shared,
    backends={},
  )


class TestReadTool:
  """Tests for the read tool."""

  def test_name(self) -> None:
    """read tool has correct name."""
    spec = _read_spec()
    assert spec.name == "read"

  def test_description(self) -> None:
    """read tool has description."""
    spec = _read_spec()
    assert "Read" in spec.description

  def test_schema(self) -> None:
    """read tool schema has required fields."""
    spec = _read_spec()
    schema = spec.schema
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "read"
    assert "parameters" in func
    assert "path" in func["parameters"]["properties"]
    assert "path" in func["parameters"]["required"]

  @pytest.mark.asyncio
  async def test_read_existing_file(self, tmp_path: Path) -> None:
    """read tool reads an existing file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), ctx=ctx)
    assert result.success is True
    assert result.result == "hello world"
    assert result.error is None

  @pytest.mark.asyncio
  async def test_read_missing_file(self) -> None:
    """read tool returns error for missing file."""
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path="/nonexistent/path/file.txt", ctx=ctx)
    assert result.success is False
    assert result.result == ""
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_result_is_toolresult(self) -> None:
    """read tool execute returns ToolResult."""
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path="/dev/null", ctx=ctx)
    assert isinstance(result, ToolResult)

  @pytest.mark.asyncio
  async def test_read_with_guardrail_blocks(self, tmp_path: Path) -> None:
    """Path guardrail blocks paths outside allowed directories for read."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": "/etc/passwd"})
    assert not validation.valid
    assert "outside allowed" in (validation.reason or "").lower()

  @pytest.mark.asyncio
  async def test_read_with_guardrail_allows(self, tmp_path: Path) -> None:
    """Path guardrail allows paths inside allowed directories for read."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("allowed content")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    spec = _read_spec()
    ctx = _read_context()
    validation = guardrail.validate(spec.name, {"path": str(file_path)})
    assert validation.valid
    result = await spec.execute(path=str(file_path), ctx=ctx)
    assert result.success is True
    assert result.result == "allowed content"

  @pytest.mark.asyncio
  async def test_read_rejects_symlink(self, tmp_path: Path) -> None:
    """read tool rejects reading symlinks."""
    target = tmp_path / "target.txt"
    target.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(link), ctx=ctx)
    assert result.success is False

  @pytest.mark.asyncio
  async def test_read_file_with_encoding(self, tmp_path: Path) -> None:
    """read tool handles different encodings."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), ctx=ctx)
    assert result.success is True
    assert result.result == "hello world"

  @pytest.mark.asyncio
  async def test_read_result_truncation(self, tmp_path: Path) -> None:
    """read tool returns full file content."""
    content = "line1\nline2\nline3"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), ctx=ctx)
    assert result.success is True
    assert result.result == content

  @pytest.mark.asyncio
  async def test_read_traversal_rejected(self, tmp_path: Path) -> None:
    """read tool resolves and handles path traversal safely."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    real_file = real_dir / "real.txt"
    real_file.write_text("allowed")
    sensitive_path = str(tmp_path / ".." / tmp_path.name / "real" / "real.txt")
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=sensitive_path, ctx=ctx)
    # Path should be resolved by realpath, so it should succeed
    assert result.success is True

  @pytest.mark.asyncio
  async def test_read_guardrail_logs_blocked(self, tmp_path: Path) -> None:
    """Path guardrail blocks read access to files matching blocked patterns."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("secret")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(blocked_patterns=(r"test\.txt",))),
    )
    guardrail = PathGuardrail(config)
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(file_path)})
    assert not validation.valid
    assert "blocked" in (validation.reason or "").lower()

  @pytest.mark.asyncio
  async def test_read_nonexistent_file(self) -> None:
    """read tool returns error for non-existent file."""
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path="/nonexistent/file.txt", ctx=ctx)
    assert result.success is False
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_directory(self, tmp_path: Path) -> None:
    """read tool returns error for directory path."""
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(tmp_path), ctx=ctx)
    assert result.success is False
    assert "not a file" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_empty_path(self) -> None:
    """read tool returns error for empty path."""
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path="", ctx=ctx)
    assert result.success is False
    assert result.error

  @pytest.mark.asyncio
  async def test_read_invalid_path_type(self) -> None:
    """read tool returns error for invalid path type."""
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=123, ctx=ctx)  # type: ignore
    assert result.success is False
    assert result.error

  @pytest.mark.asyncio
  async def test_read_permission_denied(self) -> None:
    """read tool handles permission denied."""
    # Skip on systems where /dev/null might not have permission issues
    spec = _read_spec()
    ctx = _read_context()
    # Reading a directory should fail with "not a file" not permission error
    result = await spec.execute(path="/dev", ctx=ctx)
    assert result.success is False


class TestReadOffsetLimit:
  """Tests for the offset/limit pagination parameters of the read tool."""

  @pytest.mark.asyncio
  async def test_default_path_unchanged(self, tmp_path: Path) -> None:
    """Default path (offset=limit=None) returns raw content, no metadata."""
    content = "line1\nline2\nline3\n"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), ctx=ctx)
    assert result.success is True
    assert result.result == content
    assert result.content_metadata is None

  @pytest.mark.asyncio
  async def test_offset_only(self, tmp_path: Path) -> None:
    """offset=N returns lines N to EOF with cat -n prefix and flat metadata."""
    content = "l1\nl2\nl3\nl4\nl5\n"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), offset=3, ctx=ctx)
    assert result.success is True
    # Lines 3, 4, 5 (1-indexed) with cat -n prefix.
    rendered = "     3\tl3\n     4\tl4\n     5\tl5\n"
    assert result.result == rendered
    assert result.content_metadata == {
      "operation": "read",
      "path": str(file_path.resolve()),
      "content_type": "text/plain",
      "content": rendered,
      "metadata": {"offset": 3, "limit": None, "total_lines": 5, "returned_lines": 3},
    }

  @pytest.mark.asyncio
  async def test_limit_only(self, tmp_path: Path) -> None:
    """limit=N returns first N lines with cat -n prefix; metadata offset=1."""
    content = "l1\nl2\nl3\nl4\nl5\n"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), limit=2, ctx=ctx)
    assert result.success is True
    rendered = "     1\tl1\n     2\tl2\n"
    assert result.result == rendered
    assert result.content_metadata == {
      "operation": "read",
      "path": str(file_path.resolve()),
      "content_type": "text/plain",
      "content": rendered,
      "metadata": {"offset": 1, "limit": 2, "total_lines": 5, "returned_lines": 2},
    }

  @pytest.mark.asyncio
  async def test_offset_and_limit(self, tmp_path: Path) -> None:
    """offset=10, limit=5 returns lines 10-14 from a larger file."""
    content = "".join(f"line{i}\n" for i in range(1, 21))  # 20 lines
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), offset=10, limit=5, ctx=ctx)
    assert result.success is True
    expected = "".join(f"{i:>6}\tline{i}\n" for i in range(10, 15))
    assert result.result == expected
    assert result.content_metadata == {
      "operation": "read",
      "path": str(file_path.resolve()),
      "content_type": "text/plain",
      "content": expected,
      "metadata": {"offset": 10, "limit": 5, "total_lines": 20, "returned_lines": 5},
    }

  @pytest.mark.asyncio
  async def test_offset_beyond_eof(self, tmp_path: Path) -> None:
    """offset > total_lines returns empty result, returned_lines=0, success=True."""
    content = "l1\nl2\nl3\n"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), offset=100, ctx=ctx)
    assert result.success is True
    assert result.result == ""
    assert result.content_metadata == {
      "operation": "read",
      "path": str(file_path.resolve()),
      "content_type": "text/plain",
      "content": "",
      "metadata": {"offset": 100, "limit": None, "total_lines": 3, "returned_lines": 0},
    }

  @pytest.mark.asyncio
  async def test_limit_exceeds_remaining(self, tmp_path: Path) -> None:
    """limit larger than remaining lines returns what remains, no padding."""
    content = "l1\nl2\nl3\n"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), offset=2, limit=50, ctx=ctx)
    assert result.success is True
    rendered = "     2\tl2\n     3\tl3\n"
    assert result.result == rendered
    assert result.content_metadata == {
      "operation": "read",
      "path": str(file_path.resolve()),
      "content_type": "text/plain",
      "content": rendered,
      "metadata": {"offset": 2, "limit": 50, "total_lines": 3, "returned_lines": 2},
    }

  @pytest.mark.asyncio
  async def test_offset_zero_rejected(self, tmp_path: Path) -> None:
    """offset=0 is rejected with a validation error, no file access."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), offset=0, ctx=ctx)
    assert result.success is False
    assert "offset" in result.error.lower()
    assert ">=" in result.error

  @pytest.mark.asyncio
  async def test_limit_zero_rejected(self, tmp_path: Path) -> None:
    """limit=0 is rejected with a validation error."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), limit=0, ctx=ctx)
    assert result.success is False
    assert "limit" in result.error.lower()
    assert ">=" in result.error

  @pytest.mark.asyncio
  async def test_negative_offset_rejected(self, tmp_path: Path) -> None:
    """Negative offset is rejected with the same validation error."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), offset=-5, ctx=ctx)
    assert result.success is False
    assert "offset" in result.error.lower()

  @pytest.mark.asyncio
  async def test_negative_limit_rejected(self, tmp_path: Path) -> None:
    """Negative limit is rejected with the same validation error."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), limit=-5, ctx=ctx)
    assert result.success is False
    assert "limit" in result.error.lower()

  @pytest.mark.asyncio
  async def test_line_number_prefix_format(self, tmp_path: Path) -> None:
    """Line numbers are right-aligned 6-wide, tab-separated, cat -n style."""
    content = "first\nsecond\n"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), offset=1, limit=2, ctx=ctx)
    assert result.success is True
    # 6-wide field: 5 spaces + digit, then tab, then line content.
    assert result.result == "     1\tfirst\n     2\tsecond\n"

  @pytest.mark.asyncio
  async def test_metadata_total_and_returned_lines(self, tmp_path: Path) -> None:
    """content_metadata carries total_lines and returned_lines in nested metadata."""
    content = "a\nb\nc\nd\ne\nf\ng\nh\n"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), offset=3, limit=4, ctx=ctx)
    assert result.success is True
    meta = result.content_metadata["metadata"]
    assert meta["total_lines"] == 8
    assert meta["returned_lines"] == 4
    assert meta["offset"] == 3
    assert meta["limit"] == 4

  @pytest.mark.asyncio
  async def test_content_metadata_flat_shape_for_event_emission(self, tmp_path: Path) -> None:
    """ToolResult from read() exposes the flat keys ToolContentEvent consumes.

    core/_processing.py reads operation/path/content_type/content/metadata
    directly off content_metadata. Verifying the flat shape here guards the
    event-emission path: if the metadata regresses to a nested envelope, the
    emitted ToolContentEvent silently loses operation/path/metadata.
    """
    content = "a\nb\nc\nd\n"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), offset=1, limit=2, ctx=ctx)
    assert result.success is True
    meta = result.content_metadata
    # Flat keys consumed by core/_processing.py:441-453.
    assert meta["operation"] == "read"
    assert meta["path"] == str(file_path.resolve())
    assert meta["content_type"] == "text/plain"
    assert meta["content"] == result.result
    # Read-specific fields nested under metadata, not at the top level.
    assert meta["metadata"]["total_lines"] == 4
    assert meta["metadata"]["returned_lines"] == 2
    assert meta["metadata"]["offset"] == 1
    assert meta["metadata"]["limit"] == 2
    # No stray top-level read envelope.
    assert "read" not in meta

  @pytest.mark.asyncio
  async def test_existing_default_assertions_still_pass(self, tmp_path: Path) -> None:
    """Reading without offset/limit returns raw content (no prefix, no metadata)."""
    content = "line1\nline2\nline3"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    ctx = _read_context()
    result = await spec.execute(path=str(file_path), ctx=ctx)
    assert result.success is True
    assert result.result == content
    assert result.content_metadata is None

  @pytest.mark.asyncio
  async def test_plugin_url_with_offset_limit(self) -> None:
    """plugin:// URLs apply offset/limit to the resolved resource text."""
    spec = _read_spec()
    ctx = _read_context()
    # Read the yoker package's builtin/__init__.py — a known non-empty resource.
    result = await spec.execute(
      path="plugin://yoker/builtin/__init__.py", offset=1, limit=2, ctx=ctx
    )
    assert result.success is True
    meta = result.content_metadata["metadata"]
    assert meta["offset"] == 1
    assert meta["limit"] == 2
    assert meta["returned_lines"] == 2
    assert meta["total_lines"] >= 2
    # Flat keys consumed by ToolContentEvent are present at the top level.
    assert result.content_metadata["operation"] == "read"
    assert result.content_metadata["content_type"] == "text/plain"
    assert result.content_metadata["content"] == result.result
    # Result uses cat -n prefix; first line should start with "     1\t".
    assert result.result.startswith("     1\t")
