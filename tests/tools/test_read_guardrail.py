"""Integration tests for ReadTool with real PathGuardrail.

Tests that ReadTool properly integrates with PathGuardrail for
path traversal prevention, blocked patterns, extension filtering,
and size limits.
"""

from pathlib import Path

import pytest

from yoker.config.schema import (
  AgentToolConfig,
  Config,
  GitToolConfig,
  ListToolConfig,
  PermissionsConfig,
  ReadToolConfig,
  SearchToolConfig,
  ToolsConfig,
  UpdateToolConfig,
  WriteToolConfig,
)
from yoker.tools import ReadTool
from yoker.tools.path_guardrail import PathGuardrail


class TestReadToolGuardrailIntegration:
  """Integration tests for ReadTool with PathGuardrail."""

  @pytest.fixture
  def restricted_config(self, tmp_path: Path) -> Config:
    """Create a config with restricted filesystem access."""
    return Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        max_file_size_kb=10,
      ),
      tools=ToolsConfig(
        list=ListToolConfig(enabled=True, max_depth=5, max_entries=2000),
        read=ReadToolConfig(
          enabled=True,
          allowed_extensions=(".txt", ".md"),
          blocked_patterns=(r"\.env", "secret"),
        ),
        write=WriteToolConfig(
          enabled=True, allow_overwrite=False, max_size_kb=1000, blocked_extensions=(".exe",)
        ),
        update=UpdateToolConfig(enabled=True, require_exact_match=True, max_diff_size_kb=100),
        search=SearchToolConfig(
          enabled=True, max_regex_complexity="medium", max_results=500, timeout_ms=10000
        ),
        agent=AgentToolConfig(enabled=True, max_recursion_depth=3, timeout_seconds=300),
        git=GitToolConfig(enabled=True, allowed_commands=("status",), requires_permission=("commit",)),
      ),
    )

  @pytest.fixture
  def guardrail(self, restricted_config: Config) -> PathGuardrail:
    """Create a PathGuardrail from restricted config."""
    return PathGuardrail(restricted_config)

  def test_allowed_path_allows(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """ReadTool allows files within allowed paths."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "hello world"

  def test_path_traversal_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """ReadTool blocks path traversal outside allowed paths."""
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(tmp_path / ".." / ".." / "etc" / "passwd"))
    assert result.success is False
    assert "outside allowed" in result.error.lower()

  def test_blocked_pattern_env_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """ReadTool blocks files matching blocked patterns."""
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=abc")
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(env_file))
    assert result.success is False
    assert "blocked" in result.error.lower()

  def test_blocked_pattern_secret_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """ReadTool blocks files with 'secret' in name."""
    secret_file = tmp_path / "secrets.txt"
    secret_file.write_text("top secret")
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(secret_file))
    assert result.success is False
    assert "blocked" in result.error.lower()

  def test_extension_filtering_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """ReadTool blocks files with disallowed extensions."""
    pem_file = tmp_path / "key.pem"
    pem_file.write_text("-----BEGIN KEY-----")
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(pem_file))
    assert result.success is False
    assert "extension" in result.error.lower()

  def test_extension_filtering_allowed(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """ReadTool allows files with allowed extensions."""
    md_file = tmp_path / "readme.md"
    md_file.write_text("# Hello")
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(md_file))
    assert result.success is True
    assert result.result == "# Hello"

  def test_size_limit_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """ReadTool blocks files exceeding size limit."""
    large_file = tmp_path / "large.txt"
    large_file.write_text("x" * 20 * 1024)  # 20KB > 10KB limit
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(large_file))
    assert result.success is False
    assert "size" in result.error.lower()

  def test_symlink_outside_root_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """ReadTool blocks symlinks pointing outside allowed paths."""
    # Create a file outside the allowed root
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside content")
    # Create a symlink inside the allowed root pointing outside
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path=str(link))
    # Tool-layer blocks symlinks before guardrail even runs
    assert result.success is False
    assert "symlink" in result.error.lower()

  def test_absolute_path_outside_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """ReadTool blocks absolute paths outside allowed directories."""
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path="/etc/passwd")
    assert result.success is False
    assert "outside allowed" in result.error.lower()

  def test_empty_path_blocked(self, guardrail: PathGuardrail) -> None:
    """ReadTool blocks empty path parameter."""
    tool = ReadTool(guardrail=guardrail)
    result = tool.execute(path="")
    assert result.success is False

  def test_no_guardrail_tool_validates_internally(self, tmp_path: Path) -> None:
    """ReadTool without guardrail still validates path existence and symlinks."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello")
    tool = ReadTool()  # No guardrail
    result = tool.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "hello"
