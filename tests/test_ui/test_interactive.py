"""Tests for InteractiveUIHandler."""

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from rich.console import Console

from yoker import __version__
from yoker.agent.thinking import ThinkingMode
from yoker.exceptions import NetworkError, ToolError
from yoker.ui import InteractiveUIHandler
from yoker.ui.spinner import LiveDisplay

if sys.platform == "win32":
  pytest.skip(
    "prompt_toolkit interactive tests require a Windows console",
    allow_module_level=True,
  )


def make_console(output: StringIO) -> Console:
  """Create a console for tests with plain output."""
  return Console(
    file=output,
    force_terminal=True,
    color_system=None,
    highlight=False,
  )


class TestInteractiveUIHandlerInitialization:
  """Tests for InteractiveUIHandler initialization."""

  def test_init_defaults(self):
    """Should initialize with default values."""
    handler = InteractiveUIHandler()
    assert handler.show_thinking is True
    assert handler.show_tool_calls is True
    assert handler.wrap_width is None
    assert handler.history_file == Path.home() / ".yoker_history"
    assert handler._live is None

  def test_init_custom_values(self):
    """Should initialize with custom values."""
    history = Path("/tmp/test_history")
    handler = InteractiveUIHandler(
      history_file=history,
      show_thinking=False,
      show_tool_calls=False,
      wrap_width=80,
    )
    assert handler.show_thinking is False
    assert handler.show_tool_calls is False
    assert handler.wrap_width == 80
    assert handler.history_file == history

  def test_prompt_session_created(self):
    """Should create prompt_toolkit session."""
    handler = InteractiveUIHandler()
    assert handler._session is not None

  def test_init_accepts_custom_console(self):
    """Should use provided console instead of creating a new one."""
    output = StringIO()
    console = make_console(output)
    handler = InteractiveUIHandler(console=console)
    assert handler.console is console


class TestInteractiveUIHandlerLifecycle:
  """Tests for InteractiveUIHandler lifecycle methods."""

  @pytest.mark.asyncio
  async def test_start_prints_banner(self):
    """start should print banner and config info."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    agent = MagicMock()
    agent.model = "llama3.1"
    agent.thinking_mode = ThinkingMode.ON
    agent.config.harness.name = "test-harness"
    agent.config.harness.version = "1.2.3"
    agent.config.harness.author = "Test Author"

    await handler.start(agent)

    text = output.getvalue()
    assert __version__ in text
    # Banner now shows provider and model together
    assert "Model: llama3.1" in text
    assert "Harness: test-harness v1.2.3 by Test Author" in text
    assert "Thinking: on" in text
    assert "Type /help" in text
    assert "Ctrl+D" in text

  @pytest.mark.asyncio
  async def test_start_respects_thinking_disabled(self):
    """start should show disabled thinking status."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    agent = MagicMock()
    agent.model = "model"
    agent.thinking_mode = ThinkingMode.OFF
    agent.config.harness.name = "yoker"
    agent.config.harness.version = None
    agent.config.harness.author = None

    await handler.start(agent)

    text = output.getvalue()
    assert "Harness: yoker" in text
    assert "Thinking: off" in text

  @pytest.mark.asyncio
  async def test_shutdown_prints_goodbye(self):
    """shutdown should print goodbye message."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    await handler.shutdown("quit")

    assert "Goodbye!" in output.getvalue()

  @pytest.mark.asyncio
  async def test_shutdown_exits_live_display(self):
    """shutdown should clean up active LiveDisplay."""
    handler = InteractiveUIHandler()
    handler.start_content_stream()
    assert handler._live is not None

    await handler.shutdown("quit")
    assert handler._live is None


class TestInteractiveUIHandlerInput:
  """Tests for InteractiveUIHandler input handling."""

  @pytest.mark.asyncio
  async def test_get_input_returns_input(self):
    """get_input should return user input."""
    handler = InteractiveUIHandler()
    handler._session.prompt_async = AsyncMock(return_value="hello")  # type: ignore[method-assign]

    result = await handler.get_input()
    assert result == "hello"

  @pytest.mark.asyncio
  async def test_get_input_handles_eof(self):
    """get_input should return None on EOFError."""
    handler = InteractiveUIHandler()
    handler._session.prompt_async = AsyncMock(side_effect=EOFError)  # type: ignore[method-assign]

    result = await handler.get_input()
    assert result is None

  @pytest.mark.asyncio
  async def test_get_input_handles_keyboard_interrupt(self):
    """get_input should return None on KeyboardInterrupt."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)
    handler._session.prompt_async = AsyncMock(side_effect=KeyboardInterrupt)  # type: ignore[method-assign]

    result = await handler.get_input()
    assert result is None

  @pytest.mark.asyncio
  async def test_get_input_uses_predefined_messages(self):
    """get_input should return predefined messages in order."""
    handler = InteractiveUIHandler()
    handler.set_input_messages(["hello", "world"])

    assert await handler.get_input() == "hello"
    assert await handler.get_input() == "world"

  @pytest.mark.asyncio
  async def test_get_input_returns_none_after_predefined_messages(self):
    """get_input should return None when predefined messages are exhausted."""
    handler = InteractiveUIHandler()
    handler.set_input_messages(["only one"])

    assert await handler.get_input() == "only one"
    assert await handler.get_input() is None


