"""Tests for tool-specific validators (operational constraints).

These validators run after the generic guardrail passes and check
tool-specific constraints like file size, content size, diff size,
and directory depth.
"""

from pathlib import Path

from yoker.builtin._validators import (
  validate_mkdir_depth,
  validate_read_file_size,
  validate_update_diff_size,
  validate_write_content_size,
)
from yoker.config import (
  Config,
  MkdirToolConfig,
  PermissionsConfig,
  ReadToolConfig,
  ToolsConfig,
  UpdateToolConfig,
  WriteToolConfig,
)


def _make_config(
  *,
  read: ReadToolConfig | None = None,
  write: WriteToolConfig | None = None,
  update: UpdateToolConfig | None = None,
  mkdir: MkdirToolConfig | None = None,
) -> Config:
  return Config(
    enabled=True,
    permissions=PermissionsConfig(filesystem_paths=(".", "plugin://")),
    tools=ToolsConfig(
      read=read or ReadToolConfig(),
      write=write or WriteToolConfig(),
      update=update or UpdateToolConfig(),
      mkdir=mkdir or MkdirToolConfig(),
    ),
  )


class TestValidateReadFileSize:
  def test_small_file_passes(self, tmp_path: Path) -> None:
    target = tmp_path / "small.txt"
    target.write_text("hello")
    config = ReadToolConfig(max_file_size_kb=500)
    result = validate_read_file_size({"path": str(target)}, config)
    assert result.valid is True

  def test_large_file_blocked(self, tmp_path: Path) -> None:
    target = tmp_path / "large.txt"
    target.write_text("x" * (2048 * 1024))  # 2MB
    config = ReadToolConfig(max_file_size_kb=1)
    result = validate_read_file_size({"path": str(target)}, config)
    assert result.valid is False
    assert "size limit" in (result.reason or "")

  def test_plugin_url_skipped(self) -> None:
    config = ReadToolConfig(max_file_size_kb=1)
    result = validate_read_file_size({"path": "plugin://yoker/skills/foo.md"}, config)
    assert result.valid is True

  def test_nonexistent_file_passes(self) -> None:
    config = ReadToolConfig(max_file_size_kb=1)
    result = validate_read_file_size({"path": "/nonexistent/file.txt"}, config)
    assert result.valid is True


class TestValidateWriteContentSize:
  def test_small_content_passes(self) -> None:
    config = WriteToolConfig(max_size_kb=1000)
    result = validate_write_content_size({"content": "hello"}, config)
    assert result.valid is True

  def test_large_content_blocked(self) -> None:
    config = WriteToolConfig(max_size_kb=1)
    result = validate_write_content_size({"content": "x" * (2048 * 1024)}, config)
    assert result.valid is False
    assert "size limit" in (result.reason or "")


class TestValidateUpdateDiffSize:
  def test_small_diff_passes(self) -> None:
    config = UpdateToolConfig(max_diff_size_kb=100)
    result = validate_update_diff_size({"new_string": "hello"}, config)
    assert result.valid is True

  def test_large_diff_blocked(self) -> None:
    config = UpdateToolConfig(max_diff_size_kb=1)
    result = validate_update_diff_size({"new_string": "x" * (2048 * 1024)}, config)
    assert result.valid is False
    assert "exceeds limit" in (result.reason or "")


class TestValidateMkdirDepth:
  def test_shallow_path_passes(self) -> None:
    config = MkdirToolConfig(max_depth=20)
    result = validate_mkdir_depth({"path": "/tmp/test"}, config)
    assert result.valid is True

  def test_deep_path_blocked(self) -> None:
    config = MkdirToolConfig(max_depth=2)
    deep_path = "/a/b/c/d/e/f/g/h"
    result = validate_mkdir_depth({"path": deep_path}, config)
    assert result.valid is False
    assert "depth" in (result.reason or "")

  def test_zero_limit_skips_check(self) -> None:
    config = MkdirToolConfig(max_depth=0)
    result = validate_mkdir_depth({"path": "/a/b/c/d/e"}, config)
    assert result.valid is True
