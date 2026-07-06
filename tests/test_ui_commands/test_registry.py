"""Tests for the UI-layer CommandRegistry."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.core import Agent
from yoker.skills import Skill, SkillRegistry
from yoker.ui import BatchUIHandler
from yoker.ui.commands import Command, CommandRegistry, create_default_registry


class MockUI(BatchUIHandler):
  """UI handler that captures command output."""

  def __init__(self) -> None:
    super().__init__()
    self.command_results: list[str] = []

  def output_command_result(self, result: str) -> None:
    self.command_results.append(result)


class TestCommandRegistry:
  """Tests for CommandRegistry registration and dispatch."""

  def test_register_and_get_command(self):
    """Registering a command makes it retrievable by name."""
    registry = CommandRegistry()
    cmd = Command(name="test", description="A test command", handler=AsyncMock())

    registry.register(cmd)

    assert registry.get("test") is cmd
    assert registry.names == ["test"]

  def test_register_duplicate_raises(self):
    """Registering a duplicate command name raises ValueError."""
    registry = CommandRegistry()
    cmd = Command(name="test", description="A test command", handler=AsyncMock())
    registry.register(cmd)

    with pytest.raises(ValueError, match="already registered"):
      registry.register(cmd)

  def test_list_commands_sorted(self):
    """list_commands returns commands sorted by name."""
    registry = CommandRegistry()
    registry.register(Command(name="z", description="Z", handler=AsyncMock()))
    registry.register(Command(name="a", description="A", handler=AsyncMock()))
    registry.register(Command(name="m", description="M", handler=AsyncMock()))

    names = [cmd.name for cmd in registry.list_commands()]
    assert names == ["a", "m", "z"]

  @pytest.mark.asyncio
  async def test_dispatch_non_command_returns_none(self):
    """dispatch returns None for input that is not a slash-command."""
    registry = CommandRegistry()
    agent = MagicMock(spec=Agent)
    ui = MockUI()

    result = await registry.dispatch("hello", agent, ui)
    assert result is None

  @pytest.mark.asyncio
  async def test_dispatch_empty_command(self):
    """dispatch returns an error for an empty slash-command."""
    registry = CommandRegistry()
    agent = MagicMock(spec=Agent)
    ui = MockUI()

    result = await registry.dispatch("/", agent, ui)
    assert result is not None
    assert "Empty command" in result

  @pytest.mark.asyncio
  async def test_dispatch_unknown_command(self):
    """dispatch returns an error for unknown commands."""
    registry = CommandRegistry()
    agent = MagicMock(spec=Agent)
    agent.skills = None
    ui = MockUI()

    result = await registry.dispatch("/unknown", agent, ui)
    assert result is not None
    assert "Unknown command" in result

  @pytest.mark.asyncio
  async def test_dispatch_command_with_args(self):
    """dispatch passes arguments to the command handler."""
    registry = CommandRegistry()
    handler = AsyncMock(return_value="handled")
    registry.register(Command(name="echo", description="Echo", handler=handler))

    agent = MagicMock(spec=Agent)
    ui = MockUI()

    result = await registry.dispatch("/echo hello world", agent, ui)

    handler.assert_awaited_once_with("hello world", agent, ui)
    assert result == "handled"

  @pytest.mark.asyncio
  async def test_dispatch_skill_invocation(self):
    """dispatch treats unknown commands matching skill names as skill invocations."""
    registry = CommandRegistry()
    skill_registry = SkillRegistry()
    skill_registry.register(
      Skill(simple_name="commit", description="Guide commits", content="commit instructions")
    )

    agent = MagicMock(spec=Agent)
    agent.skills = skill_registry
    ui = MockUI()

    with patch("yoker.ui.commands.skill_invoke.handle") as mock_handle:
      mock_handle.return_value = None
      result = await registry.dispatch("/commit fix bug", agent, ui)

    mock_handle.assert_awaited_once_with("commit", "fix bug", agent, ui)
    assert result is None


class TestCreateDefaultRegistry:
  """Tests for the default command registry factory."""

  def test_includes_builtin_commands(self):
    """Default registry includes all built-in commands."""
    registry = create_default_registry()

    names = registry.names
    assert "help" in names
    assert "think" in names
    assert "skills" in names
    assert "context" in names
    assert "tools" in names
    assert "agents" in names

  @pytest.mark.asyncio
  async def test_help_command_lists_all_commands(self):
    """/help lists the commands registered in the default registry."""
    registry = create_default_registry()
    agent = MagicMock(spec=Agent)
    ui = MockUI()

    result = await registry.dispatch("/help", agent, ui)

    assert result is not None
    assert "Available commands:" in result
    for name in registry.names:
      assert f"/{name}" in result
