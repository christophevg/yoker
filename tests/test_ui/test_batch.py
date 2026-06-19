"""Tests for BatchUIHandler."""

from io import StringIO
from unittest.mock import MagicMock

import pytest

from yoker.exceptions import NetworkError
from yoker.ui import BatchUIHandler


class TestBatchUIHandlerInitialization:
  """Tests for BatchUIHandler initialization."""

  def test_init_defaults(self):
    """Should initialize with default values."""
    handler = BatchUIHandler()
    assert handler.show_thinking is False
    assert handler.show_tool_calls is False
    assert handler.show_stats is False
    assert handler._input_source is None
    assert handler._input_index == 0

  def test_init_custom_streams(self):
    """Should use provided streams."""
    stdin = StringIO()
    stdout = StringIO()
    stderr = StringIO()
    handler = BatchUIHandler(stdin=stdin, stdout=stdout, stderr=stderr)
    assert handler._stdin is stdin
    assert handler._stdout is stdout
    assert handler._stderr is stderr

  def test_init_custom_flags(self):
    """Should initialize with custom show flags."""
    handler = BatchUIHandler(
      show_thinking=True,
      show_tool_calls=True,
      show_stats=True,
    )
    assert handler.show_thinking is True
    assert handler.show_tool_calls is True
    assert handler.show_stats is True


class TestBatchUIHandlerInput:
  """Tests for BatchUIHandler input handling."""

  def test_set_input_messages(self):
    """set_input_messages should configure predefined inputs."""
    handler = BatchUIHandler()
    handler.set_input_messages(["first", "second"])
    assert handler._input_source == ["first", "second"]
    assert handler._input_index == 0

  @pytest.mark.asyncio
  async def test_get_input_predefined(self):
    """get_input should return predefined messages in order."""
    handler = BatchUIHandler()
    handler.set_input_messages(["first", "second"])

    assert await handler.get_input() == "first"
    assert await handler.get_input() == "second"
    assert await handler.get_input() is None

  @pytest.mark.asyncio
  async def test_get_input_from_stdin(self):
    """get_input should read from stdin."""
    stdin = StringIO("hello\nworld\n")
    handler = BatchUIHandler(stdin=stdin)

    assert await handler.get_input() == "hello"
    assert await handler.get_input() == "world"
    assert await handler.get_input() is None

  @pytest.mark.asyncio
  async def test_get_input_empty_stdin(self):
    """get_input should return None on empty stdin."""
    stdin = StringIO("")
    handler = BatchUIHandler(stdin=stdin)

    assert await handler.get_input() is None


class TestBatchUIHandlerLifecycle:
  """Tests for BatchUIHandler lifecycle methods."""

  @pytest.mark.asyncio
  async def test_start_minimal_output(self):
    """start should not print in batch mode by default."""
    stderr = StringIO()
    handler = BatchUIHandler(stderr=stderr)
    agent = MagicMock()
    agent.model = "llama3.1"
    await handler.start(agent)
    assert stderr.getvalue() == ""

  @pytest.mark.asyncio
  async def test_start_with_thinking(self):
    """start should print model info when show_thinking is enabled."""
    stderr = StringIO()
    handler = BatchUIHandler(show_thinking=True, stderr=stderr)
    agent = MagicMock()
    agent.model = "llama3.1"
    await handler.start(agent)
    assert "# Model: llama3.1" in stderr.getvalue()

  @pytest.mark.asyncio
  async def test_shutdown_silent(self):
    """shutdown should produce no output."""
    stderr = StringIO()
    handler = BatchUIHandler(stderr=stderr)
    await handler.shutdown("complete")
    assert stderr.getvalue() == ""


class TestBatchUIHandlerContentOutput:
  """Tests for BatchUIHandler content output to stdout."""

  def test_content_stream_goes_to_stdout(self):
    """Content stream should be written to stdout."""
    stdout = StringIO()
    handler = BatchUIHandler(stdout=stdout)

    handler.start_content_stream()
    handler.stream_content("Hello ")
    handler.stream_content("World")
    handler.end_content_stream(11)

    assert stdout.getvalue() == "Hello World\n"

  def test_content_stream_preserves_ansi(self):
    """Content stream should preserve ANSI codes."""
    stdout = StringIO()
    handler = BatchUIHandler(stdout=stdout)

    handler.start_content_stream()
    handler.stream_content("\033[31mred\033[0m")
    handler.end_content_stream(9)

    assert "\033[31mred\033[0m" in stdout.getvalue()

  def test_command_result_to_stdout(self):
    """Command result should go to stdout."""
    stdout = StringIO()
    handler = BatchUIHandler(stdout=stdout)

    handler.output_command_result("command output")
    assert stdout.getvalue() == "command output\n"


