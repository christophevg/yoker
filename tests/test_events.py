"""Tests for yoker events module."""

from io import StringIO

import pytest
from pytest_mock import MockerFixture
from rich.console import Console

from yoker.events import (
  CommandEvent,
  ConsoleEventHandler,
  ContentChunkEvent,
  ErrorEvent,
  EventType,
  SessionEndEvent,
  SessionStartEvent,
  ThinkingChunkEvent,
  ToolCallEvent,
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
)
from yoker.events.types import Event


class TestEventTypes:
  """Tests for event type definitions."""

  def test_event_type_values(self) -> None:
    """Test that all event types have unique values."""
    event_types = list(EventType)
    values = [et.value for et in event_types]
    assert len(values) == len(set(values))  # All unique

  def test_event_type_count(self) -> None:
    """Test that all expected event types exist."""
    expected = [
      "SESSION_START",
      "SESSION_END",
      "TURN_START",
      "TURN_END",
      "THINKING_START",
      "THINKING_CHUNK",
      "THINKING_END",
      "CONTENT_START",
      "CONTENT_CHUNK",
      "CONTENT_END",
      "TOOL_CALL",
      "TOOL_RESULT",
      "COMMAND",
      "ERROR",
    ]
    actual = [et.name for et in EventType]
    assert set(expected) == set(actual)


class TestEventClasses:
  """Tests for event dataclasses."""

  def test_session_start_event(self) -> None:
    """Test SessionStartEvent creation."""
    event = SessionStartEvent(
      type=EventType.SESSION_START,
      model="test-model",
      thinking_enabled=True,
    )
    assert event.model == "test-model"
    assert event.thinking_enabled is True
    assert event.type == EventType.SESSION_START

  def test_session_end_event(self) -> None:
    """Test SessionEndEvent creation."""
    event = SessionEndEvent(type=EventType.SESSION_END, reason="quit")
    assert event.reason == "quit"
    assert event.type == EventType.SESSION_END

  def test_turn_start_event(self) -> None:
    """Test TurnStartEvent creation."""
    event = TurnStartEvent(type=EventType.TURN_START, message="Hello")
    assert event.message == "Hello"
    assert event.type == EventType.TURN_START

  def test_turn_end_event(self) -> None:
    """Test TurnEndEvent creation."""
    event = TurnEndEvent(
      type=EventType.TURN_END,
      response="Hi there",
      tool_calls_count=2,
    )
    assert event.response == "Hi there"
    assert event.tool_calls_count == 2

  def test_thinking_chunk_event(self) -> None:
    """Test ThinkingChunkEvent creation."""
    event = ThinkingChunkEvent(type=EventType.THINKING_CHUNK, text="thinking...")
    assert event.text == "thinking..."

  def test_content_chunk_event(self) -> None:
    """Test ContentChunkEvent creation."""
    event = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Hello world")
    assert event.text == "Hello world"

  def test_tool_call_event(self) -> None:
    """Test ToolCallEvent creation."""
    event = ToolCallEvent(
      type=EventType.TOOL_CALL,
      tool_name="read",
      arguments={"path": "/tmp/test.txt"},
    )
    assert event.tool_name == "read"
    assert event.arguments == {"path": "/tmp/test.txt"}

  def test_tool_result_event(self) -> None:
    """Test ToolResultEvent creation."""
    event = ToolResultEvent(
      type=EventType.TOOL_RESULT,
      tool_name="read",
      result="file contents",
      success=True,
    )
    assert event.tool_name == "read"
    assert event.result == "file contents"
    assert event.success is True

  def test_error_event(self) -> None:
    """Test ErrorEvent creation."""
    event = ErrorEvent(
      type=EventType.ERROR,
      error_type="ValueError",
      message="Something went wrong",
    )
    assert event.error_type == "ValueError"
    assert event.message == "Something went wrong"

  def test_command_event(self) -> None:
    """Test CommandEvent creation."""
    event = CommandEvent(
      type=EventType.COMMAND,
      command="/help",
      result="Available commands:\n  /help - Show help",
    )
    assert event.command == "/help"
    assert event.result == "Available commands:\n  /help - Show help"
    assert event.type == EventType.COMMAND

  def test_events_are_frozen(self) -> None:
    """Test that events are immutable (frozen dataclasses)."""
    event = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="test")
    with pytest.raises(AttributeError):
      event.text = "modified"  # type: ignore[misc]


