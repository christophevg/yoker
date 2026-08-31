"""Security-focused tests for PathGuardrail permission system.

These tests attempt to find bypasses and security holes in the three-layer
permission system:
1. filesystem_paths (allowlist)
2. blocked_paths (remove from read+write)
3. blocked_write_paths (remove from write only)

Tests cover:
- Path traversal attacks
- Glob pattern bypasses
- Unicode/special character tricks
- Symlink attacks
- Case sensitivity issues
- Race conditions (TOCTOU)
- Tool-specific bypasses
- Edge cases in path normalization
"""

import os
from pathlib import Path

import pytest

from yoker.config import Config, PermissionsConfig
from yoker.tools.guardrails.path import ReadPathGuardrail, WritePathGuardrail


class TestPathTraversalAttacks:
  """Test path traversal bypass attempts."""

  def test_double_dot_traversal(self, tmp_path: Path) -> None:
    """Basic ../ traversal should be blocked."""
    outside_file = tmp_path.parent / "outside.txt"
    outside_file.write_text("secret")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # Try to escape via traversal
    malicious = str(tmp_path / ".." / "outside.txt")
    result = guardrail.validate("read", {"path": malicious})
    assert result.valid is False, "Path traversal should be blocked"

  def test_multiple_traversal_levels(self, tmp_path: Path) -> None:
    """Multiple ../ levels should still be blocked."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    malicious = str(tmp_path / ".." / ".." / ".." / "etc" / "passwd")
    result = guardrail.validate("read", {"path": malicious})
    assert result.valid is False

  def test_traversal_in_middle_of_path(self, tmp_path: Path) -> None:
    """Traversal in middle of path should be normalized and checked."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("ok")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # Path that goes out and back in
    malicious = str(subdir / ".." / "target.txt")
    result = guardrail.validate("read", {"path": malicious})
    # This should be ALLOWED because it resolves within tmp_path
    assert result.valid is True

  def test_traversal_with_encoded_chars(self, tmp_path: Path) -> None:
    """URL-encoded traversal is NOT decoded, so %2e%2e is literal.

    This is actually safe behavior - URL encoding does not bypass traversal checks
    because the path validation uses os.path.realpath() which doesn't decode URLs.
    The path /tmp/xyz/%2e%2e/etc/passwd refers to a literal directory named '%2e%2e',
    not '..'. This test verifies that encoded chars are treated as literals.
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # URL-encoded .. is NOT decoded - it's a literal filename
    malicious = str(tmp_path / "%2e%2e" / "etc" / "passwd")
    result = guardrail.validate("read", {"path": malicious})
    # This is ALLOWED because:
    # 1. %2e%2e is a literal directory name, not traversal
    # 2. The path is within tmp_path (the allowed root)
    # 3. Guardrail doesn't check file existence
    assert result.valid is True, "URL-encoded paths are literals, not traversal"

  def test_absolute_path_escape(self, tmp_path: Path) -> None:
    """Absolute paths outside filesystem_paths should be blocked."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": "/etc/passwd"})
    assert result.valid is False

  def test_tilde_expansion_escape(self, tmp_path: Path) -> None:
    """Tilde expansion should not allow escape from filesystem_paths."""
    # If home is not in filesystem_paths, ~ should be blocked
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # Tilde expands to home, which is outside tmp_path
    result = guardrail.validate("read", {"path": "~/.bashrc"})
    assert result.valid is False

  def test_symlink_to_outside(self, tmp_path: Path) -> None:
    """Symlinks pointing outside allowed paths should be blocked."""
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    symlink = tmp_path / "link.txt"
    try:
      os.symlink(str(outside), str(symlink))
    except OSError:
      pytest.skip("Symlinks not supported on this platform")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(symlink)})
    assert result.valid is False, "Symlinks escaping allowed paths should be blocked"

  def test_nested_symlink_escape(self, tmp_path: Path) -> None:
    """Nested symlinks should still be caught."""
    # Create a chain: link1 -> link2 -> outside
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    link2 = tmp_path / "link2.txt"
    link1 = tmp_path / "link1.txt"
    try:
      os.symlink(str(outside), str(link2))
      os.symlink(str(link2), str(link1))
    except OSError:
      pytest.skip("Symlinks not supported on this platform")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": str(link1)})
    assert result.valid is False


