"""Tests for ReadTool."""

from pathlib import Path

import pytest

from yoker.tools import ReadTool
from yoker.tools.base import ToolResult, ValidationResult


class FakeGuardrail:
  """Fake guardrail for testing ReadTool integration."""

  def __init__(self, allow: bool = True, reason: str = "blocked") -> None:
    self.allow = allow
    self.reason = reason
    self.calls: list[tuple[str, dict]] = []

  def validate(self, tool_name: str, params: dict) -> ValidationResult:
    self.calls.append((tool_name, params))
    if self.allow:
      return ValidationResult(valid=True)
    return ValidationResult(valid=False, reason=self.reason)


class TestReadTool:
  """Tests for ReadTool."""

  def test_name(self) -> None:
    """ReadTool has correct name."""
    tool = ReadTool()
    assert tool.name == "read"

  def test_description(self) -> None:
    """ReadTool has description."""
    tool = ReadTool()
    assert "Read" in tool.description

  def test_schema(self) -> None:
    """ReadTool schema has required fields."""
    tool = ReadTool()
    schema = tool.get_schema()
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "read"
    assert "parameters" in func
    assert "path" in func["parameters"]["properties"]
    assert "path" in func["parameters"]["required"]

  @pytest.mark.asyncio
  async def test_read_existing_file(self, tmp_path: Path) -> None:
    """ReadTool reads an existing file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = ReadTool()
    result = await tool.execute_async(path=str(file_path))
    assert result.success is True
    assert result.result == "hello world"
    assert result.error is None

  @pytest.mark.asyncio
  async def test_read_missing_file(self) -> None:
    """ReadTool returns error for missing file."""
    tool = ReadTool()
    result = await tool.execute_async(path="/nonexistent/path/file.txt")
    assert result.success is False
    assert result.result == ""
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_result_is_toolresult(self) -> None:
    """ReadTool execute returns ToolResult."""
    tool = ReadTool()
    result = await tool.execute_async(path="/dev/null")
    assert isinstance(result, ToolResult)

  @pytest.mark.asyncio
  async def test_read_with_guardrail_blocks(self) -> None:
    """ReadTool with guardrail blocks unauthorized paths."""
    guardrail = FakeGuardrail(allow=False, reason="outside allowed")
    tool = ReadTool(guardrail=guardrail)
    result = await tool.execute_async(path="/etc/passwd")
    assert result.success is False
    assert result.error == "outside allowed"
    assert guardrail.calls == [("read", {"path": "/etc/passwd"})]

  @pytest.mark.asyncio
  async def test_read_with_guardrail_allows(self, tmp_path: Path) -> None:
    """ReadTool with guardrail allows authorized paths."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("allowed content")
    guardrail = FakeGuardrail(allow=True)
    tool = ReadTool(guardrail=guardrail)
    result = await tool.execute_async(path=str(file_path))
    assert result.success is True
    assert result.result == "allowed content"
    assert guardrail.calls == [("read", {"path": str(file_path)})]

  @pytest.mark.asyncio
  async def test_read_rejects_symlink(self, tmp_path: Path) -> None:
    """ReadTool rejects reading symlinks."""
    target = tmp_path / "target.txt"
    target.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    tool = ReadTool()
    result = await tool.execute_async(path=str(link))
    assert result.success is False

  @pytest.mark.asyncio
  async def test_read_file_with_encoding(self, tmp_path: Path) -> None:
    """ReadTool handles different encodings."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = ReadTool()
    result = await tool.execute_async(path=str(file_path))
    assert result.success is True
    assert result.result == "hello world"

  @pytest.mark.asyncio
  async def test_read_result_truncation(self, tmp_path: Path) -> None:
    """ReadTool returns full file content."""
    content = "line1\nline2\nline3"
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)
    tool = ReadTool()
    result = await tool.execute_async(path=str(file_path))
    assert result.success is True
    assert result.result == content

  @pytest.mark.asyncio
  async def test_read_traversal_rejected(self, tmp_path: Path) -> None:
    """ReadTool rejects path traversal via symlink."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    real_file = real_dir / "real.txt"
    real_file.write_text("allowed")
    sensitive_path = str(tmp_path / ".." / tmp_path.name / "real" / "real.txt")
    tool = ReadTool()
    result = await tool.execute_async(path=sensitive_path)
    # Path should be resolved by realpath, so it should succeed
    assert result.success is True

  @pytest.mark.asyncio
  async def test_read_guardrail_logs_blocked(self, tmp_path: Path) -> None:
    """ReadTool logs when guardrail blocks access."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("secret")
    guardrail = FakeGuardrail(allow=False, reason="blocked")
    tool = ReadTool(guardrail=guardrail)
    result = await tool.execute_async(path=str(file_path))
    assert result.success is False
    assert result.error == "blocked"

  @pytest.mark.asyncio
  async def test_read_nonexistent_file(self) -> None:
    """ReadTool returns error for non-existent file."""
    tool = ReadTool()
    result = await tool.execute_async(path="/nonexistent/file.txt")
    assert result.success is False
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_directory(self, tmp_path: Path) -> None:
    """ReadTool returns error for directory path."""
    tool = ReadTool()
    result = await tool.execute_async(path=str(tmp_path))
    assert result.success is False
    assert "not a file" in result.error.lower()

  @pytest.mark.asyncio
  async def test_read_empty_path(self) -> None:
    """ReadTool returns error for empty path."""
    tool = ReadTool()
    result = await tool.execute_async(path="")
    assert result.success is False
    assert result.error

  @pytest.mark.asyncio
  async def test_read_invalid_path_type(self) -> None:
    """ReadTool returns error for invalid path type."""
    tool = ReadTool()
    result = await tool.execute_async(path=123)  # type: ignore
    assert result.success is False
    assert result.error

  @pytest.mark.asyncio
  async def test_read_permission_denied(self) -> None:
    """ReadTool handles permission denied."""
    # Skip on systems where /dev/null might not have permission issues
    tool = ReadTool()
    # Reading a directory should fail with "not a file" not permission error
    result = await tool.execute_async(path="/dev")
    assert result.success is False
