"""Tests for ReadTool."""

from pathlib import Path

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

  def test_read_with_guardrail_blocks(self) -> None:
    """ReadTool with guardrail blocks unauthorized paths."""
    guardrail = FakeGuardrail(allow=False, reason="outside allowed")
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path="/etc/passwd")
    assert result.success is False
    assert result.error == "outside allowed"
    assert guardrail.calls == [("read", {"path": "/etc/passwd"})]

  def test_read_with_guardrail_allows(self, tmp_path: Path) -> None:
    """ReadTool with guardrail allows authorized paths."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("allowed content")
    guardrail = FakeGuardrail(allow=True)
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "allowed content"
    assert guardrail.calls == [("read", {"path": str(file_path)})]

  def test_read_rejects_symlink(self, tmp_path: Path) -> None:
    """ReadTool rejects reading symlinks."""
    target = tmp_path / "target.txt"
    target.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    tool = ReadTool()
    result = tool.execute(path=str(link))
    assert result.success is False
    assert "symlink" in result.error.lower()

  def test_read_encoding_utf8(self, tmp_path: Path) -> None:
    """ReadTool reads UTF-8 content correctly."""
    file_path = tmp_path / "utf8.txt"
    file_path.write_text("héllo wörld ❤", encoding="utf-8")
    tool = ReadTool()
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "héllo wörld ❤"

  def test_read_encoding_with_invalid_bytes(self, tmp_path: Path) -> None:
    """ReadTool replaces invalid bytes instead of crashing."""
    file_path = tmp_path / "binary.txt"
    file_path.write_bytes(b"hello \xff\xfe world")
    tool = ReadTool()
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert "hello" in result.result
    assert "world" in result.result
    assert "�" in result.result

  def test_read_sanitizes_error_messages(self, tmp_path: Path) -> None:
    """ReadTool does not leak full paths in error messages."""
    tool = ReadTool()
    sensitive_path = str(tmp_path / ".ssh" / "id_rsa")
    result = tool.execute(path=sensitive_path)
    assert result.success is False
    assert sensitive_path not in result.error

  def test_read_resolves_path(self, tmp_path: Path) -> None:
    """ReadTool resolves relative paths before reading."""
    file_path = tmp_path / "real.txt"
    file_path.write_text("resolved")
    tool = ReadTool()
    result = tool.execute(path=str(tmp_path / ".." / tmp_path.name / "real.txt"))
    assert result.success is True
    assert result.result == "resolved"

  def test_read_not_a_file(self, tmp_path: Path) -> None:
    """ReadTool returns error when path is a directory."""
    tool = ReadTool()
    result = tool.execute(path=str(tmp_path))
    assert result.success is False
    assert "not a file" in result.error.lower()

  def test_read_permission_denied(self, tmp_path: Path, monkeypatch) -> None:
    """ReadTool returns sanitized error on permission denied."""
    file_path = tmp_path / "secret.txt"
    file_path.write_text("secret")

    def mock_read_text(*args, **kwargs):
      raise PermissionError("Access denied")

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    tool = ReadTool()
    result = tool.execute(path=str(file_path))
    assert result.success is False
    assert "permission denied" in result.error.lower()
    assert str(file_path) not in result.error

  def test_read_non_string_path_without_guardrail(self) -> None:
    """ReadTool handles non-string path parameters gracefully."""
    tool = ReadTool()
    result = tool.execute(path=None)
    assert result.success is False
    assert result.error == "Invalid path parameter"

  def test_read_non_string_path_int(self) -> None:
    """ReadTool handles integer path parameter gracefully."""
    tool = ReadTool()
    result = tool.execute(path=123)
    assert result.success is False
    assert result.error == "Invalid path parameter"

  def test_read_symlink_inside_allowed_with_guardrail(self, tmp_path: Path) -> None:
    """ReadTool rejects symlinks even when pointing inside allowed paths."""
    target = tmp_path / "target.txt"
    target.write_text("allowed target")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    guardrail = FakeGuardrail(allow=True)
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(link))
    # Tool layer rejects symlinks before guardrail allows
    assert result.success is False
    assert "symlink" in result.error.lower()

  def test_read_oserror_during_read_text(self, tmp_path: Path, monkeypatch) -> None:
    """ReadTool handles OSError during read_text gracefully."""
    file_path = tmp_path / "device.txt"
    file_path.write_text("data")

    def mock_read_text(*args, **kwargs):
      raise OSError("device error")

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    tool = ReadTool()
    result = tool.execute(path=str(file_path))
    assert result.success is False
    assert "error reading file" in result.error.lower()
    assert str(file_path) not in result.error

  def test_read_empty_path_without_guardrail(self) -> None:
    """ReadTool handles empty path without guardrail."""
    tool = ReadTool()
    result = tool.execute(path="")
    assert result.success is False
    assert result.error == "Path is not a file"