class TestGlobPatternBypasses:
  """Test glob pattern matching edge cases."""

  def test_simple_pattern_only_matches_root(self, tmp_path: Path) -> None:
    """Pattern 'local' only blocks at root level, not nested."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # Root level - should be blocked
    root_local = tmp_path / "local" / "file.txt"
    root_local.parent.mkdir(exist_ok=True)
    root_local.write_text("test")
    result = guardrail.validate("read", {"path": str(root_local)})
    assert result.valid is False, "'local' should block root-level local/"
    # Nested level - should be ALLOWED
    nested = tmp_path / "src" / "local" / "file.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("test")
    result = guardrail.validate("read", {"path": str(nested)})
    assert result.valid is True, "'local' pattern should NOT block nested local/"

  def test_double_star_matches_nested(self, tmp_path: Path) -> None:
    """Pattern **/local blocks at any depth."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_paths=("**/local",),
      )
    )
    guardrail = ReadPathGuardrail(config)
    # Nested should now be blocked
    nested = tmp_path / "src" / "local" / "file.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("test")
    result = guardrail.validate("read", {"path": str(nested)})
    assert result.valid is False, "'**/local' should block nested local/"

  def test_git_pattern_root_only(self, tmp_path: Path) -> None:
    """Pattern '.git' only blocks at root level."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # Root level - blocked
    root_git = tmp_path / ".git" / "config"
    root_git.parent.mkdir(exist_ok=True)
    result = guardrail.validate("read", {"path": str(root_git)})
    assert result.valid is False
    # Nested - allowed
    nested = tmp_path / "subdir" / ".git" / "config"
    nested.parent.mkdir(parents=True)
    result = guardrail.validate("read", {"path": str(nested)})
    assert result.valid is True

  def test_glob_star_matches_extensions(self, tmp_path: Path) -> None:
    """*.exe pattern should match all .exe files."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_paths=("*.exe",),
      )
    )
    guardrail = ReadPathGuardrail(config)
    exe_file = tmp_path / "malware.exe"
    exe_file.write_text("bad")
    result = guardrail.validate("read", {"path": str(exe_file)})
    assert result.valid is False

  def test_double_star_matches_deep_paths(self, tmp_path: Path) -> None:
    """**/*.pem should match .pem files at any depth."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_paths=("**/*.pem",),
      )
    )
    guardrail = ReadPathGuardrail(config)
    deep_pem = tmp_path / "a" / "b" / "c" / "secret.pem"
    deep_pem.parent.mkdir(parents=True)
    deep_pem.write_text("cert")
    result = guardrail.validate("read", {"path": str(deep_pem)})
    assert result.valid is False

  def test_case_insensitive_glob(self, tmp_path: Path) -> None:
    """Glob patterns should be case-insensitive."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_paths=("*.EXE",),  # Uppercase pattern
      )
    )
    guardrail = ReadPathGuardrail(config)
    # Lowercase file should still match
    exe_file = tmp_path / "file.exe"
    exe_file.write_text("test")
    result = guardrail.validate("read", {"path": str(exe_file)})
    assert result.valid is False, "Glob matching should be case-insensitive"

  def test_question_mark_single_char(self, tmp_path: Path) -> None:
    """? should match exactly one character."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_paths=(".env?",),  # Matches .env1, .envA, etc.
      )
    )
    guardrail = ReadPathGuardrail(config)
    # Should match
    env1 = tmp_path / ".env1"
    env1.write_text("test")
    result = guardrail.validate("read", {"path": str(env1)})
    assert result.valid is False
    # Should not match (no extra char)
    env = tmp_path / ".env"
    env.write_text("test")
    result = guardrail.validate("read", {"path": str(env)})
    assert result.valid is True


class TestUnicodeAndSpecialChars:
  """Test Unicode and special character handling."""

  def test_unicode_normalization(self, tmp_path: Path) -> None:
    """Unicode normalization should not create bypasses."""
    # Using composed vs decomposed forms
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # Test with various unicode in path
    unicode_file = tmp_path / "tëst.txt"
    unicode_file.write_text("test")
    result = guardrail.validate("read", {"path": str(unicode_file)})
    assert result.valid is True  # Should be allowed (within tmp_path)

  def test_zero_width_chars(self, tmp_path: Path) -> None:
    """Zero-width characters should not create bypasses."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # Path with zero-width joiner
    zwj_file = tmp_path / "test\u200dfile.txt"
    zwj_file.write_text("test")
    result = guardrail.validate("read", {"path": str(zwj_file)})
    assert result.valid is True  # Within allowed path

  @pytest.mark.parametrize(
    ("description", "path"),
    [
      ("nul in filename", "test\x00.txt"),
      (
        "nul directly after prefix truncates path on Windows",
        str(Path("%TEMP%") / "\x00" / "test.txt"),
      ),
      ("nul spoofing hidden extension", "test.txt\x00.exe"),
      ("bare nul", "\x00"),
    ],
  )
  def test_null_byte_rejected_on_all_platforms(
    self, tmp_path: Path, description: str, path: str
  ) -> None:
    """Null bytes must be rejected identically on every platform.

    Regression test: on Windows, ntpath.realpath() does not raise on
    embedded NULs (the Win32 layer truncates at the NUL), so the path
    slipped through resolution and was accepted. The guardrail must
    reject NULs explicitly instead of relying on POSIX rejection.
    """
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # %TEMP% marker resolves inside tmp_path, so only the NUL itself makes it invalid
    full_path = path.replace("%TEMP%", str(tmp_path))
    result = guardrail.validate("read", {"path": full_path})
    assert result.valid is False, f"{description} must be rejected"

  def test_newline_in_path(self, tmp_path: Path) -> None:
    """Newlines in paths should be handled safely."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    newline_file = tmp_path / "test\ntxt"
    try:
      newline_file.write_text("test")
      result = guardrail.validate("read", {"path": str(newline_file)})
      # Should not crash
      assert result.valid is True  # Within allowed path
    except (OSError, ValueError):
      # Some platforms don't allow newlines in filenames
      pytest.skip("Platform doesn't support newlines in filenames")


class TestEdgeCases:
  """Test edge cases and boundary conditions."""

  def test_empty_path(self, tmp_path: Path) -> None:
    """Empty path should be blocked."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": ""})
    assert result.valid is False

  def test_whitespace_only_path(self, tmp_path: Path) -> None:
    """Whitespace-only path should be blocked."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": "   "})
    assert result.valid is False

  def test_trailing_slash_handling(self, tmp_path: Path) -> None:
    """Trailing slashes should be normalized."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # With trailing slash
    result = guardrail.validate("read", {"path": str(tmp_path) + "/"})
    assert result.valid is True
    # Without trailing slash
    result = guardrail.validate("read", {"path": str(tmp_path)})
    assert result.valid is True

  def test_double_slash_normalization(self, tmp_path: Path) -> None:
    """Double slashes should be normalized."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # Path with double slashes
    result = guardrail.validate("read", {"path": str(tmp_path) + "//subdir//file.txt"})
    # Should normalize and check correctly
    assert result.valid is True

  def test_dot_dot_normalization(self, tmp_path: Path) -> None:
    """./.. should be normalized."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    # Path with ./..
    result = guardrail.validate("read", {"path": str(subdir / "." / ".." / "subdir")})
    assert result.valid is True  # Resolves to tmp_path/subdir

  def test_single_file_in_filesystem_paths(self, tmp_path: Path) -> None:
    """Single file in filesystem_paths should allow only that file."""
    allowed_file = tmp_path / "allowed.txt"
    allowed_file.write_text("ok")
    other_file = tmp_path / "other.txt"
    other_file.write_text("no")
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(allowed_file),)))
    guardrail = ReadPathGuardrail(config)
    # Allowed file
    result = guardrail.validate("read", {"path": str(allowed_file)})
    assert result.valid is True
    # Other file in same directory
    result = guardrail.validate("read", {"path": str(other_file)})
    assert result.valid is False