class TestInteractiveUIHandlerContentStreaming:
  """Tests for InteractiveUIHandler content streaming."""

  def test_start_content_stream_creates_live(self):
    """start_content_stream should create LiveDisplay."""
    handler = InteractiveUIHandler()
    handler.start_content_stream()
    assert handler._live is not None
    assert isinstance(handler._live, LiveDisplay)

  def test_stream_content_appends_response(self):
    """stream_content should append response chunks."""
    handler = InteractiveUIHandler()
    handler.start_content_stream()
    handler.stream_content("Hello ")
    handler.stream_content("World")

    assert handler._live is not None
    assert handler._live._response_text.plain == "Hello World"

  def test_end_content_stream_stops_spinner(self):
    """end_content_stream should stop spinner."""
    handler = InteractiveUIHandler()
    handler.start_content_stream()
    handler.stream_content("Hello")
    handler.end_content_stream(5)

    assert handler._live is not None
    assert handler._live._spinner_active is False

  def test_content_stream_preserves_ansi(self):
    """stream_content should preserve ANSI codes."""
    handler = InteractiveUIHandler()
    handler.start_content_stream()
    handler.stream_content("\033[31mred\033[0m")

    assert handler._live is not None
    assert "\033[31mred\033[0m" in handler._live._response_text.plain

  def test_content_stream_after_thinking_adds_separator(self):
    """Content stream after thinking should add separator."""
    handler = InteractiveUIHandler()
    handler.start_thinking_stream()
    handler.stream_thinking("thinking")
    handler.start_content_stream()
    handler.stream_content("content")

    assert handler._live is not None
    assert handler._live._response_text.plain == "\ncontent"


class TestInteractiveUIHandlerThinkingStreaming:
  """Tests for InteractiveUIHandler thinking streaming."""

  def test_start_thinking_stream_creates_live(self):
    """start_thinking_stream should create LiveDisplay when enabled."""
    handler = InteractiveUIHandler(show_thinking=True)
    handler.start_thinking_stream()
    assert handler._live is not None

  def test_start_thinking_stream_respects_setting(self):
    """start_thinking_stream should do nothing when disabled."""
    handler = InteractiveUIHandler(show_thinking=False)
    handler.start_thinking_stream()
    assert handler._live is None

  def test_stream_thinking_appends_thinking(self):
    """stream_thinking should append thinking chunks."""
    handler = InteractiveUIHandler(show_thinking=True)
    handler.start_thinking_stream()
    handler.stream_thinking("thinking...")

    assert handler._live is not None
    assert handler._live._thinking_text.plain == "thinking..."

  def test_stream_thinking_suppressed_when_disabled(self):
    """stream_thinking should be suppressed when disabled."""
    output = StringIO()
    handler = InteractiveUIHandler(show_thinking=False)
    handler.console = make_console(output)

    handler.stream_thinking("thinking...")
    assert output.getvalue() == ""

  def test_end_thinking_stream_stops_spinner(self):
    """end_thinking_stream should stop spinner."""
    handler = InteractiveUIHandler(show_thinking=True)
    handler.start_thinking_stream()
    handler.stream_thinking("done")
    handler.end_thinking_stream(4)

    assert handler._live is not None
    assert handler._live._spinner_active is False


