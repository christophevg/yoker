"""Tests for ReadTool."""

from pathlib import Path

from yoker.tools import ReadTool
from yoker.tools.base import ToolResult


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

  def test_read_existing_file(self, tmp_path: Path) -> None:
    """ReadTool reads an existing file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = ReadTool()
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "hello world"
    assert result.error is None

  def test_read_missing_file(self) -> None:
    """ReadTool returns error for missing file."""
    tool = ReadTool()
    result = tool.execute(path="/nonexistent/path/file.txt")
    assert result.success is False
    assert result.result == ""
    assert "not found" in result.error.lower()

  def test_read_result_is_toolresult(self) -> None:
    """ReadTool execute returns ToolResult."""
    tool = ReadTool()
    result = tool.execute(path="/dev/null")
    assert isinstance(result, ToolResult)