class TestBatchUIHandlerThinkingOutput:
  """Tests for BatchUIHandler thinking output to stderr."""

  def test_thinking_stream_to_stderr_when_enabled(self):
    """Thinking stream should go to stderr when enabled."""
    stderr = StringIO()
    handler = BatchUIHandler(show_thinking=True, stderr=stderr)

    handler.start_thinking_stream()
    handler.stream_thinking("thinking...")
    handler.end_thinking_stream(11)

    assert stderr.getvalue() == "thinking...\n"

  def test_thinking_stream_suppressed_when_disabled(self):
    """Thinking stream should be suppressed when disabled."""
    stderr = StringIO()
    handler = BatchUIHandler(show_thinking=False, stderr=stderr)

    handler.start_thinking_stream()
    handler.stream_thinking("thinking...")
    handler.end_thinking_stream(11)

    assert stderr.getvalue() == ""


class TestBatchUIHandlerToolOutput:
  """Tests for BatchUIHandler tool output to stderr."""

  def test_tool_call_to_stderr_when_enabled(self):
    """Tool call should go to stderr when enabled."""
    stderr = StringIO()
    handler = BatchUIHandler(show_tool_calls=True, stderr=stderr)

    handler.output_tool_call("read", {"path": "/tmp/file.txt"})
    assert "# Tool: read(path=/tmp/file.txt)" in stderr.getvalue()

  def test_tool_call_suppressed_when_disabled(self):
    """Tool call should be suppressed when disabled."""
    stderr = StringIO()
    handler = BatchUIHandler(show_tool_calls=False, stderr=stderr)

    handler.output_tool_call("read", {"path": "/tmp/file.txt"})
    assert stderr.getvalue() == ""

  def test_tool_result_success(self):
    """Tool result success should go to stderr."""
    stderr = StringIO()
    handler = BatchUIHandler(show_tool_calls=True, stderr=stderr)

    handler.output_tool_result("read", True, "contents")
    assert "# OK read: contents" in stderr.getvalue()

  def test_tool_result_failure(self):
    """Tool result failure should go to stderr."""
    stderr = StringIO()
    handler = BatchUIHandler(show_tool_calls=True, stderr=stderr)

    handler.output_tool_result("read", False, "error message")
    assert "# FAIL read: error message" in stderr.getvalue()

  def test_tool_result_no_detail(self):
    """Tool result should not include trailing colon when no detail."""
    stderr = StringIO()
    handler = BatchUIHandler(show_tool_calls=True, stderr=stderr)

    handler.output_tool_result("read", True, "")
    assert stderr.getvalue().strip() == "# OK read"

  def test_tool_content_to_stderr(self):
    """Tool content should go to stderr when enabled."""
    stderr = StringIO()
    handler = BatchUIHandler(show_tool_calls=True, stderr=stderr)

    handler.output_tool_content(
      "write",
      "write",
      "/tmp/file.txt",
      "content here",
      "text/plain",
      {},
    )
    text = stderr.getvalue()
    assert "# Tool content: write write /tmp/file.txt (text/plain)" in text
    assert "content here" in text


class TestBatchUIHandlerStats:
  """Tests for BatchUIHandler stats output."""

  def test_stats_to_stderr_when_enabled(self):
    """Stats should go to stderr when enabled."""
    stderr = StringIO()
    handler = BatchUIHandler(show_stats=True, stderr=stderr)

    handler.output_stats(1500, 50, 100)
    assert "# Stats: 1.5s, 150 tokens" in stderr.getvalue()

  def test_stats_suppressed_when_disabled(self):
    """Stats should be suppressed when disabled."""
    stderr = StringIO()
    handler = BatchUIHandler(show_stats=False, stderr=stderr)

    handler.output_stats(1500, 50, 100)
    assert stderr.getvalue() == ""


class TestBatchUIHandlerErrors:
  """Tests for BatchUIHandler error output."""

  def test_error_to_stderr(self):
    """Errors should go to stderr with type information."""
    stderr = StringIO()
    handler = BatchUIHandler(stderr=stderr)

    handler.output_error(ValueError("something failed"))
    assert "Error [ValueError]: something failed" in stderr.getvalue()

  def test_network_error_to_stderr(self):
    """NetworkError should be formatted on stderr."""
    stderr = StringIO()
    handler = BatchUIHandler(stderr=stderr)

    handler.output_error(NetworkError("timeout", recoverable=True))
    assert "Error [NetworkError]: timeout" in stderr.getvalue()