class TestWriteSpecificAttacks:
  """Test attacks specific to write operations."""

  def test_write_blocked_paths_layer(self, tmp_path: Path) -> None:
    """blocked_write_paths should block writes even if blocked_paths doesn't."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_paths=(),  # No blocked_paths
        blocked_write_paths=("Makefile",),
      )
    )
    guardrail = WritePathGuardrail(config)
    makefile = tmp_path / "Makefile"
    result = guardrail.validate("write", {"path": str(makefile), "content": "test"})
    assert result.valid is False

  def test_write_allowed_if_not_in_blocked_write_paths(self, tmp_path: Path) -> None:
    """Write should be allowed for non-blocked files."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=("Makefile",),
      )
    )
    guardrail = WritePathGuardrail(config)
    txt_file = tmp_path / "test.txt"
    result = guardrail.validate("write", {"path": str(txt_file), "content": "test"})
    assert result.valid is True

  def test_update_respects_blocked_write_paths(self, tmp_path: Path) -> None:
    """Update tool should also respect blocked_write_paths."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=("pyproject.toml",),
      )
    )
    guardrail = WritePathGuardrail(config)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("old")
    result = guardrail.validate(
      "update",
      {"path": str(pyproject), "operation": "replace", "old_string": "old", "new_string": "new"},
    )
    assert result.valid is False

  def test_write_rejects_null_byte(self, tmp_path: Path) -> None:
    """Write guardrail must reject null bytes like the read guardrail."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate(
      "write", {"path": str(tmp_path / "test\x00.txt"), "content": "test"}
    )
    assert result.valid is False

  def test_skip_blocks_bypass(self, tmp_path: Path) -> None:
    """skip_blocks=True should bypass blocked_write_paths check."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=("Makefile",),
      )
    )
    guardrail = WritePathGuardrail(config)
    makefile = tmp_path / "Makefile"
    # Without skip_blocks
    result = guardrail.validate("write", {"path": str(makefile), "content": "test"})
    assert result.valid is False
    # With skip_blocks
    result = guardrail.validate(
      "write", {"path": str(makefile), "content": "test"}, skip_blocks=True
    )
    assert result.valid is True

  def test_empty_blocked_write_paths_disables_protection(self, tmp_path: Path) -> None:
    """Empty blocked_write_paths should disable all write protections."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=(),
      )
    )
    guardrail = WritePathGuardrail(config)
    makefile = tmp_path / "Makefile"
    result = guardrail.validate("write", {"path": str(makefile), "content": "test"})
    assert result.valid is True


