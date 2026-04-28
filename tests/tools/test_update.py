"""Tests for UpdateTool."""

from pathlib import Path

from yoker.config.schema import Config, ToolsConfig, UpdateToolConfig
from yoker.tools import UpdateTool
from yoker.tools.base import ToolResult, ValidationResult


class FakeGuardrail:
  """Fake guardrail for testing UpdateTool integration."""

  def __init__(self, allow: bool = True, reason: str = "blocked") -> None:
    self.allow = allow
    self.reason = reason
    self.calls: list[tuple[str, dict]] = []

  def validate(self, tool_name: str, params: dict) -> ValidationResult:
    self.calls.append((tool_name, params))
    if self.allow:
      return ValidationResult(valid=True)
    return ValidationResult(valid=False, reason=self.reason)


class TestUpdateTool:
  """Tests for UpdateTool."""

  def test_name(self) -> None:
    """UpdateTool has correct name."""
    tool = UpdateTool()
    assert tool.name == "update"

  def test_description(self) -> None:
    """UpdateTool has description."""
    tool = UpdateTool()
    assert "Update" in tool.description

  def test_schema(self) -> None:
    """UpdateTool schema has required fields."""
    tool = UpdateTool()
    schema = tool.get_schema()
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "update"
    assert "parameters" in func
    props = func["parameters"]["properties"]
    assert "path" in props
    assert "operation" in props
    assert "old_string" in props
    assert "new_string" in props
    assert "line_number" in props
    assert "path" in func["parameters"]["required"]
    assert "operation" in func["parameters"]["required"]

  # --- Replace operation tests ---

  def test_replace_success(self, tmp_path: Path) -> None:
    """UpdateTool replaces old_string with new_string."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="hello",
      new_string="goodbye",
    )
    assert result.success is True
    assert result.result == "File updated successfully"
    assert result.error is None
    assert file_path.read_text(encoding="utf-8") == "goodbye world"

  def test_replace_exact_match_multiple_rejected(self, tmp_path: Path) -> None:
    """UpdateTool rejects ambiguous match when require_exact_match=True."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello hello world")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(require_exact_match=True)))
    tool = UpdateTool(config=config)
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="hello",
      new_string="goodbye",
    )
    assert result.success is False
    assert "ambiguous" in result.error.lower()
    assert file_path.read_text(encoding="utf-8") == "hello hello world"

  def test_replace_exact_match_single_allowed(self, tmp_path: Path) -> None:
    """UpdateTool allows replacement when match is unique."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(require_exact_match=True)))
    tool = UpdateTool(config=config)
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="hello",
      new_string="goodbye",
    )
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "goodbye world"

  def test_replace_no_match(self, tmp_path: Path) -> None:
    """UpdateTool returns error when old_string not found."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="missing",
      new_string="replacement",
    )
    assert result.success is False
    assert "not found" in result.error.lower()

  def test_replace_not_exact_match_allows_first(self, tmp_path: Path) -> None:
    """When require_exact_match=False, replaces first occurrence."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello hello world")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(require_exact_match=False)))
    tool = UpdateTool(config=config)
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="hello",
      new_string="goodbye",
    )
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "goodbye hello world"

  # --- Insert operation tests ---

  def test_insert_before(self, tmp_path: Path) -> None:
    """UpdateTool inserts before specified line."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2\nline3")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="insert_before",
      line_number=2,
      new_string="inserted",
    )
    assert result.success is True
    content = file_path.read_text(encoding="utf-8")
    assert "inserted" in content
    lines = content.splitlines()
    assert lines[1] == "inserted"
    assert lines[2] == "line2"

  def test_insert_after(self, tmp_path: Path) -> None:
    """UpdateTool inserts after specified line."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2\nline3")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="insert_after",
      line_number=2,
      new_string="inserted",
    )
    assert result.success is True
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[2] == "inserted"
    assert lines[1] == "line2"

  def test_insert_line_number_out_of_range(self, tmp_path: Path) -> None:
    """UpdateTool returns error for invalid line number."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="insert_before",
      line_number=5,
      new_string="inserted",
    )
    assert result.success is False
    assert "out of range" in result.error.lower()

  def test_insert_line_number_zero(self, tmp_path: Path) -> None:
    """UpdateTool returns error for line_number=0."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="insert_before",
      line_number=0,
      new_string="inserted",
    )
    assert result.success is False
    assert "out of range" in result.error.lower()

  def test_insert_missing_line_number(self, tmp_path: Path) -> None:
    """UpdateTool requires line_number for insert operations."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="insert_before",
      new_string="inserted",
    )
    assert result.success is False
    assert "line_number" in result.error.lower()

  def test_insert_into_empty_file(self, tmp_path: Path) -> None:
    """UpdateTool handles insertion into empty file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="insert_before",
      line_number=1,
      new_string="first line",
    )
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "first line\n"

  # --- Delete operation tests ---

  def test_delete_by_old_string(self, tmp_path: Path) -> None:
    """UpdateTool deletes content by old_string match."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="delete",
      old_string="hello ",
    )
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "world"

  def test_delete_by_line_number(self, tmp_path: Path) -> None:
    """UpdateTool deletes line by line_number."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2\nline3")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="delete",
      line_number=2,
    )
    assert result.success is True
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert "line2" not in lines
    assert "line1" in lines
    assert "line3" in lines

  def test_delete_no_match(self, tmp_path: Path) -> None:
    """UpdateTool returns error when delete old_string not found."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="delete",
      old_string="missing",
    )
    assert result.success is False
    assert "not found" in result.error.lower()

  def test_delete_multiple_rejected(self, tmp_path: Path) -> None:
    """UpdateTool rejects ambiguous delete when require_exact_match=True."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello hello world")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(require_exact_match=True)))
    tool = UpdateTool(config=config)
    result = tool.execute(
      path=str(file_path),
      operation="delete",
      old_string="hello",
    )
    assert result.success is False
    assert "ambiguous" in result.error.lower()

  def test_delete_line_number_out_of_range(self, tmp_path: Path) -> None:
    """UpdateTool returns error for invalid delete line number."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("line1\nline2")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="delete",
      line_number=5,
    )
    assert result.success is False
    assert "out of range" in result.error.lower()

  # --- Guardrail tests ---

  def test_update_with_guardrail_blocks(self) -> None:
    """UpdateTool with guardrail blocks unauthorized paths."""
    guardrail = FakeGuardrail(allow=False, reason="outside allowed")
    tool = UpdateTool(guardrail=guardrail)
    result = tool.execute(
      path="/etc/passwd",
      operation="replace",
      old_string="x",
      new_string="y",
    )
    assert result.success is False
    assert result.error == "outside allowed"
    assert guardrail.calls == [
      (
        "update",
        {
          "path": "/etc/passwd",
          "operation": "replace",
          "old_string": "x",
          "new_string": "y",
        },
      )
    ]

  def test_update_with_guardrail_allows(self, tmp_path: Path) -> None:
    """UpdateTool with guardrail allows authorized paths."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello")
    guardrail = FakeGuardrail(allow=True)
    tool = UpdateTool(guardrail=guardrail)
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="hello",
      new_string="goodbye",
    )
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "goodbye"
    assert guardrail.calls == [
      (
        "update",
        {
          "path": str(file_path),
          "operation": "replace",
          "old_string": "hello",
          "new_string": "goodbye",
        },
      )
    ]

  # --- Security tests ---

  def test_update_rejects_symlink(self, tmp_path: Path) -> None:
    """UpdateTool rejects updating via symlinks."""
    target = tmp_path / "target.txt"
    target.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    tool = UpdateTool()
    result = tool.execute(
      path=str(link),
      operation="replace",
      old_string="secret",
      new_string="new data",
    )
    assert result.success is False
    assert "symlink" in result.error.lower()

  def test_update_nonexistent_file(self, tmp_path: Path) -> None:
    """UpdateTool returns error when file does not exist."""
    file_path = tmp_path / "missing.txt"
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="x",
      new_string="y",
    )
    assert result.success is False
    assert "not found" in result.error.lower()

  def test_update_directory(self, tmp_path: Path) -> None:
    """UpdateTool returns error when path is a directory."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    tool = UpdateTool()
    result = tool.execute(
      path=str(subdir),
      operation="replace",
      old_string="x",
      new_string="y",
    )
    assert result.success is False
    assert "not a file" in result.error.lower()

  def test_update_sanitizes_error_messages(self, tmp_path: Path) -> None:
    """UpdateTool does not leak full paths in error messages."""
    tool = UpdateTool()
    sensitive_path = str(tmp_path / ".ssh" / "id_rsa")
    result = tool.execute(
      path=sensitive_path,
      operation="replace",
      old_string="x",
      new_string="y",
    )
    assert result.success is False
    assert sensitive_path not in result.error

  def test_update_resolves_path(self, tmp_path: Path) -> None:
    """UpdateTool resolves relative paths before updating."""
    file_path = tmp_path / "real.txt"
    file_path.write_text("original")
    tool = UpdateTool()
    result = tool.execute(
      path=str(tmp_path / ".." / tmp_path.name / "real.txt"),
      operation="replace",
      old_string="original",
      new_string="resolved",
    )
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "resolved"

  # --- Diff size tests ---

  def test_diff_size_exceeded(self, tmp_path: Path) -> None:
    """UpdateTool rejects when diff size exceeds limit."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("x")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(max_diff_size_kb=1)))
    tool = UpdateTool(config=config)
    # 2048 bytes = 2KB, exceeds 1KB limit
    large_string = "a" * 2048
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="x",
      new_string=large_string,
    )
    assert result.success is False
    assert "exceeds limit" in result.error.lower()

  def test_diff_size_within_limit(self, tmp_path: Path) -> None:
    """UpdateTool allows when diff size within limit."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("x")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(max_diff_size_kb=100)))
    tool = UpdateTool(config=config)
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="x",
      new_string="replacement",
    )
    assert result.success is True

  # --- Edge case tests ---

  def test_permission_denied(self, tmp_path: Path, monkeypatch) -> None:
    """UpdateTool returns sanitized error on permission denied during read."""
    file_path = tmp_path / "readonly.txt"
    file_path.write_text("existing")

    def mock_read_text(*args, **kwargs):
      raise PermissionError("Access denied")

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="existing",
      new_string="new data",
    )
    assert result.success is False
    assert "permission denied" in result.error.lower()
    assert str(file_path) not in result.error

  def test_empty_old_string_replace(self, tmp_path: Path) -> None:
    """UpdateTool handles empty old_string as search for empty string."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello")
    config = Config(tools=ToolsConfig(update=UpdateToolConfig(require_exact_match=False)))
    tool = UpdateTool(config=config)
    result = tool.execute(
      path=str(file_path),
      operation="replace",
      old_string="",
      new_string="prefix",
    )
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "prefixhello"

  def test_invalid_operation(self) -> None:
    """UpdateTool handles invalid operation parameter."""
    tool = UpdateTool()
    result = tool.execute(
      path="/tmp/test.txt",
      operation="invalid_op",
      old_string="x",
      new_string="y",
    )
    assert result.success is False
    assert "invalid operation" in result.error.lower()

  def test_non_string_path(self) -> None:
    """UpdateTool handles non-string path parameter."""
    tool = UpdateTool()
    result = tool.execute(
      path=123,
      operation="replace",
      old_string="x",
      new_string="y",
    )
    assert result.success is False
    assert result.error == "Invalid path parameter"

  def test_non_string_old_string(self) -> None:
    """UpdateTool handles non-string old_string parameter."""
    tool = UpdateTool()
    result = tool.execute(
      path="/tmp/test.txt",
      operation="replace",
      old_string=123,
      new_string="y",
    )
    assert result.success is False
    assert result.error == "Invalid old_string parameter"

  def test_result_is_toolresult(self) -> None:
    """UpdateTool execute returns ToolResult."""
    tool = UpdateTool()
    result = tool.execute(
      path="/dev/null",
      operation="replace",
      old_string="x",
      new_string="y",
    )
    assert isinstance(result, ToolResult)

  def test_update_symlink_inside_allowed_with_guardrail(self, tmp_path: Path) -> None:
    """UpdateTool rejects symlinks even when guardrail allows."""
    target = tmp_path / "target.txt"
    target.write_text("allowed target")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    guardrail = FakeGuardrail(allow=True)
    tool = UpdateTool(guardrail=guardrail)
    result = tool.execute(
      path=str(link),
      operation="replace",
      old_string="allowed",
      new_string="new data",
    )
    assert result.success is False
    assert "symlink" in result.error.lower()

  def test_delete_requires_old_string_or_line_number(self, tmp_path: Path) -> None:
    """UpdateTool delete requires either old_string or line_number."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = UpdateTool()
    result = tool.execute(
      path=str(file_path),
      operation="delete",
    )
    assert result.success is False
    assert "required" in result.error.lower()
