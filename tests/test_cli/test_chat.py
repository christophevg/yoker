"""Tests for the ``yoker chat`` subcommand handler (MBI-004 task 4.2).

The bulk of the REPL/UI tests remain in ``tests/test_main.py`` (they test the
extracted functions via ``yoker.cli.chat`` imports). This file verifies the
module is importable and exports the expected public API.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from yoker.cli.chat import create_ui, run_chat


class TestChatModule:
  """Verify cli.chat module structure."""

  def test_run_chat_callable(self):
    """run_chat is a callable function."""
    assert callable(run_chat)

  def test_create_ui_callable(self):
    """create_ui is a callable function."""
    assert callable(create_ui)


class TestRunReplPrompt:
  """Test --prompt initial message behavior in _run_repl."""

  def _make_ui(self, inputs):
    ui = MagicMock()
    ui.start = AsyncMock()
    ui.shutdown = AsyncMock()
    ui.get_input = AsyncMock(side_effect=inputs)
    ui.output_error = MagicMock()
    return ui

  def _make_agent(self):
    agent = MagicMock()
    agent.model = "test-model"
    agent.thinking_mode.value = "off"
    agent.process = AsyncMock(return_value="response")
    return agent

  @pytest.mark.asyncio
  async def test_prompt_sent_before_repl_loop(self):
    """When prompt is provided, agent.process is called with it before user input."""
    from yoker.cli.chat import _run_repl

    ui = self._make_ui([None])
    agent = self._make_agent()
    commands = MagicMock()

    await _run_repl(agent, ui, commands, prompt="Hello agent")

    # agent.process should have been called with the prompt first
    assert agent.process.await_count == 1
    assert agent.process.call_args_list[0] == ((("Hello agent",)),)

  @pytest.mark.asyncio
  async def test_prompt_then_user_input(self):
    """Prompt is processed first, then user input in the REPL loop."""
    from yoker.cli.chat import _run_repl

    ui = self._make_ui(["follow up", None])
    agent = self._make_agent()
    commands = MagicMock()

    await _run_repl(agent, ui, commands, prompt="initial prompt")

    assert agent.process.await_count == 2
    assert agent.process.call_args_list[0] == ((("initial prompt",)),)
    assert agent.process.call_args_list[1] == ((("follow up",)),)

  @pytest.mark.asyncio
  async def test_empty_prompt_skipped(self):
    """Empty prompt is not sent to agent."""
    from yoker.cli.chat import _run_repl

    ui = self._make_ui(["hello", None])
    agent = self._make_agent()
    commands = MagicMock()

    await _run_repl(agent, ui, commands, prompt="")

    # Only the user input "hello" should be processed
    assert agent.process.await_count == 1
    assert agent.process.call_args_list[0] == ((("hello",)),)

  @pytest.mark.asyncio
  async def test_whitespace_prompt_skipped(self):
    """Whitespace-only prompt is not sent to agent."""
    from yoker.cli.chat import _run_repl

    ui = self._make_ui(["hello", None])
    agent = self._make_agent()
    commands = MagicMock()

    await _run_repl(agent, ui, commands, prompt="   ")

    assert agent.process.await_count == 1
    assert agent.process.call_args_list[0] == ((("hello",)),)

  @pytest.mark.asyncio
  async def test_prompt_recoverable_error_continues_repl(self):
    """Recoverable NetworkError from prompt processing allows REPL to continue."""
    from yoker.cli.chat import _run_repl
    from yoker.exceptions import NetworkError

    ui = self._make_ui(["retry", None])
    ui.output_error = MagicMock()
    agent = self._make_agent()
    agent.process = AsyncMock(side_effect=[NetworkError("timeout", recoverable=True), "response"])
    commands = MagicMock()

    await _run_repl(agent, ui, commands, prompt="initial")

    assert agent.process.await_count == 2
    ui.output_error.assert_called_once()
    ui.shutdown.assert_awaited_once()

  @pytest.mark.asyncio
  async def test_prompt_non_recoverable_error_stops_repl(self):
    """Non-recoverable NetworkError from prompt processing stops the REPL."""
    from yoker.cli.chat import _run_repl
    from yoker.exceptions import NetworkError

    ui = self._make_ui(["should not reach", None])
    ui.output_error = MagicMock()
    agent = self._make_agent()
    agent.process = AsyncMock(side_effect=NetworkError("fatal", recoverable=False))
    commands = MagicMock()

    await _run_repl(agent, ui, commands, prompt="initial")

    assert agent.process.await_count == 1
    ui.output_error.assert_called_once()
    ui.shutdown.assert_awaited_once()