class TestMultipleFilesystemPaths:
  """Test with multiple allowed roots."""

  def test_access_to_multiple_roots(self, tmp_path: Path) -> None:
    """Should allow access to all configured filesystem_paths."""
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    root1.mkdir()
    root2.mkdir()
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(root1), str(root2))))
    guardrail = ReadPathGuardrail(config)
    # Both roots should be accessible
    result1 = guardrail.validate("read", {"path": str(root1 / "file.txt")})
    assert result1.valid is True
    result2 = guardrail.validate("read", {"path": str(root2 / "file.txt")})
    assert result2.valid is True

  def test_blocked_paths_applies_to_all_roots(self, tmp_path: Path) -> None:
    """blocked_paths should apply relative to all roots."""
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    root1.mkdir()
    root2.mkdir()
    # Create local in both roots
    (root1 / "local").mkdir()
    (root2 / "local").mkdir()
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(root1), str(root2)),
        blocked_paths=("local",),
      )
    )
    guardrail = ReadPathGuardrail(config)
    # Both should be blocked
    result1 = guardrail.validate("read", {"path": str(root1 / "local" / "file.txt")})
    assert result1.valid is False
    result2 = guardrail.validate("read", {"path": str(root2 / "local" / "file.txt")})
    assert result2.valid is False

  def test_parent_relative_pattern_blocks_across_roots(self, tmp_path: Path) -> None:
    """Parent-relative patterns like ../sibling should block correctly."""
    root1 = tmp_path / "root1"
    sibling = tmp_path / "sibling"
    root1.mkdir()
    sibling.mkdir()
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(root1), str(sibling)),
        blocked_paths=(),
        blocked_write_paths=("../sibling",),
      )
    )
    guardrail = WritePathGuardrail(config)
    # Writing to sibling should be blocked
    sibling_file = sibling / "test.txt"
    result = guardrail.validate("write", {"path": str(sibling_file), "content": "test"})
    assert result.valid is False