class TestInteractiveUIHandlerToolOutput:
  """Tests for InteractiveUIHandler tool output."""

  def test_output_tool_call_respects_setting(self):
    """output_tool_call should print when enabled."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_call("read", {"path": "/tmp/file.txt"})
    text = output.getvalue()
    assert "⏺ Read tool" in text
    assert "file.txt" in text

  def test_output_tool_call_suppressed_when_disabled(self):
    """output_tool_call should not print when disabled."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=False)
    handler.console = make_console(output)

    handler.output_tool_call("read", {"path": "/tmp/file.txt"})
    assert output.getvalue() == ""

  def test_output_tool_result_success(self):
    """output_tool_result should print success indicator."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_result("read", True, "contents")
    assert "✓ Success" in output.getvalue()

  def test_output_tool_result_failure(self):
    """output_tool_result should print failure indicator."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_result("read", False, "Error message here")
    text = output.getvalue()
    # _print_error uses a Panel with title "ERROR"
    assert "ERROR" in text
    assert "Error message here" in text

  def test_output_tool_content_full(self):
    """output_tool_content should show full content with line numbers."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_content(
      "write",
      "write",
      "/tmp/file.txt",
      "line 1\nline 2",
      "text/plain",
      {"lines": 2},
    )
    text = output.getvalue()
    assert "file.txt" in text
    assert "line 1" in text
    assert "line 2" in text

  def test_output_tool_content_summary(self):
    """output_tool_content should show summary for application/x-summary."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_content(
      "write",
      "write",
      "/tmp/file.txt",
      None,
      "application/x-summary",
      {"lines": 5, "is_new_file": True},
    )
    text = output.getvalue()
    assert "Creating new file file.txt" in text
    assert "5 lines" in text

  def test_output_tool_content_diff(self):
    """output_tool_content should show diff content with colors."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_content(
      "update",
      "replace",
      "/tmp/file.txt",
      "@@ -1,1 +1,1 @@\n-old\n+new",
      "text/x-diff",
      {},
    )
    text = output.getvalue()
    assert "file.txt" in text
    assert "-old" in text
    assert "+new" in text

  def test_tool_call_exits_live_display(self):
    """output_tool_call should exit active LiveDisplay."""
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.start_content_stream()
    assert handler._live is not None

    handler.output_tool_call("read", {"path": "/tmp/file.txt"})
    assert handler._live is None

  def test_tool_result_creates_live_display(self):
    """output_tool_result should create LiveDisplay for subsequent processing."""
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.output_tool_result("read", True, "contents")
    assert handler._live is not None


class TestInteractiveUIHandlerCommandOutput:
  """Tests for InteractiveUIHandler command output."""

  def test_output_command_result(self):
    """output_command_result should print result and exit live display."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.start_content_stream()
    handler.output_command_result("command output")
    assert handler._live is None
    assert "command output" in output.getvalue()


class TestInteractiveUIHandlerStats:
  """Tests for InteractiveUIHandler stats output."""

  def test_output_stats_with_live_display(self):
    """output_stats should show stats and exit LiveDisplay."""
    handler = InteractiveUIHandler()
    handler.start_content_stream()
    handler.stream_content("Hello")
    handler.output_stats(1500, 50, 100)

    assert handler._live is None

  def test_output_stats_without_live_display(self):
    """output_stats should print stats directly when no LiveDisplay."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_stats(1500, 50, 100)
    text = output.getvalue()
    assert "1.5s" in text
    assert "50+100=150" in text
    assert "tok/s" in text

  def test_output_stats_no_timing_data(self):
    """output_stats should add blank line when no timing data."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_stats(0, 0, 0)
    # Should just print a blank line
    assert output.getvalue() == "\n"

  def test_output_stats_resets_state(self):
    """output_stats should reset thinking and content flags."""
    handler = InteractiveUIHandler()
    handler._thinking_shown = True
    handler._content_shown = True
    handler.output_stats(100, 1, 1)
    assert handler._thinking_shown is False
    assert handler._content_shown is False


class TestInteractiveUIHandlerErrors:
  """Tests for InteractiveUIHandler error display."""

  def test_output_error_recoverable_network(self):
    """Should format recoverable NetworkError correctly."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    error = NetworkError("connection refused", recoverable=True)
    handler.output_error(error)

    text = output.getvalue()
    # New format shows just the message without "Network Error" prefix
    assert "connection refused" in text
    assert "Try again" in text

  def test_output_error_non_recoverable_network(self):
    """Should format non-recoverable NetworkError correctly."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    error = NetworkError("fatal error", recoverable=False)
    handler.output_error(error)

    text = output.getvalue()
    # New format shows just the message without "Fatal Network Error" prefix
    assert "fatal error" in text
    assert "restart" in text

  def test_output_error_tool(self):
    """Should format ToolError correctly."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    error = ToolError("read", "file not found")
    handler.output_error(error)

    text = output.getvalue()
    assert "Tool Error" in text
    assert "read" in text
    assert "file not found" in text

  def test_output_error_generic(self):
    """Should format generic errors correctly."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_error(ValueError("something failed"))

    text = output.getvalue()
    assert "Error" in text
    assert "something failed" in text

  def test_output_error_exits_live_display(self):
    """output_error should exit active LiveDisplay."""
    handler = InteractiveUIHandler()
    handler.start_content_stream()
    assert handler._live is not None

    handler.output_error(ValueError("test"))
    assert handler._live is None
