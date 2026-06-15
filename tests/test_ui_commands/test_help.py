"""Tests for the UI-layer /help command."""

from unittest.mock import MagicMock

import pytest

from yoker.agent import Agent
from yoker.ui import BatchUIHandler
from yoker.ui.commands import CommandRegistry, create_default_registry
from yoker.ui.commands.help import DESCRIPTION, create_command


class MockUI(BatchUIHandler):
  """UI handler that captures command output."""

  def __init__(self) -> None:
    super().__init__()
    self.command_results: list[str] = []

  def output_command_result(self, result: str) -> None:
    self.command_results.append(result)


class TestHelpCommand:
  """Tests for /help command in the UI layer."""

  @pytest.mark.asyncio
  async def test_help_lists_commands(self):
    """/help should list registered commands with descriptions."""
    registry = CommandRegistry()
    registry.register(create_command(lambda: registry))

    agent = MagicMock(spec=Agent)
    ui = MockUI()

    result = await registry.dispatch("/help", agent, ui)

    assert result is not None
    assert "Available commands:" in result
    assert "/help" in result
    assert DESCRIPTION in result

  @pytest.mark.asyncio
  async def test_help_ignores_args(self):
    """/help should ignore any arguments."""
    registry = create_default_registry()
    agent = MagicMock(spec=Agent)
    ui = MockUI()

    result1 = await registry.dispatch("/help", agent, ui)
    result2 = await registry.dispatch("/help ignored args", agent, ui)

    assert result1 == result2

  @pytest.mark.asyncio
  async def test_help_includes_chat_hint(self):
    """/help should remind users how to chat with the LLM."""
    registry = create_default_registry()
    agent = MagicMock(spec=Agent)
    ui = MockUI()

    result = await registry.dispatch("/help", agent, ui)

    assert "Type a message without / prefix" in result
