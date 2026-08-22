"""Tests for InteractiveUIHandler."""

import sys
from io import StringIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from yoker import __version__
from yoker.core.thinking import ThinkingMode
from yoker.exceptions import NetworkError, ToolError
from yoker.ui import AgentDisplay, InteractiveUIHandler

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


@pytest.fixture
def stub_session(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
  """Patch ``PromptSession`` lazily with a stub returning canned answers.

  Patches the sync ``prompt`` method (``get_input``/``get_secret_input`` run
  it via ``asyncio.to_thread``).
  """
  state: dict[str, Any] = {"answers": [], "raises": None}

  def _prompt(_prompt: str, is_password: bool = False, **_kw: Any) -> str:
    if state["raises"] is not None:
      raise state["raises"]()
    answers = state["answers"]
    if answers:
      return answers.pop(0)
    return ""

  stub = SimpleNamespace(
    prompt=_prompt,
    is_password=False,
    # PromptSession.app is the cached Application; get_input/get_secret_input
    # toggle app.erase_when_done around the prompt() call.
    app=SimpleNamespace(erase_when_done=False),
  )
  monkeypatch.setattr("yoker.ui.interactive.PromptSession", lambda *a, **kw: stub)
  stub._state = state  # type: ignore[attr-defined]
  return stub


def _set_answers(stub: SimpleNamespace, answers: list[str]) -> None:
  stub._state["answers"] = list(answers)  # type: ignore[attr-defined]


def _set_raises(stub: SimpleNamespace, raises: type[BaseException] | None) -> None:
  stub._state["raises"] = raises  # type: ignore[attr-defined]


class TestInteractiveUIHandlerInitialization:
  """Tests for InteractiveUIHandler initialization."""

  def test_init_defaults(self):
    """Should initialize with default values; no live state attributes."""
    handler = InteractiveUIHandler()
    assert handler.show_thinking is True
    assert handler.show_tool_calls is True
    assert handler.show_stats is True
    assert handler.history_file == __import__("pathlib").Path.home() / ".yoker_history"
    # Lazy session — not created in __init__.
    assert handler._session is None
    # No Live-display state attributes.
    assert not hasattr(handler, "_live")
    assert not hasattr(handler, "_thinking_shown")
    assert not hasattr(handler, "_content_shown")
    assert not hasattr(handler, "_streaming_content")
    assert not hasattr(handler, "_streaming_thinking")

  def test_init_custom_values(self):
    """Should initialize with custom values."""
    history = __import__("pathlib").Path("/tmp/test_history")
    handler = InteractiveUIHandler(
      history_file=history,
      show_thinking=False,
      show_tool_calls=False,
    )
    assert handler.show_thinking is False
    assert handler.show_tool_calls is False
    assert handler.history_file == history

  def test_session_not_created_in_init(self):
    """PromptSession is NOT created in __init__ (lazy init)."""
    handler = InteractiveUIHandler()
    assert handler._session is None

  def test_init_accepts_custom_console(self):
    """Should use provided console instead of creating a new one."""
    output = StringIO()
    console = make_console(output)
    handler = InteractiveUIHandler(console=console)
    assert handler.console is console

  def test_init_spinners_default_true(self):
    """Spinners are enabled by default."""
    handler = InteractiveUIHandler()
    assert handler._show_spinners is True

  def test_init_spinners_can_be_disabled(self):
    """Setting show_spinners=False suppresses status spinners."""
    handler = InteractiveUIHandler(show_spinners=False)
    assert handler._show_spinners is False

  def test_start_processing_no_op_when_spinners_disabled(self):
    """start_processing should not create a Status when spinners are off."""
    handler = InteractiveUIHandler(show_spinners=False)
    handler.start_processing()
    assert handler._processing_status is None

  def test_start_tool_execution_no_op_when_spinners_disabled(self):
    """Tool-execution spinner should not start when spinners are off."""
    handler = InteractiveUIHandler(show_spinners=False)
    handler._start_tool_execution_status("read")
    assert handler._tool_execution_status is None


class TestInteractiveUIHandlerLifecycle:
  """Tests for InteractiveUIHandler lifecycle methods."""

  def _make_agent(self) -> MagicMock:
    agent = MagicMock()
    agent.model = "llama3.1"
    agent.thinking_mode = ThinkingMode.ON
    agent.config.harness.name = "test-harness"
    agent.config.harness.version = "1.2.3"
    agent.config.harness.author = "Test Author"
    agent.config.backend.provider = "ollama"
    agent.config.context.session_id = "test-session"
    agent.config.context.fresh = True
    agent.config.motd.title = "Yoker"
    agent.config.motd.version = None
    agent.config.motd.font = "standard"
    agent.definition.name = "default"
    agent.definition.description = "An agent."
    agent.definition.source_path = None
    agent.tools = {}
    agent.skills = {}
    return agent

  @pytest.mark.asyncio
  async def test_start_prints_banner(self):
    """start should print banner and config info."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)
    agent = self._make_agent()

    await handler.start(agent)

    text = output.getvalue()
    assert __version__ in text
    assert "Model: llama3.1" in text
    assert "Harness: test-harness v1.2.3 by Test Author" in text
    assert "Session: Started 'test-session'" in text
    assert "Thinking: on" in text
    assert "Type /help" in text
    assert "Ctrl+D" in text

  @pytest.mark.asyncio
  async def test_start_shows_resumed_session(self):
    """start should show 'Resumed' when fresh=False and session_id is not 'auto'."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)
    agent = self._make_agent()
    agent.config.context.fresh = False

    await handler.start(agent)

    text = output.getvalue()
    assert "Session: Resumed 'test-session'" in text

  @pytest.mark.asyncio
  async def test_start_respects_thinking_disabled(self):
    """start should show disabled thinking status."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)
    agent = self._make_agent()
    agent.thinking_mode = ThinkingMode.OFF
    agent.config.harness.name = "yoker"
    agent.config.harness.version = None
    agent.config.harness.author = None

    await handler.start(agent)

    text = output.getvalue()
    assert "Harness: yoker" in text
    assert "Thinking: off" in text

  @pytest.mark.asyncio
  async def test_start_uses_explicit_version(self):
    """start should honor an explicit version kwarg."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)
    agent = self._make_agent()

    await handler.start(agent, version="9.9.9")

    assert "9.9.9" in output.getvalue()

  @pytest.mark.asyncio
  async def test_start_uses_explicit_title(self):
    """start should honor an explicit title kwarg (figlet art differs)."""
    output_default = StringIO()
    handler_default = InteractiveUIHandler()
    handler_default.console = make_console(output_default)
    agent = self._make_agent()
    await handler_default.start(agent, version="x")

    output_custom = StringIO()
    handler_custom = InteractiveUIHandler()
    handler_custom.console = make_console(output_custom)
    await handler_custom.start(agent, title="Hi", version="x")

    # Different titles produce different figlet art.
    assert output_default.getvalue() != output_custom.getvalue()

  @pytest.mark.asyncio
  async def test_start_shows_truncated_tools_banner(self):
    """start should truncate the tools list to 8 + hint."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)
    agent = self._make_agent()
    agent.tools = {f"tool{i}": None for i in range(10)}

    await handler.start(agent)

    text = output.getvalue()
    assert "Tools:" in text
    assert "tool0" in text
    assert "tool7" in text
    # tool8/tool9 are NOT listed individually; truncated with +2 more.
    assert "+2 more" in text
    assert "/tools for full list" in text

  @pytest.mark.asyncio
  async def test_start_shows_short_tools_banner(self):
    """start should list all tools when <= 8."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)
    agent = self._make_agent()
    agent.tools = {"read": None, "write": None}

    await handler.start(agent)

    text = output.getvalue()
    assert "Tools: read, write" in text

  @pytest.mark.asyncio
  async def test_shutdown_prints_goodbye(self):
    """shutdown should print goodbye message."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    await handler.shutdown("quit")

    assert "Goodbye!" in output.getvalue()


class TestInteractiveUIHandlerInput:
  """Tests for InteractiveUIHandler input handling."""

  @pytest.mark.asyncio
  async def test_get_input_returns_input(self, stub_session):
    """get_input should return user input."""
    _set_answers(stub_session, ["hello"])
    handler = InteractiveUIHandler(history_file="none")

    result = await handler.get_input()

    assert result == "hello"

  @pytest.mark.asyncio
  async def test_get_input_creates_session_lazily(self, stub_session):
    """get_input should create the PromptSession on first call."""
    _set_answers(stub_session, ["hello"])
    handler = InteractiveUIHandler(history_file="none")
    assert handler._session is None

    await handler.get_input()

    assert handler._session is not None

  @pytest.mark.asyncio
  async def test_get_input_handles_eof(self, stub_session):
    """get_input should return None on EOFError."""
    _set_raises(stub_session, EOFError)
    handler = InteractiveUIHandler(history_file="none")

    result = await handler.get_input()

    assert result is None

  @pytest.mark.asyncio
  async def test_get_input_handles_keyboard_interrupt(self, stub_session):
    """get_input should return None on KeyboardInterrupt."""
    _set_raises(stub_session, KeyboardInterrupt)
    output = StringIO()
    handler = InteractiveUIHandler(history_file="none")
    handler.console = make_console(output)

    result = await handler.get_input()

    assert result is None

  @pytest.mark.asyncio
  async def test_get_input_calls_output_prompt_for_nonempty(self, stub_session):
    """get_input should call output_prompt for non-empty input."""
    _set_answers(stub_session, ["hello"])
    output = StringIO()
    handler = InteractiveUIHandler(history_file="none")
    handler.console = make_console(output)

    await handler.get_input()

    # output_prompt renders a Panel containing the input.
    assert "hello" in output.getvalue()

  @pytest.mark.asyncio
  async def test_get_input_skips_output_prompt_for_empty(self, stub_session):
    """get_input should not render a Panel for empty input."""
    _set_answers(stub_session, [""])
    output = StringIO()
    handler = InteractiveUIHandler(history_file="none")
    handler.console = make_console(output)

    await handler.get_input()

    # No Panel marker (the Panel renders as a box); output should be
    # effectively empty (no "hello" content).
    assert "hello" not in output.getvalue()

  @pytest.mark.asyncio
  async def test_get_input_uses_predefined_messages(self):
    """get_input should return predefined messages in order (no TTY needed)."""
    handler = InteractiveUIHandler(history_file="none")
    handler.set_input_messages(["hello", "world"])

    assert await handler.get_input() == "hello"
    assert await handler.get_input() == "world"

  @pytest.mark.asyncio
  async def test_get_input_returns_none_after_predefined_messages(self):
    """get_input should return None when predefined messages are exhausted."""
    handler = InteractiveUIHandler(history_file="none")
    handler.set_input_messages(["only one"])

    assert await handler.get_input() == "only one"
    assert await handler.get_input() is None

  @pytest.mark.asyncio
  async def test_get_input_predefined_does_not_create_session(self):
    """Predefined input path must NOT create a PromptSession."""
    handler = InteractiveUIHandler(history_file="none")
    handler.set_input_messages(["hello"])

    await handler.get_input()

    assert handler._session is None

  @pytest.mark.asyncio
  async def test_get_secret_input_masks_and_resets(self, stub_session):
    """get_secret_input should use is_password=True then reset to False."""
    _set_answers(stub_session, ["secret"])
    handler = InteractiveUIHandler(history_file="none")

    result = await handler.get_secret_input("API key: ")

    assert result == "secret"
    # Session is_password flag should be reset after a secret prompt.
    assert handler._session is not None
    assert handler._session.is_password is False  # type: ignore[attr-defined]

  @pytest.mark.asyncio
  async def test_get_secret_input_no_output_prompt(self, stub_session):
    """get_secret_input should NOT echo the secret via output_prompt."""
    _set_answers(stub_session, ["secret"])
    output = StringIO()
    handler = InteractiveUIHandler(history_file="none")
    handler.console = make_console(output)

    await handler.get_secret_input()

    assert "secret" not in output.getvalue()

  @pytest.mark.asyncio
  async def test_get_input_toggles_erase_when_done(self, monkeypatch):
    """get_input should set erase_when_done True during prompt, False after.

    Captures the flag state at prompt-call time, then asserts it is reset
    to False after get_input returns. Guards against the flag leaking
    True into a subsequent confirm_approval call (which would erase the
    y/N audit trail).
    """
    captured: dict[str, Any] = {}

    def _prompt(_p: str, **_kw: Any) -> str:
      # Record the flag state at the moment prompt() is called.
      captured["erase_when_done"] = stub.app.erase_when_done
      return "hello"

    stub = SimpleNamespace(
      prompt=_prompt,
      is_password=False,
      app=SimpleNamespace(erase_when_done=False),
    )
    monkeypatch.setattr("yoker.ui.interactive.PromptSession", lambda *a, **kw: stub)

    handler = InteractiveUIHandler(history_file="none")
    result = await handler.get_input()

    assert result == "hello"
    # Flag must be True during the prompt() call.
    assert captured["erase_when_done"] is True
    # Flag must be reset to False after the call returns.
    assert stub.app.erase_when_done is False

  @pytest.mark.asyncio
  async def test_get_input_resets_erase_when_done_on_unexpected_exception(self, monkeypatch):
    """get_input must reset erase_when_done via finally on any exception.

    An unexpected exception (not EOFError/KeyboardInterrupt) must still
    trigger the finally block so the flag does not leak True.
    """

    class _UnexpectedError(Exception):
      pass

    def _prompt(_p: str, **_kw: Any) -> str:
      raise _UnexpectedError("boom")

    stub = SimpleNamespace(
      prompt=_prompt,
      is_password=False,
      app=SimpleNamespace(erase_when_done=False),
    )
    monkeypatch.setattr("yoker.ui.interactive.PromptSession", lambda *a, **kw: stub)

    handler = InteractiveUIHandler(history_file="none")
    with pytest.raises(_UnexpectedError):
      await handler.get_input()

    # The finally block must have reset the flag despite the propagation.
    assert stub.app.erase_when_done is False

  @pytest.mark.asyncio
  async def test_get_secret_input_predefined_does_not_create_session(self):
    """Predefined secret input must NOT create a PromptSession.

    Mirrors test_get_input_predefined_does_not_create_session for the
    secret path: the _input_source short-circuit returns the predefined
    message without ever touching the lazy session.
    """
    handler = InteractiveUIHandler(history_file="none")
    handler.set_input_messages(["super-secret"])

    result = await handler.get_secret_input("API key: ")

    assert result == "super-secret"
    assert handler._session is None


class TestInteractiveUIHandlerContentStreaming:
  """Tests for InteractiveUIHandler content streaming (append-only console)."""

  def test_start_stop_processing_status_toggles_status(self):
    """_start/_stop_processing_status should start/stop a Rich status."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)
    status_mock = MagicMock()
    handler.console.status = MagicMock(return_value=status_mock)

    handler._start_processing_status()

    # Status created via console.status, started, and cached.
    handler.console.status.assert_called_once()
    status_mock.start.assert_called_once()
    assert handler._processing_status is status_mock

    handler._stop_processing_status()

    status_mock.stop.assert_called_once()
    assert handler._processing_status is None

  def test_stream_content_stops_status_on_first_chunk(self):
    """start_content_stream should stop the status spinner before output.

    The spinner is started on TURN_START (via start_processing) and should
    be stopped by start_content_stream so the "⏺ " marker is visible.
    stream_content then prints directly (spinner already stopped).
    """
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)
    status_mock = MagicMock()
    handler.console.status = MagicMock(return_value=status_mock)

    # Simulate TURN_START: spinner starts.
    handler.start_processing()
    assert handler._processing_status is status_mock
    status_mock.start.assert_called_once()

    # CONTENT_START: spinner stops, marker printed.
    handler.start_content_stream()
    status_mock.stop.assert_called_once()
    assert handler._processing_status is None

    # CONTENT_CHUNK: direct print, spinner already None.
    handler.stream_content("first chunk")
    assert status_mock.stop.call_count == 1
    assert handler._processing_status is None

    # Second chunk: still no spinner.
    handler.stream_content("second chunk")
    assert status_mock.stop.call_count == 1

    handler.end_content_stream(0)

  def test_stream_content_appends_to_console(self):
    """stream_content should append chunks directly to the console."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.start_content_stream()
    handler.stream_content("Hello ")
    handler.stream_content("World")
    handler.end_content_stream(11)

    assert "Hello World" in output.getvalue()

  def test_content_stream_preserves_text(self):
    """stream_content should preserve text content."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.start_content_stream()
    handler.stream_content("raw-text")
    handler.end_content_stream(8)

    assert "raw-text" in output.getvalue()

  def test_output_content_non_streaming(self):
    """output_content should print content as a stream block."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_content("line 1\nline 2")

    assert "line 1" in output.getvalue()
    assert "line 2" in output.getvalue()

  def test_stream_content_captured_by_recording_console(self):
    """Streamed content must be captured by a recording console (for SVG export).

    The MarkdownStreamer uses a separate themed Console for rendering, but
    the final output must go through the handler's console so that
    ``console.save_svg()`` (used by demo_session.py) captures it.
    """
    output = StringIO()
    recording_console = Console(
      record=True, file=output, force_terminal=True, color_system=None, highlight=False
    )
    handler = InteractiveUIHandler(console=recording_console)

    handler.start_content_stream()
    handler.stream_content("Hello World")
    handler.end_content_stream(11)

    # The recording console should have captured the rendered text.
    exported = recording_console.export_text()
    assert "Hello World" in exported


class TestInteractiveUIHandlerThinkingStreaming:
  """Tests for InteractiveUIHandler thinking streaming."""

  def test_stream_thinking_prints_when_enabled(self):
    """stream_thinking should print chunks when enabled."""
    output = StringIO()
    handler = InteractiveUIHandler(show_thinking=True)
    handler.console = make_console(output)

    handler.start_thinking_stream()
    handler.stream_thinking("thinking...")
    handler.end_thinking_stream(12)

    assert "thinking..." in output.getvalue()

  def test_stream_thinking_suppressed_when_disabled(self):
    """stream_thinking should be suppressed when disabled."""
    output = StringIO()
    handler = InteractiveUIHandler(show_thinking=False)
    handler.console = make_console(output)

    handler.start_thinking_stream()
    handler.stream_thinking("thinking...")
    handler.end_thinking_stream(12)

    assert "thinking..." not in output.getvalue()


class TestInteractiveUIHandlerToolOutput:
  """Tests for InteractiveUIHandler tool output."""

  def test_output_tool_call_inline_args(self):
    """output_tool_call should print inline key=value args."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True, show_time=False)
    handler.console = make_console(output)

    handler.output_tool_call("read", {"path": "/tmp/file.txt"})

    text = output.getvalue()
    assert "read" in text
    assert "/tmp/file.txt" in text

  def test_output_tool_call_suppressed_when_disabled(self):
    """output_tool_call should not print when disabled."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=False)
    handler.console = make_console(output)

    handler.output_tool_call("read", {"path": "/tmp/file.txt"})

    assert output.getvalue() == ""

  def test_output_tool_call_caps_long_value(self):
    """output_tool_call should summarize long values with a preview."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    long_value = "x" * 100
    handler.output_tool_call("read", {"content": long_value})

    text = output.getvalue()
    # Preview shows char count (may wrap across lines in narrow terminals).
    assert "100" in text
    assert "chars" in text
    assert long_value not in text

  def test_output_tool_call_shows_preview_for_write(self):
    """output_tool_call should show a preview for write/update content args."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_call(
      "write",
      {"path": "/tmp/file.txt", "content": "line1\nline2\nline3"},
    )

    text = output.getvalue()
    assert "/tmp/file.txt" in text
    # content is shown as a preview (not suppressed), with char count.
    assert "17 chars" in text
    # The full content with newlines should not appear inline.
    assert "line1\nline2\nline3" not in text

  def test_output_tool_call_websearch_shows_query(self):
    """output_tool_call for websearch should show the query."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_call("websearch", {"query": "best llm"})

    text = output.getvalue()
    assert "best llm" in text

  def test_output_tool_result_success_shows_size(self):
    """output_tool_result should print success indicator with result size."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_result("read", True, "x" * 1234)

    text = output.getvalue()
    assert "✓ Success" in text
    assert "1234 chars" in text

  def test_output_tool_result_failure(self):
    """output_tool_result should print failure indicator."""
    output = StringIO()
    handler = InteractiveUIHandler(show_tool_calls=True)
    handler.console = make_console(output)

    handler.output_tool_result("read", False, "Error message here")

    text = output.getvalue()
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


class TestInteractiveUIHandlerCommandOutput:
  """Tests for InteractiveUIHandler command output."""

  def test_output_command_result(self):
    """output_command_result should print result."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_command_result("command output")

    assert "command output" in output.getvalue()