class TestConsoleEventHandler:
  """Tests for ConsoleEventHandler."""

  @pytest.fixture
  def console_handler(self) -> ConsoleEventHandler:
    """Create a ConsoleEventHandler with captured output."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    return ConsoleEventHandler(console=console, show_thinking=True, show_tool_calls=True)

  def test_handler_handles_content_chunk(self, console_handler: ConsoleEventHandler) -> None:
    """Test that ContentChunkEvent is handled."""
    event = ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Hello")
    console_handler(event)
    assert "Hello" in console_handler.console.file.getvalue()  # type: ignore[attr-defined]

  def test_handler_handles_session_start(self, console_handler: ConsoleEventHandler) -> None:
    """Test that SessionStartEvent is handled."""
    event = SessionStartEvent(
      type=EventType.SESSION_START,
      model="llama3.2",
      thinking_enabled=True,
    )
    console_handler(event)
    output = console_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "llama3.2" in output
    assert "enabled" in output

  def test_handler_handles_session_end(self, console_handler: ConsoleEventHandler) -> None:
    """Test that SessionEndEvent is handled."""
    event = SessionEndEvent(type=EventType.SESSION_END, reason="quit")
    console_handler(event)
    output = console_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "Goodbye" in output

  def test_handler_handles_thinking_chunk(self, console_handler: ConsoleEventHandler) -> None:
    """Test that ThinkingChunkEvent is handled."""
    event = ThinkingChunkEvent(type=EventType.THINKING_CHUNK, text="reasoning...")
    console_handler(event)
    assert "reasoning" in console_handler.console.file.getvalue()  # type: ignore[attr-defined]

  def test_handler_hides_thinking_when_disabled(self) -> None:
    """Test that thinking output is hidden when show_thinking=False."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    handler = ConsoleEventHandler(console=console, show_thinking=False)
    event = ThinkingChunkEvent(type=EventType.THINKING_CHUNK, text="reasoning...")
    handler(event)
    # Thinking should not appear in output
    assert "reasoning" not in output.getvalue()

  def test_handler_handles_tool_call(self, console_handler: ConsoleEventHandler) -> None:
    """Test that ToolCallEvent is handled."""
    event = ToolCallEvent(
      type=EventType.TOOL_CALL,
      tool_name="read",
      arguments={"path": "/tmp/test.txt"},
    )
    console_handler(event)
    output = console_handler.console.file.getvalue()  # type: ignore[attr-defined]
    # New format: "Read tool: test.txt"
    assert "Read" in output
    assert "test.txt" in output

  def test_handler_hides_tool_calls_when_disabled(self) -> None:
    """Test that tool calls are hidden when show_tool_calls=False."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    handler = ConsoleEventHandler(console=console, show_tool_calls=False)
    event = ToolCallEvent(
      type=EventType.TOOL_CALL,
      tool_name="read",
      arguments={"path": "/tmp/test.txt"},
    )
    handler(event)
    assert "read" not in output.getvalue().lower()

  def test_handler_handles_error(self, console_handler: ConsoleEventHandler) -> None:
    """Test that ErrorEvent is handled."""
    event = ErrorEvent(
      type=EventType.ERROR,
      error_type="ValueError",
      message="Something went wrong",
    )
    console_handler(event)
    output = console_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "Error" in output
    assert "ValueError" in output

  def test_handler_handles_command(self, console_handler: ConsoleEventHandler) -> None:
    """Test that CommandEvent is handled."""
    event = CommandEvent(
      type=EventType.COMMAND,
      command="/help",
      result="Available commands:\n  /help - Show help\n  /think - Toggle thinking",
    )
    console_handler(event)
    output = console_handler.console.file.getvalue()  # type: ignore[attr-defined]
    assert "Available commands" in output
    assert "/help" in output

  def test_handler_handles_command_empty_result(self, console_handler: ConsoleEventHandler) -> None:
    """Test that CommandEvent with empty result doesn't print anything."""
    event = CommandEvent(
      type=EventType.COMMAND,
      command="/unknown",
      result="",
    )
    console_handler(event)
    output = console_handler.console.file.getvalue()  # type: ignore[attr-defined]
    # Empty result should not produce output
    assert output == ""

  def test_handler_extract_filename_with_file_path(self) -> None:
    """Test _extract_filename with file_path argument."""
    handler = ConsoleEventHandler()
    result = handler._extract_filename({"file_path": "/path/to/test.txt"})
    assert result == "test.txt"

  def test_handler_extract_filename_with_path(self) -> None:
    """Test _extract_filename with path argument."""
    handler = ConsoleEventHandler()
    result = handler._extract_filename({"path": "/tmp/myfile.py"})
    assert result == "myfile.py"

  def test_handler_extract_filename_fallback(self) -> None:
    """Test _extract_filename fallback to first argument value."""
    handler = ConsoleEventHandler()
    result = handler._extract_filename({"query": "some query"})
    assert result == "some query"

  def test_handler_extract_filename_empty_args(self) -> None:
    """Test _extract_filename with empty arguments."""
    handler = ConsoleEventHandler()
    result = handler._extract_filename({})
    assert result == ""

  def test_handler_capitalize(self) -> None:
    """Test _capitalize helper."""
    handler = ConsoleEventHandler()
    assert handler._capitalize("read") == "Read"
    assert handler._capitalize("Read") == "Read"
    assert handler._capitalize("") == ""

  def test_handler_tool_call_display_format(self, console_handler: ConsoleEventHandler) -> None:
    """Test that tool call display shows filename only."""
    event = ToolCallEvent(
      type=EventType.TOOL_CALL,
      tool_name="read",
      arguments={"file_path": "/long/path/to/some/file.py"},
    )
    console_handler(event)
    output = console_handler.console.file.getvalue()  # type: ignore[attr-defined]
    # Should show capitalized tool name and filename only
    assert "Read tool: file.py" in output
    # Should NOT show full path
    assert "/long/path" not in output


