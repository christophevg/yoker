"""Tests for demo_session.py module."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from yoker.events import (
  EventRecorder,
  deserialize_event,
  serialize_event,
)
from yoker.events.types import (
  CommandEvent,
  ContentChunkEvent,
  ContentEndEvent,
  ContentStartEvent,
  EventType,
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
)


class TestSerializeEvent:
  """Tests for serialize_event function."""

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

  def test_serialize_turn_end_event_with_token_stats(self) -> None:
    """Test serializing TurnEndEvent with provider-neutral token stats."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = TurnEndEvent(
      type=EventType.TURN_END,
      timestamp=timestamp,
      response="Response",
      input_tokens=100,
      output_tokens=50,
    )
    result = serialize_event(event)

    assert result["type"] == "TURN_END"
    assert result["data"]["response"] == "Response"
    assert result["data"]["input_tokens"] == 100
    assert result["data"]["output_tokens"] == 50
    assert result["data"]["prompt_eval_count"] == 0
    assert result["data"]["eval_count"] == 0
    assert result["data"]["total_duration_ms"] == 0

  def test_serialize_turn_end_event_with_ollama_stats(self) -> None:
    """Test serializing TurnEndEvent with Ollama-native stats."""
    timestamp = datetime(2026, 4, 21, 10, 30, 0)
    event = TurnEndEvent(
      type=EventType.TURN_END,
      timestamp=timestamp,
      response="Response",
      prompt_eval_count=10,
      eval_count=20,
      total_duration_ms=500,
    )
    result = serialize_event(event)

    assert result["type"] == "TURN_END"
    assert result["data"]["response"] == "Response"
    assert result["data"]["prompt_eval_count"] == 10
    assert result["data"]["eval_count"] == 20
    assert result["data"]["total_duration_ms"] == 500
    assert result["data"]["input_tokens"] == 0
    assert result["data"]["output_tokens"] == 0

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

  def test_deserialize_turn_end_event_with_token_stats(self) -> None:
    """Test deserializing TurnEndEvent with provider-neutral token stats."""
    entry: dict[str, Any] = {
      "type": "TURN_END",
      "timestamp": "2026-04-21T10:30:00",
      "data": {
        "response": "Response",
        "input_tokens": 100,
        "output_tokens": 50,
      },
    }
    event = deserialize_event(entry)

    assert isinstance(event, TurnEndEvent)
    assert event.response == "Response"
    assert event.input_tokens == 100
    assert event.output_tokens == 50
    assert event.prompt_eval_count == 0
    assert event.eval_count == 0
    assert event.total_duration_ms == 0

  def test_deserialize_turn_end_event_with_ollama_stats(self) -> None:
    """Test deserializing TurnEndEvent with Ollama-native stats."""
    entry: dict[str, Any] = {
      "type": "TURN_END",
      "timestamp": "2026-04-21T10:30:00",
      "data": {
        "response": "Response",
        "prompt_eval_count": 10,
        "eval_count": 20,
        "total_duration_ms": 500,
      },
    }
    event = deserialize_event(entry)

    assert isinstance(event, TurnEndEvent)
    assert event.response == "Response"
    assert event.prompt_eval_count == 10
    assert event.eval_count == 20
    assert event.total_duration_ms == 500
    assert event.input_tokens == 0
    assert event.output_tokens == 0

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

    event = TurnStartEvent(
      type=EventType.TURN_START,
      message="Hello",
    )
    recorder(event)
    recorder.close()

    content = log_path.read_text()
    assert "TURN_START" in content
    assert "Hello" in content

  def test_recorder_writes_multiple_events(self, tmp_path: Path) -> None:
    """Test that EventRecorder writes multiple events."""
    log_path = tmp_path / "events.jsonl"
    recorder = EventRecorder(log_path)

    recorder(
      TurnStartEvent(
        type=EventType.TURN_START,
        message="Hello",
      )
    )
    recorder(
      TurnEndEvent(
        type=EventType.TURN_END,
        response="Hi there",
      )
    )
    recorder.close()

    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2

    entries = [json.loads(line) for line in lines]
    assert entries[0]["type"] == "TURN_START"
    assert entries[1]["type"] == "TURN_END"

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
      recorder(
        ContentChunkEvent(
          type=EventType.CONTENT_CHUNK,
          text=f"chunk {i}",
        )
      )
    recorder.close()

    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 5

    # Each line should be valid JSON
    for line in lines:
      entry = json.loads(line)
      assert "type" in entry
      assert "timestamp" in entry


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
