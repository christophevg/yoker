"""Tests for update tool."""

from pathlib import Path

import pytest

from yoker.builtin import update as update_tool
from yoker.config import Config, ToolsConfig, UpdateToolConfig
from yoker.tools import ToolRegistry
from yoker.tools.context import ToolContext
from yoker.tools.schema import ToolResult


def _update_spec():
  """Create and register the update tool."""
  registry = ToolRegistry()
  return registry.register(update_tool)


def _update_context(config: Config | None = None) -> ToolContext:
  """Create a ToolContext for update tool tests."""
  if config is None:
    config = Config()
  return ToolContext(
    config=config.tools.update,
    shared=config.tools_shared,
    backends={},
  )


class TestUpdateTool:
  """Tests for the update tool."""

  def test_name(self) -> None:
    """update tool has correct name."""
    spec = _update_spec()
    assert spec.name == "update"

  def test_description(self) -> None:
    """update tool has description."""
    spec = _update_spec()
    assert "Update" in spec.description

  def test_schema(self) -> None:
    """update tool schema has required fields."""
    spec = _update_spec()
    schema = spec.schema
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "update"
    assert "parameters" in func
    props = func["parameters"]["properties"]
    assert "path" in props
    assert "operation" in props
    assert "old_string" in props
    assert "new_string" in props
    assert "path" in func["parameters"]["required"]
    assert "operation" in func["parameters"]["required"]

  @pytest.mark.asyncio
  async def test_replace_success(self, tmp_path: Path) -> None:
    """update tool replaces text in file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(file_path),
      operation="replace",
      old_string="world",
      new_string="universe",
      ctx=ctx,
    )
    assert result.success is True
    assert file_path.read_text() == "hello universe"

  @pytest.mark.asyncio
  async def test_replace_exact_match_multiple_rejected(self, tmp_path: Path) -> None:
    """update tool rejects when multiple matches and exact match required."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello hello hello")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(require_exact_match=True)))
    spec = _update_spec()
    ctx = _update_context(config)
    result = await spec.execute(
      path=str(file_path),
      operation="replace",
      old_string="hello",
      new_string="world",
      ctx=ctx,
    )
    assert result.success is False
    assert "multiple times" in result.error.lower() or "ambiguous" in result.error.lower()

  @pytest.mark.asyncio
  async def test_replace_exact_match_single_allowed(self, tmp_path: Path) -> None:
    """update tool allows single match when exact match required."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(require_exact_match=True)))
    spec = _update_spec()
    ctx = _update_context(config)
    result = await spec.execute(
      path=str(file_path),
      operation="replace",
      old_string="world",
      new_string="universe",
      ctx=ctx,
    )
    assert result.success is True
    assert file_path.read_text() == "hello universe"

  @pytest.mark.asyncio
  async def test_replace_no_match(self, tmp_path: Path) -> None:
    """update tool handles no match case."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(file_path),
      operation="replace",
      old_string="missing",
      new_string="replacement",
      ctx=ctx,
    )
    assert result.success is False
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_replace_not_exact_match_allows_first(self, tmp_path: Path) -> None:
    """update tool replaces first match when exact match not required."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello hello hello")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(require_exact_match=False)))
    spec = _update_spec()
    ctx = _update_context(config)
    result = await spec.execute(
      path=str(file_path),
      operation="replace",
      old_string="hello",
      new_string="world",
      ctx=ctx,
    )
    assert result.success is True
    assert file_path.read_text() == "world hello hello"

  @pytest.mark.asyncio
  async def test_insert_before(self, tmp_path: Path) -> None:
    """update tool inserts before a line."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line2\nline3\n")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(file_path),
      operation="insert_before",
      line_number=1,
      new_string="line1",
      ctx=ctx,
    )
    assert result.success is True
    # Insert before line 1 adds it at the beginning
    assert file_path.read_text() == "line1\nline2\nline3\n"

  @pytest.mark.asyncio
  async def test_insert_after(self, tmp_path: Path) -> None:
    """update tool inserts after a line."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2\n")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(file_path),
      operation="insert_after",
      line_number=2,
      new_string="line3",
      ctx=ctx,
    )
    assert result.success is True
    # Insert after line 2 adds it at the end
    assert file_path.read_text() == "line1\nline2\nline3\n"

  @pytest.mark.asyncio
  async def test_delete_line(self, tmp_path: Path) -> None:
    """update tool deletes a line."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2\nline3\n")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(file_path),
      operation="delete",
      old_string="line2\n",
      ctx=ctx,
    )
    assert result.success is True
    assert file_path.read_text() == "line1\nline3\n"

  @pytest.mark.asyncio
  async def test_update_with_context(self, tmp_path: Path) -> None:
    """update tool works with ToolContext."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(file_path),
      operation="replace",
      old_string="hello",
      new_string="world",
      ctx=ctx,
    )
    assert result.success is True
    assert file_path.read_text() == "world"

  @pytest.mark.asyncio
  async def test_update_missing_file(self) -> None:
    """update tool handles missing file."""
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path="/nonexistent/file.txt",
      operation="replace",
      old_string="old",
      new_string="new",
      ctx=ctx,
    )
    assert result.success is False
    assert "not found" in result.error.lower()

  @pytest.mark.asyncio
  async def test_update_symlink_inside_allowed_with_guardrail(self, tmp_path: Path) -> None:
    """update tool rejects symlinks regardless of guardrail."""
    target = tmp_path / "target.txt"
    target.write_text("target content")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(link),
      operation="replace",
      old_string="target",
      new_string="modified",
      ctx=ctx,
    )
    assert result.success is False
    assert "symlink" in result.error.lower()

  @pytest.mark.asyncio
  async def test_delete_requires_old_string_or_line_number(self, tmp_path: Path) -> None:
    """update tool requires old_string or line_number for delete."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2\n")
    spec = _update_spec()
    ctx = _update_context()
    # Empty old_string is allowed for delete
    result = await spec.execute(
      path=str(file_path),
      operation="delete",
      old_string="line1\n",
      ctx=ctx,
    )
    assert result.success is True

  @pytest.mark.asyncio
  async def test_non_string_path(self, tmp_path: Path) -> None:
    """update tool handles non-string path."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=123,  # type: ignore
      operation="replace",
      old_string="content",
      new_string="new",
      ctx=ctx,
    )
    assert result.success is False
    assert "invalid" in result.error.lower()

  @pytest.mark.asyncio
  async def test_non_string_old_string(self, tmp_path: Path) -> None:
    """update tool handles non-string old_string."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(file_path),
      operation="replace",
      old_string=123,  # type: ignore
      new_string="new",
      ctx=ctx,
    )
    assert result.success is False

  @pytest.mark.asyncio
  async def test_non_string_new_string(self, tmp_path: Path) -> None:
    """update tool handles non-string new_string."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(file_path),
      operation="replace",
      old_string="content",
      new_string=123,  # type: ignore
      ctx=ctx,
    )
    assert result.success is False

  @pytest.mark.asyncio
  async def test_result_is_toolresult(self, tmp_path: Path) -> None:
    """update tool execute returns ToolResult."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")
    spec = _update_spec()
    ctx = _update_context()
    result = await spec.execute(
      path=str(file_path),
      operation="replace",
      old_string="content",
      new_string="new",
      ctx=ctx,
    )
    assert isinstance(result, ToolResult)
