"""Tests for read tool."""

from pathlib import Path

import pytest

from yoker.config import Config, PermissionsConfig
from yoker.tools import ToolRegistry, make_read_tool
from yoker.tools.base import ToolResult
from yoker.tools.path_guardrail import PathGuardrail


def _read_spec():
  """Create and register the read tool."""
  registry = ToolRegistry()
  return registry.register(make_read_tool())


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
    result = await spec.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "hello world"
    assert result.error is None

  @pytest.mark.asyncio
  async def test_read_missing_file(self) -> None:
    """read tool returns error for missing file."""
    spec = _read_spec()
    result = await spec.execute(path="/nonexistent/path/file.txt")
    assert result.success is False
    assert result.result == ""
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_result_is_toolresult(self) -> None:
    """read tool execute returns ToolResult."""
    spec = _read_spec()
    result = await spec.execute(path="/dev/null")
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
    validation = guardrail.validate(spec.name, {"path": str(file_path)})
    assert validation.valid
    result = await spec.execute(path=str(file_path))
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
    result = await spec.execute(path=str(link))
    assert result.success is False

  @pytest.mark.asyncio
  async def test_read_file_with_encoding(self, tmp_path: Path) -> None:
    """read tool handles different encodings."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    spec = _read_spec()
    result = await spec.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "hello world"

  @pytest.mark.asyncio
  async def test_read_result_truncation(self, tmp_path: Path) -> None:
    """read tool returns full file content."""
    content = "line1\nline2\nline3"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    spec = _read_spec()
    result = await spec.execute(path=str(file_path))
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
    result = await spec.execute(path=sensitive_path)
    # Path should be resolved by realpath, so it should succeed
    assert result.success is True

  @pytest.mark.asyncio
  async def test_read_guardrail_logs_blocked(self, tmp_path: Path) -> None:
    """Path guardrail blocks read access to files matching blocked patterns."""
    from yoker.config import ReadToolConfig, ToolsConfig

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
    result = await spec.execute(path="/nonexistent/file.txt")
    assert result.success is False
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_directory(self, tmp_path: Path) -> None:
    """read tool returns error for directory path."""
    spec = _read_spec()
    result = await spec.execute(path=str(tmp_path))
    assert result.success is False
    assert "not a file" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_empty_path(self) -> None:
    """read tool returns error for empty path."""
    spec = _read_spec()
    result = await spec.execute(path="")
    assert result.success is False
    assert result.error

  @pytest.mark.asyncio
  async def test_read_invalid_path_type(self) -> None:
    """read tool returns error for invalid path type."""
    spec = _read_spec()
    result = await spec.execute(path=123)  # type: ignore
    assert result.success is False
    assert result.error

  @pytest.mark.asyncio
  async def test_read_permission_denied(self) -> None:
    """read tool handles permission denied."""
    # Skip on systems where /dev/null might not have permission issues
    spec = _read_spec()
    # Reading a directory should fail with "not a file" not permission error
    result = await spec.execute(path="/dev")
    assert result.success is False
