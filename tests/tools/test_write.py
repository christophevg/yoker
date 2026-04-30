"""Tests for WriteTool."""

import platform
from pathlib import Path

import pytest

from yoker.config.schema import Config, ToolsConfig, WriteToolConfig
from yoker.tools import WriteTool
from yoker.tools.base import ToolResult, ValidationResult


class FakeGuardrail:
  """Fake guardrail for testing WriteTool integration."""

  def __init__(self, allow: bool = True, reason: str = "blocked") -> None:
    self.allow = allow
    self.reason = reason
    self.calls: list[tuple[str, dict]] = []

  def validate(self, tool_name: str, params: dict) -> ValidationResult:
    self.calls.append((tool_name, params))
    if self.allow:
      return ValidationResult(valid=True)
    return ValidationResult(valid=False, reason=self.reason)


class TestWriteTool:
  """Tests for WriteTool."""

  def test_name(self) -> None:
    """WriteTool has correct name."""
    tool = WriteTool()
    assert tool.name == "write"

  def test_description(self) -> None:
    """WriteTool has description."""
    tool = WriteTool()
    assert "Write" in tool.description

  def test_schema(self) -> None:
    """WriteTool schema has required fields."""
    tool = WriteTool()
    schema = tool.get_schema()
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "write"
    assert "parameters" in func
    props = func["parameters"]["properties"]
    assert "path" in props
    assert "content" in props
    assert "create_parents" in props
    assert "path" in func["parameters"]["required"]
    assert "content" in func["parameters"]["required"]

  def test_write_new_file(self, tmp_path: Path) -> None:
    """WriteTool writes content to a new file."""
    file_path = tmp_path / "test.txt"
    tool = WriteTool()
    result = tool.execute(path=str(file_path), content="hello world")
    assert result.success is True
    assert result.result == "File written successfully"
    assert result.error is None
    assert file_path.read_text(encoding="utf-8") == "hello world"

  def test_write_overwrite_blocked(self, tmp_path: Path) -> None:
    """WriteTool blocks overwrite when allow_overwrite=False."""
    file_path = tmp_path / "existing.txt"
    file_path.write_text("old content")
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=False)))
    tool = WriteTool(config=config)
    result = tool.execute(path=str(file_path), content="new content")
    assert result.success is False
    assert "overwrite" in result.error.lower()
    assert file_path.read_text(encoding="utf-8") == "old content"

  def test_write_overwrite_allowed(self, tmp_path: Path) -> None:
    """WriteTool allows overwrite when allow_overwrite=True."""
    file_path = tmp_path / "existing.txt"
    file_path.write_text("old content")
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    tool = WriteTool(config=config)
    result = tool.execute(path=str(file_path), content="new content")
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "new content"

  def test_write_with_guardrail_blocks(self) -> None:
    """WriteTool with guardrail blocks unauthorized paths."""
    guardrail = FakeGuardrail(allow=False, reason="outside allowed")
    tool = WriteTool(guardrail=guardrail)
    result = tool.execute(path="/etc/passwd", content="data")
    assert result.success is False
    assert result.error == "outside allowed"
    assert guardrail.calls == [("write", {"path": "/etc/passwd", "content": "data"})]

  def test_write_with_guardrail_allows(self, tmp_path: Path) -> None:
    """WriteTool with guardrail allows authorized paths."""
    file_path = tmp_path / "test.txt"
    guardrail = FakeGuardrail(allow=True)
    tool = WriteTool(guardrail=guardrail)
    result = tool.execute(path=str(file_path), content="allowed content")
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "allowed content"
    assert guardrail.calls == [("write", {"path": str(file_path), "content": "allowed content"})]

  def test_write_rejects_symlink(self, tmp_path: Path) -> None:
    """WriteTool rejects writing to symlinks."""
    target = tmp_path / "target.txt"
    target.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    tool = WriteTool()
    result = tool.execute(path=str(link), content="new data")
    assert result.success is False
    assert "symlink" in result.error.lower()

  def test_write_create_parents_false(self, tmp_path: Path) -> None:
    """WriteTool returns error when parent missing and create_parents=False."""
    file_path = tmp_path / "missing" / "test.txt"
    tool = WriteTool()
    result = tool.execute(path=str(file_path), content="data", create_parents=False)
    assert result.success is False
    assert "parent directory" in result.error.lower()

  def test_write_create_parents_true(self, tmp_path: Path) -> None:
    """WriteTool creates parents when create_parents=True."""
    file_path = tmp_path / "missing" / "test.txt"
    tool = WriteTool()
    result = tool.execute(path=str(file_path), content="data", create_parents=True)
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "data"

  def test_write_missing_path(self) -> None:
    """WriteTool handles missing path parameter."""
    tool = WriteTool()
    result = tool.execute(content="data")
    assert result.success is False
    assert "invalid path" in result.error.lower()

  def test_write_missing_content(self, tmp_path: Path) -> None:
    """WriteTool writes empty file when content is omitted."""
    file_path = tmp_path / "empty_file.txt"
    tool = WriteTool()
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "File written successfully"
    assert file_path.read_text(encoding="utf-8") == ""

  def test_write_non_string_path(self) -> None:
    """WriteTool handles non-string path parameter."""
    tool = WriteTool()
    result = tool.execute(path=123, content="data")
    assert result.success is False
    assert result.error == "Invalid path parameter"

  def test_write_non_string_content(self) -> None:
    """WriteTool handles non-string content parameter."""
    tool = WriteTool()
    result = tool.execute(path="/tmp/test.txt", content=123)
    assert result.success is False
    assert result.error == "Invalid content parameter"

  def test_write_permission_denied(self, tmp_path: Path, monkeypatch) -> None:
    """WriteTool returns sanitized error on permission denied."""
    file_path = tmp_path / "readonly.txt"
    file_path.write_text("existing")

    def mock_write_text(*args, **kwargs):
      raise PermissionError("Access denied")

    monkeypatch.setattr(Path, "write_text", mock_write_text)
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    tool = WriteTool(config=config)
    result = tool.execute(path=str(file_path), content="new data")
    assert result.success is False
    assert "permission denied" in result.error.lower()
    assert str(file_path) not in result.error

  def test_write_sanitizes_error_messages(self, tmp_path: Path) -> None:
    """WriteTool does not leak full paths in error messages."""
    tool = WriteTool()
    sensitive_path = str(tmp_path / ".ssh" / "id_rsa")
    result = tool.execute(path=sensitive_path, content="secret")
    assert result.success is False
    assert sensitive_path not in result.error

  def test_write_resolves_path(self, tmp_path: Path) -> None:
    """WriteTool resolves relative paths before writing."""
    file_path = tmp_path / "real.txt"
    tool = WriteTool()
    result = tool.execute(
      path=str(tmp_path / ".." / tmp_path.name / "real.txt"),
      content="resolved",
    )
    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "resolved"

  def test_write_oserror_during_write(self, tmp_path: Path, monkeypatch) -> None:
    """WriteTool handles OSError during write_text gracefully."""
    file_path = tmp_path / "device.txt"
    file_path.write_text("data")

    def mock_write_text(*args, **kwargs):
      raise OSError("device error")

    monkeypatch.setattr(Path, "write_text", mock_write_text)
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    tool = WriteTool(config=config)
    result = tool.execute(path=str(file_path), content="new data")
    assert result.success is False
    assert "error writing file" in result.error.lower()
    assert str(file_path) not in result.error

  def test_write_empty_path(self) -> None:
    """WriteTool handles empty path string."""
    tool = WriteTool()
    result = tool.execute(path="", content="data")
    assert result.success is False
    assert "invalid path" in result.error.lower()

  def test_write_result_is_toolresult(self) -> None:
    """WriteTool execute returns ToolResult."""
    tool = WriteTool()
    result = tool.execute(path="/dev/null", content="test")
    assert isinstance(result, ToolResult)

  def test_write_guardrail_passes_create_parents(self, tmp_path: Path) -> None:
    """Guardrail receives create_parents parameter."""
    guardrail = FakeGuardrail(allow=True)
    tool = WriteTool(guardrail=guardrail)
    result = tool.execute(
      path=str(tmp_path / "test.txt"),
      content="data",
      create_parents=True,
    )
    assert result.success is True
    # Guardrail should have received create_parents in params
    assert guardrail.calls == [
      (
        "write",
        {
          "path": str(tmp_path / "test.txt"),
          "content": "data",
          "create_parents": True,
        },
      )
    ]

  def test_write_symlink_inside_allowed_with_guardrail(self, tmp_path: Path) -> None:
    """WriteTool rejects symlinks even when guardrail allows."""
    target = tmp_path / "target.txt"
    target.write_text("allowed target")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    guardrail = FakeGuardrail(allow=True)
    tool = WriteTool(guardrail=guardrail)
    result = tool.execute(path=str(link), content="new data")
    # Tool layer rejects symlinks before writing
    assert result.success is False
    assert "symlink" in result.error.lower()

  @pytest.mark.skipif(
    platform.system() == "Windows", reason="Unix permission model differs on Windows"
  )
  def test_write_over_existing_directory(self, tmp_path: Path) -> None:
    """WriteTool returns error when path is an existing directory."""
    subdir = tmp_path / "existing_dir"
    subdir.mkdir()
    config = Config(tools=ToolsConfig(write=WriteToolConfig(allow_overwrite=True)))
    tool = WriteTool(config=config)
    result = tool.execute(path=str(subdir), content="data")
    assert result.success is False
    assert "error writing file" in result.error.lower()
