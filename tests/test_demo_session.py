"""Tests for demo_session.py module."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from yoker.events import (
  EventRecorder,
  EventReplayAgent,
  deserialize_event,
  serialize_event,
)
from yoker.events.types import (
  CommandEvent,
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  ErrorEvent,
  EventType,
  SessionEndEvent,
  SessionStartEvent,
  ThinkingChunkEvent,
  ThinkingEndEvent,
  ThinkingStartEvent,
  ToolCallEvent,
  ToolResultEvent,
  TurnEndEvent,
  TurnStartEvent,
)

# Import demo_session specific classes
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from demo_session import (  # noqa: E402
  PredefinedInput,
  ReplayInput,
)


class TestSerializeEvent:
  """Tests for serialize_event function."""

  def test_serialize_session_start_event(self) -> None:
    """Test serializing SessionStartEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = SessionStartEvent(
      type=EventType.SESSION_START,
      timestamp=timestamp,
      model="llama3.2",
      thinking_enabled=True,
      config_summary={"key": "value"},
    )
    result = serialize_event(event)

    assert result["type"] == "SESSION_START"
    assert result["timestamp"] == "2026-04-21T10:30:00"
    assert result["data"]["model"] == "llama3.2"
    assert result["data"]["thinking_enabled"] is True
    assert result["data"]["config_summary"] == {"key": "value"}

  def test_serialize_session_start_event_no_config(self) -> None:
    """Test serializing SessionStartEvent without config_summary."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = SessionStartEvent(
      type=EventType.SESSION_START,
      timestamp=timestamp,
      model="llama3.2",
      thinking_enabled=True,
    )
    result = serialize_event(event)

    assert result["data"]["config_summary"] == {}

  def test_serialize_session_end_event(self) -> None:
    """Test serializing SessionEndEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = SessionEndEvent(
      type=EventType.SESSION_END,
      timestamp=timestamp,
      reason="quit",
    )
    result = serialize_event(event)

    assert result["type"] == "SESSION_END"
    assert result["timestamp"] == "2026-04-21T10:30:00"
    assert result["data"]["reason"] == "quit"

  def test_serialize_turn_start_event(self) -> None:
    """Test serializing TurnStartEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = TurnStartEvent(
      type=EventType.TURN_START,
      timestamp=timestamp,
      message="Hello world",
    )
    result = serialize_event(event)

    assert result["type"] == "TURN_START"
    assert result["data"]["message"] == "Hello world"

  def test_serialize_turn_end_event(self) -> None:
    """Test serializing TurnEndEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = TurnEndEvent(
      type=EventType.TURN_END,
      timestamp=timestamp,
      response="Hello there",
      tool_calls_count=3,
    )
    result = serialize_event(event)

    assert result["type"] == "TURN_END"
    assert result["data"]["response"] == "Hello there"
    assert result["data"]["tool_calls_count"] == 3

  def test_serialize_turn_end_event_no_tools(self) -> None:
    """Test serializing TurnEndEvent with no tool calls."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = TurnEndEvent(
      type=EventType.TURN_END,
      timestamp=timestamp,
      response="Hello there",
    )
    result = serialize_event(event)

    assert result["data"]["tool_calls_count"] == 0

  def test_serialize_thinking_start_event(self) -> None:
    """Test serializing ThinkingStartEvent (no data fields)."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ThinkingStartEvent(
      type=EventType.THINKING_START,
      timestamp=timestamp,
    )
    result = serialize_event(event)

    assert result["type"] == "THINKING_START"
    assert result["data"] == {}

  def test_serialize_thinking_chunk_event(self) -> None:
    """Test serializing ThinkingChunkEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ThinkingChunkEvent(
      type=EventType.THINKING_CHUNK,
      timestamp=timestamp,
      text="reasoning...",
    )
    result = serialize_event(event)

    assert result["type"] == "THINKING_CHUNK"
    assert result["data"]["text"] == "reasoning..."

  def test_serialize_thinking_end_event(self) -> None:
    """Test serializing ThinkingEndEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ThinkingEndEvent(
      type=EventType.THINKING_END,
      timestamp=timestamp,
      total_length=100,
    )
    result = serialize_event(event)

    assert result["type"] == "THINKING_END"
    assert result["data"]["total_length"] == 100

  def test_serialize_content_start_event(self) -> None:
    """Test serializing ContentStartEvent (no data fields)."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ContentStartEvent(
      type=EventType.CONTENT_START,
      timestamp=timestamp,
    )
    result = serialize_event(event)

    assert result["type"] == "CONTENT_START"
    assert result["data"] == {}

  def test_serialize_content_chunk_event(self) -> None:
    """Test serializing ContentChunkEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ContentChunkEvent(
      type=EventType.CONTENT_CHUNK,
      timestamp=timestamp,
      text="Hello world",
    )
    result = serialize_event(event)

    assert result["type"] == "CONTENT_CHUNK"
    assert result["data"]["text"] == "Hello world"

  def test_serialize_content_end_event(self) -> None:
    """Test serializing ContentEndEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ContentEndEvent(
      type=EventType.CONTENT_END,
      timestamp=timestamp,
      total_length=200,
    )
    result = serialize_event(event)

    assert result["type"] == "CONTENT_END"
    assert result["data"]["total_length"] == 200

  def test_serialize_tool_call_event(self) -> None:
    """Test serializing ToolCallEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ToolCallEvent(
      type=EventType.TOOL_CALL,
      timestamp=timestamp,
      tool_name="read",
      arguments={"path": "/tmp/test.txt"},
    )
    result = serialize_event(event)

    assert result["type"] == "TOOL_CALL"
    assert result["data"]["tool_name"] == "read"
    assert result["data"]["arguments"] == {"path": "/tmp/test.txt"}

  def test_serialize_tool_result_event(self) -> None:
    """Test serializing ToolResultEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ToolResultEvent(
      type=EventType.TOOL_RESULT,
      timestamp=timestamp,
      tool_name="read",
      result="file contents",
      success=True,
    )
    result = serialize_event(event)

    assert result["type"] == "TOOL_RESULT"
    assert result["data"]["tool_name"] == "read"
    assert result["data"]["result"] == "file contents"
    assert result["data"]["success"] is True

  def test_serialize_tool_result_event_failure(self) -> None:
    """Test serializing ToolResultEvent with failure."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ToolResultEvent(
      type=EventType.TOOL_RESULT,
      timestamp=timestamp,
      tool_name="read",
      result="File not found",
      success=False,
    )
    result = serialize_event(event)

    assert result["data"]["success"] is False

  def test_serialize_error_event(self) -> None:
    """Test serializing ErrorEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ErrorEvent(
      type=EventType.ERROR,
      timestamp=timestamp,
      error_type="ValueError",
      message="Something went wrong",
      details={"key": "value"},
    )
    result = serialize_event(event)

    assert result["type"] == "ERROR"
    assert result["data"]["error_type"] == "ValueError"
    assert result["data"]["message"] == "Something went wrong"
    assert result["data"]["details"] == {"key": "value"}

  def test_serialize_error_event_no_details(self) -> None:
    """Test serializing ErrorEvent without details."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = ErrorEvent(
      type=EventType.ERROR,
      timestamp=timestamp,
      error_type="ValueError",
      message="Something went wrong",
    )
    result = serialize_event(event)

    assert result["data"]["details"] == {}

  def test_serialize_command_event(self) -> None:
    """Test serializing CommandEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = CommandEvent(
      type=EventType.COMMAND,
      timestamp=timestamp,
      command="/help",
      result="Available commands:\n  /help - Show help\n  /think - Toggle thinking",
    )
    result = serialize_event(event)

    assert result["type"] == "COMMAND"
    assert result["timestamp"] == "2026-04-21T10:30:00"
    assert result["data"]["command"] == "/help"
    assert "Available commands" in result["data"]["result"]


class TestDeserializeEvent:
  """Tests for deserialize_event function."""

  def test_deserialize_session_start_event(self) -> None:
    """Test deserializing SessionStartEvent."""
    entry: dict[str, Any] = {
      "type": "SESSION_START",
      "timestamp": "2026-04-21T10:30:00",
      "data": {
        "model": "llama3.2",
        "thinking_enabled": True,
        "config_summary": {"key": "value"},
      },
    }
    event = deserialize_event(entry)

    assert isinstance(event, SessionStartEvent)
    assert event.type == EventType.SESSION_START
    assert event.timestamp == datetime(2026, 4, 21, 10, 30, 0)
    assert event.model == "llama3.2"
    assert event.thinking_enabled is True
    assert event.config_summary == {"key": "value"}

  def test_deserialize_session_start_event_no_config(self) -> None:
    """Test deserializing SessionStartEvent without config_summary."""
    entry: dict[str, Any] = {
      "type": "SESSION_START",
      "timestamp": "2026-04-21T10:30:00",
      "data": {
        "model": "llama3.2",
        "thinking_enabled": True,
      },
    }
    event = deserialize_event(entry)

    assert event.config_summary == {}

  def test_deserialize_session_end_event(self) -> None:
    """Test deserializing SessionEndEvent."""
    entry: dict[str, Any] = {
      "type": "SESSION_END",
      "timestamp": "2026-04-21T10:30:00",
      "data": {"reason": "quit"},
    }
    event = deserialize_event(entry)

    assert isinstance(event, SessionEndEvent)
    assert event.reason == "quit"

  def test_deserialize_turn_start_event(self) -> None:
    """Test deserializing TurnStartEvent."""
    entry: dict[str, Any] = {
      "type": "TURN_START",
      "timestamp": "2026-04-21T10:30:00",
      "data": {"message": "Hello world"},
    }
    event = deserialize_event(entry)

    assert isinstance(event, TurnStartEvent)
    assert event.message == "Hello world"

  def test_deserialize_turn_end_event(self) -> None:
    """Test deserializing TurnEndEvent."""
    entry: dict[str, Any] = {
      "type": "TURN_END",
      "timestamp": "2026-04-21T10:30:00",
      "data": {"response": "Hello there", "tool_calls_count": 3},
    }
    event = deserialize_event(entry)

    assert isinstance(event, TurnEndEvent)
    assert event.response == "Hello there"
    assert event.tool_calls_count == 3

  def test_deserialize_turn_end_event_no_tools(self) -> None:
    """Test deserializing TurnEndEvent without tool_calls_count."""
    entry: dict[str, Any] = {
      "type": "TURN_END",
      "timestamp": "2026-04-21T10:30:00",
      "data": {"response": "Hello there"},
    }
    event = deserialize_event(entry)

    assert event.tool_calls_count == 0

  def test_deserialize_thinking_start_event(self) -> None:
    """Test deserializing ThinkingStartEvent."""
    entry: dict[str, Any] = {
      "type": "THINKING_START",
      "timestamp": "2026-04-21T10:30:00",
      "data": {},
    }
    event = deserialize_event(entry)

    assert isinstance(event, ThinkingStartEvent)

  def test_deserialize_thinking_chunk_event(self) -> None:
    """Test deserializing ThinkingChunkEvent."""
    entry: dict[str, Any] = {
      "type": "THINKING_CHUNK",
      "timestamp": "2026-04-21T10:30:00",
      "data": {"text": "reasoning..."},
    }
    event = deserialize_event(entry)

    assert isinstance(event, ThinkingChunkEvent)
    assert event.text == "reasoning..."

  def test_deserialize_thinking_end_event(self) -> None:
    """Test deserializing ThinkingEndEvent."""
    entry: dict[str, Any] = {
      "type": "THINKING_END",
      "timestamp": "2026-04-21T10:30:00",
      "data": {"total_length": 100},
    }
    event = deserialize_event(entry)

    assert isinstance(event, ThinkingEndEvent)
    assert event.total_length == 100

  def test_deserialize_content_start_event(self) -> None:
    """Test deserializing ContentStartEvent."""
    entry: dict[str, Any] = {
      "type": "CONTENT_START",
      "timestamp": "2026-04-21T10:30:00",
      "data": {},
    }
    event = deserialize_event(entry)

    assert isinstance(event, ContentStartEvent)

  def test_deserialize_content_chunk_event(self) -> None:
    """Test deserializing ContentChunkEvent."""
    entry: dict[str, Any] = {
      "type": "CONTENT_CHUNK",
      "timestamp": "2026-04-21T10:30:00",
      "data": {"text": "Hello world"},
    }
    event = deserialize_event(entry)

    assert isinstance(event, ContentChunkEvent)
    assert event.text == "Hello world"

  def test_deserialize_content_end_event(self) -> None:
    """Test deserializing ContentEndEvent."""
    entry: dict[str, Any] = {
      "type": "CONTENT_END",
      "timestamp": "2026-04-21T10:30:00",
      "data": {"total_length": 200},
    }
    event = deserialize_event(entry)

    assert isinstance(event, ContentEndEvent)
    assert event.total_length == 200

  def test_deserialize_tool_call_event(self) -> None:
    """Test deserializing ToolCallEvent."""
    entry: dict[str, Any] = {
      "type": "TOOL_CALL",
      "timestamp": "2026-04-21T10:30:00",
      "data": {"tool_name": "read", "arguments": {"path": "/tmp/test.txt"}},
    }
    event = deserialize_event(entry)

    assert isinstance(event, ToolCallEvent)
    assert event.tool_name == "read"
    assert event.arguments == {"path": "/tmp/test.txt"}

  def test_deserialize_tool_result_event(self) -> None:
    """Test deserializing ToolResultEvent."""
    entry: dict[str, Any] = {
      "type": "TOOL_RESULT",
      "timestamp": "2026-04-21T10:30:00",
      "data": {
        "tool_name": "read",
        "result": "file contents",
        "success": True,
      },
    }
    event = deserialize_event(entry)

    assert isinstance(event, ToolResultEvent)
    assert event.tool_name == "read"
    assert event.result == "file contents"
    assert event.success is True

  def test_deserialize_tool_result_event_default_success(self) -> None:
    """Test deserializing ToolResultEvent without success field defaults to True."""
    entry: dict[str, Any] = {
      "type": "TOOL_RESULT",
      "timestamp": "2026-04-21T10:30:00",
      "data": {
        "tool_name": "read",
        "result": "file contents",
      },
    }
    event = deserialize_event(entry)

    assert event.success is True

  def test_deserialize_error_event(self) -> None:
    """Test deserializing ErrorEvent."""
    entry: dict[str, Any] = {
      "type": "ERROR",
      "timestamp": "2026-04-21T10:30:00",
      "data": {
        "error_type": "ValueError",
        "message": "Something went wrong",
        "details": {"key": "value"},
      },
    }
    event = deserialize_event(entry)

    assert isinstance(event, ErrorEvent)
    assert event.error_type == "ValueError"
    assert event.message == "Something went wrong"
    assert event.details == {"key": "value"}

  def test_deserialize_error_event_no_details(self) -> None:
    """Test deserializing ErrorEvent without details."""
    entry: dict[str, Any] = {
      "type": "ERROR",
      "timestamp": "2026-04-21T10:30:00",
      "data": {
        "error_type": "ValueError",
        "message": "Something went wrong",
      },
    }
    event = deserialize_event(entry)

    assert event.details == {}

  def test_deserialize_command_event(self) -> None:
    """Test deserializing CommandEvent."""
    entry: dict[str, Any] = {
      "type": "COMMAND",
      "timestamp": "2026-04-21T10:30:00",
      "data": {
        "command": "/help",
        "result": "Available commands:\n  /help - Show help",
      },
    }
    event = deserialize_event(entry)

    assert isinstance(event, CommandEvent)
    assert event.command == "/help"
    assert "Available commands" in event.result


class TestSerializeDeserializeRoundTrip:
  """Tests for round-trip serialization/deserialization."""

  def test_roundtrip_session_start_event(self) -> None:
    """Test round-trip for SessionStartEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = SessionStartEvent(
      type=EventType.SESSION_START,
      timestamp=timestamp,
      model="llama3.2",
      thinking_enabled=True,
      config_summary={"key": "value"},
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.type == original.type
    assert deserialized.timestamp == original.timestamp
    assert deserialized.model == original.model
    assert deserialized.thinking_enabled == original.thinking_enabled
    assert deserialized.config_summary == original.config_summary

  def test_roundtrip_session_end_event(self) -> None:
    """Test round-trip for SessionEndEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = SessionEndEvent(
      type=EventType.SESSION_END,
      timestamp=timestamp,
      reason="quit",
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.type == original.type
    assert deserialized.timestamp == original.timestamp
    assert deserialized.reason == original.reason

  def test_roundtrip_turn_start_event(self) -> None:
    """Test round-trip for TurnStartEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = TurnStartEvent(
      type=EventType.TURN_START,
      timestamp=timestamp,
      message="Hello world",
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.message == original.message

  def test_roundtrip_turn_end_event(self) -> None:
    """Test round-trip for TurnEndEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = TurnEndEvent(
      type=EventType.TURN_END,
      timestamp=timestamp,
      response="Hello there",
      tool_calls_count=2,
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.response == original.response
    assert deserialized.tool_calls_count == original.tool_calls_count

  def test_roundtrip_thinking_chunk_event(self) -> None:
    """Test round-trip for ThinkingChunkEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = ThinkingChunkEvent(
      type=EventType.THINKING_CHUNK,
      timestamp=timestamp,
      text="reasoning...",
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.text == original.text

  def test_roundtrip_content_chunk_event(self) -> None:
    """Test round-trip for ContentChunkEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = ContentChunkEvent(
      type=EventType.CONTENT_CHUNK,
      timestamp=timestamp,
      text="Hello world",
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.text == original.text

  def test_roundtrip_tool_call_event(self) -> None:
    """Test round-trip for ToolCallEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = ToolCallEvent(
      type=EventType.TOOL_CALL,
      timestamp=timestamp,
      tool_name="read",
      arguments={"path": "/tmp/test.txt"},
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.tool_name == original.tool_name
    assert deserialized.arguments == original.arguments

  def test_roundtrip_tool_result_event(self) -> None:
    """Test round-trip for ToolResultEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = ToolResultEvent(
      type=EventType.TOOL_RESULT,
      timestamp=timestamp,
      tool_name="read",
      result="file contents",
      success=True,
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.tool_name == original.tool_name
    assert deserialized.result == original.result
    assert deserialized.success == original.success

  def test_roundtrip_error_event(self) -> None:
    """Test round-trip for ErrorEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = ErrorEvent(
      type=EventType.ERROR,
      timestamp=timestamp,
      error_type="ValueError",
      message="Something went wrong",
      details={"key": "value"},
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.error_type == original.error_type
    assert deserialized.message == original.message
    assert deserialized.details == original.details

  def test_roundtrip_command_event(self) -> None:
    """Test round-trip for CommandEvent."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    original = CommandEvent(
      type=EventType.COMMAND,
      timestamp=timestamp,
      command="/help",
      result="Available commands:\n  /help - Show help\n  /think - Toggle thinking",
    )

    serialized = serialize_event(original)
    deserialized = deserialize_event(serialized)

    assert deserialized.command == original.command
    assert deserialized.result == original.result


class TestEventRecorder:
  """Tests for EventRecorder class."""

  def test_recorder_creates_file(self, tmp_path: Path) -> None:
    """Test that EventRecorder creates a file."""
    log_path = tmp_path / "events.jsonl"
    recorder = EventRecorder(log_path)

    assert log_path.exists()
    recorder.close()

  def test_recorder_writes_event(self, tmp_path: Path) -> None:
    """Test that EventRecorder writes events to file."""
    log_path = tmp_path / "events.jsonl"
    recorder = EventRecorder(log_path)

    event = SessionStartEvent(
      type=EventType.SESSION_START,
      model="llama3.2",
      thinking_enabled=True,
    )
    recorder(event)
    recorder.close()

    content = log_path.read_text()
    assert "SESSION_START" in content
    assert "llama3.2" in content

  def test_recorder_writes_multiple_events(self, tmp_path: Path) -> None:
    """Test that EventRecorder writes multiple events."""
    log_path = tmp_path / "events.jsonl"
    recorder = EventRecorder(log_path)

    recorder(SessionStartEvent(
      type=EventType.SESSION_START,
      model="llama3.2",
      thinking_enabled=True,
    ))
    recorder(TurnStartEvent(
      type=EventType.TURN_START,
      message="Hello",
    ))
    recorder(TurnEndEvent(
      type=EventType.TURN_END,
      response="Hi there",
    ))
    recorder.close()

    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 3

    entries = [json.loads(line) for line in lines]
    assert entries[0]["type"] == "SESSION_START"
    assert entries[1]["type"] == "TURN_START"
    assert entries[2]["type"] == "TURN_END"

  def test_recorder_flushes_after_write(self, tmp_path: Path) -> None:
    """Test that EventRecorder flushes after each write."""
    log_path = tmp_path / "events.jsonl"
    recorder = EventRecorder(log_path)

    event = ContentChunkEvent(
      type=EventType.CONTENT_CHUNK,
      text="test",
    )
    recorder(event)
    # File should be flushed immediately (no need to close)
    content = log_path.read_text()
    assert "test" in content
    recorder.close()

  def test_recorder_close_cleanup(self, tmp_path: Path) -> None:
    """Test that close() properly closes the file."""
    log_path = tmp_path / "events.jsonl"
    recorder = EventRecorder(log_path)

    recorder.close()

    # Should be able to delete the file after close
    log_path.unlink()

  def test_recorder_jsonl_format(self, tmp_path: Path) -> None:
    """Test that each event is on a separate line (JSONL format)."""
    log_path = tmp_path / "events.jsonl"
    recorder = EventRecorder(log_path)

    for i in range(5):
      recorder(ContentChunkEvent(
        type=EventType.CONTENT_CHUNK,
        text=f"chunk {i}",
      ))
    recorder.close()

    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 5

    # Each line should be valid JSON
    for line in lines:
      entry = json.loads(line)
      assert "type" in entry
      assert "timestamp" in entry


class TestEventReplayAgent:
  """Tests for EventReplayAgent class."""

  @pytest.fixture
  def events_file(self, tmp_path: Path) -> Path:
    """Create a test events.jsonl file."""
    events_path = tmp_path / "events.jsonl"

    events = [
      SessionStartEvent(
        type=EventType.SESSION_START,
        model="llama3.2",
        thinking_enabled=True,
      ),
      TurnStartEvent(
        type=EventType.TURN_START,
        message="Hello",
      ),
      ContentChunkEvent(
        type=EventType.CONTENT_CHUNK,
        text="Hi there!",
      ),
      ContentEndEvent(
        type=EventType.CONTENT_END,
        total_length=8,
      ),
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Hi there!",
      ),
      SessionEndEvent(
        type=EventType.SESSION_END,
        reason="quit",
      ),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    return events_path

  def test_agent_loads_events_from_file(self, events_file: Path) -> None:
    """Test that EventReplayAgent loads events from file."""
    agent = EventReplayAgent(events_file)

    assert len(agent.events) == 6

  def test_agent_extracts_model_from_session_start(self, events_file: Path) -> None:
    """Test that EventReplayAgent extracts model from SESSION_START."""
    agent = EventReplayAgent(events_file)

    assert agent.model == "llama3.2"

  def test_agent_extracts_thinking_enabled(self, events_file: Path) -> None:
    """Test that EventReplayAgent extracts thinking_enabled from SESSION_START."""
    agent = EventReplayAgent(events_file)

    assert agent.thinking_enabled is True

  def test_agent_add_event_handler(self, events_file: Path) -> None:
    """Test adding event handlers to the replay agent."""
    agent = EventReplayAgent(events_file)

    def handler(event: Any) -> None:
      pass

    agent.add_event_handler(handler)
    assert handler in agent._handlers

  def test_agent_begin_session_noop(self, events_file: Path) -> None:
    """Test that begin_session is a no-op."""
    agent = EventReplayAgent(events_file)

    # Should not raise
    agent.begin_session()

  def test_agent_end_session_noop(self, events_file: Path) -> None:
    """Test that end_session is a no-op."""
    agent = EventReplayAgent(events_file)

    # Should not raise
    agent.end_session(reason="test")

  def test_agent_process_replays_events_to_handlers(self, events_file: Path) -> None:
    """Test that process() replays events to handlers."""
    agent = EventReplayAgent(events_file)

    collected_events: list[Any] = []

    def handler(event: Any) -> None:
      collected_events.append(event)

    agent.add_event_handler(handler)

    agent.process("Hello")

    # Should have received all events between TURN_START and TURN_END
    assert len(collected_events) == 4
    assert isinstance(collected_events[0], TurnStartEvent)
    assert isinstance(collected_events[1], ContentChunkEvent)
    assert isinstance(collected_events[2], ContentEndEvent)
    assert isinstance(collected_events[3], TurnEndEvent)

  def test_agent_process_returns_response(self, events_file: Path) -> None:
    """Test that process() returns the response from TURN_END."""
    agent = EventReplayAgent(events_file)

    response = agent.process("Hello")

    assert response == "Hi there!"

  def test_agent_process_matches_message(self, events_file: Path) -> None:
    """Test that process() finds TURN_START with matching message."""
    agent = EventReplayAgent(events_file)

    # First call should find "Hello" message
    agent.process("Hello")

    # After processing, index should be at TURN_END
    # The next process would search for another matching turn

  def test_agent_process_multiple_turns(self, tmp_path: Path) -> None:
    """Test processing multiple turns from events file."""
    events_path = tmp_path / "events.jsonl"

    events = [
      SessionStartEvent(
        type=EventType.SESSION_START,
        model="llama3.2",
        thinking_enabled=True,
      ),
      TurnStartEvent(
        type=EventType.TURN_START,
        message="First message",
      ),
      ContentChunkEvent(
        type=EventType.CONTENT_CHUNK,
        text="First response",
      ),
      ContentEndEvent(
        type=EventType.CONTENT_END,
        total_length=14,
      ),
      TurnEndEvent(
        type=EventType.TURN_END,
        response="First response",
      ),
      TurnStartEvent(
        type=EventType.TURN_START,
        message="Second message",
      ),
      ContentChunkEvent(
        type=EventType.CONTENT_CHUNK,
        text="Second response",
      ),
      ContentEndEvent(
        type=EventType.CONTENT_END,
        total_length=15,
      ),
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Second response",
      ),
      SessionEndEvent(
        type=EventType.SESSION_END,
        reason="quit",
      ),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    agent = EventReplayAgent(events_path)

    response1 = agent.process("First message")
    assert response1 == "First response"

    response2 = agent.process("Second message")
    assert response2 == "Second response"

  def test_agent_replay_command(self, tmp_path: Path) -> None:
    """Test replaying a command event."""
    events_path = tmp_path / "events.jsonl"

    events = [
      SessionStartEvent(
        type=EventType.SESSION_START,
        model="llama3.2",
        thinking_enabled=True,
      ),
      CommandEvent(
        type=EventType.COMMAND,
        command="/help",
        result="Available commands:\n  /help - Show help\n  /think - Toggle thinking",
      ),
      TurnStartEvent(
        type=EventType.TURN_START,
        message="Hello",
      ),
      ContentChunkEvent(
        type=EventType.CONTENT_CHUNK,
        text="Hi there!",
      ),
      ContentEndEvent(
        type=EventType.CONTENT_END,
        total_length=8,
      ),
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Hi there!",
      ),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    agent = EventReplayAgent(events_path)

    collected_events: list[Any] = []

    def handler(event: Any) -> None:
      collected_events.append(event)

    agent.add_event_handler(handler)

    result = agent.replay_command("/help")

    assert result == "Available commands:\n  /help - Show help\n  /think - Toggle thinking"
    assert len(collected_events) == 1
    assert isinstance(collected_events[0], CommandEvent)
    assert collected_events[0].command == "/help"

  def test_agent_replay_command_not_found(self, tmp_path: Path) -> None:
    """Test replaying a command that doesn't exist in events."""
    events_path = tmp_path / "events.jsonl"

    events = [
      SessionStartEvent(
        type=EventType.SESSION_START,
        model="llama3.2",
        thinking_enabled=True,
      ),
      CommandEvent(
        type=EventType.COMMAND,
        command="/help",
        result="Help output",
      ),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    agent = EventReplayAgent(events_path)

    result = agent.replay_command("/unknown")

    assert result == ""

  def test_agent_replay_command_mixed_with_turns(self, tmp_path: Path) -> None:
    """Test replaying commands mixed with turns."""
    events_path = tmp_path / "events.jsonl"

    events = [
      SessionStartEvent(
        type=EventType.SESSION_START,
        model="llama3.2",
        thinking_enabled=True,
      ),
      CommandEvent(
        type=EventType.COMMAND,
        command="/help",
        result="Help output",
      ),
      TurnStartEvent(
        type=EventType.TURN_START,
        message="Hello",
      ),
      ContentChunkEvent(
        type=EventType.CONTENT_CHUNK,
        text="Hi!",
      ),
      ContentEndEvent(
        type=EventType.CONTENT_END,
        total_length=3,
      ),
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Hi!",
      ),
      CommandEvent(
        type=EventType.COMMAND,
        command="/think on",
        result="Thinking enabled",
      ),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    agent = EventReplayAgent(events_path)

    # Replay command first
    result1 = agent.replay_command("/help")
    assert result1 == "Help output"

    # Then process a turn
    result2 = agent.process("Hello")
    assert result2 == "Hi!"

    # Then replay another command
    result3 = agent.replay_command("/think on")
    assert result3 == "Thinking enabled"


class TestPredefinedInput:
  """Tests for PredefinedInput class."""

  def test_returns_messages_in_order(self) -> None:
    """Test that PredefinedInput returns messages in order."""
    messages = ["Hello", "How are you?", "Goodbye"]
    input_fn = PredefinedInput(messages)

    assert input_fn("Prompt") == "Hello"
    assert input_fn("Prompt") == "How are you?"
    assert input_fn("Prompt") == "Goodbye"

  def test_raises_eoferror_when_exhausted(self) -> None:
    """Test that PredefinedInput raises EOFError when messages exhausted."""
    messages = ["Only one"]
    input_fn = PredefinedInput(messages)

    input_fn("Prompt")  # Uses the only message

    with pytest.raises(EOFError):
      input_fn("Prompt")

  def test_empty_messages_raises_eoferror(self) -> None:
    """Test that empty message list raises EOFError immediately."""
    messages: list[str] = []
    input_fn = PredefinedInput(messages)

    with pytest.raises(EOFError):
      input_fn("Prompt")

  def test_ignores_prompt_parameter(self) -> None:
    """Test that prompt parameter is ignored."""
    input_fn = PredefinedInput(["message"])

    result = input_fn("Any prompt")
    assert result == "message"


class TestReplayInput:
  """Tests for ReplayInput class."""

  def test_extracts_messages_from_turn_start_events(self, tmp_path: Path) -> None:
    """Test that ReplayInput extracts messages from TURN_START events."""
    events_path = tmp_path / "events.jsonl"

    events = [
      TurnStartEvent(type=EventType.TURN_START, message="First"),
      TurnStartEvent(type=EventType.TURN_START, message="Second"),
      TurnStartEvent(type=EventType.TURN_START, message="Third"),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    input_fn = ReplayInput(events_path)

    assert input_fn.messages == ["First", "Second", "Third"]

  def test_returns_messages_in_order(self, tmp_path: Path) -> None:
    """Test that ReplayInput returns messages in order."""
    events_path = tmp_path / "events.jsonl"

    events = [
      TurnStartEvent(type=EventType.TURN_START, message="Hello"),
      TurnStartEvent(type=EventType.TURN_START, message="World"),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    input_fn = ReplayInput(events_path)

    assert input_fn("Prompt") == "Hello"
    assert input_fn("Prompt") == "World"

  def test_raises_eoferror_when_exhausted(self, tmp_path: Path) -> None:
    """Test that ReplayInput raises EOFError when messages exhausted."""
    events_path = tmp_path / "events.jsonl"

    events = [
      TurnStartEvent(type=EventType.TURN_START, message="Only one"),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    input_fn = ReplayInput(events_path)

    input_fn("Prompt")  # Uses the only message

    with pytest.raises(EOFError):
      input_fn("Prompt")

  def test_empty_file_results_in_empty_messages(self, tmp_path: Path) -> None:
    """Test that empty file results in empty messages list."""
    events_path = tmp_path / "events.jsonl"
    events_path.write_text("")

    input_fn = ReplayInput(events_path)

    assert input_fn.messages == []

    with pytest.raises(EOFError):
      input_fn("Prompt")

  def test_ignores_other_event_types(self, tmp_path: Path) -> None:
    """Test that non-TURN_START events are ignored."""
    events_path = tmp_path / "events.jsonl"

    events = [
      SessionStartEvent(
        type=EventType.SESSION_START,
        model="test",
        thinking_enabled=True,
      ),
      TurnStartEvent(type=EventType.TURN_START, message="Hello"),
      ContentChunkEvent(type=EventType.CONTENT_CHUNK, text="Response"),
      TurnStartEvent(type=EventType.TURN_START, message="World"),
      SessionEndEvent(type=EventType.SESSION_END, reason="quit"),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    input_fn = ReplayInput(events_path)

    assert input_fn.messages == ["Hello", "World"]

  def test_extracts_command_events(self, tmp_path: Path) -> None:
    """Test that ReplayInput extracts commands from COMMAND events."""
    events_path = tmp_path / "events.jsonl"

    events = [
      SessionStartEvent(
        type=EventType.SESSION_START,
        model="test",
        thinking_enabled=True,
      ),
      CommandEvent(type=EventType.COMMAND, command="/help", result="Help output"),
      TurnStartEvent(type=EventType.TURN_START, message="Hello"),
      CommandEvent(type=EventType.COMMAND, command="/think on", result="Thinking enabled"),
      TurnStartEvent(type=EventType.TURN_START, message="World"),
    ]

    with open(events_path, "w") as f:
      for event in events:
        f.write(json.dumps(serialize_event(event)) + "\n")

    input_fn = ReplayInput(events_path)

    assert input_fn.messages == ["/help", "Hello", "/think on", "World"]
