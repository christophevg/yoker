"""Tests for ListTool."""

import os
from pathlib import Path

from yoker.tools import ListTool
from yoker.tools.base import ToolResult


class TestListTool:
  """Tests for the ListTool."""

  def test_name(self) -> None:
    """ListTool has correct name."""
    tool = ListTool()
    assert tool.name == "list"

  def test_description(self) -> None:
    """ListTool has description."""
    tool = ListTool()
    assert "List" in tool.description

  def test_schema(self) -> None:
    """ListTool schema has required fields."""
    tool = ListTool()
    schema = tool.get_schema()
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "list"
    assert "parameters" in func
    assert "path" in func["parameters"]["properties"]
    assert "max_depth" in func["parameters"]["properties"]
    assert "max_entries" in func["parameters"]["properties"]
    assert "pattern" in func["parameters"]["properties"]
    assert "path" in func["parameters"]["required"]

  def test_list_flat_directory(self, tmp_path: Path) -> None:
    """ListTool lists immediate directory contents."""
    (tmp_path / "alpha.txt").write_text("a")
    (tmp_path / "beta.py").write_text("b")
    (tmp_path / "subdir").mkdir()

    tool = ListTool()
    result = tool.execute(path=str(tmp_path))
    assert result.success is True
    assert "alpha.txt" in result.result
    assert "beta.py" in result.result
    assert "subdir/" in result.result
    assert "3 entries total (2 files, 1 directories)" in result.result

  def test_list_recursive(self, tmp_path: Path) -> None:
    """ListTool respects max_depth for recursion."""
    (tmp_path / "root.txt").write_text("root")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "bottom.txt").write_text("bottom")

    tool = ListTool()
    result = tool.execute(path=str(tmp_path), max_depth=2)
    assert result.success is True
    assert "root.txt" in result.result
    assert "nested.txt" in result.result
    assert "deep/" in result.result
    assert "bottom.txt" not in result.result

  def test_list_max_depth_zero(self, tmp_path: Path) -> None:
    """ListTool with max_depth=0 shows only root."""
    (tmp_path / "file.txt").write_text("hello")
    (tmp_path / "subdir").mkdir()

    tool = ListTool()
    result = tool.execute(path=str(tmp_path), max_depth=0)
    assert result.success is True
    assert str(tmp_path).rstrip("/") + "/" in result.result
    assert "file.txt" not in result.result
    assert "0 entries total (0 files, 0 directories)" in result.result

  def test_list_max_entries_truncation(self, tmp_path: Path) -> None:
    """ListTool truncates when max_entries exceeded."""
    for i in range(5):
      (tmp_path / f"file{i}.txt").write_text("x")

    tool = ListTool()
    result = tool.execute(path=str(tmp_path), max_entries=3)
    assert result.success is True
    assert "truncated" in result.result
    assert "3 entries total" in result.result

  def test_list_pattern_filter(self, tmp_path: Path) -> None:
    """ListTool filters by glob pattern."""
    (tmp_path / "foo.py").write_text("x")
    (tmp_path / "bar.py").write_text("x")
    (tmp_path / "baz.txt").write_text("x")
    (tmp_path / "subdir").mkdir()

    tool = ListTool()
    result = tool.execute(path=str(tmp_path), pattern="*.py")
    assert result.success is True
    assert "foo.py" in result.result
    assert "bar.py" in result.result
    assert "baz.txt" not in result.result
    assert "subdir/" not in result.result

  def test_list_nonexistent_path(self) -> None:
    """ListTool returns error for nonexistent path."""
    tool = ListTool()
    result = tool.execute(path="/nonexistent/path")
    assert result.success is False
    assert "not found" in result.error.lower()

  def test_list_file_as_path(self, tmp_path: Path) -> None:
    """ListTool handles a file path by returning it as single entry."""
    file_path = tmp_path / "single.txt"
    file_path.write_text("hello")

    tool = ListTool()
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert "single.txt" in result.result
    assert "1 entry total (1 file, 0 directories)" in result.result

  def test_list_permission_denied(self, tmp_path: Path) -> None:
    """ListTool handles permission errors gracefully."""
    restricted = tmp_path / "restricted"
    restricted.mkdir()
    # Remove read permission on the directory
    os.chmod(str(restricted), 0o000)
    try:
      tool = ListTool()
      result = tool.execute(path=str(restricted))
      assert result.success is True
      assert "permission denied" in result.result.lower()
    finally:
      os.chmod(str(restricted), 0o755)

  def test_list_invalid_max_depth(self) -> None:
    """ListTool handles invalid max_depth."""
    tool = ListTool()
    result = tool.execute(path=".", max_depth="abc")
    assert result.success is False
    assert "invalid numeric" in result.error.lower()

  def test_list_clamps_negative_max_depth(self, tmp_path: Path) -> None:
    """ListTool clamps negative max_depth to 0."""
    (tmp_path / "file.txt").write_text("hello")

    tool = ListTool()
    result = tool.execute(path=str(tmp_path), max_depth=-5)
    assert result.success is True
    assert "file.txt" not in result.result

  def test_list_clamps_excessive_max_depth(self, tmp_path: Path) -> None:
    """ListTool clamps excessive max_depth to ABSOLUTE_MAX_DEPTH."""
    (tmp_path / "file.txt").write_text("hello")

    tool = ListTool()
    result = tool.execute(path=str(tmp_path), max_depth=999)
    assert result.success is True
    assert "file.txt" in result.result

  def test_list_empty_directory(self, tmp_path: Path) -> None:
    """ListTool handles empty directory."""
    tool = ListTool()
    result = tool.execute(path=str(tmp_path))
    assert result.success is True
    assert "0 entries total (0 files, 0 directories)" in result.result

  def test_list_does_not_follow_symlinks(self, tmp_path: Path) -> None:
    """ListTool does not follow symlinks into directories."""
    target = tmp_path / ".." / "outside_target"
    target.mkdir()
    (target / "inside.txt").write_text("hello")
    symlink = tmp_path / "link"
    os.symlink(str(target), str(symlink))

    tool = ListTool()
    result = tool.execute(path=str(tmp_path), max_depth=2)
    assert result.success is True
    assert "link" in result.result
    assert "inside.txt" not in result.result

  def test_list_sorts_entries(self, tmp_path: Path) -> None:
    """ListTool sorts entries alphabetically."""
    (tmp_path / "zebra.txt").write_text("z")
    (tmp_path / "alpha.txt").write_text("a")
    (tmp_path / "beta.txt").write_text("b")

    tool = ListTool()
    result = tool.execute(path=str(tmp_path))
    lines = result.result.split("\n")
    names = [line.strip() for line in lines if line.strip() and not line.startswith(".")]
    assert names[0] == str(tmp_path).rstrip("/") + "/"
    # Entries should be sorted alphabetically
    assert names.index("alpha.txt") < names.index("beta.txt")
    assert names.index("beta.txt") < names.index("zebra.txt")

  def test_list_result_is_toolresult(self) -> None:
    """ListTool execute returns ToolResult."""
    tool = ListTool()
    result = tool.execute(path="/tmp")
    assert isinstance(result, ToolResult)
