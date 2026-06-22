"""Integration tests for read tool with real PathGuardrail.

Tests that the read tool integrates with PathGuardrail for
path traversal prevention, blocked patterns, extension filtering,
and size limits. Guardrails are enforced centrally by the harness,
so this module validates the PathGuardrail decisions that the Agent
would apply before calling the read tool.
"""

from pathlib import Path

import pytest

from yoker.builtin import read
from yoker.config import (
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
from yoker.tools import ToolRegistry
from yoker.tools.path_guardrail import PathGuardrail


def _read_spec():
  """Create and register the read tool."""
  registry = ToolRegistry()
  return registry.register(read)


class TestReadToolGuardrailIntegration:
  """Integration tests for read tool with PathGuardrail."""

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
        git=GitToolConfig(
          enabled=True, allowed_commands=("status",), requires_permission=("commit",)
        ),
      ),
    )

  @pytest.fixture
  def guardrail(self, restricted_config: Config) -> PathGuardrail:
    """Create a PathGuardrail from restricted config."""
    return PathGuardrail(restricted_config)

  @pytest.mark.asyncio
  async def test_allowed_path_allows(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """Read tool allows files within allowed paths."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(file_path)})
    assert validation.valid
    result = await spec.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "hello world"

  def test_path_traversal_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """PathGuardrail blocks path traversal outside allowed paths."""
    spec = _read_spec()
    validation = guardrail.validate(
      spec.name, {"path": str(tmp_path / ".." / ".." / "etc" / "passwd")}
    )
    assert not validation.valid
    assert "outside allowed" in (validation.reason or "").lower()

  def test_blocked_pattern_env_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """PathGuardrail blocks files matching blocked patterns."""
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=abc")
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(env_file)})
    assert not validation.valid
    assert "blocked" in (validation.reason or "").lower()

  def test_blocked_pattern_secret_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """PathGuardrail blocks files with 'secret' in name."""
    secret_file = tmp_path / "secrets.txt"
    secret_file.write_text("top secret")
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(secret_file)})
    assert not validation.valid
    assert "blocked" in (validation.reason or "").lower()

  def test_extension_filtering_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """PathGuardrail blocks files with disallowed extensions."""
    pem_file = tmp_path / "key.pem"
    pem_file.write_text("-----BEGIN KEY-----")
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(pem_file)})
    assert not validation.valid
    assert "extension" in (validation.reason or "").lower()

  @pytest.mark.asyncio
  async def test_extension_filtering_allowed(
    self, tmp_path: Path, guardrail: PathGuardrail
  ) -> None:
    """Read tool allows files with allowed extensions."""
    md_file = tmp_path / "readme.md"
    md_file.write_text("# Hello")
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(md_file)})
    assert validation.valid
    result = await spec.execute(path=str(md_file))
    assert result.success is True
    assert result.result == "# Hello"

  def test_size_limit_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """PathGuardrail blocks files exceeding size limit."""
    large_file = tmp_path / "large.txt"
    large_file.write_text("x" * 20 * 1024)  # 20KB > 10KB limit
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(large_file)})
    assert not validation.valid
    assert "size" in (validation.reason or "").lower()

  @pytest.mark.asyncio
  async def test_symlink_outside_root_blocked(
    self, tmp_path: Path, guardrail: PathGuardrail
  ) -> None:
    """Read tool blocks symlinks pointing outside allowed paths."""
    # Create a file outside the allowed root
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside content")
    # Create a symlink inside the allowed root pointing outside
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    spec = _read_spec()
    result = await spec.execute(path=str(link))
    # Tool-layer blocks symlinks before guardrail even runs
    assert result.success is False
    assert "symlink" in result.error.lower()

  def test_absolute_path_outside_blocked(self, tmp_path: Path, guardrail: PathGuardrail) -> None:
    """PathGuardrail blocks absolute paths outside allowed directories."""
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": "/etc/passwd"})
    assert not validation.valid
    assert "outside allowed" in (validation.reason or "").lower()

  def test_empty_path_blocked(self, guardrail: PathGuardrail) -> None:
    """PathGuardrail blocks empty path parameter."""
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": ""})
    assert not validation.valid

  @pytest.mark.asyncio
  async def test_no_guardrail_tool_validates_internally(self, tmp_path: Path) -> None:
    """Read tool without guardrail still validates path existence and symlinks."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello")
    spec = _read_spec()  # No guardrail
    result = await spec.execute(path=str(file_path))
    assert result.success is True
    assert result.result == "hello"
