"""Tests for __main__.py helpers and session loop."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker.config import Config, UIConfig
from yoker.exceptions import NetworkError, YokerError
from yoker.ui import BatchUIHandler, InteractiveUIHandler


class TestCreateUI:
  """Test _create_ui mode selection."""

  def test_create_ui_returns_batch_for_batch_mode(self):
    """_create_ui should return BatchUIHandler when mode is batch."""
    from yoker.__main__ import _create_ui

    config = Config(
      ui=UIConfig(mode="batch", show_thinking=True, show_tool_calls=True, show_stats=True)
    )
    ui = _create_ui(config)
    assert isinstance(ui, BatchUIHandler)
    assert ui.show_thinking is True
    assert ui.show_tool_calls is True
    assert ui.show_stats is True

  def test_create_ui_returns_interactive_by_default(self):
    """_create_ui should return InteractiveUIHandler for interactive mode."""
    from yoker.__main__ import _create_ui

    config = Config(
      ui=UIConfig(mode="interactive", show_thinking=True, show_tool_calls=True, show_stats=True)
    )
    ui = _create_ui(config)
    assert isinstance(ui, InteractiveUIHandler)
    assert ui.show_thinking is True
    assert ui.show_tool_calls is True
    assert ui.show_stats is True


class TestRunSession:
  """Test run_session loop behavior."""

  def _make_ui(self, inputs):
    ui = MagicMock()
    ui.show_tool_calls = True
    ui.start = AsyncMock()
    ui.shutdown = AsyncMock()
    ui.get_input = AsyncMock(side_effect=inputs)
    return ui

  def _make_agent(self):
    agent = MagicMock()
    agent.model = "llama3.2:latest"
    agent.thinking_mode.value = "on"
    agent.process = AsyncMock(return_value="response")
    return agent

  async def test_run_session_calls_start_and_shutdown(self):
    """run_session should start and shut down the UI."""
    from yoker.__main__ import run_session

    ui = self._make_ui([None])
    agent = self._make_agent()
    commands = MagicMock()

    await run_session(agent, ui, commands)

    ui.start.assert_awaited_once()
    ui.shutdown.assert_awaited_once()

  async def test_run_session_processes_user_input(self):
    """run_session should call agent.process for regular input."""
    from yoker.__main__ import run_session

    ui = self._make_ui(["hello", None])
    agent = self._make_agent()
    commands = MagicMock()

    await run_session(agent, ui, commands)

    agent.process.assert_awaited_once_with("hello")
    commands.dispatch.assert_not_called()

  async def test_run_session_dispatches_slash_commands(self):
    """run_session should dispatch slash commands via the registry."""
    from yoker.__main__ import run_session

    ui = self._make_ui(["/help", None])
    agent = self._make_agent()
    commands = MagicMock()
    commands.dispatch = AsyncMock(return_value="command result")

    await run_session(agent, ui, commands)

    commands.dispatch.assert_awaited_once_with("/help", agent, ui)
    ui.output_command_result.assert_called_once_with("command result")
    agent.process.assert_not_called()

  async def test_run_session_ignores_empty_input(self):
    """run_session should ignore empty input lines."""
    from yoker.__main__ import run_session

    ui = self._make_ui(["", "hello", None])
    agent = self._make_agent()
    commands = MagicMock()

    await run_session(agent, ui, commands)

    agent.process.assert_awaited_once_with("hello")

  async def test_run_session_handles_recoverable_network_error(self):
    """Recoverable NetworkError should be displayed and allow retry."""
    from yoker.__main__ import run_session

    ui = self._make_ui(["hello", "again", None])
    agent = self._make_agent()
    agent.process = AsyncMock(
      side_effect=[
        NetworkError("timeout", recoverable=True),
        "response",
      ]
    )
    commands = MagicMock()

    await run_session(agent, ui, commands)

    assert agent.process.await_count == 2
    ui.output_error.assert_called_once()
    ui.shutdown.assert_awaited_once()

  async def test_run_session_breaks_on_non_recoverable_network_error(self):
    """Non-recoverable NetworkError should end the session."""
    from yoker.__main__ import run_session

    ui = self._make_ui(["hello", "ignored", None])
    agent = self._make_agent()
    agent.process = AsyncMock(side_effect=NetworkError("fatal", recoverable=False))
    commands = MagicMock()

    await run_session(agent, ui, commands)

    agent.process.assert_awaited_once_with("hello")
    ui.output_error.assert_called_once()
    ui.shutdown.assert_awaited_once()

  async def test_run_session_breaks_on_yoker_error(self):
    """YokerError should end the session."""
    from yoker.__main__ import run_session

    ui = self._make_ui(["hello", None])
    agent = self._make_agent()
    agent.process = AsyncMock(side_effect=YokerError("something failed"))
    commands = MagicMock()

    await run_session(agent, ui, commands)

    ui.output_error.assert_called_once()
    ui.shutdown.assert_awaited_once()

  async def test_run_session_breaks_on_keyboard_interrupt(self):
    """KeyboardInterrupt should end the session gracefully."""
    from yoker.__main__ import run_session

    ui = self._make_ui([])
    ui.get_input = AsyncMock(side_effect=KeyboardInterrupt)
    agent = self._make_agent()
    commands = MagicMock()

    await run_session(agent, ui, commands)

    ui.shutdown.assert_awaited_once()


class TestParsePluginArgs:
  """Test _parse_plugin_args helper."""

  def test_extracts_with_args(self):
    """_parse_plugin_args should extract --with packages and clean argv."""
    from yoker.__main__ import _parse_plugin_args

    plugins, cleaned = _parse_plugin_args(["yoker", "--with", "pkg1", "--ui-mode", "batch"])
    assert plugins == ["pkg1"]
    assert cleaned == ["yoker", "--ui-mode", "batch"]

  def test_extracts_multiple_with_args(self):
    """_parse_plugin_args should support multiple --with arguments."""
    from yoker.__main__ import _parse_plugin_args

    plugins, cleaned = _parse_plugin_args(
      [
        "yoker",
        "--with",
        "pkg1",
        "--with",
        "pkg2",
        "--ui-mode",
        "batch",
      ]
    )
    assert plugins == ["pkg1", "pkg2"]
    assert cleaned == ["yoker", "--ui-mode", "batch"]

  def test_exits_when_with_missing_value(self):
    """_parse_plugin_args should exit when --with has no value."""
    from yoker.__main__ import _parse_plugin_args

    with patch("sys.stderr", new_callable=MagicMock()):
      with pytest.raises(SystemExit) as exc_info:
        _parse_plugin_args(["yoker", "--with"])

    assert exc_info.value.code == 1


class TestMainIntegration:
  """Test main() wiring without running a real session."""

  def test_main_creates_batch_ui_and_runs_session(self):
    """main() should create BatchUIHandler in batch mode and wire events."""
    test_args = ["yoker", "--ui-mode", "batch"]

    with patch.object(sys, "argv", test_args):
      with patch("yoker.__main__.get_yoker_config") as mock_get_config:
        mock_get_config.return_value = Config(
          ui=UIConfig(mode="batch", show_thinking=False, show_tool_calls=False, show_stats=False),
        )
        with patch("yoker.__main__.Agent") as mock_agent_cls:
          with patch("yoker.__main__.run_session", new_callable=AsyncMock) as mock_run:
            with patch("yoker.__main__.configure_logging"):
              from yoker.__main__ import main

              main()

              mock_agent_cls.assert_called_once()
              mock_run.assert_awaited_once()
              args, _ = mock_run.call_args
              assert isinstance(args[1], BatchUIHandler)
