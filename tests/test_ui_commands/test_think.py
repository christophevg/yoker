"""Tests for the UI-layer /think command."""

from unittest.mock import MagicMock

import pytest

from yoker.core import Agent
from yoker.core.thinking import ThinkingMode
from yoker.ui import BatchUIHandler
from yoker.ui.commands import create_default_registry
from yoker.ui.commands.think import DESCRIPTION, handle


class MockUI(BatchUIHandler):
  """UI handler that captures command output."""

  def __init__(self) -> None:
    super().__init__()
    self.command_results: list[str] = []

  def output_command_result(self, result: str) -> None:
    self.command_results.append(result)


class TestThinkCommand:
  """Tests for /think command in the UI layer."""

  @pytest.mark.asyncio
  async def test_think_no_args_shows_current_mode(self):
    """/think with no args should display current thinking mode."""
    agent = MagicMock(spec=Agent)
    agent.thinking_mode = ThinkingMode.ON
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "Thinking mode is currently on" in result
    assert "on|off|silent" in result

  @pytest.mark.asyncio
  async def test_think_on_sets_mode(self):
    """/think on should enable thinking mode."""
    agent = MagicMock(spec=Agent)
    agent.thinking_mode = ThinkingMode.OFF
    ui = MockUI()

    result = await handle("on", agent, ui)

    assert agent.thinking_mode == ThinkingMode.ON
    assert "enabled" in result

  @pytest.mark.asyncio
  async def test_think_off_sets_mode(self):
    """/think off should disable thinking mode."""
    agent = MagicMock(spec=Agent)
    agent.thinking_mode = ThinkingMode.ON
    ui = MockUI()

    result = await handle("off", agent, ui)

    assert agent.thinking_mode == ThinkingMode.OFF
    assert "disabled" in result

  @pytest.mark.asyncio
  async def test_think_silent_sets_mode(self):
    """/think silent should set silent thinking mode."""
    agent = MagicMock(spec=Agent)
    agent.thinking_mode = ThinkingMode.OFF
    ui = MockUI()

    result = await handle("silent", agent, ui)

    assert agent.thinking_mode == ThinkingMode.SILENT
    assert "silent" in result.lower()

  @pytest.mark.asyncio
  async def test_think_invalid_argument(self):
    """/think with invalid arg should return an error."""
    agent = MagicMock(spec=Agent)
    agent.thinking_mode = ThinkingMode.ON
    ui = MockUI()

    result = await handle("invalid", agent, ui)

    assert "Invalid argument" in result

  @pytest.mark.asyncio
  async def test_think_registered_in_default_registry(self):
    """/think should be registered in the default registry."""
    registry = create_default_registry()
    agent = MagicMock(spec=Agent)
    agent.thinking_mode = ThinkingMode.ON
    ui = MockUI()

    result = await registry.dispatch("/think off", agent, ui)

    assert "disabled" in result
    assert agent.thinking_mode == ThinkingMode.OFF

  def test_description(self):
    """The /think command should advertise its usage."""
    assert "on|off|silent" in DESCRIPTION