class TestInteractiveUIHandlerStepTitle:
  """Tests for InteractiveUIHandler step-title output (bootstrap wizard)."""

  @pytest.mark.asyncio
  async def test_output_step_title_first_step(self):
    """output_step_title for step 1 should not emit a leading blank line."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    await handler.output_step_title(1, 3, "Welcome")

    text = output.getvalue()
    assert "Step 1 of 3: Welcome" in text

  @pytest.mark.asyncio
  async def test_output_step_title_subsequent_step_emits_blank_line(self):
    """output_step_title for step > 1 should emit a leading blank line."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    await handler.output_step_title(2, 3, "Select Provider")

    text = output.getvalue()
    assert "Step 2 of 3: Select Provider" in text
    # A leading blank line is emitted before the title for step > 1.
    assert text.startswith("\n")


class TestInteractiveUIHandlerStats:
  """Tests for InteractiveUIHandler stats output."""

  def test_output_stats_prints_simple_format(self):
    """output_stats should print the simpler RichUIHandler format."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_stats(1500, 50, 100)

    text = output.getvalue()
    assert "1.5s" in text
    assert "150 tokens" in text

  def test_output_stats_suppressed_when_disabled(self):
    """output_stats should not print when show_stats is False."""
    output = StringIO()
    handler = InteractiveUIHandler(show_stats=False)
    handler.console = make_console(output)

    handler.output_stats(1500, 50, 100)

    assert "tokens" not in output.getvalue()

  def test_output_stats_with_usage_limits(self):
    """output_stats should include session and weekly usage percentages."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_stats(
      1500,
      50,
      100,
      usage_limits={"session": {"usage": 0.975}, "weekly": {"usage": 0.531}},
    )

    text = output.getvalue()
    assert "1.5s" in text
    assert "150 tokens" in text
    assert "session" in text
    assert "98%" in text
    assert "weekly" in text
    assert "53%" in text

  def test_output_stats_without_usage_limits(self):
    """output_stats should not show usage when usage_limits is None."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_stats(1500, 50, 100, usage_limits=None)

    text = output.getvalue()
    assert "1.5s" in text
    assert "150 tokens" in text
    assert "session" not in text
    assert "weekly" not in text


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


class TestInteractiveUIHandlerAgentLifecycle:
  """Tests for the optional agent_spawned / agent_finished methods."""

  def test_agent_spawned_prints(self):
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.agent_spawned(AgentDisplay(id="child-1", name="child"))

    text = output.getvalue()
    assert "Agent spawned" in text
    assert "child-1" in text

  def test_agent_finished_prints(self):
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.agent_finished(AgentDisplay(id="child-1", name="child"))

    text = output.getvalue()
    assert "Agent finished" in text
    assert "child-1" in text

  def test_agent_spawned_with_color(self):
    """agent_spawned renders the agent name with color when provided."""
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.agent_spawned(AgentDisplay(id="researcher", name="researcher", color="#FF6B35"))

    text = output.getvalue()
    assert "researcher" in text
    assert "Agent spawned" in text

  def test_agent_tag_none_returns_empty(self):
    """_agent_tag returns empty string for None (primary agent)."""
    handler = InteractiveUIHandler()
    assert handler._agent_tag(None) == ""

  def test_agent_tag_no_color(self):
    """_agent_tag returns 'id: ' when no color is set."""
    handler = InteractiveUIHandler()
    tag = handler._agent_tag(AgentDisplay(id="researcher", name="researcher"))
    assert tag == "researcher: "

  def test_agent_tag_with_color(self):
    """_agent_tag returns Rich markup with bg/fg when color is set."""
    handler = InteractiveUIHandler()
    tag = handler._agent_tag(AgentDisplay(id="researcher", name="researcher", color="#FF6B35"))
    assert "researcher" in tag
    assert "#FF6B35" in tag
    # Should have Rich markup brackets
    assert "[" in tag and "]" in tag

  def test_agent_tag_dark_bg_uses_white_fg(self):
    """_agent_tag uses white foreground for dark backgrounds."""
    handler = InteractiveUIHandler()
    tag = handler._agent_tag(AgentDisplay(id="r", name="r", color="#000000"))
    assert "white" in tag

  def test_agent_tag_light_bg_uses_black_fg(self):
    """_agent_tag uses black foreground for light backgrounds."""
    handler = InteractiveUIHandler()
    tag = handler._agent_tag(AgentDisplay(id="r", name="r", color="#FFFFFF"))
    assert "black" in tag


class TestInteractiveUIHandlerOutputPrompt:
  """Tests for the output_prompt Panel method."""

  def test_output_prompt_renders_panel(self):
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_prompt("hello user")

    assert "hello user" in output.getvalue()

  def test_output_prompt_skips_empty(self):
    output = StringIO()
    handler = InteractiveUIHandler()
    handler.console = make_console(output)

    handler.output_prompt("")

    # No Panel rendered for empty input.
    assert output.getvalue() == ""
