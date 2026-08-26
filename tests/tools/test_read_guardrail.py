"""Integration tests for read tool with real ReadPathGuardrail.

Tests that the read tool integrates with ReadPathGuardrail for
path traversal prevention, blocked patterns, and plugin URL handling.
Guardrails are enforced centrally by the harness, so this module
validates the ReadPathGuardrail decisions that the Agent would apply
before calling the read tool.
"""

from pathlib import Path

import pytest

from yoker.builtin import read
from yoker.config import (
  Config,
  PermissionsConfig,
)
from yoker.tools import ToolContext, ToolRegistry
from yoker.tools.guardrails.path import ReadPathGuardrail


def _read_spec():
  """Create and register the read tool."""
  registry = ToolRegistry()
  return registry.register(read)


def _mock_ctx() -> ToolContext:
  """Create a mock ToolContext for testing."""
  from yoker.config import ToolConfig, ToolsSharedConfig

  return ToolContext(
    config=ToolConfig(),
    shared=ToolsSharedConfig(),
    backends={},
  )


class TestReadToolGuardrailIntegration:
  """Integration tests for read tool with ReadPathGuardrail."""

  @pytest.fixture
  def restricted_config(self, tmp_path: Path) -> Config:
    """Create a config with restricted filesystem access."""
    return Config(
      permissions=PermissionsConfig(
        filesystem_paths=(str(tmp_path),),
        blocked_paths=(".env", "secret*"),
      ),
    )

  @pytest.fixture
  def guardrail(self, restricted_config: Config) -> ReadPathGuardrail:
    """Create a ReadPathGuardrail from restricted config."""
    return ReadPathGuardrail(restricted_config)

  @pytest.mark.asyncio
  async def test_allowed_path_allows(self, tmp_path: Path, guardrail: ReadPathGuardrail) -> None:
    """Read tool allows files within allowed paths."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(file_path)})
    assert validation.valid
    result = await spec.execute(path=str(file_path), ctx=_mock_ctx())
    assert result.success is True
    assert result.result == "hello world"

  def test_path_traversal_blocked(self, tmp_path: Path, guardrail: ReadPathGuardrail) -> None:
    """ReadPathGuardrail blocks path traversal outside allowed paths."""
    spec = _read_spec()
    validation = guardrail.validate(
      spec.name, {"path": str(tmp_path / ".." / ".." / "etc" / "passwd")}
    )
    assert not validation.valid
    assert "outside allowed" in (validation.reason or "").lower()

  def test_blocked_pattern_env_blocked(self, tmp_path: Path, guardrail: ReadPathGuardrail) -> None:
    """ReadPathGuardrail blocks files matching blocked_paths glob patterns."""
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=abc")
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(env_file)})
    assert not validation.valid
    assert "blocked" in (validation.reason or "").lower()

  def test_blocked_pattern_secret_blocked(
    self, tmp_path: Path, guardrail: ReadPathGuardrail
  ) -> None:
    """ReadPathGuardrail blocks files with 'secret' in name."""
    secret_file = tmp_path / "secrets.txt"
    secret_file.write_text("top secret")
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": str(secret_file)})
    assert not validation.valid
    assert "blocked" in (validation.reason or "").lower()

  @pytest.mark.asyncio
  async def test_symlink_outside_root_blocked(
    self, tmp_path: Path, guardrail: ReadPathGuardrail
  ) -> None:
    """Read tool blocks symlinks pointing outside allowed paths."""
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside content")
    link = tmp_path / "link.txt"
    try:
      link.symlink_to(outside)
    except OSError:
      pytest.skip("Symlinks not supported on this platform")
    spec = _read_spec()
    result = await spec.execute(path=str(link), ctx=_mock_ctx())
    assert result.success is False
    assert "symlink" in result.error.lower()

  def test_absolute_path_outside_blocked(
    self, tmp_path: Path, guardrail: ReadPathGuardrail
  ) -> None:
    """ReadPathGuardrail blocks absolute paths outside allowed directories."""
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": "/etc/passwd"})
    assert not validation.valid
    assert "outside allowed" in (validation.reason or "").lower()

  def test_empty_path_blocked(self, guardrail: ReadPathGuardrail) -> None:
    """ReadPathGuardrail blocks empty path parameter."""
    spec = _read_spec()
    validation = guardrail.validate(spec.name, {"path": ""})
    assert not validation.valid

  @pytest.mark.asyncio
  async def test_no_guardrail_tool_validates_internally(self, tmp_path: Path) -> None:
    """Read tool without guardrail still validates path existence and symlinks."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello")
    spec = _read_spec()
    result = await spec.execute(path=str(file_path), ctx=_mock_ctx())
    assert result.success is True
    assert result.result == "hello"
