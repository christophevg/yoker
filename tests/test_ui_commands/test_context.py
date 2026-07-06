"""Tests for the UI-layer /context command."""

from unittest.mock import MagicMock

import pytest

from yoker.context import ContextStatistics
from yoker.core import Agent
from yoker.ui import BatchUIHandler
from yoker.ui.commands import create_default_registry
from yoker.ui.commands.context import DESCRIPTION, handle


class MockUI(BatchUIHandler):
  """UI handler that captures command output."""

  def __init__(self) -> None:
    super().__init__()
    self.command_results: list[str] = []

  def output_command_result(self, result: str) -> None:
    self.command_results.append(result)


class TestContextCommand:
  """Tests for /context command in the UI layer."""

  def _make_agent(self):
    """Create a mock agent with context."""
    agent = MagicMock(spec=Agent)
    agent.context = MagicMock()
    return agent

  @pytest.mark.asyncio
  async def test_context_shows_session_info(self):
    """/context should show session ID and statistics."""
    agent = self._make_agent()
    agent.context.get_session_id.return_value = "session-123"
    agent.context.get_statistics.return_value = ContextStatistics(
      message_count=5,
      turn_count=2,
      tool_call_count=1,
    )
    agent.context.get_messages.return_value = []
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "Current Context" in result
    assert "session-123" in result
    assert "Messages: 5" in result
    assert "Turns: 2" in result
    assert "Tool calls: 1" in result

  @pytest.mark.asyncio
  async def test_context_shows_all_messages(self):
    """/context should show all messages."""
    agent = self._make_agent()
    agent.context.get_session_id.return_value = "session-123"
    agent.context.get_statistics.return_value = ContextStatistics()
    agent.context.get_messages.return_value = [
      {"role": "system", "content": "You are helpful."},
      {"role": "user", "content": "Hello"},
      {"role": "assistant", "content": "Hi there"},
    ]
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "Messages:" in result
    assert "#1 (system)" in result
    assert "#2 (user)" in result
    assert "#3 (assistant)" in result

  @pytest.mark.asyncio
  async def test_context_shows_full_content(self):
    """/context should show full message content."""
    agent = self._make_agent()
    agent.context.get_session_id.return_value = "session-123"
    agent.context.get_statistics.return_value = ContextStatistics()
    agent.context.get_messages.return_value = [
      {"role": "user", "content": "a" * 100},
    ]
    ui = MockUI()

    result = await handle("", agent, ui)

    assert "a" * 100 in result

  @pytest.mark.asyncio
  async def test_context_registered_in_default_registry(self):
    """/context should be dispatchable from the default registry."""
    registry = create_default_registry()
    agent = self._make_agent()
    agent.context.get_session_id.return_value = "session-123"
    agent.context.get_statistics.return_value = ContextStatistics()
    agent.context.get_messages.return_value = []
    ui = MockUI()

    result = await registry.dispatch("/context", agent, ui)

    assert "Current Context" in result

  def test_description(self):
    """The /context command should describe itself."""
    assert "context" in DESCRIPTION.lower()