class TestEventCollector:
  """Test helper to collect events."""

  def __init__(self) -> None:
    self.events: list[Event] = []

  def __call__(self, event: Event) -> None:
    self.events.append(event)


class TestAgentEventEmission:
  """Tests for Agent event emission."""

  def test_agent_emits_events_during_process(self, mocker: MockerFixture) -> None:
    """Test that Agent emits events during process()."""
    # Mock the ollama client
    mock_client = mocker.MagicMock()
    mock_chunk = mocker.MagicMock()
    mock_chunk.message.thinking = None
    mock_chunk.message.content = "Hello there"
    mock_chunk.message.tool_calls: list = []
    mock_client.chat.return_value = [mock_chunk]

    mocker.patch("yoker.agent.Client", return_value=mock_client)

    from yoker.agent import Agent

    agent = Agent(model="test-model")
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    agent.process("Hi")

    # Check that events were emitted
    assert len(collector.events) > 0

    # Check for specific event types
    event_types = [e.type for e in collector.events]
    assert EventType.TURN_START in event_types
    assert EventType.TURN_END in event_types

  def test_agent_add_remove_handler(self) -> None:
    """Test adding and removing event handlers."""
    from yoker.agent import Agent

    agent = Agent(model="test-model")

    def handler(event: Event) -> None:
      pass

    agent.add_event_handler(handler)
    assert handler in agent._event_handlers

    agent.remove_event_handler(handler)
    assert handler not in agent._event_handlers

  def test_agent_emits_session_events(self) -> None:
    """Test that Agent emits session events via begin_session/end_session."""
    from yoker.agent import Agent

    agent = Agent(model="test-model")
    collector = TestEventCollector()
    agent.add_event_handler(collector)

    # Begin session
    agent.begin_session()

    # End session
    agent.end_session(reason="quit")

    # Check session events
    event_types = [e.type for e in collector.events]
    assert EventType.SESSION_START in event_types
    assert EventType.SESSION_END in event_types