class TestReadVsWritePermissions:
  """Test the difference between read and write permissions."""

  def test_read_allowed_write_blocked(self, tmp_path: Path) -> None:
    """File can be readable but not writable."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_write_paths=("Makefile",),
      )
    )
    read_guardrail = ReadPathGuardrail(config)
    write_guardrail = WritePathGuardrail(config)
    makefile = tmp_path / "Makefile"
    makefile.write_text("test")
    # Read should work
    read_result = read_guardrail.validate("read", {"path": str(makefile)})
    assert read_result.valid is True
    # Write should be blocked
    write_result = write_guardrail.validate("write", {"path": str(makefile), "content": "test"})
    assert write_result.valid is False

  def test_both_blocked(self, tmp_path: Path) -> None:
    """File in blocked_paths should block both read and write."""
    config = Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_paths=(".env",),
      )
    )
    read_guardrail = ReadPathGuardrail(config)
    write_guardrail = WritePathGuardrail(config)
    env_file = tmp_path / ".env"
    env_file.write_text("secret")
    # Both should be blocked
    read_result = read_guardrail.validate("read", {"path": str(env_file)})
    assert read_result.valid is False
    write_result = write_guardrail.validate("write", {"path": str(env_file), "content": "test"})
    assert write_result.valid is False


class TestPluginUrls:
  """Test plugin:// URL handling."""

  def test_plugin_url_read_allowed(self) -> None:
    """plugin:// URLs should be allowed for read when configured."""
    config = Config()  # Default includes plugin://
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": "plugin://yoker/builtin/__init__.py"})
    assert result.valid is True

  def test_plugin_url_read_blocked_when_not_configured(self) -> None:
    """plugin:// URLs should be blocked if not in filesystem_paths."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(".",)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("read", {"path": "plugin://yoker/builtin/__init__.py"})
    assert result.valid is False

  def test_plugin_url_write_always_blocked(self) -> None:
    """plugin:// URLs should always be blocked for write."""
    config = Config()
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("write", {"path": "plugin://yoker/builtin/__init__.py"})
    assert result.valid is False


class TestToolSpecificBehavior:
  """Test that different tools are handled correctly."""

  def test_list_tool_uses_read_guardrail(self, tmp_path: Path) -> None:
    """List tool should use read guardrail."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("list", {"path": str(tmp_path)})
    assert result.valid is True

  def test_search_tool_uses_read_guardrail(self, tmp_path: Path) -> None:
    """Search tool should use read guardrail."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("search", {"path": str(tmp_path), "pattern": "test"})
    assert result.valid is True

  def test_existence_tool_uses_read_guardrail(self, tmp_path: Path) -> None:
    """Existence tool should use read guardrail."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = ReadPathGuardrail(config)
    result = guardrail.validate("existence", {"path": str(tmp_path / "file.txt")})
    assert result.valid is True

  def test_mkdir_tool_uses_write_guardrail(self, tmp_path: Path) -> None:
    """Mkdir tool should use write guardrail."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate("mkdir", {"path": str(tmp_path / "newdir")})
    assert result.valid is True

  def test_file_copy_uses_write_guardrail(self, tmp_path: Path) -> None:
    """File copy (destination) should use write guardrail."""
    config = Config(permissions=PermissionsConfig(filesystem_paths=(str(tmp_path),)))
    guardrail = WritePathGuardrail(config)
    result = guardrail.validate(
      "file", {"operation": "copy", "destination": str(tmp_path / "dest.txt")}
    )
    assert result.valid is True
