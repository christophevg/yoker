"""Tests for ReadPathGuardrail and WritePathGuardrail implementation."""

import os
from pathlib import Path

import pytest

from yoker.config import (
  Config,
  PermissionsConfig,
)
from yoker.tools.guardrails.path import ReadPathGuardrail, WritePathGuardrail


class TestReadPathGuardrail:
  """Tests for ReadPathGuardrail."""

  def test_non_filesystem_tool_allowed(self) -> None:
    """The guardrail only receives Path-annotated parameters.

    With the hardcoded _FILESYSTEM_TOOLS list removed, the guardrail no
    longer gates on tool name. It always validates the path parameter it
    receives. A dict without a 'path' key is rejected (missing path).
    This is correct: the guardrail is only invoked for Path-annotated
    parameters, so a non-filesystem tool like 'agent' would never reach
    the ReadPathGuardrail.
    """
    config = Config()
    guardrail = ReadPathGuardrail(config)
    # A dict without 'path' → missing path parameter (not a non-filesystem skip)
    result = guardrail.validate("agent", {"prompt": "hello"})
    assert result.valid is False
    assert "path" in (result.reason or "").lower()

  def test_missing_path_parameter(self) -> None:
    """Blocks when path parameter is missing."""
    config = Config()
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {})
    assert result.valid is False
    assert "empty" in result.reason.lower()

  def test_invalid_path_type(self) -> None:
    """Blocks when path is not a string."""
    config = Config()
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": 123})
    assert result.valid is False

  def test_empty_path(self) -> None:
    """Blocks when path is empty string."""
    config = Config()
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": "  "})
    assert result.valid is False
    assert "cannot be empty" in result.reason.lower()

  def test_path_traversal_blocked(self, tmp_path: Path) -> None:
    """Blocks path traversal attempts."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    malicious = str(tmp_path / ".." / ".." / "etc" / "passwd")
    result = guardrail.validate("read", {"path": malicious})
    assert result.valid is False
    assert "outside allowed" in result.reason.lower()

  def test_allowed_path_permitted(self, tmp_path: Path) -> None:
    """Allows paths within allowed directories."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(test_file)})
    assert result.valid is True

  def test_blocked_pattern_match(self, tmp_path: Path) -> None:
    """Blocks paths matching blocked_paths glob patterns."""
    env_file = tmp_path / ".env"
    env_file.write_text("secret")
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_paths=(".env", ".env.*"),
      ),
    )
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(env_file)})
    assert result.valid is False
    assert "blocked pattern" in result.reason.lower()

  def test_nonexistent_read_allowed(self, tmp_path: Path) -> None:
    """Nonexistent files within allowed paths are allowed by the guardrail.

    The guardrail uses os.path.realpath which normalizes any string; it
    doesn't check existence. The read tool itself checks existence.
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    missing = str(tmp_path / "missing.txt")
    result = guardrail.validate("read", {"path": missing})
    assert result.valid is True

  def test_symlink_escape_blocked(self, tmp_path: Path) -> None:
    """Blocks symlinks that resolve outside allowed paths."""
    outside = tmp_path / ".." / "outside.txt"
    outside.write_text("secret")
    symlink = tmp_path / "link.txt"
    try:
      os.symlink(str(outside), str(symlink))
    except OSError:
      pytest.skip("Symlinks not supported on this platform")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(symlink)})
    assert result.valid is False
    assert "outside allowed" in result.reason.lower()

  def test_symlink_within_allowed(self, tmp_path: Path) -> None:
    """Allows symlinks that resolve within allowed paths."""
    target = tmp_path / "target.txt"
    target.write_text("hello")
    symlink = tmp_path / "link.txt"
    try:
      os.symlink(str(target), str(symlink))
    except OSError:
      pytest.skip("Symlinks not supported on this platform")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(symlink)})
    assert result.valid is True

  def test_list_tool_allowed(self, tmp_path: Path) -> None:
    """List tool is validated for path access."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("list", {"path": str(tmp_path)})
    assert result.valid is True

  def test_relative_path_resolved(self, tmp_path: Path) -> None:
    """Relative paths are resolved against cwd and validated."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    test_file = subdir / "test.txt"
    test_file.write_text("hello")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(test_file)})
    assert result.valid is True

  def test_individual_file_path_allowed(self, tmp_path: Path) -> None:
    """A single file in filesystem_paths allows access to that file only."""
    allowed_file = tmp_path / "VOICE.md"
    allowed_file.write_text("hello")
    other_file = tmp_path / "OTHER.md"
    other_file.write_text("world")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(allowed_file),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(allowed_file)})
    assert result.valid is True
    result = guardrail.validate("read", {"path": str(other_file)})
    assert result.valid is False
    assert "outside allowed" in result.reason

  def test_tilde_expansion_in_filesystem_paths(self, tmp_path: Path) -> None:
    """~ in filesystem_paths is expanded to the user's home directory."""
    home = Path.home()
    test_file = home / ".yoker_test_tilde_expand.md"
    test_file.write_text("test")
    try:
      config = Config(
        permissions=PermissionsConfig(filesystem_paths=("~/.yoker_test_tilde_expand.md",))
      )
      guardrail = ReadPathGuardrail(config)
      result = guardrail.validate("read", {"path": str(test_file)})
      assert result.valid is True
    finally:
      test_file.unlink(missing_ok=True)

  def test_tilde_expansion_with_directory(self, tmp_path: Path) -> None:
    """~ in a directory path is expanded and allows files beneath it."""
    home = Path.home()
    test_dir = home / ".yoker_test_tilde_dir"
    test_dir.mkdir(exist_ok=True)
    test_file = test_dir / "note.md"
    test_file.write_text("test")
    try:
      config = Config(permissions=PermissionsConfig(filesystem_paths=("~/.yoker_test_tilde_dir",)))
      guardrail = ReadPathGuardrail(config)
      result = guardrail.validate("read", {"path": str(test_file)})
      assert result.valid is True
    finally:
      test_file.unlink(missing_ok=True)
      test_dir.rmdir()

  def test_default_blocked_patterns_dont_block_gitignore(self, tmp_path: Path) -> None:
    """Default blocked_paths must not block .gitignore, .gitconfig, etc.

    The .git glob pattern matches the .git directory itself, not .gitignore.
    """
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("node_modules/\n")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
    )
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(gitignore)})
    assert result.valid is True

  def test_default_blocked_patterns_block_git_directory(self, tmp_path: Path) -> None:
    """Default blocked_paths block the .git directory itself."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
    )
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(git_dir)})
    assert result.valid is False
    assert "blocked pattern" in result.reason.lower()

  def test_default_blocked_patterns_block_env_file(self, tmp_path: Path) -> None:
    """Default blocked_paths still block .env files."""
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=abc\n")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
    )
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(env_file)})
    assert result.valid is False
    assert "blocked pattern" in result.reason.lower()

  def test_default_blocked_patterns_block_env_local(self, tmp_path: Path) -> None:
    """Default blocked_paths still block .env.local files."""
    env_local = tmp_path / ".env.local"
    env_local.write_text("SECRET=abc\n")
    config = Config(
      permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)),
    )
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(env_local)})
    assert result.valid is False
    assert "blocked pattern" in result.reason.lower()

  def test_plugin_url_allowed(self) -> None:
    """plugin:// URLs are allowed when plugin:// is in filesystem_paths."""
    config = Config()
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": "plugin://yoker/builtin/__init__.py"})
    assert result.valid is True

  def test_plugin_url_not_allowed(self) -> None:
    """plugin:// URLs are blocked when plugin:// is not in filesystem_paths."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(".",)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": "plugin://yoker/builtin/__init__.py"})
    assert result.valid is False
    assert "plugin" in result.reason.lower()


class TestWritePathGuardrail:
  """Tests for WritePathGuardrail."""

  def test_write_tool_allowed(self, tmp_path: Path) -> None:
    """Write tool is validated for path access."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(tmp_path / "new.txt")})
    assert result.valid is True

  def test_update_tool_allowed(self, tmp_path: Path) -> None:
    """Update tool is validated for path access."""
    target = tmp_path / "existing.txt"
    target.write_text("hello")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("update", {"path": str(target)})
    assert result.valid is True

  def test_write_blocked_by_blocked_write_paths(self, tmp_path: Path) -> None:
    """Write tool blocked for files matching blocked_write_paths."""
    exe_file = tmp_path / "malware.exe"
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=("*.exe",),
      ),
    )
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(exe_file), "content": "bad"})
    assert result.valid is False
    assert "write-protected" in result.reason.lower()

  def test_write_allowed_non_blocked(self, tmp_path: Path) -> None:
    """Allows write of files not matching blocked_write_paths."""
    txt_file = tmp_path / "readme.txt"
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=("*.exe", "*.sh"),
      ),
    )
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(txt_file), "content": "hello"})
    assert result.valid is True

  def test_write_makefile_blocked_by_default(self, tmp_path: Path) -> None:
    """Makefile is blocked by default blocked_write_paths."""
    makefile = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(makefile), "content": "x"})
    assert result.valid is False
    assert "write-protected" in result.reason.lower()

  def test_skip_blocks_allows_write(self, tmp_path: Path) -> None:
    """skip_blocks=True skips blocked_write_paths check."""
    makefile = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(makefile), "content": "x"}, skip_blocks=True)
    assert result.valid is True

  def test_skip_blocks_allows_update(self, tmp_path: Path) -> None:
    """skip_blocks=True skips blocked_write_paths check for update."""
    target = tmp_path / "pyproject.toml"
    target.write_text("old")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate(
      "update",
      {"path": str(target), "operation": "replace", "old_string": "old", "new_string": "new"},
      skip_blocks=True,
    )
    assert result.valid is True

  def test_empty_blocked_write_paths_disables(self, tmp_path: Path) -> None:
    """Empty blocked_write_paths disables all write protections."""
    target = tmp_path / "Makefile"
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=(),
      )
    )
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": str(target), "content": "x"})
    assert result.valid is True

  def test_empty_blocked_write_paths_disables_update(self, tmp_path: Path) -> None:
    """Empty blocked_write_paths disables update protections."""
    target = tmp_path / "pyproject.toml"
    target.write_text("old")
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=(),
      )
    )
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate(
      "update",
      {"path": str(target), "operation": "replace", "old_string": "old", "new_string": "new"},
    )
    assert result.valid is True

  def test_is_write_blocked_true_for_makefile(self, tmp_path: Path) -> None:
    """is_write_blocked returns True for blocked_write_paths entries."""
    target = tmp_path / "Makefile"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    assert guardrail.is_write_blocked(str(target)) is True

  def test_is_write_blocked_false_for_normal_file(self, tmp_path: Path) -> None:
    """is_write_blocked returns False for non-blocked files."""
    target = tmp_path / "foo.txt"
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    assert guardrail.is_write_blocked(str(target)) is False

  def test_is_write_blocked_respects_empty_list(self, tmp_path: Path) -> None:
    """is_write_blocked returns False when blocked_write_paths is empty."""
    target = tmp_path / "Makefile"
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=(),
      )
    )
    guardrail = WritePathGuardrail(config)
    assert guardrail.is_write_blocked(str(target)) is False

  def test_read_never_triggers_write_blocks(self, tmp_path: Path) -> None:
    """ReadPathGuardrail doesn't check blocked_write_paths."""
    target = tmp_path / "Makefile"
    target.write_text("all:")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(target)})
    assert result.valid is True

  def test_plugin_url_blocked_for_write(self) -> None:
    """plugin:// URLs are not supported for write operations."""
    config = Config()
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": "plugin://yoker/builtin/__init__.py"})
    assert result.valid is False
    assert "plugin" in result.reason.lower()
