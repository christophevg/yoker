"""Tests for PathGuardrail implementation."""

import os
from pathlib import Path

from yoker.config.schema import (
  Config,
  PermissionsConfig,
  ReadToolConfig,
  ToolsConfig,
  UpdateToolConfig,
  WriteToolConfig,
)
from yoker.tools.path_guardrail import PathGuardrail


class TestPathGuardrail:
  """Tests for PathGuardrail."""

  def test_non_filesystem_tool_allowed(self) -> None:
    """Non-filesystem tools pass through without path validation."""
    config = Config()
    guardrail = PathGuardrail(config)
    result = guardrail.validate("agent", {"prompt": "hello"})
    assert result.valid is True

  def test_missing_path_parameter(self) -> None:
    """Blocks when path parameter is missing."""
    config = Config()
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {})
    assert result.valid is False
    assert "missing" in result.reason.lower()

  def test_invalid_path_type(self) -> None:
    """Blocks when path is not a string."""
    config = Config()
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": 123})
    assert result.valid is False
    assert "must be a string" in result.reason.lower()

  def test_empty_path(self) -> None:
    """Blocks when path is empty string."""
    config = Config()
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": "  "})
    assert result.valid is False
    assert "cannot be empty" in result.reason.lower()

  def test_path_traversal_blocked(self, tmp_path: Path) -> None:
    """Blocks path traversal attempts."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    malicious = str(tmp_path / ".." / ".." / "etc" / "passwd")
    result = guardrail.validate("read", {"path": malicious})
    assert result.valid is False
    assert "outside allowed" in result.reason.lower()

  def test_allowed_path_permitted(self, tmp_path: Path) -> None:
    """Allows paths within allowed directories."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": str(test_file)})
    assert result.valid is True

  def test_blocked_pattern_match(self, tmp_path: Path) -> None:
    """Blocks paths matching blocked patterns."""
    env_file = tmp_path / "config.env"
    env_file.write_text("secret")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(
        read=ReadToolConfig(
          blocked_patterns=(r"\.env",),
          allowed_extensions=(".txt", ".md", ".env"),
        )
      ),
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": str(env_file)})
    assert result.valid is False
    assert "blocked pattern" in result.reason.lower()

  def test_extension_filtering_blocked(self, tmp_path: Path) -> None:
    """Blocks read of files with disallowed extensions."""
    exe_file = tmp_path / "malware.exe"
    exe_file.write_text("bad")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(allowed_extensions=(".txt", ".md"))),
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": str(exe_file)})
    assert result.valid is False
    assert "extension not allowed" in result.reason.lower()

  def test_extension_filtering_allowed(self, tmp_path: Path) -> None:
    """Allows read of files with allowed extensions."""
    txt_file = tmp_path / "readme.txt"
    txt_file.write_text("hello")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(read=ReadToolConfig(allowed_extensions=(".txt", ".md"))),
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": str(txt_file)})
    assert result.valid is True

  def test_file_size_limit(self, tmp_path: Path) -> None:
    """Blocks read of files exceeding size limit."""
    big_file = tmp_path / "big.txt"
    big_file.write_text("x" * 2048)  # 2KB
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        max_file_size_kb=1,
      )
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": str(big_file)})
    assert result.valid is False
    assert "exceeds size limit" in result.reason.lower()

  def test_file_size_within_limit(self, tmp_path: Path) -> None:
    """Allows read of files within size limit."""
    small_file = tmp_path / "small.txt"
    small_file.write_text("x" * 512)  # 0.5KB
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        max_file_size_kb=1,
      )
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": str(small_file)})
    assert result.valid is True

  def test_nonexistent_read_blocked(self, tmp_path: Path) -> None:
    """Blocks read of nonexistent files."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    missing = str(tmp_path / "missing.txt")
    result = guardrail.validate("read", {"path": missing})
    assert result.valid is False
    assert "not found" in result.reason.lower()

  def test_symlink_escape_blocked(self, tmp_path: Path) -> None:
    """Blocks symlinks that resolve outside allowed paths."""
    outside = tmp_path / ".." / "outside.txt"
    outside.write_text("secret")
    symlink = tmp_path / "link.txt"
    os.symlink(str(outside), str(symlink))
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": str(symlink)})
    assert result.valid is False
    assert "outside allowed" in result.reason.lower()

  def test_symlink_within_allowed(self, tmp_path: Path) -> None:
    """Allows symlinks that resolve within allowed paths."""
    target = tmp_path / "target.txt"
    target.write_text("hello")
    symlink = tmp_path / "link.txt"
    os.symlink(str(target), str(symlink))
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("read", {"path": str(symlink)})
    assert result.valid is True

  def test_list_tool_allowed(self, tmp_path: Path) -> None:
    """List tool is validated for path access."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("list", {"path": str(tmp_path)})
    assert result.valid is True

  def test_write_tool_allowed(self, tmp_path: Path) -> None:
    """Write tool is validated for path access."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(tmp_path / "new.txt")})
    assert result.valid is True

  def test_write_blocked_extension(self, tmp_path: Path) -> None:
    """Blocks write of files with blocked extensions."""
    exe_file = tmp_path / "malware.exe"
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(write=WriteToolConfig(blocked_extensions=(".exe", ".sh"))),
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(exe_file), "content": "bad"})
    assert result.valid is False
    assert "extension blocked" in result.reason.lower()

  def test_write_allowed_extension(self, tmp_path: Path) -> None:
    """Allows write of files with non-blocked extensions."""
    txt_file = tmp_path / "readme.txt"
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(write=WriteToolConfig(blocked_extensions=(".exe", ".sh"))),
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(txt_file), "content": "hello"})
    assert result.valid is True

  def test_write_content_size_limit(self, tmp_path: Path) -> None:
    """Blocks write when content exceeds size limit."""
    file_path = tmp_path / "big.txt"
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(write=WriteToolConfig(max_size_kb=1)),
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(file_path), "content": "x" * 2048})
    assert result.valid is False
    assert "exceeds size limit" in result.reason.lower()

  def test_write_content_within_limit(self, tmp_path: Path) -> None:
    """Allows write when content is within size limit."""
    file_path = tmp_path / "small.txt"
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(write=WriteToolConfig(max_size_kb=1)),
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate("write", {"path": str(file_path), "content": "x" * 512})
    assert result.valid is True

  def test_update_tool_allowed(self, tmp_path: Path) -> None:
    """Update tool is validated for path access."""
    target = tmp_path / "existing.txt"
    target.write_text("hello")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("update", {"path": str(target)})
    assert result.valid is True

  def test_update_nonexistent_file_blocked(self, tmp_path: Path) -> None:
    """Update tool blocked when file does not exist."""
    target = tmp_path / "missing.txt"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("update", {"path": str(target)})
    assert result.valid is False
    assert "not found" in result.reason.lower()

  def test_update_directory_blocked(self, tmp_path: Path) -> None:
    """Update tool blocked when path is a directory."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("update", {"path": str(subdir)})
    assert result.valid is False
    assert "not a file" in result.reason.lower()

  def test_update_blocked_extension(self, tmp_path: Path) -> None:
    """Update tool blocked for write-blocked extensions."""
    target = tmp_path / "script.exe"
    target.write_text("hello")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    result = guardrail.validate("update", {"path": str(target)})
    assert result.valid is False
    assert ".exe" in result.reason.lower()

  def test_update_diff_size_exceeded(self, tmp_path: Path) -> None:
    """Update tool blocked when diff size exceeds limit."""
    target = tmp_path / "test.txt"
    target.write_text("hello")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(update=UpdateToolConfig(max_diff_size_kb=1)),
    )
    guardrail = PathGuardrail(config)
    large_string = "a" * 2048
    result = guardrail.validate(
      "update",
      {"path": str(target), "new_string": large_string},
    )
    assert result.valid is False
    assert "exceeds limit" in result.reason.lower()

  def test_update_diff_size_within_limit(self, tmp_path: Path) -> None:
    """Update tool allowed when diff size within limit."""
    target = tmp_path / "test.txt"
    target.write_text("hello")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
      tools=ToolsConfig(update=UpdateToolConfig(max_diff_size_kb=100)),
    )
    guardrail = PathGuardrail(config)
    result = guardrail.validate(
      "update",
      {"path": str(target), "new_string": "replacement"},
    )
    assert result.valid is True

  def test_relative_path_resolved(self, tmp_path: Path) -> None:
    """Relative paths are resolved against cwd and validated."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    test_file = subdir / "test.txt"
    test_file.write_text("hello")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = PathGuardrail(config)
    # Use relative path from within allowed root
    result = guardrail.validate("read", {"path": str(test_file)})
    assert result.valid is True
